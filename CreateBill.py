from flask import request, jsonify
import pandas as pd
import requests
from billing import Rates, Trucks, Provider, db

def get_rate(product_id, scope):
    rate = Rates.query.filter_by(product_id=product_id, scope=scope).first()
    if not rate and scope != 'ALL':
        rate = Rates.query.filter_by(product_id=product_id, scope='ALL').first()
    return rate.rate if rate else None


def create_bill(id, params):
    
    weight_weight_url = f'http://weight-team-container-name:8080/weight/' 
    weight_session_url = f'http://weight-api:8080/session/'
    weight_item_url = f'http://weight-team-container-name:8080/item/'    
    
    try:
        response = requests.get(weight_weight_url, params=params)
    except:
        return jsonify({"error: transactions not found for provided time period"}), 404
    
    containers_data = []    
    for transaction in response:
        for container in transaction['containers']:
            container_record_dict = {
                'transaction_id': transaction['id'],
                'container_id': container,
                'produce': transaction['produce'],
                'bruto': transaction['bruto']                
                }
            containers_data.append(container_record_dict)

    for container in containers_data:
        container_id = container['container_id']         
        filtered_params = {
            'from': params['from'],
            'to': params['to']        
        }
        try:
            response = requests.get(weight_item_url+str(container_id), params=filtered_params)
        except:
            print("error - Container not found")
        container['container_tara'] = response['tara']

        sessions_data = []
        for session_id in response['sessions']:
            session_record_dict = {
                'session_id': session_id,
                'container_id': container_id}
            sessions_data.append(session_record_dict)
        
    for session in sessions_data:
        session_id = session['session_id']         
        try:
            response = requests.get(weight_session_url+str(session))
        except:
            print("error - Session not found")
        
        session['truck_id'] = response['truck']
        session['bruto'] = response['bruto']
        if response['neto']:
            session['neto'] = response['neto']
        else:
             session['neto'] = None

        if response['truckTara']:
            session['truck_tara'] = response['truckTara']
        else:
            try:
                response = requests.get(weight_item_url+str(response['truck']))
                session['truck_tara'] = response['truckTara']
            except:
                session['truck_tara'] = None
                print("error - Truck not found")
        
    containers_df = pd.DataFrame(containers_data)
    sessions_df = pd.DataFrame(sessions_data)

    # Merge dataframes based on the matching criteria
    merged_df = pd.merge(containers_df, sessions_df,
                        left_on=['container_id', 'bruto'],
                        right_on=['container_id', 'bruto'],
                        how='inner')
    
    trucks_data = db.session.query(Trucks.id, Trucks.provider_id).all()
    providers_data = db.session.query(Provider.id, Provider.name).all()

    # Create dictionaries to map IDs to corresponding values
    provider_id_to_name = {provider.id: provider.name for provider in providers_data}

    # Create a list of tuples with the required data
    data = []
    for truck_id, provider_id in trucks_data:
        provider_name = provider_id_to_name.get(provider_id, '')
        data.append((truck_id, provider_id, provider_name))

    # Create the pandas DataFrame
    trucks_df = pd.DataFrame(data, columns=['truck_id', 'provider_id', 'provider_name'])
    
    # Merge the trucks_df DataFrame with the merged_df DataFrame based on truck_id
    merged_df = pd.merge(merged_df, trucks_df, on='truck_id', how='left')

    for session_id in merged_df['session_id'].unique():
        session_mask = merged_df['session_id'] == session_id
        session_data = merged_df[session_mask]

        if session_data['neto'].isnull().all():
            truck_tara = session_data.iloc[0]['truckTara']
            containers_tara_sum = session_data['tara'].sum()

            merged_df.loc[session_mask, 'neto'] = session_data['bruto'] - (truck_tara + containers_tara_sum)


    provider_df = merged_df[merged_df['provider_id'] == id].copy()
    name = provider_df.iloc[0]['provider_name']
    truckCount = provider_df['truck_id'].value_count()
    sessionCount = provider_df['session_id'].value_count()
    
    products_list = provider_df['produce'].unique().values
    products_data = []
    for product in products_list:
        product_dict = {
            "product": product,
            "count": provider_df[provider_df['produce'] == product]['session_id'].value_count(),
            "amount": provider_df[provider_df['produce'] == product].groupby('session_id')['neto'].sum(),
            "rate": get_rate(product, id)        
        }
        product_dict['pay'] = product_dict['amount'] * product_dict['rate']
        products_data.append(product_dict)
    
    total = sum([product_record['pay'] for product_record in products_data])

    response_dict = {
        "id": id,
        "name": name,
        "from": params['from'],
        "to": params['to'],
        "truckCount": truckCount,
        "sessionCount": sessionCount,
        "products": products_data,
        "total": total
    }
    return jsonify(response), 200
FROM python:3.10.0-alpine

# RUN pip3 install --upgrage pip3

WORKDIR /billing-microservice

COPY requirements.txt .

RUN pip3 install -r requirements.txt

COPY ./billing-db.yaml ./billing-db.yaml
COPY ./billing.py .

ENTRYPOINT [ "python3", "billing.py" ]
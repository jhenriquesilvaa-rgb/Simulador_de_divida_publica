import requests

def get_cdi():
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados/ultimos/1?formato=json"
    r = requests.get(url)
    return float(r.json()[0]["valor"]) / 100

def get_ipca():
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/1?formato=json"
    r = requests.get(url)
    return float(r.json()[0]["valor"]) / 100

def get_cambio():
    url = "https://economia.awesomeapi.com.br/json/last/USD-BRL"
    r = requests.get(url)
    return float(r.json()["USDBRL"]["bid"])

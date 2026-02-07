import requests
import pandas as pd
from datetime import datetime

# ========= CDI =========
def pegar_cdi():
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados/ultimos/1?formato=json"
        return float(requests.get(url, timeout=5).json()[0]["valor"]) / 100
    except:
        return 0.13  # fallback

# ========= SELIC =========
def pegar_selic():
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1178/dados/ultimos/1?formato=json"
        return float(requests.get(url, timeout=5).json()[0]["valor"]) / 100
    except:
        return 0.12

# ========= IPCA =========
def pegar_ipca():
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/1?formato=json"
        return float(requests.get(url, timeout=5).json()[0]["valor"]) / 100
    except:
        return 0.04

# ========= SOFR (proxy) =========
def pegar_sofr():
    return 0.052  # pode integrar API depois

# ========= CÂMBIO =========
def pegar_cambio(moeda):
    taxas = {"USD": 5.0, "EUR": 5.4, "GBP": 6.3, "JPY": 0.034}
    return taxas.get(moeda, 1)

# ========= CURVA FUTURA =========
def curva_futura(base, anos=30):
    return [base * (1 + 0.02*i) for i in range(anos)]

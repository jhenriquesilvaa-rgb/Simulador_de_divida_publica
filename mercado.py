import requests
import json
import os
from datetime import datetime

CACHE_FILE = "cache_mercado.json"


# ===============================
# 🔹 Sistema de CACHE LOCAL
# ===============================
def salvar_cache(dados):
    with open(CACHE_FILE, "w") as f:
        json.dump(dados, f)


def carregar_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}


# ===============================
# 🔹 BACEN API com proteção
# ===============================
def pegar_serie_bacen(codigo, fallback):
    cache = carregar_cache()

    try:
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/1?formato=json"
        r = requests.get(url, timeout=5)
        r.raise_for_status()

        valor = float(r.json()[0]["valor"].replace(",", ".")) / 100
        cache[str(codigo)] = valor
        salvar_cache(cache)

        return valor

    except Exception:
        # 🔥 Fallback automático
        if str(codigo) in cache:
            return cache[str(codigo)]
        return fallback


# ===============================
# 🔹 CÂMBIO BACEN
# ===============================
def pegar_cambio(moeda):

    cache = carregar_cache()

    codigos = {
        "USD": 1,
        "EUR": 21619,
        "GBP": 21623,
        "JPY": 21621
    }

    if moeda == "BRL":
        return 1

    codigo = codigos.get(moeda)

    try:
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/1?formato=json"
        r = requests.get(url, timeout=5)
        r.raise_for_status()

        valor = float(r.json()[0]["valor"].replace(",", "."))
        cache[f"FX_{moeda}"] = valor
        salvar_cache(cache)

        return valor

    except Exception:
        return cache.get(f"FX_{moeda}", 5.0)  # fallback genérico


# ===============================
# 🔹 TAXAS OFICIAIS
# ===============================
def pegar_cdi():
    return pegar_serie_bacen(12, 0.1065)


def pegar_ipca():
    return pegar_serie_bacen(433, 0.045)


def pegar_selic():
    return pegar_serie_bacen(1178, 0.105)


# ===============================
# 🔹 SOFR (FRED API)
# ===============================
def pegar_sofr():
    cache = carregar_cache()

    try:
        url = "https://api.stlouisfed.org/fred/series/observations?series_id=SOFR&api_key=fred&file_type=json"
        r = requests.get(url, timeout=5)
        r.raise_for_status()

        valor = float(r.json()["observations"][-1]["value"]) / 100
        cache["SOFR"] = valor
        salvar_cache(cache)

        return valor

    except Exception:
        return cache.get("SOFR", 0.052)

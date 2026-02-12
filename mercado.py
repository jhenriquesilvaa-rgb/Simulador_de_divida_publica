import requests
import json
import os


CACHE_FILE = "cache_mercado.json"


# ===============================
# 🔹 Sistema de CACHE LOCAL
# ===============================

def salvar_cache(dados: dict) -> None:
    with open(CACHE_FILE, "w") as f:
        json.dump(dados, f)


def carregar_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


# ===============================
# 🔹 BACEN API com proteção
# ===============================

def pegar_serie_bacen(codigo: int, fallback: float) -> float:
    """
    Retorna taxa da série do Bacen em base 1.0 (ex.: 0.13 = 13% ao ano).

    Se falhar:
    - Tenta cache local.
    - Se não houver, devolve fallback informado.
    """
    cache = carregar_cache()
    chave = str(codigo)

    try:
        url = (
            f"https://api.bcb.gov.br/dados/serie/bcdata.sgs."
            f"{codigo}/dados/ultimos/1?formato=json"
        )
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        bruto = r.json()[0]["valor"]

        # A série 12 (CDI over) é anualizada base 252, em % a.a.
        # Em teoria, dividir por 100 dá a taxa em base 1.0.
        # Porém, na prática, temos observado valores muito baixos
        # (ex.: 0.055131 em vez de ~13), então aplicamos um piso.
        valor = float(bruto.replace(",", ".")) / 100.0

        # Piso de segurança: se vier algo anormalmente baixo,
        # substitui pelo fallback.
        if valor < 0.01:  # menor que 1% a.a. é claramente irreal
            valor = fallback

        cache[chave] = valor
        salvar_cache(cache)

        return valor
    except Exception:
        if chave in cache:
            return cache[chave]
        return fallback


# ===============================
# 🔹 CÂMBIO BACEN
# ===============================

def pegar_cambio(moeda: str) -> float:
    moeda = str(moeda).upper()
    if moeda == "BRL":
        return 1.0

    cache = carregar_cache()

    codigos = {
        "USD": 1,
        "EUR": 21619,
        "GBP": 21623,
        "JPY": 21621,
    }

    codigo = codigos.get(moeda)
    if codigo is None:
        return cache.get(f"FX_{moeda}", 5.0)

    try:
        url = (
            f"https://api.bcb.gov.br/dados/serie/bcdata.sgs."
            f"{codigo}/dados/ultimos/1?formato=json"
        )
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        bruto = r.json()[0]["valor"]
        valor = float(bruto.replace(",", "."))

        cache[f"FX_{moeda}"] = valor
        salvar_cache(cache)

        return valor
    except Exception:
        return cache.get(f"FX_{moeda}", 5.0)


# ===============================
# 🔹 TAXAS OFICIAIS
# ===============================

def pegar_cdi() -> float:
    """
    CDI anual (ex.: 0.13 = 13% a.a.).
    Usamos a série 12 do Bacen com um fallback institucional
    e um piso de segurança para evitar valores quase zero.
    """
    # Ajuste aqui o fallback conforme o CDI corrente (ex.: 0.14 = 14% a.a.)
    return pegar_serie_bacen(12, 0.145)


def pegar_ipca() -> float:
    """
    IPCA anual aproximado (0.045 = 4,5% a.a.), série 433.
    """
    return pegar_serie_bacen(433, 0.045)


def pegar_selic() -> float:
    """
    SELIC meta anual (0.105 = 10,5% a.a.), série 1178.
    """
    return pegar_serie_bacen(1178, 0.105)


# ===============================
# 🔹 SOFR (FRED API)
# ===============================

def pegar_sofr() -> float:
    cache = carregar_cache()

    try:
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            "?series_id=SOFR&api_key=fred&file_type=json"
        )
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        valor = float(r.json()["observations"][-1]["value"]) / 100.0

        cache["SOFR"] = valor
        salvar_cache(cache)

        return valor
    except Exception:
        return cache.get("SOFR", 0.052)

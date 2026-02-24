import functools
import datetime as dt

import pandas as pd
import requests

# Arquivo oficial de feriados nacionais da ANBIMA
ANBIMA_FERIADOS_XLS = "https://www.anbima.com.br/feriados/arqs/feriados_nacionais.xls"


@functools.lru_cache(maxsize=None)
def get_feriados_anbima(ano: int):
    """
    Retorna lista de datas (datetime.date) de feriados nacionais ANBIMA
    para o ano informado.
    Em caso de erro de conexão ou de parsing, retorna lista vazia.
    """
    try:
        resp = requests.get(ANBIMA_FERIADOS_XLS, timeout=20)
        resp.raise_for_status()
    except Exception:
        # Falha de rede: não interrompe o modelo, apenas sem feriados ANBIMA
        return []

    xls_bytes = resp.content
    try:
        df = pd.read_excel(xls_bytes, header=0)
    except Exception:
        return []

    # Tenta achar a coluna de data
    if "Data" not in df.columns:
        col_data = [c for c in df.columns if "data" in str(c).lower()]
        if not col_data:
            return []
        df = df.rename(columns={col_data[0]: "Data"})

    # Remove linhas vazias ou claramente não relacionadas a datas (ex.: 'Fonte: ANBIMA')
    df = df[df["Data"].notna()]

    # Converte para datetime, descartando o que não for data
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce").dt.date
    df = df[df["Data"].notna()]

    feriados_ano = df[df["Data"].apply(lambda d: d.year == ano)]["Data"].tolist()
    return feriados_ano


def get_feriados_intervalo(inicio: dt.date, fim: dt.date):
    """
    Retorna lista de feriados ANBIMA no intervalo [inicio, fim].
    Junta os feriados de todos os anos cobertos pelo intervalo.
    Em caso de problema, devolve lista vazia e o modelo segue só com seg–sex.
    """
    anos = range(inicio.year, fim.year + 1)
    feriados = []
    for ano in anos:
        feriados += get_feriados_anbima(ano)

    feriados = [d for d in set(feriados) if inicio <= d <= fim]
    return sorted(feriados)

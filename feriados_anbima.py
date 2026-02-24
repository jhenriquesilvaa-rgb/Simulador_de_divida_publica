import functools
import datetime as dt

import pandas as pd
import requests

ANBIMA_FERIADOS_XLS = "https://www.anbima.com.br/feriados/arqs/feriados_nacionais.xls"


@functools.lru_cache(maxsize=None)
def get_feriados_anbima(ano: int):
    """
    Retorna lista de datas (datetime.date) de feriados nacionais ANBIMA
    para o ano informado.
    Em caso de erro de conexão, retorna lista vazia (não interrompe o modelo).
    """
    try:
        resp = requests.get(ANBIMA_FERIADOS_XLS, timeout=20)
        resp.raise_for_status()
    except Exception:
        # Falha de rede: sem feriados ANBIMA, deixamos a contagem só com sábados/domingos
        return []

    xls_bytes = resp.content
    df = pd.read_excel(xls_bytes)

    if "Data" not in df.columns:
        col_data = [c for c in df.columns if "data" in str(c).lower()]
        if not col_data:
            return []

        df = df.rename(columns={col_data[0]: "Data"})

    df["Data"] = pd.to_datetime(df["Data"]).dt.date
    feriados_ano = df[df["Data"].apply(lambda d: d.year == ano)]["Data"].tolist()
    return feriados_ano


def get_feriados_intervalo(inicio: dt.date, fim: dt.date):
    """
    Retorna lista de feriados ANBIMA no intervalo [inicio, fim].
    Em caso de falha na leitura, devolve lista vazia.
    """
    anos = range(inicio.year, fim.year + 1)
    feriados = []
    for ano in anos:
        feriados += get_feriados_anbima(ano)

    feriados = [d for d in set(feriados) if inicio <= d <= fim]
    return sorted(feriados)

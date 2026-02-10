import pandas as pd
import numpy as np
import numpy_financial as npf
from mercado import pegar_cdi, pegar_ipca, pegar_cambio

# =========================
# 🔹 CONVERSÕES DE TAXA
# =========================
def anual_para_diaria(taxa_anual):
    return (1 + taxa_anual) ** (1/365) - 1

def periodo_para_anual(taxa_periodo, periodicidade):
    return (1 + taxa_periodo) ** (12 / periodicidade) - 1


# =========================
# 🔹 INDEXADORES
# =========================
def taxa_indexador(row):
    indexador = str(row["Indexador"]).upper()

    if indexador == "CDI":
        return pegar_cdi()
    elif indexador == "IPCA":
        return pegar_ipca()
    elif indexador == "SELIC":
        return pegar_cdi()
    elif indexador == "SOFR":
        return 0.052  # proxy institucional
    else:
        return 0.0


# =========================
# 🔹 GERADOR DE DATAS FINANCEIRAS REAIS
# =========================
def gerar_datas_pagamento(data_inicio, prazo, periodicidade):

    datas = []
    data_base = pd.to_datetime(data_inicio)

    if periodicidade == 6:
        meses_pagamento = [5, 11]  # Maio e Novembro
    elif periodicidade == 3:
        meses_pagamento = [3, 6, 9, 12]
    elif periodicidade == 12:
        meses_pagamento = [data_base.month]
    else:
        meses_pagamento = list(range(1, 13))

    ano = data_base.year

    while len(datas) < prazo:
        for mes in meses_pagamento:
            data_pag = pd.Timestamp(year=ano, month=mes, day=15)

            if data_pag > data_base:
                datas.append(data_pag)

            if len(datas) == prazo:
                break

        ano += 1

    return datas


# =========================
# 🔹 TIR e VPL
# =========================
def calcular_tir(fluxo_fin, periodicidade):
    try:
        tir_periodo = npf.irr(fluxo_fin)
        if tir_periodo is None or np.isnan(tir_periodo):
            return 0
        tir_anual = periodo_para_anual(tir_periodo, periodicidade)
        return tir_anual * 100
    except:
        return 0


def calcular_vpl(fluxo_fin, taxa_desconto_anual):
    taxa_periodo = (1 + taxa_desconto_anual) ** (1/12) - 1
    return npf.npv(taxa_periodo, fluxo_fin)


# =========================
# 🔹 SIMULAÇÃO DO CONTRATO
# =========================
def simular_contrato(row):

    valor = float(row["Valor_Contratado"])
    prazo = int(row["Prazo"])
    carencia = int(row["Carencia"])
    periodicidade = int(row["Periodicidade"])
    sistema = str(row["Sistema_Amortização"]).upper()
    moeda = str(row["Moeda"]).upper()

    spread = float(row["Spread"] or 0)
    fator = float(row["Fator_indexador"] or 1)

    taxa_base = taxa_indexador(row)
    taxa_anual = taxa_base * fator + spread
    taxa_dia = anual_para_diaria(taxa_anual)

    cambio = pegar_cambio(moeda) if moeda != "BRL" else 1

    datas_pagamento = gerar_datas_pagamento(
        row["Data_contratação"],
        prazo,
        periodicidade
    )

    saldo = valor
    pagamentos = []

    if sistema == "SAC":
        amortizacao_constante = valor / (prazo - carencia)

    data_anterior = pd.to_datetime(row["Data_contratação"])

    for i, data_pag in enumerate(datas_pagamento):

        dias = (data_pag - data_anterior).days
        juros = saldo * ((1 + taxa_dia) ** dias - 1)

        if i < carencia:
            amort = 0
            pagamento = juros
        else:
            if sistema == "SAC":
                amort = amortizacao_constante
                pagamento = amort + juros
            else:
                amort = 0
                pagamento = juros

            saldo -= amort

        pagamentos.append({
            "ID": row["Id"],
            "Data": data_pag,
            "Ano": data_pag.year,
            "Pagamento": pagamento * cambio,
            "Amortização": amort * cambio,
            "Juros": juros * cambio,
            "Saldo_Devedor": max(saldo * cambio, 0)
        })

        data_anterior = data_pag

    df = pd.DataFrame(pagamentos)

    fluxo_fin = [-valor * cambio] + df["Pagamento"].tolist()

    tir = calcular_tir(fluxo_fin, periodicidade)
    vpl = calcular_vpl(fluxo_fin, taxa_base)

    return df, tir, vpl

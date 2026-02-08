import pandas as pd
import numpy as np
import numpy_financial as npf
from mercado import pegar_cdi, pegar_ipca, pegar_cambio

# =========================
# 🔹 Conversões de taxa
# =========================
def anual_para_periodo(taxa_anual, periodicidade):
    return (1 + taxa_anual) ** (periodicidade / 12) - 1

def periodo_para_anual(taxa_periodo, periodicidade):
    return (1 + taxa_periodo) ** (12 / periodicidade) - 1


# =========================
# 🔹 Motor de Indexadores
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
    elif indexador == "VARIAÇÃO CAMBIAL":
        return 0
    else:
        return 0.0


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
# 🔹 Simulação do contrato
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
    taxa_periodo = anual_para_periodo(taxa_anual, periodicidade)

    # 🔹 Câmbio
    cambio = pegar_cambio(moeda) if moeda != "BRL" else 1

    saldo = valor
    pagamentos = []

    datas = pd.date_range(
        start=pd.to_datetime(row["Data_contratação"]),
        periods=prazo,
        freq="ME"
    )

    # 🔹 PRICE PMT
    if sistema == "PRICE":
        pmt = npf.pmt(taxa_periodo, prazo - carencia, -valor)

    for i in range(prazo):

        juros = saldo * taxa_periodo

        # =============================
        # 🔥 CORREÇÃO PRINCIPAL AQUI
        # Carência = paga juros, NÃO capitaliza
        # =============================
        if i < carencia:
            amort = 0
            pagamento = juros
        else:
            if sistema == "SAC":
                amort = valor / (prazo - carencia)
                pagamento = amort + juros
            elif sistema == "PRICE":
                amort = pmt - juros
                pagamento = pmt
            else:
                amort = 0
                pagamento = juros

            saldo -= amort

        pagamento_brl = pagamento * cambio

        pagamentos.append({
            "ID": row["Id"],
            "Data": datas[i],
            "Ano": datas[i].year,
            "Pagamento": pagamento_brl,
            "Amortização": amort * cambio,
            "Juros": juros * cambio,
            "Saldo_Devedor": max(saldo * cambio, 0)
        })

    df = pd.DataFrame(pagamentos)

    fluxo_fin = [-valor * cambio] + df["Pagamento"].tolist()

    tir = calcular_tir(fluxo_fin, periodicidade)
    vpl = calcular_vpl(fluxo_fin, taxa_base)

    return df, tir, vpl

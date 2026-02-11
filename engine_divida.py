import pandas as pd
import numpy as np
import numpy_financial as npf

from mercado import pegar_cdi, pegar_ipca, pegar_cambio, pegar_selic, pegar_sofr
from cenarios import CenarioMercado


# =========================
# 🔹 Conversões de taxa
# =========================

def anual_para_periodo(taxa_anual: float, periodicidade_meses: int) -> float:
    """
    Converte taxa efetiva anual em taxa efetiva por período
    de 'periodicidade_meses' meses.
    """
    return (1 + taxa_anual) ** (periodicidade_meses / 12) - 1


def periodo_para_anual(taxa_periodo: float, periodicidade_meses: int) -> float:
    """
    Converte taxa efetiva por período de 'periodicidade_meses' meses
    em taxa efetiva anual.
    """
    return (1 + taxa_periodo) ** (12 / periodicidade_meses) - 1


# =========================
# 🔹 Motor de Indexadores
# =========================

def taxa_indexador(row, cenario: CenarioMercado) -> float:
    """
    Retorna taxa efetiva anual do indexador de referência,
    já incluindo choques de cenário (em bps).
    """
    indexador = str(row["Indexador"]).upper()

    if indexador == "CDI":
        base = pegar_cdi()
        base += cenario.choque_cdi_bps / 10000.0
    elif indexador == "IPCA":
        base = pegar_ipca()
        base += cenario.choque_ipca_bps / 10000.0
    elif indexador == "SELIC":
        base = pegar_selic()
        base += cenario.choque_cdi_bps / 10000.0
    elif indexador == "SOFR":
        base = pegar_sofr()
    elif indexador == "VARIAÇÃO CAMBIAL":
        base = 0.0
    else:
        base = 0.0

    return base


# =========================
# 🔹 TIR e VPL
# =========================

def calcular_tir(fluxo_fin, periodicidade_meses: int) -> float:
    """
    Calcula TIR anual (%) a partir de um fluxo com periodicidade fixa
    em 'periodicidade_meses' meses.
    """
    try:
        fluxo_fin = list(fluxo_fin)
        if len(fluxo_fin) < 2:
            return 0.0

        if fluxo_fin[0] >= 0 or all(f <= 0 for f in fluxo_fin[1:]):
            return 0.0

        tir_periodo = npf.irr(fluxo_fin)

        if tir_periodo is None or np.isnan(tir_periodo):
            return 0.0

        tir_anual = periodo_para_anual(tir_periodo, periodicidade_meses)
        return float(tir_anual * 100)
    except Exception:
        return 0.0


def calcular_vpl(fluxo_fin, taxa_desconto_anual: float, periodicidade_meses: int) -> float:
    """
    Calcula VPL com taxa de desconto anual,
    convertida para taxa por período de 'periodicidade_meses' meses.
    """
    taxa_periodo = (1 + taxa_desconto_anual) ** (periodicidade_meses / 12) - 1
    return float(npf.npv(taxa_periodo, fluxo_fin))


# =========================
# 🔹 Simulação do contrato
# =========================

def simular_contrato(row, cenario: CenarioMercado):
    """
    Simula o fluxo de um contrato de dívida.

    Convenções:
    - Se Periodicidade = 1 → períodos mensais (como antes).
    - Se Periodicidade = 6 → períodos semestrais (pagamentos a cada 6 meses),
      com Prazo e Carencia interpretados como número de semestres.
    """

    valor = float(row["Valor_Contratado"])
    prazo = int(row["Prazo"])
    carencia = int(row["Carencia"])
    periodicidade = int(row["Periodicidade"])
    sistema = str(row["Sistema_Amortização"]).upper()
    moeda = str(row["Moeda"]).upper()

    # Desvio: modo semestral
    if periodicidade == 6:
        return simular_contrato_semestral(row, cenario)

    # Modo padrão (mensal) – já validado
    spread = float(row["Spread"] or 0.0)
    fator = float(row["Fator_indexador"] or 1.0)

    taxa_base = taxa_indexador(row, cenario)
    taxa_anual = taxa_base * fator + spread + (cenario.choque_spread_bps / 10000.0)
    taxa_periodo = anual_para_periodo(taxa_anual, periodicidade)

    cambio = pegar_cambio(moeda) if moeda != "BRL" else 1.0
    if cenario.choque_cambio_pct != 0.0 and moeda != "BRL":
        cambio *= (1 + cenario.choque_cambio_pct)

    saldo = valor
    pagamentos = []

    datas = pd.date_range(
        start=pd.to_datetime(row["Data_contratação"]),
        periods=prazo,
        freq="MS",  # mensal
    )

    pmt = None
    if sistema == "PRICE" and prazo > carencia:
        pmt = float(npf.pmt(taxa_periodo, prazo - carencia, -valor))
    elif sistema == "PRICE" and prazo <= carencia:
        pmt = None

    for i in range(prazo):
        juros = saldo * taxa_periodo

        if i < carencia:
            amort = 0.0
            pagamento = juros
        else:
            if sistema == "SAC":
                n_amort = max(prazo - carencia, 1)
                amort = valor / n_amort
                pagamento = amort + juros
            elif sistema == "PRICE" and pmt is not None:
                amort = pmt - juros
                pagamento = pmt
            else:
                amort = 0.0
                pagamento = juros

        saldo -= amort
        saldo = max(saldo, 0.0)

        pagamento_brl = pagamento * cambio

        pagamentos.append(
            {
                "ID": row["Id"],
                "Data": datas[i],
                "Ano": datas[i].year,
                "Pagamento": pagamento_brl,
                "Amortização": amort * cambio,
                "Juros": juros * cambio,
                "Saldo_Devedor": saldo * cambio,
                "Taxa_Periodo": taxa_periodo * 100,
                "Taxa_Anual": taxa_anual * 100,
                "Indexador": row["Indexador"],
                "Spread": spread * 100,
            }
        )

    df = pd.DataFrame(pagamentos)

    fluxo_fin = [-valor * cambio] + df["Pagamento"].tolist()
    tir = calcular_tir(fluxo_fin, periodicidade)
    vpl = calcular_vpl(fluxo_fin, taxa_base, periodicidade)

    return df, tir, vpl


# =========================
# 🔹 Simulação semestral (Periodicidade = 6)
# =========================

def simular_contrato_semestral(row, cenario: CenarioMercado):
    """
    Simula contrato com pagamentos semestrais.

    Convenções:
    - Periodicidade = 6  → período de 6 meses.
    - Prazo e Carencia são interpretados como número de períodos (semestrais).
      Ex.: Prazo = 40 → 40 semestres ~ 20 anos.
    - Carencia = número de semestres em que se paga só juros.
    - Sistema SAC: amortização constante semestral após a carência.
    - Sistema PRICE: prestação fixa semestral após a carência.
    """

    valor = float(row["Valor_Contratado"])
    prazo = int(row["Prazo"])              # em semestres
    carencia = int(row["Carencia"])        # em semestres
    periodicidade = int(row["Periodicidade"])  # deve ser 6 aqui
    sistema = str(row["Sistema_Amortização"]).upper()
    moeda = str(row["Moeda"]).upper()

    spread = float(row["Spread"] or 0.0)
    fator = float(row["Fator_indexador"] or 1.0)

    taxa_base = taxa_indexador(row, cenario)
    taxa_anual = taxa_base * fator + spread + (cenario.choque_spread_bps / 10000.0)

    # taxa efetiva por semestre (6 meses)
    taxa_periodo = anual_para_periodo(taxa_anual, periodicidade)

    cambio = pegar_cambio(moeda) if moeda != "BRL" else 1.0
    if cenario.choque_cambio_pct != 0.0 and moeda != "BRL":
        cambio *= (1 + cenario.choque_cambio_pct)

    saldo = valor
    pagamentos = []

    # Geração de datas semestrais:
    # simplificação: a partir da Data_contratação, a cada 6 meses.
    # (não fixamos ainda em 15/05 e 15/11; isso é o próximo refinamento)
    datas = pd.date_range(
        start=pd.to_datetime(row["Data_contratação"]),
        periods=prazo,
        freq="6MS",  # início de mês, a cada 6 meses
    )

    # Se você quiser aproximar mais 15/05 e 15/11, pode ajustar as datas depois.

    pmt = None
    n_amort = max(prazo - carencia, 1)

    if sistema == "PRICE" and prazo > carencia:
        pmt = float(npf.pmt(taxa_periodo, prazo - carencia, -valor))
    elif sistema == "PRICE" and prazo <= carencia:
        pmt = None

    for i in range(prazo):
        juros = saldo * taxa_periodo

        if i < carencia:
            # carência semestral: só juros
            amort = 0.0
            pagamento = juros
        else:
            if sistema == "SAC":
                amort = valor / n_amort
                pagamento = amort + juros
            elif sistema == "PRICE" and pmt is not None:
                amort = pmt - juros
                pagamento = pmt
            else:
                amort = 0.0
                pagamento = juros

        saldo -= amort
        saldo = max(saldo, 0.0)

        pagamento_brl = pagamento * cambio

        pagamentos.append(
            {
                "ID": row["Id"],
                "Data": datas[i],
                "Ano": datas[i].year,
                "Pagamento": pagamento_brl,
                "Amortização": amort * cambio,
                "Juros": juros * cambio,
                "Saldo_Devedor": saldo * cambio,
                "Taxa_Periodo": taxa_periodo * 100,
                "Taxa_Anual": taxa_anual * 100,
                "Indexador": row["Indexador"],
                "Spread": spread * 100,
            }
        )

    df = pd.DataFrame(pagamentos)

    fluxo_fin = [-valor * cambio] + df["Pagamento"].tolist()
    # periodicidade_meses = 6 para semestral
    tir = calcular_tir(fluxo_fin, periodicidade)
    vpl = calcular_vpl(fluxo_fin, taxa_base, periodicidade)

    return df, tir, vpl

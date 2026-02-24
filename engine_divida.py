import pandas as pd
import numpy as np
import numpy_financial as npf

from mercado import pegar_cdi, pegar_ipca, pegar_cambio, pegar_selic, pegar_sofr
from cenarios import CenarioMercado
from feriados_anbima import get_feriados_intervalo


# =========================
# 🔹 Conversões de taxa
# =========================

def anual_para_periodo(taxa_anual: float, periodicidade_meses: int) -> float:
    """
    (Mantida para compatibilidade)
    Converte taxa efetiva anual em taxa efetiva por período
    de 'periodicidade_meses' meses.
    """
    return (1 + taxa_anual) ** (periodicidade_meses / 12) - 1


def periodo_para_anual(taxa_periodo: float, periodicidade_meses: int) -> float:
    """
    (Mantida para compatibilidade)
    Converte taxa efetiva por período de 'periodicidade_meses' meses
    em taxa efetiva anual.
    """
    return (1 + taxa_periodo) ** (12 / periodicidade_meses) - 1


def taxa_ao_dia_util(taxa_anual: float, dias_uteis_ano: int = 252) -> float:
    """
    Converte taxa efetiva anual em taxa efetiva por dia útil.
    Ex.: CDI a.a. -> CDI diário base 252.
    """
    return (1 + taxa_anual) ** (1 / dias_uteis_ano) - 1


def fator_periodo_dias_uteis(taxa_dia_util: float, data_inicio, data_fim, feriados=None) -> float:
    """
    Calcula a taxa efetiva do período com base no número de dias úteis
    entre data_inicio (inclusive) e data_fim (exclusive).
    Exclui sábados, domingos e feriados ANBIMA.
    """
    if feriados is None:
        feriados = []

    dias = pd.date_range(start=data_inicio, end=data_fim, freq="D")[:-1]
    dias_uteis = dias[dias.weekday < 5]

    if feriados:
        feriados_set = set(feriados)
        dias_uteis = [d for d in dias_uteis if d.date() not in feriados_set]

    n = len(dias_uteis)
    if n <= 0:
        return 0.0
    return (1 + taxa_dia_util) ** n - 1


def periodo_para_anual_dias_uteis(taxa_periodo: float, dias_uteis_periodo: int, dias_uteis_ano: int = 252) -> float:
    """
    Converte taxa efetiva de um período (n dias úteis) em taxa anual
    base 252 dias úteis.
    """
    if taxa_periodo <= -1 or dias_uteis_periodo <= 0:
        return 0.0
    return (1 + taxa_periodo) ** (dias_uteis_ano / dias_uteis_periodo) - 1


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

def calcular_tir(fluxo_fin, periodicidade_meses: int, dias_uteis_entre_pagamentos: int | None = None) -> float:
    """
    Calcula TIR anual (%) a partir de um fluxo.

    - Se 'dias_uteis_entre_pagamentos' for informado, converte a TIR por período
      em TIR anual usando base de 252 dias úteis.
    - Caso contrário, usa a conversão por meses (função antiga).
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

        if dias_uteis_entre_pagamentos is not None and dias_uteis_entre_pagamentos > 0:
            tir_anual = periodo_para_anual_dias_uteis(tir_periodo, dias_uteis_entre_pagamentos, 252)
        else:
            tir_anual = periodo_para_anual(tir_periodo, periodicidade_meses)

        return float(tir_anual * 100)
    except Exception:
        return 0.0


def calcular_vpl(fluxo_fin, taxa_desconto_anual: float, periodicidade_meses: int) -> float:
    """
    Calcula VPL com taxa de desconto anual,
    convertida para taxa por período de 'periodicidade_meses' meses.
    (Mantida a mesma lógica de antes – taxa de desconto em meses.)
    """
    taxa_periodo = (1 + taxa_desconto_anual) ** (periodicidade_meses / 12) - 1
    return float(npf.npv(taxa_periodo, fluxo_fin))


# =========================
# 🔹 Simulação do contrato – Modo mensal (Periodicidade != 6)
# =========================

def simular_contrato(row, cenario: CenarioMercado):
    """
    Simula o fluxo de um contrato de dívida.

    Convenções:
    - Se Periodicidade = 1 → períodos mensais (dia útil ANBIMA entre pagamentos).
    - Se Periodicidade = 6 → encaminha para simulação semestral.
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

    # Modo padrão (mensal)
    spread = float(row["Spread"] or 0.0)
    fator = float(row["Fator_indexador"] or 1.0)

    taxa_base = taxa_indexador(row, cenario)
    taxa_anual = taxa_base * fator + spread + (cenario.choque_spread_bps / 10000.0)

    # Taxa diária em dias úteis
    taxa_dia_util = taxa_ao_dia_util(taxa_anual, dias_uteis_ano=252)

    cambio = pegar_cambio(moeda) if moeda != "BRL" else 1.0
    if cenario.choque_cambio_pct != 0.0 and moeda != "BRL":
        cambio *= (1 + cenario.choque_cambio_pct)

    saldo = valor
    pagamentos = []

    # Datas de pagamento mensais (início de mês)
    datas = pd.date_range(
        start=pd.to_datetime(row["Data_contratação"]),
        periods=prazo,
        freq="MS",  # mensal
    )

    # Feriados ANBIMA no intervalo do contrato
    data_inicio = datas[0].date()
    data_fim = datas[-1].date()
    feriados = get_feriados_intervalo(data_inicio, data_fim)
    feriados_set = set(feriados)

    # Estimar número médio de dias úteis entre pagamentos (para TIR anual)
    datas_exemplo = pd.date_range(start=datas[0], periods=2, freq="MS")
    dias_exemplo = pd.date_range(
        start=datas_exemplo[0],
        end=datas_exemplo[1],
        freq="D",
    )[:-1]
    dias_uteis_exemplo = [
        d for d in dias_exemplo
        if d.weekday() < 5 and d.date() not in feriados_set
    ]
    dias_uteis_entre_pagamentos = len(dias_uteis_exemplo)

    # PRICE: calcular prestação aproximada usando taxa por período derivada dos dias úteis médios
    pmt = None
    if sistema == "PRICE" and prazo > carencia:
        taxa_periodo_aprox = (1 + taxa_dia_util) ** dias_uteis_entre_pagamentos - 1
        pmt = float(npf.pmt(taxa_periodo_aprox, prazo - carencia, -valor))
    elif sistema == "PRICE" and prazo <= carencia:
        pmt = None

    data_anterior = datas[0]

    for i in range(prazo):
        data_atual = datas[i]

        # Taxa efetiva do período com base em dias úteis ANBIMA
        taxa_periodo_efetiva = fator_periodo_dias_uteis(
            taxa_dia_util,
            data_anterior,
            data_atual,
            feriados=feriados,
        )

        juros = saldo * taxa_periodo_efetiva

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
                "Data": data_atual,
                "Ano": data_atual.year,
                "Pagamento": pagamento_brl,
                "Amortização": amort * cambio,
                "Juros": juros * cambio,
                "Saldo_Devedor": saldo * cambio,
                "Taxa_Dia_Util": taxa_dia_util * 100,
                "Taxa_Anual": taxa_anual * 100,
                "Indexador": row["Indexador"],
                "Spread": spread * 100,
            }
        )

        data_anterior = data_atual

    df = pd.DataFrame(pagamentos)

    fluxo_fin = [-valor * cambio] + df["Pagamento"].tolist()

    tir = calcular_tir(
        fluxo_fin,
        periodicidade_meses=periodicidade,
        dias_uteis_entre_pagamentos=dias_uteis_entre_pagamentos,
    )

    # VPL sempre descontado a CDI (taxa anual), mantida lógica por período em meses
    taxa_cdi_desconto = pegar_cdi()
    vpl = calcular_vpl(fluxo_fin, taxa_cdi_desconto, periodicidade)

    return df, tir, vpl


# =========================
# 🔹 Simulação semestral (Periodicidade = 6)
# =========================

def simular_contrato_semestral(row, cenario: CenarioMercado):
    """
    Simula contrato com pagamentos semestrais.

    Convenções:
    - Periodicidade = 6 → período de 6 meses.
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

    # Taxa diária em dias úteis
    taxa_dia_util = taxa_ao_dia_util(taxa_anual, dias_uteis_ano=252)

    cambio = pegar_cambio(moeda) if moeda != "BRL" else 1.0
    if cenario.choque_cambio_pct != 0.0 and moeda != "BRL":
        cambio *= (1 + cenario.choque_cambio_pct)

    saldo = valor
    pagamentos = []

    # Datas semestrais: a cada 6 meses
    datas = pd.date_range(
        start=pd.to_datetime(row["Data_contratação"]),
        periods=prazo,
        freq="6MS",  # início de mês, a cada 6 meses
    )

    # Feriados ANBIMA no intervalo
    data_inicio = datas[0].date()
    data_fim = datas[-1].date()
    feriados = get_feriados_intervalo(data_inicio, data_fim)
    feriados_set = set(feriados)

    # Número médio de dias úteis entre dois pagamentos semestrais
    datas_exemplo = pd.date_range(start=datas[0], periods=2, freq="6MS")
    dias_exemplo = pd.date_range(
        start=datas_exemplo[0],
        end=datas_exemplo[1],
        freq="D",
    )[:-1]
    dias_uteis_exemplo = [
        d for d in dias_exemplo
        if d.weekday() < 5 and d.date() not in feriados_set
    ]
    dias_uteis_entre_pagamentos = len(dias_uteis_exemplo)

    pmt = None
    n_amort = max(prazo - carencia, 1)

    if sistema == "PRICE" and prazo > carencia:
        taxa_periodo_aprox = (1 + taxa_dia_util) ** dias_uteis_entre_pagamentos - 1
        pmt = float(npf.pmt(taxa_periodo_aprox, prazo - carencia, -valor))
    elif sistema == "PRICE" and prazo <= carencia:
        pmt = None

    data_anterior = datas[0]

    for i in range(prazo):
        data_atual = datas[i]

        taxa_periodo_efetiva = fator_periodo_dias_uteis(
            taxa_dia_util,
            data_anterior,
            data_atual,
            feriados=feriados,
        )

        juros = saldo * taxa_periodo_efetiva

        if i < carencia:
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
                "Data": data_atual,
                "Ano": data_atual.year,
                "Pagamento": pagamento_brl,
                "Amortização": amort * cambio,
                "Juros": juros * cambio,
                "Saldo_Devedor": saldo * cambio,
                "Taxa_Dia_Util": taxa_dia_util * 100,
                "Taxa_Anual": taxa_anual * 100,
                "Indexador": row["Indexador"],
                "Spread": spread * 100,
            }
        )

        data_anterior = data_atual

    df = pd.DataFrame(pagamentos)

    fluxo_fin = [-valor * cambio] + df["Pagamento"].tolist()

    tir = calcular_tir(
        fluxo_fin,
        periodicidade_meses=periodicidade,
        dias_uteis_entre_pagamentos=dias_uteis_entre_pagamentos,
    )

    taxa_cdi_desconto = pegar_cdi()
    vpl = calcular_vpl(fluxo_fin, taxa_cdi_desconto, periodicidade)

    return df, tir, vpl

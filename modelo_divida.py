import pandas as pd
import numpy_financial as npf
from engine_divida import simular_contrato

def rodar_modelo(df=None):

    # 🔹 Permite rodar com planilha do app ou arquivo fixo
    if df is None:
        df = pd.read_excel("Contratos.xlsx")

    resultados = []
    fluxos = []

    # =============================
    # 🔹 Simulação contrato a contrato
    # =============================
    for _, row in df.iterrows():
        fluxo_df, tir, vpl = simular_contrato(row)

        custo_total = fluxo_df["Pagamento"].sum()

        resultados.append({
            "ID": row["Id"],
            "Tipo": row["Tipo"],
            "Descrição": row["Descrição"],
            "Moeda": row["Moeda"],
            "Valor_Contratado": row["Valor_Contratado"],
            "Custo_Total": custo_total,
            "TIR": tir,
            "VPL": vpl
        })

        fluxos.append(fluxo_df)

    resumo = pd.DataFrame(resultados)
    fluxo = pd.concat(fluxos, ignore_index=True)

    # =============================
    # 🔹 CONSOLIDAÇÃO CARTEIRA (ROBUSTA)
    # =============================
    carteira = resumo.groupby("Tipo").agg({
        "Custo_Total": "sum",
        "VPL": "sum",
        "TIR": "mean"
    }).reset_index()

    # Garante linhas mesmo se faltar um tipo
    if "Antigo" not in carteira["Tipo"].values:
        carteira = pd.concat([carteira, pd.DataFrame([{
            "Tipo": "Antigo", "Custo_Total": 0, "VPL": 0, "TIR": 0
        }])], ignore_index=True)

    if "Novo" not in carteira["Tipo"].values:
        carteira = pd.concat([carteira, pd.DataFrame([{
            "Tipo": "Novo", "Custo_Total": 0, "VPL": 0, "TIR": 0
        }])], ignore_index=True)

    # 🔹 Diferença sempre calculada
    atual = carteira[carteira["Tipo"] == "Antigo"].iloc[0]
    novo = carteira[carteira["Tipo"] == "Novo"].iloc[0]

    carteira_dif = pd.DataFrame({
        "Tipo": ["Diferença"],
        "Custo_Total": [atual["Custo_Total"] - novo["Custo_Total"]],
        "VPL": [atual["VPL"] - novo["VPL"]],
        "TIR": [atual["TIR"] - novo["TIR"]]
    })

    carteira = pd.concat([carteira, carteira_dif], ignore_index=True)

    # =============================
    # 🔹 FLUXO ANUAL
    # =============================
    fluxo["Ano"] = fluxo["Data"].dt.year
    fluxo_anual = fluxo.groupby(["Ano", "ID"])["Pagamento"].sum().reset_index()
    fluxo_anual = fluxo_anual.merge(resumo[["ID", "Tipo"]], on="ID")
    fluxo_anual = fluxo_anual.groupby(["Ano", "Tipo"])["Pagamento"].sum().reset_index()

    # =============================
    # 🔹 FLUXO MENSAL
    # =============================
    fluxo_mensal = fluxo.groupby(["Data", "ID"])["Pagamento"].sum().reset_index()
    fluxo_mensal = fluxo_mensal.merge(resumo[["ID", "Tipo"]], on="ID")
    fluxo_mensal = fluxo_mensal.groupby(["Data", "Tipo"])["Pagamento"].sum().reset_index()

    return resumo, fluxo, carteira, fluxo_anual, fluxo_mensal
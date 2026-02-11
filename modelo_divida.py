import pandas as pd
import numpy_financial as npf

from engine_divida import simular_contrato
from cenarios import CenarioMercado


def _normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza nomes de colunas:
    - remove espaços nas extremidades
    """
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    return df


def rodar_modelo(
    df: pd.DataFrame | None = None,
    cenario: CenarioMercado | None = None,
):
    """
    Roda o modelo de dívida para um conjunto de contratos.

    Espera colunas mínimas:
    - Id
    - Tipo
    - Descrição
    - Moeda
    - Valor_Contratado
    """
    if cenario is None:
        cenario = CenarioMercado(nome="Base")

    if df is None:
        df = pd.read_excel("Contratos.xlsx")

    df = _normalizar_colunas(df)

    colunas_obrigatorias = [
        "Id",
        "Tipo",
        "Descrição",
        "Moeda",
        "Valor_Contratado",
    ]
    faltando = [c for c in colunas_obrigatorias if c not in df.columns]
    if faltando:
        raise ValueError(f"Planilha de contratos sem colunas obrigatórias: {faltando}")

    resultados = []
    fluxos = []

    # =============================
    # 🔹 Simulação contrato a contrato
    # =============================
    for _, row in df.iterrows():
        fluxo_df, tir, vpl = simular_contrato(row, cenario=cenario)

        if "Pagamento" not in fluxo_df.columns:
            raise ValueError("Fluxo do contrato não possui coluna 'Pagamento'.")
        if "Data" not in fluxo_df.columns:
            raise ValueError("Fluxo do contrato não possui coluna 'Data'.")

        custo_total = fluxo_df["Pagamento"].sum()

        resultados.append(
            {
                "ID": row["Id"],
                "Tipo": row["Tipo"],
                "Descrição": row["Descrição"],
                "Moeda": row["Moeda"],
                "Valor_Contratado": row["Valor_Contratado"],
                "Custo_Total": custo_total,
                "TIR": tir,
                "VPL": vpl,
            }
        )

        fluxo_df = fluxo_df.copy()
        fluxo_df["ID"] = row["Id"]
        fluxos.append(fluxo_df)

    if not resultados:
        resumo = pd.DataFrame(
            columns=[
                "ID",
                "Tipo",
                "Descrição",
                "Moeda",
                "Valor_Contratado",
                "Custo_Total",
                "TIR",
                "VPL",
            ]
        )
        fluxo = pd.DataFrame(columns=["ID", "Data", "Pagamento"])
        carteira = pd.DataFrame(
            [
                {"Tipo": "Antigo", "Custo_Total": 0, "VPL": 0, "TIR": 0},
                {"Tipo": "Novo", "Custo_Total": 0, "VPL": 0, "TIR": 0},
                {"Tipo": "Diferença", "Custo_Total": 0, "VPL": 0, "TIR": 0},
            ]
        )
        fluxo_anual = pd.DataFrame(columns=["Ano", "Tipo", "Pagamento"])
        fluxo_mensal = pd.DataFrame(columns=["Data", "Tipo", "Pagamento"])
        ranking = pd.DataFrame()
        return resumo, fluxo, carteira, fluxo_anual, fluxo_mensal, ranking

    resumo = pd.DataFrame(resultados)
    fluxo = pd.concat(fluxos, ignore_index=True)

    # =============================
    # 🔹 CONSOLIDAÇÃO CARTEIRA
    # =============================

    carteira = (
        resumo.groupby("Tipo")
        .agg(
            {
                "Custo_Total": "sum",
                "VPL": "sum",
                "TIR": "mean",
            }
        )
        .reset_index()
    )

    tipos_necessarios = ["Antigo", "Novo"]
    for t in tipos_necessarios:
        if t not in carteira["Tipo"].values:
            linha = {"Tipo": t, "Custo_Total": 0, "VPL": 0, "TIR": 0}
            carteira = pd.concat([carteira, pd.DataFrame([linha])], ignore_index=True)

    carteira = carteira.set_index("Tipo")
    atual = carteira.loc["Antigo"]
    novo = carteira.loc["Novo"]

    carteira_dif = pd.DataFrame(
        {
            "Tipo": ["Diferença"],
            "Custo_Total": [atual["Custo_Total"] - novo["Custo_Total"]],
            "VPL": [atual["VPL"] - novo["VPL"]],
            "TIR": [atual["TIR"] - novo["TIR"]],
        }
    )

    carteira = carteira.reset_index()
    carteira = pd.concat([carteira, carteira_dif], ignore_index=True)

    # =============================
    # 🔹 FLUXO ANUAL
    # =============================

    fluxo = fluxo.copy()
    if not pd.api.types.is_datetime64_any_dtype(fluxo["Data"]):
        fluxo["Data"] = pd.to_datetime(fluxo["Data"])

    fluxo["Ano"] = fluxo["Data"].dt.year

    fluxo_anual = (
        fluxo.groupby(["Ano", "ID"])["Pagamento"]
        .sum()
        .reset_index()
        .merge(resumo[["ID", "Tipo"]], on="ID")
    )

    fluxo_anual = (
        fluxo_anual.groupby(["Ano", "Tipo"])["Pagamento"]
        .sum()
        .reset_index()
    )

    # =============================
    # 🔹 FLUXO MENSAL
    # =============================

    fluxo_mensal = (
        fluxo.groupby(["Data", "ID"])["Pagamento"]
        .sum()
        .reset_index()
        .merge(resumo[["ID", "Tipo"]], on="ID")
    )

    fluxo_mensal = (
        fluxo_mensal.groupby(["Data", "Tipo"])["Pagamento"]
        .sum()
        .reset_index()
    )

    # =============================
    # 🔹 RANKING (CUSTO E PICO ANUAL)
    # =============================

    fluxo_anual_id = (
        fluxo.groupby(["Ano", "ID"])["Pagamento"]
        .sum()
        .reset_index()
    )
    pico_por_id = (
        fluxo_anual_id.groupby("ID")["Pagamento"]
        .max()
        .reset_index()
        .rename(columns={"Pagamento": "Pico_Anual"})
    )

    ranking = resumo.merge(pico_por_id, on="ID", how="left")
    ranking["Pico_Anual"] = ranking["Pico_Anual"].fillna(0)
    ranking = ranking.sort_values(by="Custo_Total", ascending=False)

    return resumo, fluxo, carteira, fluxo_anual, fluxo_mensal, ranking

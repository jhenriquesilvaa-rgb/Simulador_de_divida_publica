import streamlit as st
import pandas as pd
import plotly.express as px
from modelo_divida import rodar_modelo

st.set_page_config(layout="wide")
st.title("📊 Simulador Estratégico da Dívida Pública")

# =========================================================
# 📂 UPLOAD DA PLANILHA (FUNCIONA LOCAL E NA NUVEM)
# =========================================================
st.sidebar.header("📂 Base de Dados")

arquivo = st.sidebar.file_uploader(
    "Envie a planilha de contratos",
    type=["xlsx"]
)

if arquivo is None:
    st.warning("Envie a planilha para iniciar a simulação.")
    st.stop()

contratos = pd.read_excel(arquivo)

# =========================================================
# 🔹 RODAR MODELO
# =========================================================
resumo, fluxo, carteira, fluxo_anual, fluxo_mensal = rodar_modelo(contratos)

# =========================================================
# 🔹 FUNÇÃO FORMATAÇÃO BRL
# =========================================================
def brl(x):
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def safe_val(df, col):
    return df[col].values[0] if not df.empty else 0

# =========================================================
# 📌 INDICADORES CONSOLIDADOS
# =========================================================
st.header("📌 Indicadores Consolidados")

atual = carteira[carteira["Tipo"] == "Antigo"]
novo = carteira[carteira["Tipo"] == "Novo"]
dif = carteira[carteira["Tipo"] == "Diferença"]

col1, col2, col3 = st.columns(3)
col1.metric("💰 Custo Atual", brl(safe_val(atual, "Custo_Total")))
col2.metric("💰 Custo Novo", brl(safe_val(novo, "Custo_Total")))
col3.metric("Diferença", brl(safe_val(dif, "Custo_Total")))

col1, col2, col3 = st.columns(3)
col1.metric("📊 VPL Atual", brl(safe_val(atual, "VPL")))
col2.metric("📊 VPL Novo", brl(safe_val(novo, "VPL")))
col3.metric("Diferença VPL", brl(safe_val(dif, "VPL")))

col1, col2, col3 = st.columns(3)
col1.metric("📈 TIR Atual", f"{safe_val(atual, 'TIR'):.2f}%")
col2.metric("📈 TIR Nova", f"{safe_val(novo, 'TIR'):.2f}%")
col3.metric("Diferença TIR", f"{safe_val(dif, 'TIR'):.2f}%")

# =========================================================
# 📋 TABELA COMPARATIVA
# =========================================================
st.subheader("📋 Comparativo Carteira Atual vs Proposta")
st.dataframe(carteira, width="stretch")

# =========================================================
# 📅 IMPACTO ANUAL NO CAIXA
# =========================================================
st.subheader("📅 Impacto Anual no Caixa")

fig_anual = px.bar(
    fluxo_anual,
    x="Ano",
    y="Pagamento",
    color="Tipo",
    barmode="group",
    text_auto=True
)
st.plotly_chart(fig_anual, width="stretch")

tabela_anual = fluxo_anual.pivot(index="Ano", columns="Tipo", values="Pagamento").fillna(0)
tabela_anual["Diferença"] = tabela_anual.get("Antigo", 0) - tabela_anual.get("Novo", 0)
tabela_anual.loc["TOTAL"] = tabela_anual.sum()

st.dataframe(tabela_anual.applymap(brl), width="stretch")

# =========================================================
# 📆 PRESSÃO MENSAL NO CAIXA
# =========================================================
st.subheader("📆 Pressão Mensal no Caixa")

fig_mensal = px.line(
    fluxo_mensal,
    x="Data",
    y="Pagamento",
    color="Tipo"
)
st.plotly_chart(fig_mensal, width="stretch")

# =========================================================
# 🔍 ANÁLISE INDIVIDUAL
# =========================================================
st.header("🔍 Análise Individual do Contrato")

if not resumo.empty:
    contrato_sel = st.selectbox("Escolha o contrato", resumo["Descrição"])

    dados = resumo[resumo["Descrição"] == contrato_sel]
    fluxo_ind = fluxo[fluxo["ID"] == dados["ID"].values[0]]

    col1, col2, col3 = st.columns(3)
    col1.metric("Valor Contratado", brl(dados["Valor_Contratado"].values[0]))
    col2.metric("Custo Total", brl(dados["Custo_Total"].values[0]))
    col3.metric("TIR", f"{dados['TIR'].values[0]:.2f}%")

    st.metric("VPL", brl(dados["VPL"].values[0]))

    fig_ind = px.line(fluxo_ind, x="Data", y="Pagamento", title="Fluxo do Contrato")
    st.plotly_chart(fig_ind, width="stretch")

    st.dataframe(
        fluxo_ind[["Data", "Pagamento"]].applymap(
            lambda x: brl(x) if isinstance(x, (int, float)) else x
        ),
        width="stretch"
    )

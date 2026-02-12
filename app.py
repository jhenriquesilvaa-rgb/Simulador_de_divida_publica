import io
import os
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.express as px

import pdfkit
from jinja2 import Environment, FileSystemLoader

from modelo_divida import rodar_modelo
from cenarios import CENARIO_BASE, CENARIO_ESTRESSE, CENARIO_OTIMISTA
from mercado import pegar_cdi, pegar_ipca, pegar_selic, pegar_sofr, pegar_cambio


# =========================================================
# ⚙️ CONFIGURAÇÃO BÁSICA
# =========================================================

st.set_page_config(layout="wide")
st.title("📊 Simulador de Reestruturação da Dívida Pública")


# =========================================================
# 🔹 TAXAS DE MERCADO USADAS
# =========================================================
cdi = pegar_cdi()
ipca = pegar_ipca()
selic = pegar_selic()
sofr = pegar_sofr()
usd = pegar_cambio("USD")

st.markdown(
    f"""
**Taxas usadas no modelo agora:**

- CDI: {cdi*100:.2f}% a.a.
- Selic: {selic*100:.2f}% a.a.
- IPCA: {ipca*100:.2f}% a.a.
- SOFR: {sofr*100:.2f}% a.a.
- Câmbio USD/BRL: {usd:.4f}
"""
)


# =========================================================
# 📂 UPLOAD DA PLANILHA (FUNCIONA LOCAL E NA NUVEM)
# =========================================================

st.sidebar.header("📂 Base de Dados")

arquivo = st.sidebar.file_uploader(
    "Envie a planilha de contratos",
    type=["xlsx"]
)

cenario_opcao = st.sidebar.selectbox(
    "Cenário de Mercado",
    ["Base", "Estresse", "Otimista"]
)

mapa_cenarios = {
    "Base": CENARIO_BASE,
    "Estresse": CENARIO_ESTRESSE,
    "Otimista": CENARIO_OTIMISTA,
}

cenario_escolhido = mapa_cenarios[cenario_opcao]

if arquivo is None:
    st.warning("Envie a planilha para iniciar a simulação.")
    st.stop()

try:
    contratos = pd.read_excel(arquivo)
except Exception as e:
    st.error(f"Erro ao ler a planilha: {e}")
    st.stop()


# =========================================================
# 🔹 RODAR MODELO
# =========================================================

try:
    resumo, fluxo, carteira, fluxo_anual, fluxo_mensal, ranking = rodar_modelo(
        contratos,
        cenario=cenario_escolhido,
    )
except Exception as e:
    st.error(f"Erro ao rodar o modelo de dívida: {e}")
    st.stop()


# =========================================================
# 🔹 FUNÇÕES AUXILIARES (FORMATAÇÃO)
# =========================================================

def brl(x):
    """Formata número em R$ com separador brasileiro."""
    try:
        if pd.isna(x):
            return "-"
        return f"{float(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(x)


def safe_val(df, col):
    """Retorna o primeiro valor de uma coluna ou 0 se vazio/ausente."""
    if df is None or df.empty or col not in df.columns:
        return 0
    val = df[col].values[0]
    return 0 if pd.isna(val) else val


def safe_percent(x):
    """Formata percentuais de forma segura."""
    try:
        if pd.isna(x):
            return "-"
        return f"{float(x):.2f}%"
    except Exception:
        return "-"


# =========================================================
# 🔹 PREPARO DE DADOS PARA RELATÓRIO PDF
# =========================================================

def preparar_dados_relatorio(resumo_df, carteira_df, fluxo_anual_df, ranking_df):
    resumo_r = resumo_df.copy()
    carteira_r = carteira_df.copy()
    fluxo_anual_r = fluxo_anual_df.copy()
    ranking_r = ranking_df.copy()

    def _fmt_brl(x):
        try:
            if pd.isna(x):
                return "-"
            return f"{float(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return str(x)

    def _fmt_pct(x):
        try:
            if pd.isna(x):
                return "-"
            return f"{float(x):.2f}%"
        except Exception:
            return "-"

    # carteira
    if not carteira_r.empty:
        carteira_r["Custo_Total_fmt"] = carteira_r["Custo_Total"].apply(_fmt_brl)
        carteira_r["VPL_fmt"] = carteira_r["VPL"].apply(_fmt_brl)
        carteira_r["TIR_fmt"] = carteira_r["TIR"].apply(_fmt_pct)

    # fluxo anual: pivot para Antigo, Novo, Diferença
    if not fluxo_anual_r.empty:
        tabela_anual = (
            fluxo_anual_r.pivot(index="Ano", columns="Tipo", values="Pagamento")
            .fillna(0)
        )
        tabela_anual["Diferença"] = tabela_anual.get("Antigo", 0) - tabela_anual.get("Novo", 0)
        tabela_anual = tabela_anual.reset_index()

        fluxo_anual_list = []
        for _, row in tabela_anual.iterrows():
            fluxo_anual_list.append(
                {
                    "Ano": int(row["Ano"]),
                    "Antigo_fmt": _fmt_brl(row.get("Antigo", 0)),
                    "Novo_fmt": _fmt_brl(row.get("Novo", 0)),
                    "Diferenca_fmt": _fmt_brl(row.get("Diferença", 0)),
                }
            )
    else:
        fluxo_anual_list = []

    # ranking
    if not ranking_r.empty:
        ranking_r["Valor_Contratado_fmt"] = ranking_r["Valor_Contratado"].apply(_fmt_brl)
        ranking_r["Custo_Total_fmt"] = ranking_r["Custo_Total"].apply(_fmt_brl)
        ranking_r["Pico_Anual_fmt"] = ranking_r["Pico_Anual"].apply(_fmt_brl)
        ranking_r["TIR_fmt"] = ranking_r["TIR"].apply(_fmt_pct)

    # resumo contratos
    if not resumo_r.empty:
        resumo_r["Valor_Contratado_fmt"] = resumo_r["Valor_Contratado"].apply(_fmt_brl)
        resumo_r["Custo_Total_fmt"] = resumo_r["Custo_Total"].apply(_fmt_brl)
        resumo_r["VPL_fmt"] = resumo_r["VPL"].apply(_fmt_brl)
        resumo_r["TIR_fmt"] = resumo_r["TIR"].apply(_fmt_pct)

    return resumo_r, carteira_r, fluxo_anual_list, ranking_r


def gerar_pdf_relatorio(resumo_df, carteira_df, fluxo_anual_df, ranking_df, cenario_nome: str):
    """
    Gera PDF em memória a partir dos dataframes e do cenário.
    Requer:
      - pasta 'templates' na raiz do projeto
      - arquivo 'relatorio.html' dentro de 'templates'
      - wkhtmltopdf instalado no sistema
    """
    resumo_r, carteira_r, fluxo_anual_list, ranking_r = preparar_dados_relatorio(
        resumo_df, carteira_df, fluxo_anual_df, ranking_df
    )

    base_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(base_dir, "templates")
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template("relatorio.html")

    html = template.render(
        titulo="Simulação da Dívida Pública",
        cenario_nome=cenario_nome,
        data_geracao=datetime.now().strftime("%d/%m/%Y %H:%M"),
        resumo=resumo_r.to_dict(orient="records"),
        carteira=carteira_r.to_dict(orient="records"),
        fluxo_anual=fluxo_anual_list,
        ranking=ranking_r.to_dict(orient="records"),
    )

    # Caminho explícito para wkhtmltopdf (ajuste se necessário)
    wkhtml_path = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
    if not os.path.exists(wkhtml_path):
        raise RuntimeError(
            f"wkhtmltopdf não encontrado em {wkhtml_path}. "
            "Verifique o caminho de instalação."
        )

    config = pdfkit.configuration(wkhtmltopdf=wkhtml_path)
    pdf_bytes = pdfkit.from_string(html, False, configuration=config)
    return pdf_bytes


# =========================================================
# 📌 INDICADORES CONSOLIDADOS
# =========================================================

st.header("📌 Indicadores Consolidados")

if "Tipo" not in carteira.columns:
    st.error("A tabela 'carteira' não possui a coluna 'Tipo'. Verifique o modelo.")
    st.stop()

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
col1.metric("📈 TIR Atual", safe_percent(safe_val(atual, "TIR")))
col2.metric("📈 TIR Nova", safe_percent(safe_val(novo, "TIR")))
col3.metric("Diferença TIR", safe_percent(safe_val(dif, "TIR")))

st.caption(f"Cenário: {cenario_escolhido.nome}")


# =========================================================
# 📋 TABELA COMPARATIVA
# =========================================================

st.subheader("📋 Comparativo Carteira Atual vs Proposta")

carteira_fmt = carteira.copy()
if not carteira_fmt.empty:
    if "Custo_Total" in carteira_fmt.columns:
        carteira_fmt["Custo_Total"] = carteira_fmt["Custo_Total"].apply(brl)
    if "VPL" in carteira_fmt.columns:
        carteira_fmt["VPL"] = carteira_fmt["VPL"].apply(brl)
    if "TIR" in carteira_fmt.columns:
        carteira_fmt["TIR"] = carteira_fmt["TIR"].apply(safe_percent)

st.dataframe(carteira_fmt, use_container_width=True)


# =========================================================
# 📅 IMPACTO ANUAL NO CAIXA
# =========================================================

st.subheader("📅 Impacto Anual no Caixa")

if not fluxo_anual.empty:
    if not {"Ano", "Pagamento", "Tipo"}.issubset(fluxo_anual.columns):
        st.error("A tabela 'fluxo_anual' não possui as colunas necessárias (Ano, Pagamento, Tipo).")
    else:
        fig_anual = px.bar(
            fluxo_anual,
            x="Ano",
            y="Pagamento",
            color="Tipo",
            barmode="group",
            text_auto=True,
        )
        st.plotly_chart(fig_anual, use_container_width=True)

        tabela_anual = (
            fluxo_anual
            .pivot(index="Ano", columns="Tipo", values="Pagamento")
            .fillna(0)
        )
        tabela_anual["Diferença"] = tabela_anual.get("Antigo", 0) - tabela_anual.get("Novo", 0)
        tabela_anual.loc["TOTAL"] = tabela_anual.sum()

        tabela_anual_fmt = tabela_anual.applymap(brl)
        st.dataframe(tabela_anual_fmt, use_container_width=True)
else:
    st.info("Nenhum dado para fluxo anual.")


# =========================================================
# 📆 PRESSÃO MENSAL NO CAIXA
# =========================================================

st.subheader("📆 Pressão Mensal no Caixa")

if not fluxo_mensal.empty:
    if not {"Data", "Pagamento", "Tipo"}.issubset(fluxo_mensal.columns):
        st.error("A tabela 'fluxo_mensal' não possui as colunas necessárias (Data, Pagamento, Tipo).")
    else:
        fig_mensal = px.line(
            fluxo_mensal,
            x="Data",
            y="Pagamento",
            color="Tipo",
        )
        st.plotly_chart(fig_mensal, use_container_width=True)
else:
    st.info("Nenhum dado para fluxo mensal.")


# =========================================================
# 🏆 RANKING DE CONTRATOS
# =========================================================

st.header("🏆 Contratos que Mais Estressam o Caixa")

if ranking is not None and not ranking.empty:
    ranking_cols = [
        "Descrição", "Tipo", "Valor_Contratado",
        "Custo_Total", "Pico_Anual", "Ano_Pico", "TIR",
    ]
    cols_existentes = [c for c in ranking_cols if c in ranking.columns]

    df_rank = ranking[cols_existentes].copy()
    for c in ["Valor_Contratado", "Custo_Total", "Pico_Anual"]:
        if c in df_rank.columns:
            df_rank[c] = df_rank[c].apply(brl)
    if "TIR" in df_rank.columns:
        df_rank["TIR"] = df_rank["TIR"].apply(safe_percent)

    st.dataframe(df_rank, use_container_width=True)
else:
    st.info("Ranking não disponível.")


# =========================================================
# 🔍 ANÁLISE INDIVIDUAL + AUDITORIA
# =========================================================

st.header("🔍 Análise Individual do Contrato")

if resumo is not None and not resumo.empty:
    if "Descrição" not in resumo.columns or "ID" not in resumo.columns:
        st.error("A tabela 'resumo' não possui as colunas necessárias (Descrição, ID).")
    else:
        contrato_sel = st.selectbox("Escolha o contrato", resumo["Descrição"])
        dados = resumo[resumo["Descrição"] == contrato_sel]

        if not dados.empty:
            fluxo_ind = fluxo[fluxo["ID"] == dados["ID"].values[0]]

            col1, col2, col3 = st.columns(3)
            col1.metric("Valor Contratado", brl(dados["Valor_Contratado"].values[0]))
            col2.metric("Custo Total", brl(dados["Custo_Total"].values[0]))
            col3.metric("TIR", safe_percent(dados["TIR"].values[0]))
            st.metric("VPL", brl(dados["VPL"].values[0]))

            auditoria = st.checkbox("🔎 Modo auditoria detalhada")

            if auditoria and not fluxo_ind.empty:
                st.subheader("Taxas Utilizadas")

                if "Taxa_Anual" in fluxo_ind.columns:
                    st.write(
                        f"**Taxa anual (indexador + spread):** "
                        f"{safe_percent(fluxo_ind['Taxa_Anual'].iloc[0])}"
                    )
                if "Taxa_Periodo" in fluxo_ind.columns:
                    st.write(
                        f"**Taxa por período:** "
                        f"{safe_percent(fluxo_ind['Taxa_Periodo'].iloc[0])}"
                    )

                st.subheader("Tabela de Auditoria do Fluxo")

                colunas_auditoria = [
                    "Data", "Pagamento", "Amortização",
                    "Juros", "Saldo_Devedor",
                    "Taxa_Periodo", "Taxa_Anual",
                ]
                cols_existentes = [
                    c for c in colunas_auditoria if c in fluxo_ind.columns
                ]

                df_aud = fluxo_ind[cols_existentes].copy()

                for c in ["Pagamento", "Amortização", "Juros", "Saldo_Devedor"]:
                    if c in df_aud.columns:
                        df_aud[c] = df_aud[c].apply(brl)

                for c in ["Taxa_Periodo", "Taxa_Anual"]:
                    if c in df_aud.columns:
                        df_aud[c] = df_aud[c].apply(safe_percent)

                st.dataframe(df_aud, use_container_width=True)

            else:
                if not fluxo_ind.empty and {"Data", "Pagamento"}.issubset(fluxo_ind.columns):
                    fig_ind = px.line(
                        fluxo_ind,
                        x="Data",
                        y="Pagamento",
                        title="Fluxo do Contrato",
                    )
                    st.plotly_chart(fig_ind, use_container_width=True)

                    st.dataframe(
                        fluxo_ind[["Data", "Pagamento"]].assign(
                            Pagamento=lambda df: df["Pagamento"].apply(brl)
                        ),
                        use_container_width=True,
                    )
                else:
                    st.info("Não há fluxo detalhado para este contrato.")
else:
    st.info("Nenhum contrato disponível no resumo.")


# =========================================================
# 💾 EXPORTAÇÕES (EXCEL E PDF)
# =========================================================

st.header("💾 Exportações")

col_exp1, col_exp2 = st.columns(2)

with col_exp1:
    if st.button("⬇️ Exportar para Excel"):
        with io.BytesIO() as buffer:
            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                resumo.to_excel(writer, sheet_name="Resumo", index=False)
                fluxo.to_excel(writer, sheet_name="Fluxo", index=False)
                carteira.to_excel(writer, sheet_name="Carteira", index=False)
                fluxo_anual.to_excel(writer, sheet_name="Fluxo_Anual", index=False)
                fluxo_mensal.to_excel(writer, sheet_name="Fluxo_Mensal", index=False)
                if ranking is not None:
                    ranking.to_excel(writer, sheet_name="Ranking", index=False)

            st.download_button(
                label="Baixar Excel completo",
                data=buffer.getvalue(),
                file_name="simulador_divida_publica.xlsx",
                mime=(
                    "application/"
                    "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
            )

with col_exp2:
    if st.button("📄 Exportar Relatório em PDF"):
        try:
            pdf_bytes = gerar_pdf_relatorio(
                resumo, carteira, fluxo_anual, ranking, cenario_escolhido.nome
            )
            st.download_button(
                label="Baixar PDF do Relatório",
                data=pdf_bytes,
                file_name="relatorio_divida_publica.pdf",
                mime="application/pdf",
            )
        except RuntimeError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Erro ao gerar PDF: {e}")

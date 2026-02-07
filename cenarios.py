def aplicar_estresse(df, choque_juros=0.02):
    df["Fluxo_Estresse"] = df["Fluxo"] * (1 + choque_juros)
    return df

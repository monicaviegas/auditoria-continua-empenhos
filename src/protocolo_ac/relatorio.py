"""Relatório Excel da execução (uma aba por saída). Sem rótulos conclusivos; CPF mascarado."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

LEIA_ME = [
    "Relatório de Auditoria Contínua – protocolo T0–T7 sobre registros de empenho.",
    "Cada linha sinalizada é um registro priorizado para exame, não uma conclusão sobre regularidade.",
    "Contagens informam a unidade: linhas, empenhos_distintos, favorecidos_distintos ou estratos.",
    "Universos: U_total (todas as linhas), U_positivos (valor > 0), U_distinto (1 linha por nº de empenho), "
    "U_triagem (positivos de natureza comparável). Exclusões em T2_universos e log_exclusoes.csv.",
    "Procedimentos não executáveis e o motivo constam em T0_executabilidade.",
]


def _mascarar(df: pd.DataFrame) -> pd.DataFrame:
    """Mascara CPFs (11 dígitos) na coluna id_favorecido, se existir."""
    if "id_favorecido" in df:
        from .t7_favorecidos import mascarar_cpf
        df = df.assign(id_favorecido=df["id_favorecido"].map(lambda v: mascarar_cpf(v) if pd.notna(v) else v))
    return df


def gravar_excel(caminho: Path, perfil_cols, exe, cob, universos, excl, nuc, t6, metadados, d) -> None:
    with pd.ExcelWriter(caminho, engine="openpyxl") as xw:
        pd.DataFrame({"LEIA-ME": LEIA_ME}).to_excel(xw, sheet_name="LEIA-ME", index=False)
        perfil_cols.to_excel(xw, sheet_name="T0_perfil_colunas", index=False)
        exe.to_excel(xw, sheet_name="T0_executabilidade", index=False)
        cob.to_excel(xw, sheet_name="T1_cobertura", index=False)
        pd.concat([universos, pd.DataFrame([{}]), excl]).to_excel(xw, sheet_name="T2_universos", index=False)
        t3 = nuc["t3"]
        if t3:
            s = t3["sinalizadas"].copy()
            chaves = [c for c in ("numero_empenho", "data_emissao", "unidade", "favorecido", "id_favorecido") if c in d]
            s = _mascarar(s.join(d[chaves]))
            s.rename(columns={"n": "linhas_no_estrato", "x": "log1p_valor"}).to_excel(xw, sheet_name="T3_sinalizadas", index=False)
            t3["estratos"].to_excel(xw, sheet_name="T3_estratos", index=False)
        nuc["t4_linhas"]["frequencias"].assign(universo="U_positivos (linhas)").to_excel(xw, sheet_name="T4_frequencias", index=False)
        if nuc["t4_distintos"]:
            nuc["t4_distintos"]["frequencias"].assign(universo="U_distinto (empenhos)").to_excel(
                xw, sheet_name="T4_frequencias", index=False, startrow=12)
        from .t4_benford import valores_digito
        valores_digito(nuc["t4_linhas"]).to_excel(xw, sheet_name="T4_valores_digito", index=False)
        if nuc["t5"]:
            nuc["t5"]["exercicio_mes"].to_excel(xw, sheet_name="T5_exercicio_mes", index=False)
            r = 0
            for nome, c in nuc["t5"]["composicao"].items():
                c.assign(dimensao=nome).to_excel(xw, sheet_name="T5_mes_maior", index=False, startrow=r)
                r += len(c) + 3
        t6["distribuicao_tamanho"].assign(linhas_repetidas=t6["linhas_repetidas"], grupos=t6["grupos_repetidos"]).to_excel(
            xw, sheet_name="T6_repeticoes", index=False)
        if nuc["t7"]:
            rk = nuc["t7"]["ranking"].head(100).reset_index()
            rk.columns = ["favorecido", "valor_empenhado"]
            rk["pct_valor"] = rk["valor_empenhado"] / nuc["t7"]["ranking"].sum()
            rk.to_excel(xw, sheet_name="T7_favorecidos", index=False)
            nuc["t7"]["tipos"].to_excel(xw, sheet_name="T7_tipos", index=False)
        from .t2_preparo import tabela_trilhas
        if d["trilha"].notna().any():
            tabela_trilhas(d).to_excel(xw, sheet_name="T2_trilhas", index=False)
        if nuc.get("t7") is not None:
            nuc["t7"]["por_elemento"].to_excel(xw, sheet_name="T7_por_elemento", index=False)
        if nuc.get("t8"):
            nuc["t8"]["rubrica_exercicio"].to_excel(xw, sheet_name="T8_rubricas", index=False)
        if nuc.get("t9"):
            s9 = nuc["t9"]["sinalizadas"].drop(columns=["x"])
            if "id_favorecido" in d:
                ids = d.loc[d["u_pessoas"]].groupby("favorecido")["id_favorecido"].first()
                s9 = _mascarar(s9.assign(id_favorecido=s9["favorecido"].map(ids)))
            s9.to_excel(xw, sheet_name="T9_sinalizados", index=False)
            nuc["t9"]["estratos"].to_excel(xw, sheet_name="T9_estratos", index=False)
            nuc["t9"]["agregados"].to_excel(xw, sheet_name="T9_pagamentos_agregados", index=False)
        pd.DataFrame([{"chave": k, "valor": json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v}
                      for k, v in metadados.items()]).to_excel(xw, sheet_name="metadados", index=False)

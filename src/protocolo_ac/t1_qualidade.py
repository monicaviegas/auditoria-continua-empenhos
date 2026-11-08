"""T1 – Qualidade e cobertura. Universo: U_total. Unidade: linhas (e números de empenho distintos)."""
from __future__ import annotations

import pandas as pd


def _contagens(d: pd.DataFrame) -> dict:
    tem_num = d["numero_empenho"].notna() if "numero_empenho" in d else pd.Series(False, index=d.index)
    tem_data = d["data_emissao"].notna() if "data_emissao" in d else pd.Series(False, index=d.index)
    v = d["valor_empenhado"]
    ano_div = tem_data & (d["data_emissao"].dt.year != d["exercicio"]) if "data_emissao" in d else tem_data
    return {
        "linhas": int(len(d)),
        "linhas_com_numero": int(tem_num.sum()),
        "empenhos_distintos": int(d.loc[tem_num, "numero_empenho"].nunique()) if "numero_empenho" in d else 0,
        "linhas_sem_numero": int((~tem_num).sum()),
        "linhas_data_valida": int(tem_data.sum()),
        "linhas_numero_e_data": int((tem_num & tem_data).sum()),
        "linhas_ano_divergente": int(ano_div.sum()),
        "linhas_valor_positivo": int((v > 0).sum()),
        "linhas_valor_zero": int((v == 0).sum()),
        "linhas_valor_negativo": int((v < 0).sum()),
        "linhas_valor_ausente": int(v.isna().sum()),
    }


def cobertura(can: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Contagens por exercício e total (linhas da extração)."""
    linhas = []
    for ex, d in can.groupby("exercicio", sort=True):
        linhas.append({"exercicio": int(ex), **_contagens(d)})
    total = _contagens(can)
    linhas.append({"exercicio": "Total", **total})
    return pd.DataFrame(linhas), total

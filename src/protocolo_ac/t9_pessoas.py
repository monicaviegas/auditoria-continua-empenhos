"""T9 – Trilha de pagamentos a pessoas físicas: valor acumulado por favorecido em cada rubrica e exercício.

Universo: U_pessoas. Unidade: favorecido-rubrica-exercício (favorecido × elemento × exercício).
Favorecidos cujo nome indica unidade ou órgão (regra declarada em params.t9.padrao_favorecido_agregado) são
separados como "pagamento agregado" e não pontuados; os demais têm o acumulado pontuado por escore robusto.
"""
from __future__ import annotations

import pandas as pd

from .t3_triagem import escore_robusto


def pessoas(d: pd.DataFrame, params: dict) -> dict:
    p = params["t9"]
    u = d.loc[d["u_pessoas"] & d["favorecido"].notna()]
    acc = u.groupby(["elemento", "exercicio", "favorecido"])["valor_empenhado"].agg(["size", "sum"]).rename(
        columns={"size": "linhas", "sum": "acumulado"}).reset_index()
    padrao = p.get("padrao_favorecido_agregado")
    acc["agregado"] = acc["favorecido"].astype(str).str.upper().str.contains(padrao, regex=True) if padrao else False
    ind = acc[~acc["agregado"]]
    pont, estr = escore_robusto(ind, ["elemento", "exercicio"], "acumulado", p["min_grupo"], p["limiar"])
    med = estr.set_index(["elemento", "exercicio"])["mediana_valor"]
    pont["razao_mediana"] = pont["acumulado"].to_numpy() / med.reindex(pd.MultiIndex.from_frame(pont[["elemento", "exercicio"]])).to_numpy()
    sup = pont[pont["cauda"] == "superior"]
    eleg = pont["elegivel"]
    total = float(u["valor_empenhado"].sum())
    total_ind = float(ind["acumulado"].sum())
    agr = acc[acc["agregado"]]
    return {
        "pontuadas": pont, "estratos": estr, "sinalizadas": sup.sort_values("z", ascending=False), "agregados": agr,
        "resumo": {
            "linhas": int(len(u)), "valor": total,
            "favorecidos_distintos": int(u["favorecido"].nunique()),
            "agregados_favorecidos": int(agr["favorecido"].nunique()),
            "agregados_linhas": int(agr["linhas"].sum()),
            "agregados_pct_valor": float(agr["acumulado"].sum() / total) if total else 0.0,
            "individuais_favorecidos": int(ind["favorecido"].nunique()),
            "acumulados": int(len(pont)), "acumulados_elegiveis": int(eleg.sum()),
            "estratos_elegiveis": int(estr["elegivel"].sum()),
            "sinalizados": int(len(sup)),
            "taxa": len(sup) / int(eleg.sum()) if eleg.sum() else 0.0,
            "pct_valor_sinalizados": float(sup["acumulado"].sum() / total_ind) if total_ind else 0.0,
            "linhas_sinalizados": int(sup["linhas"].sum()),
            "razao_mediana_max": float(sup["razao_mediana"].max()) if len(sup) else 0.0,
            "razao_mediana_mediana": float(sup["razao_mediana"].median()) if len(sup) else 0.0,
            "acumulado_max": float(sup["acumulado"].max()) if len(sup) else 0.0,
            "linhas_mediana_sinalizados": float(sup["linhas"].median()) if len(sup) else 0.0,
        },
    }

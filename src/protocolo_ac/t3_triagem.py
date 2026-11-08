"""T3 – Trilha de fornecedores: triagem robusta (escore z modificado) por estrato.

Universo: U_fornecedores. Unidade: linhas. A função `escore_robusto` é reutilizada em T9.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def escore_robusto(u: pd.DataFrame, campos: list[str], coluna: str, min_grupo: int, limiar: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Escore z modificado de log1p(coluna) dentro de cada estrato. Retorna (linhas pontuadas, estratos)."""
    u = u.copy()
    u["x"] = np.log1p(u[coluna].astype(float))
    g = u.groupby(campos, sort=True, dropna=False)["x"]
    u["n"] = g.transform("size")
    u["mediana"] = g.transform("median")
    u["_absdev"] = (u["x"] - u["mediana"]).abs()
    mad = u.groupby(campos, dropna=False)["_absdev"].transform("median")
    q1 = g.transform(lambda s: s.quantile(0.25))
    q3 = g.transform(lambda s: s.quantile(0.75))
    escala, escala_iqr = 1.4826 * mad, (q3 - q1) / 1.349
    u["metodo_escala"] = np.where(escala > 0, "MAD", np.where(escala_iqr > 0, "IQR", "nao_pontuado"))
    u["escala"] = np.where(escala > 0, escala, np.where(escala_iqr > 0, escala_iqr, np.nan))
    u["elegivel"] = u["n"] >= min_grupo
    u["z"] = np.where(u["elegivel"], (u["x"] - u["mediana"]) / u["escala"], np.nan)
    u["cauda"] = np.where(u["z"] > limiar, "superior", np.where(u["z"] < -limiar, "inferior", ""))
    u = u.drop(columns="_absdev")
    estr = u.groupby(campos, dropna=False).agg(
        n=("x", "size"), mediana_log=("mediana", "first"), escala=("escala", "first"),
        metodo_escala=("metodo_escala", "first"),
        sinalizadas_superior=("cauda", lambda s: int((s == "superior").sum())),
        sinalizadas_inferior=("cauda", lambda s: int((s == "inferior").sum())),
    ).reset_index()
    estr["elegivel"] = estr["n"] >= min_grupo
    estr["mediana_valor"] = np.expm1(estr["mediana_log"])
    return u, estr


def triagem(d: pd.DataFrame, params: dict) -> dict:
    p = params["t3"]
    campos = list(p["estrato_campos"])
    u, estr = escore_robusto(d.loc[d["u_triagem"], campos + ["valor_empenhado"]], campos, "valor_empenhado",
                             p["min_grupo"], p["limiar"])
    eleg = u["elegivel"]
    sup = int((u["cauda"] == "superior").sum())
    n_eleg = int(eleg.sum())
    return {
        "pontuadas": u,
        "estratos": estr,
        "sinalizadas": u[u["cauda"] != ""].sort_values("z", ascending=False),
        "resumo": {
            "linhas_elegiveis": n_eleg,
            "linhas_nao_elegiveis": int((~eleg).sum()),
            "estratos_elegiveis": int(estr["elegivel"].sum()),
            "estratos_nao_elegiveis": int((~estr["elegivel"]).sum()),
            "estratos_escala_iqr": int((estr["elegivel"] & (estr["metodo_escala"] == "IQR")).sum()),
            "estratos_nao_pontuados": int((estr["elegivel"] & (estr["metodo_escala"] == "nao_pontuado")).sum()),
            "sinalizadas_superior": sup,
            "sinalizadas_inferior": int((u["cauda"] == "inferior").sum()),
            "taxa_sinalizacao_superior": sup / n_eleg if n_eleg else 0.0,
            "valor_sinalizadas_superior": float(u.loc[u["cauda"] == "superior", "valor_empenhado"].sum()),
        },
    }


def top_estratos(res: dict, k: int = 10) -> pd.DataFrame:
    e = res["estratos"]
    return e[e["elegivel"]].sort_values(["sinalizadas_superior", "n"], ascending=False).head(k)

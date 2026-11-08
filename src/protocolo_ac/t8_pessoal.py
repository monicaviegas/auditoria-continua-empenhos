"""T8 – Trilha de pessoal: variação do valor por rubrica (elemento) entre exercícios.

Universo: U_pessoal. Unidade: rubrica-exercício (elemento × exercício).
Uma rubrica-exercício é sinalizada quando seu valor é >= razao_limiar × a mediana dos demais exercícios da rubrica
(e, à parte, quando é <= 1/razao_limiar dessa mediana).
"""
from __future__ import annotations

import pandas as pd


def pessoal(d: pd.DataFrame, params: dict) -> dict:
    p = params["t8"]
    u = d.loc[d["u_pessoal"]]
    re = u.groupby(["elemento", "exercicio"])["valor_empenhado"].agg(["size", "sum"]).rename(
        columns={"size": "linhas", "sum": "valor"}).reset_index()
    linhas = []
    for _el, g in re.groupby("elemento"):
        if len(g) < p["min_exercicios"]:
            continue
        for i, r in g.iterrows():
            outros = g.drop(index=i)["valor"]
            med = float(outros.median())
            linhas.append({**r.to_dict(), "mediana_demais": med, "razao": r["valor"] / med if med else float("nan")})
    t = pd.DataFrame(linhas)
    if t.empty:
        t = pd.DataFrame(columns=["elemento", "exercicio", "linhas", "valor", "mediana_demais", "razao"])
    lim = p["razao_limiar"]
    t["sinal"] = ""
    t.loc[t["razao"] >= lim, "sinal"] = "acima"
    t.loc[t["razao"] <= 1 / lim, "sinal"] = "abaixo"
    por_rubrica = u.groupby("elemento")["valor_empenhado"].sum().sort_values(ascending=False)
    total = float(u["valor_empenhado"].sum())
    return {
        "rubrica_exercicio": t,
        "sinalizadas": t[t["sinal"] != ""].sort_values("razao", ascending=False),
        "por_rubrica": por_rubrica,
        "resumo": {
            "linhas": int(len(u)), "valor": total,
            "rubricas": int(u["elemento"].nunique()),
            "rubricas_analisadas": int(t["elemento"].nunique()),
            "rubrica_exercicios": int(len(t)),
            "sinalizadas_acima": int((t["sinal"] == "acima").sum()),
            "sinalizadas_abaixo": int((t["sinal"] == "abaixo").sum()),
            "favorecidos_distintos": int(u["favorecido"].nunique()) if "favorecido" in u else 0,
            "part_maior_rubrica": float(por_rubrica.iloc[0] / total) if total else 0.0,
            "part_top4_rubricas": float(por_rubrica.head(4).sum() / total) if total else 0.0,
        },
    }

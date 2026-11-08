"""T7 – Trilha de fornecedores: concentração por favorecido. Universo: U_fornecedores. Unidade: favorecidos e valor."""
from __future__ import annotations

import pandas as pd


def tipo_favorecido(ids: pd.Series) -> pd.Series:
    dig = ids.astype("string").str.replace(r"\D", "", regex=True)
    t = pd.Series("órgão/código", index=ids.index, dtype="object")
    t[dig.str.len() == 14] = "pessoa jurídica"
    t[dig.str.len() == 11] = "pessoa física"
    t[ids.isna() | (dig.str.len() == 0)] = "não classificado"
    return t


def mascarar_cpf(cpf: str) -> str:
    d = "".join(ch for ch in str(cpf) if ch.isdigit())
    return f"***.{d[3:6]}.{d[6:9]}-**" if len(d) == 11 else str(cpf)


def favorecidos(d: pd.DataFrame, params: dict) -> dict:
    top_n = params["t7"]["top_n"]
    u = d.loc[d["u_triagem"]]
    soma = u.groupby("favorecido", dropna=False)["valor_empenhado"].sum().sort_values(ascending=False)
    total = float(soma.sum())
    res = {
        "favorecidos_distintos": int(u["favorecido"].nunique()),
        "linhas_sem_favorecido": int(u["favorecido"].isna().sum()),
        "part_top1": float(soma.iloc[0] / total) if total else 0.0,
        "part_topn": float(soma.head(top_n).sum() / total) if total else 0.0,
        "ranking": soma,
        "por_elemento": _lider_por_elemento(u),
    }
    if "id_favorecido" in u and u["id_favorecido"].notna().any():
        tipo = tipo_favorecido(u["id_favorecido"])
        t = u.assign(tipo=tipo).groupby("tipo")["valor_empenhado"].agg(["size", "sum"])
        t.columns = ["linhas", "valor"]
        t["pct_valor"] = t["valor"] / total
        res["tipos"] = t.reset_index()
        res["part_nao_classificados"] = float(t["pct_valor"].get("não classificado", 0.0)) if "não classificado" in t.index else 0.0
        pj = u.loc[tipo == "pessoa jurídica"].groupby("id_favorecido")["valor_empenhado"].sum()
        sh = pj / pj.sum() if len(pj) else pj
        res["hhi_pj"] = float((sh ** 2).sum() * 10000) if len(pj) else None
        res["tipo_executado"] = True
    else:
        res["tipos"] = pd.DataFrame([{"tipo": "não classificado (id_favorecido ausente)", "linhas": int(len(u)),
                                      "valor": total, "pct_valor": 1.0}])
        res["part_nao_classificados"] = 1.0
        res["hhi_pj"] = None
        res["tipo_executado"] = False
    return res


def _lider_por_elemento(u: pd.DataFrame) -> pd.DataFrame:
    """Por elemento: favorecidos, valor e participação do maior favorecido e dos 3 maiores (sem nomes)."""
    linhas = []
    for el, g in u.groupby("elemento"):
        s = g.groupby("favorecido")["valor_empenhado"].sum().sort_values(ascending=False)
        tot = s.sum()
        linhas.append({"elemento": el, "favorecidos": len(s), "valor": tot,
                       "pct_maior": s.iloc[0] / tot if tot else 0.0, "pct_top3": s.head(3).sum() / tot if tot else 0.0})
    return pd.DataFrame(linhas).sort_values("valor", ascending=False)

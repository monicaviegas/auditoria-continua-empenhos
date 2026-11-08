"""T2 – Preparação e universos analíticos.

Saída: o DataFrame canônico acrescido de `sinal`, `flag_rap` e máscaras de universo
(`u_positivos`, `u_distinto`, `u_triagem`), e o registro de exclusões (unidade: linhas).
"""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)


def filtrar_escopo(can: pd.DataFrame, unidades_por_exercicio: dict | None) -> tuple[pd.DataFrame, list[dict]]:
    """Mantém as linhas cujas unidades constam do escopo do caso para o exercício."""
    if not unidades_por_exercicio or "unidade" not in can:
        return can, []
    manter = pd.Series(False, index=can.index)
    for ex, unidades in unidades_por_exercicio.items():
        manter |= (can["exercicio"] == int(ex)) & can["unidade"].isin([str(u) for u in unidades])
    excl = [{"universo": "U_total", "motivo": "unidade fora do escopo do caso", "linhas": int((~manter).sum())}]
    return can.loc[manter].copy(), excl


def unidades_todo_periodo(can: pd.DataFrame) -> list[str]:
    """Unidades presentes em todos os exercícios (escopo de sensibilidade)."""
    if "unidade" not in can:
        return []
    n_ex = can["exercicio"].nunique()
    por_un = can.groupby("unidade")["exercicio"].nunique()
    return sorted(por_un[por_un == n_ex].index.astype(str))


def preparar(can: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = params["t2"]
    d = can.copy()
    v = d["valor_empenhado"]
    d["sinal"] = pd.Series("ausente", index=d.index, dtype="object")
    d.loc[v > 0, "sinal"] = "positivo"
    d.loc[v == 0, "sinal"] = "nulo"
    d.loc[v < 0, "sinal"] = "negativo"
    if "data_emissao" in d:
        d["flag_rap"] = (d["data_emissao"].dt.year < d["exercicio"]).fillna(False).astype(bool)
    else:
        d["flag_rap"] = False
    if p.get("deflacionar"):
        raise NotImplementedError("Deflação requer data/referencia/ipca.csv")

    excl: list[dict] = []
    n = len(d)
    pos = (v > 0).fillna(False)
    d["u_positivos"] = pos
    for motivo, m in (("valor nulo", v == 0), ("valor negativo (anulação)", v < 0), ("valor ausente", v.isna())):
        excl.append({"universo": "U_positivos", "motivo": motivo, "linhas": int(m.fillna(False).sum())})

    # U_distinto: uma linha por número de empenho (primeira ocorrência pela data de emissão)
    if "numero_empenho" in d:
        cand = d.loc[pos & d["numero_empenho"].notna()]
        ordem = [c for c in ("data_emissao", "exercicio") if c in cand]
        primeiro = cand.sort_values(ordem + ["numero_empenho"], kind="mergesort").drop_duplicates("numero_empenho").index
        d["u_distinto"] = d.index.isin(primeiro)
        excl.append({"universo": "U_distinto", "motivo": "linha positiva sem número de empenho",
                     "linhas": int((pos & d["numero_empenho"].isna()).sum())})
        excl.append({"universo": "U_distinto", "motivo": "ocorrência posterior do mesmo número de empenho",
                     "linhas": int(len(cand) - len(primeiro))})
    else:
        d["u_distinto"] = False

    # Recorte da base em trilhas: cada linha positiva pertence a uma única trilha (ordem de precedência abaixo)
    d["trilha"] = pd.Series(pd.NA, index=d.index, dtype="object")
    if "gnd" in d and "elemento" in d:
        el, gnd = d["elemento"], d["gnd"]
        if "modalidade_aplicacao" in d and d["modalidade_aplicacao"].notna().any():
            transf = ~d["modalidade_aplicacao"].isin(p["modalidades_incluidas"])
        else:
            transf = el.isin(p["elementos_transferencia_fallback"])
        regras = [
            (TRILHAS[0], gnd.isna() | el.isna()),
            (TRILHAS[1], ((gnd == 1) & ~el.isin(p["elementos_excluidos_pessoal"])) | el.isin(p["elementos_pessoal_odc"])),
            (TRILHAS[2], transf),
            (TRILHAS[3], el.isin(p["elementos_pagamento_pessoa"])),
            (TRILHAS[4], gnd.isin(p["gnd_excluidos"]) | el.isin(p["elementos_nao_fornecedor"])),
        ]
        livre = pos.copy()
        for nome, m in regras:
            m = m.fillna(False).astype(bool) & livre
            d.loc[m, "trilha"] = nome
            livre &= ~m
        d.loc[livre, "trilha"] = TRILHAS[5]
        for nome in TRILHAS[:5]:
            excl.append({"universo": "U_fornecedores", "motivo": f"trilha: {nome}", "linhas": int((d["trilha"] == nome).sum())})
    else:
        excl.append({"universo": "U_fornecedores", "motivo": "não executado (campos gnd/elemento ausentes)", "linhas": int(pos.sum())})
    d["u_triagem"] = (d["trilha"] == TRILHAS[5]).fillna(False).astype(bool)
    d["u_pessoal"] = (d["trilha"] == TRILHAS[1]).fillna(False).astype(bool)
    d["u_pessoas"] = (d["trilha"] == TRILHAS[3]).fillna(False).astype(bool)
    log.info("T2: %d linhas; U_positivos=%d; U_fornecedores=%d", n, int(pos.sum()), int(d["u_triagem"].sum()))
    return d, pd.DataFrame(excl)


TRILHAS = ["sem classificação (GND/elemento ausente)", "pessoal", "transferências", "pagamentos a pessoas físicas",
           "outras despesas (dívida, sentenças, tributos, subsídios)", "fornecedores"]


def tabela_trilhas(d: pd.DataFrame) -> pd.DataFrame:
    """Recorte de U_positivos por trilha. Unidade: linhas, favorecidos e valor."""
    u = d.loc[d["u_positivos"]]
    t = u.groupby("trilha", dropna=False).agg(linhas=("valor_empenhado", "size"), valor=("valor_empenhado", "sum"),
                                              favorecidos=("favorecido", "nunique") if "favorecido" in u else ("valor_empenhado", "size"))
    t = t.reindex([x for x in TRILHAS[::-1] if x in t.index])
    t["pct_linhas"] = t["linhas"] / t["linhas"].sum()
    t["pct_valor"] = t["valor"] / t["valor"].sum()
    return t.reset_index()


def tabela_universos(d: pd.DataFrame) -> pd.DataFrame:
    def soma(m):
        return float(d.loc[m, "valor_empenhado"].sum())
    tot = pd.Series(True, index=d.index)
    linhas = [
        ("U_total", "Todas as linhas no escopo", tot),
        ("U_positivos", "Valor empenhado > 0", d["u_positivos"]),
        ("U_distinto", "Uma linha por número de empenho", d["u_distinto"]),
        ("U_fornecedores", "Trilha de fornecedores (aquisições e contratações diretas)", d["u_triagem"]),
        ("U_pessoal", "Trilha de pessoal (GND 1 e benefícios pagos em folha)", d["u_pessoal"]),
        ("U_pessoas", "Trilha de pagamentos a pessoas físicas", d["u_pessoas"]),
        ("Restos a pagar (marcação)", "Ano da data < exercício", d["flag_rap"]),
    ]
    return pd.DataFrame([{"universo": u, "definicao": df_, "linhas": int(m.sum()),
                          "valor_empenhado": soma(m)} for u, df_, m in linhas])

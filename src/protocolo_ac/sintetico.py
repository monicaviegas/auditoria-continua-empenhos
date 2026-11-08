"""Gerador de base sintética (usado nos testes e como base de demonstração do painel) no modelo canônico, com anomalias injetadas de resultado conhecido.

Também grava a mesma base em dois formatos de origem (Excel no estilo SIGA Brasil e CSV pt-BR genérico).
Semente fixa: mesma chamada => mesma base.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ESTRATOS = {  # (gnd, elemento) -> mediana do valor (R$)
    (3, "30"): 800.0, (3, "39"): 25000.0, (3, "14"): 350.0, (4, "52"): 150000.0,
}
EXERCICIOS = [2020, 2021, 2022, 2023]
DESC_EL = {"30": "MATERIAL DE CONSUMO", "39": "OUTROS SERVICOS DE TERCEIROS - PJ", "14": "DIARIAS - CIVIL",
           "52": "EQUIPAMENTOS E MATERIAL PERMANENTE", "11": "VENCIMENTOS E VANTAGENS FIXAS",
           "91": "SENTENCAS JUDICIAIS", "41": "CONTRIBUICOES"}
ABREV_GND = {1: "PES", 3: "ODC", 4: "INV"}


@dataclass
class Injecao:
    extremos: list[int] = field(default_factory=list)       # índices com valor extremo (cauda superior)
    duplicadas: list[int] = field(default_factory=list)     # índices das cópias (o original também conta)
    digito: int = 7
    mes: int = 11
    esperado: dict = field(default_factory=dict)
    t8_rubrica_exercicio: tuple = ("11", 2022)               # rubrica de pessoal com pico injetado
    t9_pessoas: list[str] = field(default_factory=list)      # pessoas com acúmulo injetado em diárias


def gerar(n_por_estrato: int = 1000, seed: int = 20261107, excesso_digito: float = 0.04,
          extremos_por_estrato: int = 5) -> tuple[pd.DataFrame, Injecao]:
    rng = np.random.default_rng(seed)
    partes = []
    for (gnd, el), med in ESTRATOS.items():
        for ex in EXERCICIOS:
            partes.append(pd.DataFrame({
                "exercicio": ex, "gnd": gnd, "elemento": el, "modalidade_aplicacao": "90",
                "valor_empenhado": np.round(rng.lognormal(np.log(med), 1.6, n_por_estrato), 2),
            }))
    base = pd.concat(partes, ignore_index=True)
    inj = Injecao()

    # meses: uniforme, com peso maior no mês injetado
    pesos = np.ones(12)
    pesos[inj.mes - 1] = 4.0
    meses = rng.choice(np.arange(1, 13), size=len(base), p=pesos / pesos.sum())
    dias = rng.integers(1, 29, size=len(base))
    base["data_emissao"] = pd.to_datetime(dict(year=base["exercicio"], month=meses, day=dias))

    # excesso controlado no dígito 7 (substitui valores, preservando a ordem de grandeza)
    idx_dig = rng.choice(base.index, size=int(excesso_digito * len(base)), replace=False)
    mag = 10.0 ** np.floor(np.log10(base.loc[idx_dig, "valor_empenhado"].clip(lower=1)))
    base.loc[idx_dig, "valor_empenhado"] = np.round(mag * rng.uniform(7.0, 7.99, len(idx_dig)), 2)

    # extremos: m por estrato, multiplicando por 10^4 (exclui linhas do excesso de dígito)
    livres = base.index.difference(idx_dig)
    for (_, el, _), g in base.loc[livres].groupby(["gnd", "elemento", "exercicio"]):
        if not extremos_por_estrato:
            break
        if el == "14":  # diárias pertencem à trilha de pagamentos a pessoas (avaliada em T9)
            continue
        sel = rng.choice(g.index, size=extremos_por_estrato, replace=False)
        base.loc[sel, "valor_empenhado"] = np.round(base.loc[sel, "valor_empenhado"] * 1e4, 2)
        inj.extremos.extend(int(i) for i in sel)

    base["favorecido"] = [f"FAVORECIDO {i:04d}" for i in rng.integers(0, 1500, len(base))]
    base["unidade"] = rng.choice(["10001", "10002", "10003"], size=len(base))

    # registros especiais (positivos), acrescentados ao fim
    def extra(n, gnd, el, mod, ano_desloc=0, sigma=1.0):
        ex = rng.choice(EXERCICIOS, n)
        return pd.DataFrame({
            "exercicio": ex, "gnd": gnd, "elemento": el, "modalidade_aplicacao": mod,
            "valor_empenhado": np.round(rng.lognormal(np.log(5000), sigma, n), 2),
            "data_emissao": pd.to_datetime(dict(year=ex + ano_desloc, month=rng.integers(1, 13, n), day=10)),
            "favorecido": [f"FAVORECIDO {i:04d}" for i in rng.integers(0, 1500, n)],
            "unidade": rng.choice(["10001", "10002"], size=n),
        })
    n_gnd1, n_el91, n_transf, n_rap = 300, 50, 250, 200
    # T8: pico em uma rubrica de pessoal (40 linhas adicionais em um exercício)
    el8, ex8 = inj.t8_rubrica_exercicio
    pico = extra(40, 1, el8, "90").assign(exercicio=ex8, valor_empenhado=50000.0,
                                          data_emissao=pd.Timestamp(ex8, 1, 15))
    # T9: 5 pessoas com acúmulo de diárias (60 linhas cada) em um exercício
    inj.t9_pessoas = [f"PESSOA INJETADA {k}" for k in range(5)]
    acum = pd.concat([extra(60, 3, "14", "90").assign(exercicio=2021, favorecido=nome,
                                                       valor_empenhado=np.round(rng.lognormal(np.log(8000), 0.3, 60), 2),
                                                       data_emissao=pd.Timestamp(2021, 6, 10))
                      for nome in inj.t9_pessoas])
    n_extra = n_gnd1 + len(pico) + len(acum) + n_el91 + n_transf + n_rap
    base = pd.concat([base, extra(n_gnd1, 1, "11", "90", sigma=0.3), pico, acum, extra(n_el91, 3, "91", "90"),
                      extra(n_transf, 3, "41", "40"), extra(n_rap, 3, "39", "90", ano_desloc=-1)], ignore_index=True)
    idx_rap = base.index[-n_rap:]

    # números de empenho: únicos, exceto um bloco que repete números já usados (mesmo empenho em várias linhas)
    base["numero_empenho"] = [f"{ex}NE{i:06d}" for i, ex in enumerate(base["exercicio"])]
    especiais = set(idx_rap) | set(inj.extremos) | set(base.index[-n_extra:])
    cand = np.array([i for i in base.index if i not in especiais])
    k = min(1000, len(cand) // 10)
    rep = rng.choice(cand, size=k, replace=False)
    origem = rng.choice(np.setdiff1d(cand, rep), size=k, replace=False)
    base.loc[rep, "numero_empenho"] = base.loc[origem, "numero_empenho"].to_numpy()
    resto = np.setdiff1d(cand, np.concatenate([rep, origem]))
    sem_num = rng.choice(resto, size=100, replace=False)
    base.loc[sem_num, "numero_empenho"] = pd.NA

    # qualidade: datas inválidas, zeros e negativos em linhas comuns (disjuntas)
    resto = np.setdiff1d(resto, sem_num)
    pool = rng.permutation(resto)
    datas_inv, zeros, negs = pool[:120], pool[120:270], pool[270:360]
    base.loc[datas_inv, "data_emissao"] = pd.NaT
    base.loc[zeros, "valor_empenhado"] = 0.0
    base.loc[negs, "valor_empenhado"] = -np.abs(base.loc[negs, "valor_empenhado"])

    # duplicação integral de 60 linhas comuns
    dup_orig = pool[360:420]
    copias = base.loc[dup_orig].copy()
    base = pd.concat([base, copias], ignore_index=True)
    inj.duplicadas = list(range(len(base) - len(copias), len(base)))

    n = len(base)
    v = base["valor_empenhado"]
    inj.esperado = {
        "linhas": n,
        "linhas_sem_numero": 100,
        "linhas_data_valida": n - 120,
        "linhas_valor_zero": 150,
        "linhas_valor_negativo": 90,
        "linhas_rap": n_rap,
        "trilha_pessoal": n_gnd1 + len(pico),
        "trilha_outras": n_el91,
        "trilha_transferencias": n_transf,
        "trilha_pessoas": int(((v > 0) & (base["elemento"] == "14")).sum()),
        "linhas_repetidas": 2 * len(copias),
        "grupos_repetidos": len(copias),
        "u_positivos": int((v > 0).sum()),
    }
    base = base[["exercicio", "numero_empenho", "data_emissao", "valor_empenhado", "gnd", "elemento",
                 "modalidade_aplicacao", "favorecido", "unidade"]]
    return base, inj


# ---------- formatos de origem ----------

def _moeda_ptbr(x: float) -> str:
    return f"{x:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


def gravar_csv_generico(base: pd.DataFrame, caminho: Path) -> None:
    out = base.copy()
    out["valor_empenhado"] = out["valor_empenhado"].map(_moeda_ptbr)
    out["data_emissao"] = out["data_emissao"].dt.strftime("%d/%m/%Y").fillna("")
    out["numero_empenho"] = out["numero_empenho"].fillna("")
    out["elemento"] = out["elemento"].map(lambda e: f"{e} - {DESC_EL[e]}")
    out.to_csv(caminho, sep=";", index=False, encoding="utf-8")


def gravar_excel_siga(base: pd.DataFrame, caminho: Path) -> None:
    """Mesma base no leiaute do SIGA Brasil: linhas de título, rótulos 'cód - descrição', subelemento de 8 dígitos."""
    out = pd.DataFrame({
        "Empenhado": base["valor_empenhado"],
        "Empenho": base["numero_empenho"].fillna("NÃO APLICÁVEL"),
        "Data Emissão Empenho": base["data_emissao"],
        "Favorecido": base["favorecido"],
        "GND (Cod/Abrev)": base["gnd"].map(lambda g: f"{g}-{ABREV_GND[g]}"),
        "Elemento Despesa (Cod/Desc)": base["elemento"].map(lambda e: f"{e} - {DESC_EL[e]}"),
        "Sub-elemento Despesa (Cod/Desc)": [
            f"{3 if g in (1, 3) else 4}{g}{m}{e}01 - SUBELEMENTO" for g, m, e in
            zip(base["gnd"], base["modalidade_aplicacao"], base["elemento"], strict=True)],
        "Ano": base["exercicio"].astype(str),
        "UO (Cod/Desc)": base["unidade"].map(lambda u: f"{u} - UNIDADE {u}"),
    })
    with pd.ExcelWriter(caminho, engine="openpyxl") as xw:
        pd.DataFrame([["Relatório sintético"], [None]]).to_excel(xw, sheet_name="Relatorio", index=False, header=False)
        out.to_excel(xw, sheet_name="Relatorio", index=False, startrow=3)


PERFIL_GENERICO = {
    "nome": "generico_teste", "leitura": {"separador": ";", "encoding": "utf-8"},
    "colunas": {c: c for c in ["exercicio", "numero_empenho", "data_emissao", "valor_empenhado", "gnd",
                               "elemento", "modalidade_aplicacao", "favorecido", "unidade"]},
}

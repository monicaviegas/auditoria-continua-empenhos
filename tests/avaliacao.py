"""Avaliação técnica artificial (DSR/FEDS): procedimentos sobre base sintética de resultado conhecido.

Observação obrigatória: avaliação artificial; não estima desempenho em dados reais.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from protocolo_ac.config import carregar_params
from protocolo_ac.t1_qualidade import cobertura
from protocolo_ac.t2_preparo import preparar
from protocolo_ac.t3_triagem import triagem
from protocolo_ac.t4_benford import benford
from protocolo_ac.t5_temporal import temporal
from protocolo_ac.t6_repeticoes import repeticoes
from protocolo_ac.t8_pessoal import pessoal
from protocolo_ac.t9_pessoas import pessoas
from sintetico import gerar


def _prec_rec(preditos: set, verdadeiros: set) -> tuple[float, float, int, int]:
    vp = len(preditos & verdadeiros)
    prec = vp / len(preditos) if preditos else 0.0
    rec = vp / len(verdadeiros) if verdadeiros else 0.0
    return prec, rec, vp, len(preditos - verdadeiros)


def avaliar(seed: int = 20261107) -> dict:
    params = carregar_params()
    t0 = time.perf_counter()
    base, inj = gerar(seed=seed)
    esp = inj.esperado
    _, t1 = cobertura(base)
    d, excl = preparar(base, params)
    trilha = d.loc[d["u_positivos"], "trilha"].value_counts()

    conferencias = {
        "linhas": (t1["linhas"], esp["linhas"]),
        "linhas_sem_numero": (t1["linhas_sem_numero"], esp["linhas_sem_numero"]),
        "linhas_data_valida": (t1["linhas_data_valida"], esp["linhas_data_valida"]),
        "linhas_valor_zero": (t1["linhas_valor_zero"], esp["linhas_valor_zero"]),
        "linhas_valor_negativo": (t1["linhas_valor_negativo"], esp["linhas_valor_negativo"]),
        "u_positivos": (int(d["u_positivos"].sum()), esp["u_positivos"]),
        "linhas_rap": (int(d["flag_rap"].sum()), esp["linhas_rap"]),
        "trilha_pessoal": (int(trilha.get("pessoal", 0)), esp["trilha_pessoal"]),
        "trilha_pessoas": (int(trilha.get("pagamentos a pessoas físicas", 0)), esp["trilha_pessoas"]),
        "trilha_transferencias": (int(trilha.get("transferências", 0)), esp["trilha_transferencias"]),
        "trilha_outras": (int(trilha.get("outras despesas (dívida, sentenças, tributos, subsídios)", 0)), esp["trilha_outras"]),
    }
    t3 = triagem(d, params)
    sup = set(t3["sinalizadas"].index[t3["sinalizadas"]["cauda"] == "superior"])
    extremos = {i for i in inj.extremos if d.loc[i, "u_triagem"]}
    p3, r3, vp3, fp3 = _prec_rec(sup, extremos)

    b_com = benford(d.loc[d["u_positivos"], "valor_empenhado"], params["t4"]["valor_minimo"])
    base_sem, _ = gerar(seed=seed, excesso_digito=0.0)
    d_sem, _ = preparar(base_sem, params)
    b_sem = benford(d_sem.loc[d_sem["u_positivos"], "valor_empenhado"], params["t4"]["valor_minimo"])

    # T5: base sem extremos, para que o mês com mais registros não seja mascarado por poucos valores muito altos
    base_t5, _ = gerar(seed=seed, extremos_por_estrato=0)
    d_t5, _ = preparar(base_t5, params)
    t5 = temporal(d_t5)
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
             "setembro", "outubro", "novembro", "dezembro"]

    t6 = repeticoes(base, base)
    rep = set(np.flatnonzero(t6["mascara"].to_numpy()))
    dup_verdadeiras = set(inj.duplicadas)
    # cada cópia tem um original idêntico: as linhas verdadeiras em grupos são as cópias + seus originais
    orig = base.iloc[inj.duplicadas]
    chave = pd.util.hash_pandas_object(base.astype("string").fillna("<NA>"), index=False)
    dup_verdadeiras |= set(np.flatnonzero(chave.isin(pd.util.hash_pandas_object(orig.astype("string").fillna("<NA>"), index=False)).to_numpy()))
    p6, r6, _, _ = _prec_rec(rep, dup_verdadeiras)

    t8 = pessoal(d, params)
    s8 = t8["sinalizadas"]
    s8 = {(r.elemento, int(r.exercicio)) for r in s8[s8["sinal"] == "acima"].itertuples()}
    p8, r8, _, fp8 = _prec_rec(s8, {inj.t8_rubrica_exercicio})
    t9 = pessoas(d, params)
    s9 = set(t9["sinalizadas"]["favorecido"])
    p9, r9, vp9, fp9 = _prec_rec(s9, set(inj.t9_pessoas))

    return {
        "observacao": "avaliação artificial; não estima desempenho em dados reais",
        "semente": seed,
        "n_linhas": int(len(base)),
        "conferencias": {k: {"obtido": int(a), "esperado": int(b), "ok": int(a) == int(b)} for k, (a, b) in conferencias.items()},
        "t3": {"injetados": len(extremos), "sinalizados_superior": len(sup), "verdadeiros_positivos": vp3,
               "falsos_positivos": fp3, "precisao": p3, "recall": r3},
        "t4": {"digito_injetado": inj.digito, "digito_detectado": b_com["digito_maior_z"],
               "z_detectado": b_com["z_maximo"], "dam_sem_excesso": b_sem["dam"], "classe_sem_excesso": b_sem["classe"],
               "dam_com_excesso": b_com["dam"], "classe_com_excesso": b_com["classe"]},
        "t5": {"mes_injetado": meses[inj.mes - 1], "mes_detectado": t5["resumo"]["mes_maior_valor"]},
        "t6": {"linhas_injetadas": len(dup_verdadeiras), "linhas_detectadas": len(rep), "precisao": p6, "recall": r6,
               "grupos_esperados": esp["grupos_repetidos"], "grupos_detectados": t6["grupos_repetidos"]},
        "t8": {"injetados": 1, "sinalizados": len(s8), "precisao": p8, "recall": r8, "falsos_positivos": fp8},
        "t9": {"injetados": len(inj.t9_pessoas), "sinalizados": len(s9), "verdadeiros_positivos": vp9,
               "falsos_positivos": fp9, "precisao": p9, "recall": r9},
        "tempo_s": time.perf_counter() - t0,
    }

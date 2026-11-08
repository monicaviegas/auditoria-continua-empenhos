"""T6 – Repetições. Universo: U_total. Unidade: linhas e grupos de repetição."""
from __future__ import annotations

import pandas as pd


def repeticoes(bruto: pd.DataFrame, can: pd.DataFrame) -> dict:
    """(a) linhas idênticas em todas as colunas da origem; (b) repetição por chave de documento, se houver."""
    chaves = pd.util.hash_pandas_object(bruto.astype("string").fillna("<NA>"), index=False)
    tam = chaves.map(chaves.value_counts())
    em_grupo = tam > 1
    grupos = chaves[em_grupo].nunique()
    dist = tam[em_grupo].groupby(chaves[em_grupo]).first().value_counts().sort_index()
    res = {
        "linhas_repetidas": int(em_grupo.sum()),
        "grupos_repetidos": int(grupos),
        "linhas_excedentes": int(em_grupo.sum() - grupos),
        "distribuicao_tamanho": pd.DataFrame({"tamanho_grupo": dist.index, "grupos": dist.values}),
        "mascara": em_grupo,
    }
    chave = ["numero_documento", "numero_empenho", "valor_empenhado", "data_emissao"]
    if all(c in can and can[c].notna().any() for c in chave):
        dup = can.duplicated(chave, keep=False) & can["numero_documento"].notna()
        res["chave"] = {"executado": True, "linhas": int(dup.sum()),
                        "grupos": int(can.loc[dup, chave].drop_duplicates().shape[0])}
    else:
        falt = [c for c in chave if c not in can or not can[c].notna().any()]
        res["chave"] = {"executado": False, "motivo": f"campo {', '.join(falt)} ausente"}
    return res

"""T4 – Lei de Benford (1º dígito). Universos: U_positivos (linhas) e U_distinto (empenhos distintos)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

ESPERADA = np.log10(1 + 1 / np.arange(1, 10))
FAIXAS_NIGRINI = [(0.006, "conformidade estreita"), (0.012, "conformidade aceitável"),
                  (0.015, "conformidade marginalmente aceitável")]


def primeiro_digito(x: pd.Series | np.ndarray) -> np.ndarray:
    """1º dígito significativo por magnitude (nunca pelo 1º caractere do texto)."""
    x = np.asarray(x, dtype=float)
    out = np.full(x.shape, -1, dtype=int)
    ok = np.isfinite(x) & (x > 0)
    e = np.floor(np.log10(x[ok]))
    d = np.floor(x[ok] / 10.0 ** e).astype(int)
    d = np.clip(d, 1, 9)  # protege contra erro de ponto flutuante (ex.: 9,9999 -> 10)
    out[ok] = d
    return out


def classe_nigrini(dam: float) -> str:
    for lim, nome in FAIXAS_NIGRINI:
        if dam <= lim:
            return nome
    return "não conformidade"


def benford(valores: pd.Series, valor_minimo: float) -> dict:
    v = valores[valores >= valor_minimo].astype(float)
    d = primeiro_digito(v.to_numpy())
    n = len(d)
    cont = np.bincount(d, minlength=10)[1:10]
    obs = cont / n if n else np.zeros(9)
    dam = float(np.mean(np.abs(obs - ESPERADA))) if n else float("nan")
    z = (np.abs(obs - ESPERADA) - 1 / (2 * n)) / np.sqrt(ESPERADA * (1 - ESPERADA) / n) if n else np.zeros(9)
    z = np.maximum(z, 0)
    chi2, pval = stats.chisquare(cont, ESPERADA * n) if n else (np.nan, np.nan)
    freq = pd.DataFrame({"digito": range(1, 10), "contagem": cont, "observada": obs,
                         "esperada": ESPERADA, "diferenca": obs - ESPERADA, "z": z})
    dig = int(freq.loc[freq["z"].idxmax(), "digito"]) if n else 0
    return {"n": n, "frequencias": freq, "dam": dam, "classe": classe_nigrini(dam), "chi2": float(chi2),
            "p_valor": float(pval), "digito_maior_z": dig, "z_maximo": float(freq["z"].max()) if n else 0.0,
            "valores": v, "digitos": d}


def valores_digito(res: dict, k: int = 20) -> pd.DataFrame:
    """Os k valores mais frequentes iniciados pelo dígito de maior |z| (apenas valores, sem favorecidos)."""
    v = res["valores"][res["digitos"] == res["digito_maior_z"]].round(2)
    vc = v.value_counts().head(k)
    tot = len(res["valores"])
    return pd.DataFrame({"valor": vc.index, "linhas": vc.values, "pct_do_total": vc.values / tot})

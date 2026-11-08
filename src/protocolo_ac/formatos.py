"""Formatação pt-BR e tabelas Markdown para o capítulo."""
from __future__ import annotations

import math

import pandas as pd

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


def _troca(s: str) -> str:
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def inteiro(x) -> str:
    return _troca(f"{int(round(x)):,}")


def decimal(x, casas: int = 2) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return _troca(f"{x:,.{casas}f}")


def pct(x, casas: int = 2) -> str:
    return decimal(100 * x, casas) + "%"


def moeda(x) -> str:
    return "R$ " + decimal(x, 2)


def milhoes(x) -> str:
    return decimal(x / 1e6, 1)


def tabela_md(df: pd.DataFrame, alinhar_direita: list[str] | None = None) -> str:
    cols = list(df.columns)
    alinhar_direita = alinhar_direita or []
    cab = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join("---:" if c in alinhar_direita else "---" for c in cols) + "|"
    linhas = ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([cab, sep, *linhas])

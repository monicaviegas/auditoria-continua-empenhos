"""Matriz de procedimentos por trilha: questão, critério, informações requeridas, verificação e possíveis achados."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

MATRIZ_PADRAO = Path(__file__).resolve().parents[2] / "config" / "matriz_procedimentos.yaml"


def carregar_matriz(caminho: Path = MATRIZ_PADRAO) -> pd.DataFrame:
    if not Path(caminho).exists():
        return pd.DataFrame(columns=["trilha", "procedimento", "questao", "criterio", "informacoes", "verificacao", "achados"])
    return pd.DataFrame(yaml.safe_load(Path(caminho).read_text(encoding="utf-8")))


def tabela_matriz(m: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Trilha e procedimento": m["trilha"] + " – " + m["procedimento"], "Questão de auditoria": m["questao"],
        "Critério": m["criterio"], "Informações requeridas": m["informacoes"],
        "Procedimento de verificação": m["verificacao"], "Possíveis achados": m["achados"]})

"""Carrega e valida parâmetros, perfil de entrada e metadados do caso."""
from __future__ import annotations

from pathlib import Path

import yaml

from .canonico import CAMPOS


def carregar_yaml(caminho: str | Path) -> dict:
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def carregar_params(caminho: str | Path = "config/params.yaml") -> dict:
    p = carregar_yaml(caminho)
    for sec in ("t2", "t3", "t4", "t7", "t8", "t9"):
        if sec not in p:
            raise ValueError(f"params.yaml sem a seção {sec}")
    for k in ("elementos_nao_fornecedor", "elementos_pessoal_odc", "elementos_pagamento_pessoa", "modalidades_incluidas",
              "elementos_transferencia_fallback", "elementos_excluidos_pessoal"):
        p["t2"][k] = [str(e).zfill(2) for e in p["t2"].get(k, [])]
    return p


def carregar_perfil(caminho: str | Path) -> dict:
    p = carregar_yaml(caminho)
    desconhecidos = set(p.get("colunas", {})) - set(CAMPOS)
    if desconhecidos:
        raise ValueError(f"Perfil com campos não canônicos: {sorted(desconhecidos)}")
    for nome in (p.get("derivacoes") or {}):
        if nome not in CAMPOS:
            raise ValueError(f"Derivação para campo não canônico: {nome}")
    return p


def carregar_caso(caminho: str | Path | None) -> dict:
    if caminho is None or not Path(caminho).exists():
        return {}
    return carregar_yaml(caminho)

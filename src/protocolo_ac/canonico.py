"""Modelo canônico de campos (Quadro 3 do Cap. 4) e requisitos por procedimento.

Fonte única de verdade: T0 usa estes dicionários para gerar a executabilidade.
"""
from __future__ import annotations

CAMPOS: dict[str, dict] = {
    "exercicio": {"tipo": "int", "descricao": "Ano de referência da linha"},
    "numero_empenho": {"tipo": "str", "descricao": "Identificador da nota de empenho"},
    "data_emissao": {"tipo": "date", "descricao": "Data de emissão do empenho"},
    "valor_empenhado": {"tipo": "decimal", "descricao": "Valor empenhado na linha"},
    "gnd": {"tipo": "int", "descricao": "Grupo de Natureza da Despesa (1–6)"},
    "elemento": {"tipo": "str", "descricao": "Elemento de despesa (2 dígitos)"},
    "modalidade_aplicacao": {"tipo": "str", "descricao": "Modalidade de aplicação (2 dígitos)"},
    "modalidade_empenho": {"tipo": "str", "descricao": "Ordinário, estimativo, global"},
    "favorecido": {"tipo": "str", "descricao": "Nome do destinatário"},
    "id_favorecido": {"tipo": "str", "descricao": "CNPJ/CPF/código do destinatário"},
    "numero_documento": {"tipo": "str", "descricao": "Identificador do documento/movimento"},
    "unidade": {"tipo": "str", "descricao": "Órgão/UO/UG"},
    "valor_liquidado": {"tipo": "decimal", "descricao": "Valor liquidado"},
    "valor_pago": {"tipo": "decimal", "descricao": "Valor pago"},
}

CAMPOS_MONETARIOS = ["valor_empenhado", "valor_liquidado", "valor_pago"]

# Procedimento -> (descrição, campos obrigatórios)
REQUISITOS: dict[str, tuple[str, list[str]]] = {
    "T0": ("Perfil e mapeamento", []),
    "T1": ("Qualidade e cobertura", ["exercicio", "numero_empenho", "data_emissao", "valor_empenhado"]),
    "T2": ("Preparação e universos", ["exercicio", "valor_empenhado"]),
    "T2_trilhas": ("Recorte da base em trilhas", ["valor_empenhado", "gnd", "elemento"]),
    "T2_distinto": ("Universo de empenhos distintos (U_distinto)", ["numero_empenho", "valor_empenhado"]),
    "T3": ("Fornecedores: triagem robusta de valores", ["valor_empenhado", "gnd", "elemento", "exercicio"]),
    "T4": ("Lei de Benford", ["valor_empenhado"]),
    "T5": ("Distribuição temporal", ["data_emissao", "exercicio", "valor_empenhado"]),
    "T5_modalidade": ("Composição por modalidade de empenho", ["modalidade_empenho"]),
    "T6": ("Repetições integrais", []),
    "T6_chave": ("Repetição por chave de documento", ["numero_documento", "numero_empenho", "valor_empenhado", "data_emissao"]),
    "T7": ("Fornecedores: concentração por favorecido", ["favorecido", "valor_empenhado", "gnd", "elemento"]),
    "T7_tipo": ("Fornecedores: tipo de favorecido e HHI", ["id_favorecido"]),
    "T8": ("Pessoal: variação por rubrica", ["valor_empenhado", "gnd", "elemento", "exercicio"]),
    "T8_individual": ("Pessoal: pagamentos por servidor", ["id_favorecido"]),
    "T9": ("Pagamentos a pessoas: acumulado por favorecido", ["favorecido", "valor_empenhado", "elemento", "exercicio"]),
}


def faltantes(procedimento: str, presentes: set[str]) -> list[str]:
    """Campos obrigatórios ausentes para um procedimento."""
    return [c for c in REQUISITOS[procedimento][1] if c not in presentes]


def executavel(procedimento: str, presentes: set[str]) -> bool:
    return not faltantes(procedimento, presentes)

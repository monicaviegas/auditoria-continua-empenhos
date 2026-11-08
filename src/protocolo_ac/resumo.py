"""Resumo legível de uma execução, usado pelas interfaces (desktop e painel). Sem nomes de favorecidos."""
from __future__ import annotations

import json
from pathlib import Path

NOME_PRODUTO = "Auditoria Contínua de Empenhos por Trilhas"


def carregar_numeros(run: Path) -> dict:
    return json.loads((Path(run) / "numeros_capitulos.json").read_text(encoding="utf-8"))


def linhas_resumo(run: Path) -> list[str]:
    """Texto curto: o que a base permite, o recorte em trilhas e o que examinar primeiro em cada trilha."""
    n = carregar_numeros(run)
    t0, t1, t2, t3, t7, t8, t9 = (n.get(k, {}) for k in ("t0", "t1", "t2", "t3", "t7", "t8", "t9"))
    s = [
        f"Base: {t1.get('linhas', '–')} linhas; {t1.get('empenhos_distintos', '–')} empenhos distintos.",
        f"Procedimentos executáveis: {t0.get('procedimentos_executaveis', '–')} de {t0.get('procedimentos_total', '–')} "
        "(ver aba T0_executabilidade).",
        "",
        "Recorte das linhas positivas em trilhas (linhas | valor):",
    ]
    for chave, nome in (("fornecedores", "Fornecedores"), ("pessoal", "Pessoal"), ("pessoas", "Pagamentos a pessoas"),
                        ("transferencias", "Transferências"), ("outras", "Outras despesas")):
        if f"{chave}_linhas" in t2:
            s.append(f"  {nome}: {t2[f'{chave}_linhas']} | {t2[f'{chave}_pct_valor']} do valor")
    s += [
        "",
        "O que examinar primeiro:",
        f"  Fornecedores (T3): {t3.get('sinalizadas_superior', '–')} empenhos com valor atípico no estrato "
        f"({t3.get('taxa_sinalizacao_superior', '–')}) – aba T3_sinalizadas.",
        f"  Fornecedores (T7): {t7.get('part_topn', '–')} do valor nos maiores fornecedores – abas T7_favorecidos e T7_por_elemento.",
        f"  Pessoal (T8): {t8.get('sinalizadas_acima', '–')} rubricas-exercício acima do padrão – aba T8_rubricas.",
        f"  Pagamentos a pessoas (T9): {t9.get('sinalizados', '–')} beneficiários com acúmulo atípico – aba T9_sinalizados.",
        "",
        "Sinais servem para priorizar exames; não comprovam irregularidade.",
        f"Resultados em: {Path(run).resolve()}",
    ]
    return s

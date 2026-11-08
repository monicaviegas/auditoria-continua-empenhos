"""Substitui os marcadores do modelo-mestre pelos valores de uma execução.

Marcadores: {{chave.sub}} (numeros_capitulos.json, caso.yaml, avaliacao_sintetica.json),
{{tabela:id}}, {{figura:id}}. {{texto_livre:id}} é mantido visível.
Falha se sobrar marcador sem valor.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PADRAO = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def _achatar(d: dict, prefixo: str = "") -> dict[str, str]:
    out = {}
    for k, v in d.items():
        chave = f"{prefixo}{k}"
        if isinstance(v, dict):
            out.update(_achatar(v, chave + "."))
        else:
            out[chave] = str(v)
    return out


def preencher(modelo: Path, run: Path, caso: dict, extras: dict | None = None, destino: Path | None = None) -> Path:
    numeros = json.loads((run / "numeros_capitulos.json").read_text(encoding="utf-8"))
    valores = _achatar(numeros)
    valores.update(_achatar({"caso": {k: v for k, v in caso.items() if not isinstance(v, (dict, list))}}))
    if extras:
        valores.update(_achatar(extras))
    texto = Path(modelo).read_text(encoding="utf-8")
    texto = re.sub(r"<!--.*?-->\n?", "", texto, flags=re.S)  # remove notas internas do modelo
    faltando: list[str] = []
    destino = destino or Path("docs/build") / (Path(modelo).stem + "_preenchido.md")
    destino.parent.mkdir(parents=True, exist_ok=True)

    def sub(m: re.Match) -> str:
        k = m.group(1)
        if k.startswith("texto_livre:"):
            return m.group(0)
        if k.startswith("tabela:"):
            p = run / "tabelas" / f"{k.split(':', 1)[1]}.md"
            if p.exists():
                return p.read_text(encoding="utf-8")
        elif k.startswith("figura:"):
            p = run / "figuras" / f"{k.split(':', 1)[1]}.png"
            if p.exists():
                return f"![]({p.resolve().as_posix()})"
        elif k in valores:
            return valores[k]
        faltando.append(k)
        return m.group(0)

    # duas passadas: valores podem conter marcadores (ex.: tabelas com {{param...}})
    for _ in range(2):
        faltando.clear()
        texto = PADRAO.sub(sub, texto)
    if faltando:
        raise KeyError(f"Marcadores sem valor: {sorted(set(faltando))}")
    destino.write_text(texto, encoding="utf-8")
    return destino

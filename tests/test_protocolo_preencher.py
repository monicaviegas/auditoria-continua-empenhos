"""O preenchimento substitui todos os marcadores e falha quando falta valor."""
import json

import pytest

from protocolo_ac.preencher import preencher


def _run(tmp_path):
    run = tmp_path / "run"
    (run / "tabelas").mkdir(parents=True)
    (run / "figuras").mkdir()
    (run / "numeros_capitulos.json").write_text(json.dumps({"t1": {"linhas_total": "1.234"}}), encoding="utf-8")
    (run / "tabelas" / "x.md").write_text("| a |\n|---|\n| 1 |", encoding="utf-8")
    return run


def test_preenche_numeros_tabelas_caso_e_mantem_texto_livre(tmp_path):
    run = _run(tmp_path)
    modelo = tmp_path / "m.md"
    modelo.write_text("<!-- nota -->\nTotal {{t1.linhas_total}} em {{caso.periodo}}.\n{{tabela:x}}\n{{texto_livre:a}}", encoding="utf-8")
    out = preencher(modelo, run, {"periodo": "2016–2025"}, destino=tmp_path / "o.md").read_text(encoding="utf-8")
    assert "1.234" in out and "2016–2025" in out and "| 1 |" in out and "{{texto_livre:a}}" in out and "nota" not in out


def test_falha_com_marcador_sem_valor(tmp_path):
    run = _run(tmp_path)
    modelo = tmp_path / "m.md"
    modelo.write_text("{{t9.inexistente}}", encoding="utf-8")
    with pytest.raises(KeyError, match="t9.inexistente"):
        preencher(modelo, run, {}, destino=tmp_path / "o.md")

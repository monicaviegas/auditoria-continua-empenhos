"""Teste de fumaça do painel: base de demonstração → execução → todas as guias renderizam sem erro."""
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

APP = str(Path(__file__).parents[1] / "app_streamlit.py")


def test_painel_executa_base_de_demonstracao():
    at = st_testing.AppTest.from_file(APP, default_timeout=300)
    at.run()
    assert not at.exception
    at.sidebar.radio[0].set_value("Base de demonstração (sintética)").run()
    botao = [b for b in at.sidebar.button if b.label == "Executar protocolo"][0]
    botao.click().run()
    assert not at.exception, at.exception
    assert len(at.tabs) == 7
    metricas = {m.label: m.value for m in at.metric}
    executaveis, total = (int(x) for x in metricas["Procedimentos executáveis"].split(" de "))
    assert 0 < executaveis <= total
    assert int(metricas["Empenhos sinalizados (T3)"].replace(".", "")) > 0
    assert int(metricas["Beneficiários sinalizados"].replace(".", "")) >= 5
    assert len([e for e in at.expander if e.label == "Procedimentos de verificação"]) == 4

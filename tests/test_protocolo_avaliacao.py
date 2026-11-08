"""Avaliação sintética, perfis de origem, executabilidade e reprodutibilidade (evidência do Cap. 5)."""
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from avaliacao import avaliar
from protocolo_ac.config import carregar_params, carregar_perfil
from protocolo_ac.pipeline import executar
from sintetico import PERFIL_GENERICO, gerar, gravar_csv_generico, gravar_excel_siga

RAIZ = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def resultado():
    return avaliar()


def test_conferencias_t1_t2_exatas(resultado):
    falhas = {k: v for k, v in resultado["conferencias"].items() if not v["ok"]}
    assert not falhas


def test_t3_recupera_extremos(resultado):
    assert resultado["t3"]["recall"] >= 0.95
    assert resultado["t3"]["precisao"] >= 0.9


def test_t4_identifica_digito(resultado):
    t4 = resultado["t4"]
    assert t4["digito_detectado"] == t4["digito_injetado"]
    assert t4["dam_com_excesso"] > t4["dam_sem_excesso"]


def test_t5_identifica_mes(resultado):
    assert resultado["t5"]["mes_detectado"] == resultado["t5"]["mes_injetado"]


def test_t6_repeticoes_exatas(resultado):
    t6 = resultado["t6"]
    assert t6["precisao"] == 1.0 and t6["recall"] == 1.0
    assert t6["grupos_detectados"] == t6["grupos_esperados"]


def test_t8_identifica_rubrica_com_pico(resultado):
    assert resultado["t8"]["recall"] == 1.0


def test_t9_identifica_pessoas_com_acumulo(resultado):
    assert resultado["t9"]["recall"] == 1.0 and resultado["t9"]["precisao"] >= 0.8


def _rodar(tmp: Path, entrada: Path, perfil: dict, nome: str) -> Path:
    return executar([entrada], perfil, carregar_params(), {}, tmp / nome, usar_cache=False)


def _numeros_sem_exec(run: Path) -> dict:
    n = json.loads((run / "numeros_capitulos.json").read_text(encoding="utf-8"))
    n.pop("exec")
    n["t0"] = {k: v for k, v in n["t0"].items() if not k.startswith(("modalidade_", "ausentes_declarados", "campos_mapeados"))}
    return n


@pytest.fixture(scope="module")
def execucoes(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("perfis")
    base, _ = gerar(n_por_estrato=300)
    csv, xlsx = tmp / "base.csv", tmp / "base.xlsx"
    gravar_csv_generico(base, csv)
    gravar_excel_siga(base, xlsx)
    siga = carregar_perfil(RAIZ / "config/perfis/siga_brasil.yaml")
    return {
        "csv": _rodar(tmp, csv, PERFIL_GENERICO, "a"),
        "csv_2": _rodar(tmp, csv, PERFIL_GENERICO, "b"),
        "xlsx": _rodar(tmp, xlsx, siga, "c"),
    }


def test_perfis_diferentes_mesmos_resultados(execucoes):
    assert _numeros_sem_exec(execucoes["csv"]) == _numeros_sem_exec(execucoes["xlsx"])


def test_reprodutibilidade(execucoes):
    def h(run):
        partes = [json.dumps(_numeros_sem_exec(run), sort_keys=True)]
        partes += [p.read_text(encoding="utf-8") for p in sorted((run / "tabelas").glob("*.md"))]
        partes.append((run / "log_exclusoes.csv").read_text(encoding="utf-8"))
        return hashlib.sha256("".join(partes).encode()).hexdigest()
    assert h(execucoes["csv"]) == h(execucoes["csv_2"])


def test_base_sem_gnd_elemento_nao_executa_t3(tmp_path):
    base, _ = gerar(n_por_estrato=100)
    base = base.drop(columns=["gnd", "elemento", "modalidade_aplicacao"])
    csv = tmp_path / "pobre.csv"
    base.assign(valor_empenhado=base["valor_empenhado"].map(lambda x: f"{x:.2f}".replace(".", ",")),
                data_emissao=base["data_emissao"].dt.strftime("%d/%m/%Y").fillna("")).to_csv(csv, sep=";", index=False)
    perfil = {"nome": "pobre", "leitura": {"separador": ";"},
              "colunas": {c: c for c in ["exercicio", "numero_empenho", "data_emissao", "valor_empenhado", "favorecido"]}}
    run = executar([csv], perfil, carregar_params(), {}, tmp_path / "o", usar_cache=False)
    n = json.loads((run / "numeros_capitulos.json").read_text(encoding="utf-8"))
    exe = (run / "tabelas" / "t0_executabilidade.md").read_text(encoding="utf-8")
    assert "| T3 | Fornecedores: triagem robusta de valores | não | gnd, elemento |" in exe
    assert n["t3"]["sinalizadas_superior"].startswith("não executado")
    assert n["t4"]["n_linhas"] != "0" and n["t5"]["mes_maior_valor"]


def test_nenhum_termo_conclusivo_nas_saidas(execucoes):
    proibidos = ("fraude", "fraudador", "suspeito", "irregular", "ilegal")
    for run in execucoes.values():
        for p in list((run / "tabelas").glob("*.md")) + [run / "numeros_capitulos.json"]:
            texto = p.read_text(encoding="utf-8").lower()
            assert not any(t in texto for t in proibidos), p


def test_params_yaml_coerente_com_tabela1():
    p = yaml.safe_load((RAIZ / "config/params.yaml").read_text(encoding="utf-8"))
    assert p["t3"]["limiar"] == 3.5 and p["t3"]["min_grupo"] == 30 and p["t4"]["valor_minimo"] == 10

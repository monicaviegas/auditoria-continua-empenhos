"""Casos unitários dos procedimentos."""
import numpy as np
import pandas as pd

from protocolo_ac.canonico import executavel
from protocolo_ac.config import carregar_params
from protocolo_ac.formatos import decimal, inteiro, pct
from protocolo_ac.t0_perfil import aplicar_perfil
from protocolo_ac.t3_triagem import triagem
from protocolo_ac.t4_benford import benford, classe_nigrini, primeiro_digito
from protocolo_ac.t7_favorecidos import mascarar_cpf, tipo_favorecido


def test_primeiro_digito_por_magnitude():
    assert list(primeiro_digito([0.0042, 4200, 4.2, 9.99, 1, 10, 0, -5])) == [4, 4, 4, 9, 1, 1, -1, -1]


def test_normalizacoes_gnd_elemento_moeda_data():
    bruto = pd.DataFrame({"G": ["3 - OUTRAS DESPESAS CORRENTES", "4-INV"], "E": ["39 - OUTROS SERVIÇOS", "5 - X"],
                          "V": ["1.234,56", "10,00"], "D": ["31/01/2024", "99/99/9999"], "A": ["2024", "2024"]})
    perfil = {"colunas": {"gnd": "G", "elemento": "E", "valor_empenhado": "V", "data_emissao": "D", "exercicio": "A"}}
    can, diag = aplicar_perfil(bruto, perfil)
    assert can["gnd"].tolist() == [3, 4]
    assert can["elemento"].tolist() == ["39", "05"]
    assert can["valor_empenhado"].tolist() == [1234.56, 10.0]
    assert can["data_emissao"].iloc[0] == pd.Timestamp(2024, 1, 31) and pd.isna(can["data_emissao"].iloc[1])
    assert diag["falhas_conversao"]["data_emissao"] == 1


def test_valores_ausentes_declarados_no_perfil():
    bruto = pd.DataFrame({"N": ["2024NE1", "NÃO APLICÁVEL"], "V": [1.0, 0.0]})
    can, diag = aplicar_perfil(bruto, {"colunas": {"numero_empenho": "N", "valor_empenhado": "V"},
                                       "valores_ausentes": ["NÃO APLICÁVEL"]})
    assert can["numero_empenho"].isna().tolist() == [False, True]
    assert diag["valores_ausentes_declarados"]["numero_empenho"] == 1


def test_derivacao_modalidade_e_conferencia():
    bruto = pd.DataFrame({"G": ["4-INV"], "E": ["42 - AUXILIOS"], "S": ["44404229 - A MUNICIPIOS"]})
    perfil = {"colunas": {"gnd": "G", "elemento": "E"},
              "derivacoes": {"modalidade_aplicacao": {"coluna": "S", "inicio": 2, "fim": 4,
                                                      "conferir": {"gnd": [1, 2], "elemento": [4, 6]}}}}
    can, diag = aplicar_perfil(bruto, perfil)
    assert can["modalidade_aplicacao"].iloc[0] == "40"
    assert all(c["divergentes"] == 0 for c in diag["derivacoes"]["modalidade_aplicacao"]["conferencia"].values())


def test_mad_zero_cai_para_iqr():
    params = carregar_params()
    v = [100.0] * 20 + [200.0] * 15 + [10_000_000.0]
    d = pd.DataFrame({"gnd": 3, "elemento": "30", "exercicio": 2024, "valor_empenhado": v, "u_triagem": True})
    res = triagem(d, params)
    assert res["estratos"]["metodo_escala"].iloc[0] == "IQR"
    assert res["resumo"]["sinalizadas_superior"] == 1


def test_estrato_pequeno_nao_pontuado():
    params = carregar_params()
    d = pd.DataFrame({"gnd": 3, "elemento": "30", "exercicio": 2024, "valor_empenhado": np.arange(1, 11) * 10.0,
                      "u_triagem": True})
    res = triagem(d, params)
    assert res["resumo"]["linhas_elegiveis"] == 0 and res["resumo"]["sinalizadas_superior"] == 0


def test_benford_conforme_e_faixas():
    rng = np.random.default_rng(1)
    v = pd.Series(10 ** rng.uniform(1, 7, 200_000))
    r = benford(v, 10)
    assert r["dam"] < 0.006 and r["classe"] == "conformidade estreita"
    assert classe_nigrini(0.010) == "conformidade aceitável"
    assert classe_nigrini(0.014) == "conformidade marginalmente aceitável"
    assert classe_nigrini(0.020) == "não conformidade"


def test_tipo_favorecido_e_mascara_cpf():
    t = tipo_favorecido(pd.Series(["12.345.678/0001-90", "123.456.789-01", "170500", None]))
    assert t.tolist() == ["pessoa jurídica", "pessoa física", "órgão/código", "não classificado"]
    assert mascarar_cpf("123.456.789-01") == "***.456.789-**"


def test_executabilidade_sem_gnd_elemento():
    pres = {"exercicio", "numero_empenho", "data_emissao", "valor_empenhado", "favorecido"}
    assert not executavel("T3", pres) and not executavel("T7", pres) and not executavel("T8", pres)
    assert all(executavel(p, pres) for p in ("T1", "T4", "T5", "T6"))


def test_formatos_ptbr():
    assert inteiro(1234567) == "1.234.567"
    assert pct(0.12345) == "12,35%"
    assert decimal(0.00537, 4) == "0,0054"

"""Execução completa do protocolo T0–T7 e geração das saídas da execução."""
from __future__ import annotations

import hashlib
import json
import logging
import platform
import subprocess
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import __version__
from .canonico import executavel
from .formatos import MESES, decimal, inteiro, milhoes, moeda, pct, tabela_md
from .io import ler_entrada
from .t0_perfil import aplicar_perfil, campos_presentes, executabilidade, perfil_colunas
from .t1_qualidade import cobertura
from .t2_preparo import TRILHAS, filtrar_escopo, preparar, tabela_trilhas, tabela_universos, unidades_todo_periodo
from .t3_triagem import top_estratos, triagem
from .t4_benford import benford, valores_digito
from .t5_temporal import heatmap, temporal
from .t6_repeticoes import repeticoes
from .t7_favorecidos import favorecidos
from .t8_pessoal import pessoal
from .t9_pessoas import pessoas

log = logging.getLogger(__name__)


def _commit() -> str:
    try:
        c = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        sujo = subprocess.run(["git", "status", "--porcelain", "src", "config/params.yaml"], capture_output=True, text=True).stdout.strip()
        return c + ("-modificado" if sujo else "")
    except Exception:  # noqa: BLE001
        return "indisponível"


def _memoria_pico_mb() -> float | None:
    try:
        import psutil
        mi = psutil.Process().memory_info()
        return round(getattr(mi, "peak_wset", getattr(mi, "rss", 0)) / 2**20, 1)
    except Exception:  # noqa: BLE001
        return None


def _nucleo(d_can: pd.DataFrame, params: dict) -> dict:
    """T2–T5 e T7 sobre um escopo (usado no escopo principal e no de sensibilidade)."""
    pres = campos_presentes(d_can)
    d, excl = preparar(d_can, params)
    r: dict = {"d": d, "excl": excl}
    r["t3"] = triagem(d, params) if executavel("T3", pres) else None
    r["t4_linhas"] = benford(d.loc[d["u_positivos"], "valor_empenhado"], params["t4"]["valor_minimo"])
    r["t4_distintos"] = (benford(d.loc[d["u_distinto"], "valor_empenhado"], params["t4"]["valor_minimo"])
                         if executavel("T2_distinto", pres) else None)
    r["t5"] = temporal(d) if executavel("T5", pres) else None
    r["t7"] = favorecidos(d, params) if executavel("T7", pres) else None
    r["t8"] = pessoal(d, params) if executavel("T8", pres) else None
    r["t9"] = pessoas(d, params) if executavel("T9", pres) else None
    return r


def executar(entradas: list[Path], perfil: dict, params: dict, caso: dict, saida_base: Path = Path("outputs"),
             usar_cache: bool = True) -> Path:
    t0 = time.perf_counter()
    inicio = datetime.now()
    bruto, info = ler_entrada(entradas, perfil, usar_cache=usar_cache)
    t_leitura = time.perf_counter() - t0
    sha_conj = hashlib.sha256("".join(i["sha256"] for i in info).encode()).hexdigest()
    run = saida_base / f"run_{inicio:%Y%m%d-%H%M}_{sha_conj[:8]}"
    (run / "tabelas").mkdir(parents=True, exist_ok=True)
    (run / "figuras").mkdir(exist_ok=True)

    # T0
    perfil_cols = perfil_colunas(bruto)
    can, diag = aplicar_perfil(bruto, perfil)
    can, excl_escopo = filtrar_escopo(can, caso.get("escopo_unidades"))
    bruto = bruto.loc[can.index]
    pres = campos_presentes(can)
    exe = executabilidade(pres)

    # T1
    cob, t1 = cobertura(can)

    # T2–T5, T7 (escopo principal)
    nuc = _nucleo(can, params)
    d = nuc["d"]
    excl = pd.concat([pd.DataFrame(excl_escopo), nuc["excl"]], ignore_index=True)

    # T6
    t6 = repeticoes(bruto, can)

    # Sensibilidade: unidades presentes em todo o período
    unid = unidades_todo_periodo(can)
    sens = _nucleo(can[can["unidade"].isin(unid)], params) if unid else None
    t_total = time.perf_counter() - t0

    # ---------- números e tabelas ----------
    num, tab = _numeros_e_tabelas(bruto, can, d, diag, exe, cob, t1, nuc, t6, sens, unid, params, perfil)
    metadados = {
        "versao": __version__, "commit": _commit(), "python": platform.python_version(),
        "pandas": pd.__version__, "plataforma": platform.platform(),
        "entradas": [{"sha256": i["sha256"], "linhas": i["linhas"]} for i in info],
        "sha256_conjunto": sha_conj, "perfil": perfil.get("nome"), "parametros": params,
        "inicio": inicio.isoformat(timespec="seconds"), "fim": datetime.now().isoformat(timespec="seconds"),
        "tempo_total_s": round(t_total, 1), "tempo_leitura_s": round(t_leitura, 1),
        "memoria_pico_mb": _memoria_pico_mb(), "cache_parquet": usar_cache,
    }
    num["exec"] = {
        "versao": __version__, "commit": metadados["commit"], "python": metadados["python"],
        "sha256_curto": sha_conj[:12], "tempo": _tempo(t_total), "tempo_leitura": _tempo(t_leitura),
        "memoria_pico": (decimal(metadados["memoria_pico_mb"] / 1024, 1) + " GB") if metadados["memoria_pico_mb"] else "não medida",
        "n_arquivos": inteiro(len(info)),
    }
    for k, v in tab.items():
        (run / "tabelas" / f"{k}.md").write_text(v, encoding="utf-8")
    if nuc["t5"]:
        heatmap(nuc["t5"], run / "figuras" / "t5_heatmap_exercicio_mes.png")
    (run / "numeros_capitulos.json").write_text(json.dumps(num, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "metadados.json").write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")
    excl.to_csv(run / "log_exclusoes.csv", index=False, encoding="utf-8")
    from .matriz import carregar_matriz, tabela_matriz
    (run / "tabelas" / "matriz_procedimentos.md").write_text(tabela_md(tabela_matriz(carregar_matriz())), encoding="utf-8")

    from .relatorio import gravar_excel
    gravar_excel(run / "resultados_auditoria.xlsx", perfil_cols, exe, cob, tabela_universos(d), excl, nuc, t6, metadados, d)
    log.info("execução concluída em %s: %s", _tempo(t_total), run)
    return run


def _tempo(s: float) -> str:
    m, s = divmod(int(round(s)), 60)
    return f"{m} min {s} s" if m else f"{s} s"


def _rot_gnd(g) -> str:
    return {1: "1 Pessoal", 2: "2 Juros", 3: "3 ODC", 4: "4 Investimentos", 5: "5 Inversões", 6: "6 Amortização"}.get(int(g), str(g))


def _numeros_e_tabelas(bruto, can, d, diag, exe, cob, t1, nuc, t6, sens, unid, params, perfil):
    num: dict = {}
    tab: dict = {}
    nao_exec = lambda campos: f"não executado (campo {campos} ausente)"  # noqa: E731

    # descrições de elemento (rótulos genéricos da classificação orçamentária)
    col_el = perfil["colunas"].get("elemento")
    desc_el = {}
    if col_el in bruto:
        s = bruto[col_el].dropna().astype(str).drop_duplicates()
        for v in s:
            cod = v.split("-")[0].strip().zfill(2)
            desc_el.setdefault(cod, v.split("-", 1)[1].strip().capitalize() if "-" in v else v)

    num["t0"] = {"ausentes_declarados_empenho": inteiro(diag.get("valores_ausentes_declarados", {}).get("numero_empenho", 0)),
                 "ausentes_declarados_favorecido": inteiro(diag.get("valores_ausentes_declarados", {}).get("favorecido", 0)),
                 "colunas_total": inteiro(bruto.shape[1]), "campos_mapeados": inteiro(len(campos_presentes(can))),
                 "procedimentos_executaveis": inteiro((exe["executavel"] == "sim").sum()),
                 "procedimentos_total": inteiro(len(exe))}
    der = diag.get("derivacoes", {}).get("modalidade_aplicacao")
    if der:
        conf = der["conferencia"]
        num["t0"]["modalidade_derivada_linhas"] = inteiro(der["linhas_com_codigo"])
        num["t0"]["modalidade_divergencias"] = inteiro(sum(c["divergentes"] for c in conf.values()))
        num["t0"]["modalidade_comparadas"] = inteiro(max((c["comparadas"] for c in conf.values()), default=0))
    tab["t0_executabilidade"] = tabela_md(exe.rename(columns={
        "procedimento": "Procedimento", "descricao": "Descrição", "executavel": "Executável",
        "campos_faltantes": "Campos ausentes"}))

    num["t1"] = {k: inteiro(v) for k, v in t1.items()}
    c = cob.copy()
    tc = pd.DataFrame({
        "Exercício": c["exercicio"].astype(str), "Linhas": c["linhas"].map(inteiro),
        "Com nº": c["linhas_com_numero"].map(inteiro), "Nºs distintos": c["empenhos_distintos"].map(inteiro),
        "Data válida": c["linhas_data_valida"].map(inteiro), "Ano da data ≠ exercício": c["linhas_ano_divergente"].map(inteiro),
        "Valor > 0": c["linhas_valor_positivo"].map(inteiro), "Valor = 0": c["linhas_valor_zero"].map(inteiro),
        "Valor < 0": c["linhas_valor_negativo"].map(inteiro)})
    tab["t1_cobertura_exercicio"] = tabela_md(tc, list(tc.columns[1:]))
    num["t1"]["pct_linhas_positivas"] = pct(t1["linhas_valor_positivo"] / t1["linhas"])
    num["t1"]["pct_linhas_zero"] = pct(t1["linhas_valor_zero"] / t1["linhas"])
    num["t1"]["pct_ano_divergente"] = pct(t1["linhas_ano_divergente"] / t1["linhas"])
    num["t1"]["linhas_por_empenho"] = decimal(t1["linhas_com_numero"] / max(t1["empenhos_distintos"], 1), 2)
    num["t1"]["exercicio_mais_linhas"] = str(int(cob.iloc[:-1].sort_values("linhas").iloc[-1]["exercicio"]))
    num["t1"]["exercicio_menos_linhas"] = str(int(cob.iloc[:-1].sort_values("linhas").iloc[0]["exercicio"]))
    num["t1"]["linhas_max_exercicio"] = inteiro(cob.iloc[:-1]["linhas"].max())
    num["t1"]["linhas_min_exercicio"] = inteiro(cob.iloc[:-1]["linhas"].min())
    sem_num = d["numero_empenho"].isna()
    num["t1"]["zero_sem_numero"] = inteiro(((d["valor_empenhado"] == 0) & sem_num).sum())
    num["t1"]["zero_corrente_com_numero"] = inteiro(((d["valor_empenhado"] == 0) & ~sem_num & ~d["flag_rap"]).sum())
    num["t1"]["zero_e_rap"] = inteiro(((d["valor_empenhado"] == 0) & d["flag_rap"]).sum())
    num["t1"]["pct_zero_rap"] = pct(((d["valor_empenhado"] == 0) & d["flag_rap"]).sum() / max(t1["linhas_valor_zero"], 1))

    # T2
    upos = d["u_positivos"]
    vpos = d.loc[upos, "valor_empenhado"].sum()
    num["t2"] = {
        "u_positivos_linhas": inteiro(upos.sum()),
        "u_distinto_linhas": inteiro(d["u_distinto"].sum()),
        "u_triagem_linhas": inteiro(d["u_triagem"].sum()),
        "linhas_rap": inteiro(d["flag_rap"].sum()),
        "pct_rap": pct(d["flag_rap"].mean()),
        "linhas_rap_positivas": inteiro((d["flag_rap"] & upos).sum()),
    }
    chaves_trilha = {TRILHAS[5]: "fornecedores", TRILHAS[1]: "pessoal", TRILHAS[3]: "pessoas",
                     TRILHAS[2]: "transferencias", TRILHAS[4]: "outras", TRILHAS[0]: "sem_classificacao"}
    tt = tabela_trilhas(d) if d["trilha"].notna().any() else pd.DataFrame()
    for _, r in tt.iterrows():
        k = chaves_trilha.get(r["trilha"])
        if k:
            num["t2"][f"{k}_linhas"] = inteiro(r["linhas"])
            num["t2"][f"{k}_pct_linhas"] = pct(r["pct_linhas"])
            num["t2"][f"{k}_pct_valor"] = pct(r["pct_valor"])
            num["t2"][f"{k}_favorecidos"] = inteiro(r["favorecidos"])
    tu = tabela_universos(d)
    tu2 = pd.DataFrame({"Universo": tu["universo"], "Definição": tu["definicao"], "Linhas": tu["linhas"].map(inteiro),
                        "Valor empenhado (R$ milhões)": tu["valor_empenhado"].map(milhoes)})
    tab["t2_universos"] = tabela_md(tu2, ["Linhas", "Valor empenhado (R$ milhões)"])
    if len(tt):
        uso = {TRILHAS[5]: "T3 triagem de valores; T7 concentração", TRILHAS[1]: "T8 variação por rubrica",
               TRILHAS[3]: "T9 acumulado por pessoa", TRILHAS[2]: "descritivo (T4, T5)", TRILHAS[4]: "descritivo (T4, T5)",
               TRILHAS[0]: "–"}
        tab["t2_trilhas"] = tabela_md(pd.DataFrame({
            "Trilha": tt["trilha"], "Linhas": tt["linhas"].map(inteiro), "% linhas": tt["pct_linhas"].map(pct),
            "Valor (R$ milhões)": tt["valor"].map(milhoes), "% valor": tt["pct_valor"].map(pct),
            "Favorecidos": tt["favorecidos"].map(inteiro), "Procedimentos específicos": tt["trilha"].map(uso)}),
            ["Linhas", "% linhas", "Valor (R$ milhões)", "% valor", "Favorecidos"])
    else:
        tab["t2_trilhas"] = "não executado (campos gnd/elemento ausentes)"
    _ = vpos

    # T3
    t3 = nuc["t3"]
    if t3:
        r = t3["resumo"]
        num["t3"] = {k: (pct(v) if k.startswith("taxa") else moeda(v) if k.startswith("valor") else inteiro(v)) for k, v in r.items()}
        num["t3"]["pct_valor_sinalizadas"] = pct(r["valor_sinalizadas_superior"] / d.loc[d["u_triagem"], "valor_empenhado"].sum())
        top = top_estratos(t3, 10)
        tt = pd.DataFrame({
            "GND": top["gnd"].map(_rot_gnd),
            "Elemento": top["elemento"].map(lambda e: f"{e} {desc_el.get(e, '')}".strip()),
            "Exercício": top["exercicio"].astype(int).astype(str),
            "Linhas no estrato": top["n"].map(inteiro),
            "Mediana (R$)": top["mediana_valor"].map(lambda v: decimal(v, 2)),
            "Sinalizadas (superior)": top["sinalizadas_superior"].map(inteiro),
            "% do estrato": (top["sinalizadas_superior"] / top["n"]).map(pct)})
        tab["t3_top_estratos"] = tabela_md(tt, ["Linhas no estrato", "Mediana (R$)", "Sinalizadas (superior)", "% do estrato"])
        # agregação das sinalizações por elemento (todos os exercícios)
        s = t3["sinalizadas"]
        sup = s[s["cauda"] == "superior"]
        por_el = sup.groupby("elemento").size().sort_values(ascending=False)
        num["t3"]["elemento_mais_sinalizado"] = f"{por_el.index[0]} ({desc_el.get(por_el.index[0], '').lower()})" if len(por_el) else "–"
        num["t3"]["sinalizadas_elemento_top"] = inteiro(por_el.iloc[0]) if len(por_el) else "0"
        num["t3"]["pct_sinalizadas_elemento_top"] = pct(por_el.iloc[0] / len(sup)) if len(sup) else "–"
        num["t3"]["pct_sinalizadas_top3_elementos"] = pct(por_el.head(3).sum() / len(sup)) if len(sup) else "–"
        num["t3"]["elementos_com_sinal"] = inteiro(len(por_el))
        num["t3"]["z_max"] = decimal(sup["z"].max(), 1) if len(sup) else "–"
    else:
        num["t3"] = {k: nao_exec("gnd/elemento") for k in ["linhas_elegiveis", "linhas_nao_elegiveis", "estratos_elegiveis",
                                                             "sinalizadas_superior", "sinalizadas_inferior", "taxa_sinalizacao_superior"]}
        tab["t3_top_estratos"] = nao_exec("gnd/elemento")

    # T4
    b1, b2 = nuc["t4_linhas"], nuc["t4_distintos"]
    num["t4"] = {"n_linhas": inteiro(b1["n"]), "dam_linhas": decimal(b1["dam"], 4), "classe_nigrini_linhas": b1["classe"],
                 "digito_maior_z": str(b1["digito_maior_z"]), "z_maximo": decimal(b1["z_maximo"], 2),
                 "chi2_linhas": decimal(b1["chi2"], 1),
                 "obs_digito_maior_z": pct(b1["frequencias"].loc[b1["digito_maior_z"] - 1, "observada"]),
                 "esp_digito_maior_z": pct(b1["frequencias"].loc[b1["digito_maior_z"] - 1, "esperada"])}
    if b2:
        num["t4"].update({"n_distintos": inteiro(b2["n"]), "dam_distintos": decimal(b2["dam"], 4),
                          "classe_nigrini_distintos": b2["classe"], "digito_maior_z_distintos": str(b2["digito_maior_z"]),
                          "z_maximo_distintos": decimal(b2["z_maximo"], 2)})
    else:
        for k in ("n_distintos", "dam_distintos", "classe_nigrini_distintos"):
            num["t4"][k] = nao_exec("numero_empenho")
    f1 = b1["frequencias"]
    tf = pd.DataFrame({"Dígito": f1["digito"].astype(str), "Esperada": f1["esperada"].map(lambda x: decimal(x, 4)),
                       "Observada (linhas)": f1["observada"].map(lambda x: decimal(x, 4)),
                       "z (linhas)": f1["z"].map(lambda x: decimal(x, 2))})
    if b2:
        f2 = b2["frequencias"]
        tf["Observada (empenhos distintos)"] = f2["observada"].map(lambda x: decimal(x, 4))
        tf["z (distintos)"] = f2["z"].map(lambda x: decimal(x, 2))
    tab["t4_frequencias"] = tabela_md(tf, list(tf.columns[1:]))
    vd = valores_digito(b1, 20)
    num["t4"]["pct_top20_valores_digito"] = pct(vd["linhas"].sum() / b1["n"])
    num["t4"]["linhas_top20_valores_digito"] = inteiro(vd["linhas"].sum())
    num["t4"]["valor_mais_frequente_digito"] = moeda(vd["valor"].iloc[0]) if len(vd) else "–"
    num["t4"]["linhas_valor_mais_frequente"] = inteiro(vd["linhas"].iloc[0]) if len(vd) else "0"
    # elemento predominante entre os 20 valores mais frequentes do dígito (interpretação)
    dd = d.loc[d["u_positivos"] & (d["valor_empenhado"] >= params["t4"]["valor_minimo"])]
    m = dd["valor_empenhado"].round(2).isin(vd["valor"])
    el_top = dd.loc[m, "elemento"].value_counts() if "elemento" in dd else pd.Series(dtype=int)
    if len(el_top):
        num["t4"]["elemento_valores_digito"] = f"{el_top.index[0]} ({desc_el.get(el_top.index[0], '').lower()})"
        num["t4"]["pct_elemento_valores_digito"] = pct(el_top.iloc[0] / el_top.sum())
    if len(vd) and "elemento" in dd:
        mf = dd.loc[dd["valor_empenhado"].round(2) == vd["valor"].iloc[0], "elemento"].value_counts()
        for i, (el, q) in enumerate(mf.head(2).items(), start=1):
            num["t4"][f"valor_freq_elemento{i}"] = f"{el} ({desc_el.get(el, '').lower()})"
            num["t4"][f"valor_freq_linhas{i}"] = inteiro(q)
    tv = pd.DataFrame({"Valor (R$)": vd["valor"].map(lambda v: decimal(v, 2)), "Linhas": vd["linhas"].map(inteiro),
                       "% das linhas positivas": vd["pct_do_total"].map(pct)})
    tab["t4_valores_digito"] = tabela_md(tv, list(tv.columns))

    # T5
    t5 = nuc["t5"]
    r5 = t5["resumo"]
    num["t5"] = {k: (pct(v) if k.startswith("part") else (str(v) if isinstance(v, str) else inteiro(v))) for k, v in r5.items()}
    num["t5"]["exercicio_dezembro_min"] = str(r5["exercicio_dezembro_min"])
    num["t5"]["exercicio_dezembro_max"] = str(r5["exercicio_dezembro_max"])
    partes = []
    comp = t5["composicao"]
    if "modalidade_empenho" not in comp:
        partes.append("Modalidade de empenho: não executado (campo modalidade_empenho ausente).")
    if "gnd" in comp:
        g = comp["gnd"]
        tg = pd.DataFrame({"GND": g["gnd"].map(_rot_gnd), "Linhas": g["linhas"].map(inteiro),
                           "Valor (R$ milhões)": g["valor"].map(milhoes), "% do valor do mês": g["pct_valor"].map(pct)})
        partes.append(tabela_md(tg, ["Linhas", "Valor (R$ milhões)", "% do valor do mês"]))
        num["t5"]["gnd_mes_maior"] = _rot_gnd(g.iloc[0]["gnd"])
        num["t5"]["pct_gnd_mes_maior"] = pct(g.iloc[0]["pct_valor"])
    if "elemento" in comp:
        e = comp["elemento"].head(5)
        te_ = pd.DataFrame({"Elemento (5 maiores)": e["elemento"].map(lambda x: f"{x} {desc_el.get(x, '')}".strip()),
                            "Linhas": e["linhas"].map(inteiro), "Valor (R$ milhões)": e["valor"].map(milhoes),
                            "% do valor do mês": e["pct_valor"].map(pct)})
        partes.append(tabela_md(te_, ["Linhas", "Valor (R$ milhões)", "% do valor do mês"]))
        num["t5"]["elemento_mes_maior"] = f"{e.iloc[0]['elemento']} ({desc_el.get(e.iloc[0]['elemento'], '').lower()})"
        num["t5"]["pct_elemento_mes_maior"] = pct(e.iloc[0]["pct_valor"])
        num["t5"]["linhas_elemento_mes_maior"] = inteiro(e.iloc[0]["linhas"])
    tab["t5_composicao_mes_maior"] = "\n\n".join(partes)
    base5 = d.loc[d["u_positivos"] & d["data_emissao"].notna() & ~d["flag_rap"]]
    dez = base5[base5["data_emissao"].dt.month == 12]
    if "gnd" in dez and "elemento" in dez and len(dez):
        gd = dez.groupby("gnd")["valor_empenhado"].sum().sort_values(ascending=False)
        ed = dez.groupby("elemento")["valor_empenhado"].sum().sort_values(ascending=False)
        num["t5"]["gnd_dezembro"] = _rot_gnd(gd.index[0])
        num["t5"]["pct_gnd_dezembro"] = pct(gd.iloc[0] / gd.sum())
        num["t5"]["elemento_dezembro"] = f"{ed.index[0]} ({desc_el.get(ed.index[0], '').lower()})"
        num["t5"]["pct_elemento_dezembro"] = pct(ed.iloc[0] / ed.sum())
    tri5 = base5[base5["u_triagem"]]
    if len(tri5):
        pm = tri5.groupby(tri5["data_emissao"].dt.month)["valor_empenhado"].sum()
        pm = pm / pm.sum()
        num["t5"]["triagem_mes_maior"] = MESES[int(pm.idxmax()) - 1]
        num["t5"]["triagem_part_mes_maior"] = pct(pm.max())
        num["t5"]["triagem_part_janeiro"] = pct(pm.get(1, 0.0))
        num["t5"]["triagem_part_dezembro"] = pct(pm.get(12, 0.0))

    # T6
    num["t6"] = {"linhas_repetidas": inteiro(t6["linhas_repetidas"]), "grupos_repetidos": inteiro(t6["grupos_repetidos"]),
                 "linhas_excedentes": inteiro(t6["linhas_excedentes"]),
                 "pct_linhas_repetidas": pct(t6["linhas_repetidas"] / len(can)),
                 "maior_grupo": inteiro(t6["distribuicao_tamanho"]["tamanho_grupo"].max()) if t6["grupos_repetidos"] else "0",
                 "grupos_pares": inteiro(t6["distribuicao_tamanho"].set_index("tamanho_grupo")["grupos"].get(2, 0))}
    rep = t6["mascara"]
    num["t6"]["pct_repetidas_valor_zero"] = pct(((d["valor_empenhado"] == 0) & rep).sum() / max(rep.sum(), 1))
    ch = t6["chave"]
    num["t6"]["texto_repeticao_chave"] = (
        f"A repetição por chave de documento identificou {inteiro(ch['linhas'])} linhas em {inteiro(ch['grupos'])} grupos."
        if ch["executado"] else
        f"A repetição por chave de documento não foi executada ({ch['motivo']}).")

    # T7 (fornecedores)
    t7 = nuc["t7"]
    if t7:
        num["t7"] = {"favorecidos_distintos": inteiro(t7["favorecidos_distintos"]), "part_top1": pct(t7["part_top1"]),
                     "part_topn": pct(t7["part_topn"]), "part_nao_classificados": pct(t7["part_nao_classificados"]),
                     "hhi_pj": decimal(t7["hhi_pj"], 0) if t7["hhi_pj"] is not None else nao_exec("id_favorecido")}
        rk = t7["ranking"]
        acum = rk.cumsum() / rk.sum()
        num["t7"]["favorecidos_50pct"] = inteiro((acum < 0.5).sum() + 1)
        num["t7"]["favorecidos_80pct"] = inteiro((acum < 0.8).sum() + 1)
        pe = t7["por_elemento"].head(8)
        num["t7"]["elementos_lider_50pct"] = inteiro((t7["por_elemento"]["pct_maior"] >= 0.5).sum())
        num["t7"]["elementos_total"] = inteiro(len(t7["por_elemento"]))
        tab["t7_fornecedores_elemento"] = tabela_md(pd.DataFrame({
            "Elemento (8 maiores em valor)": pe["elemento"].map(lambda x: f"{x} {desc_el.get(x, '')}".strip()),
            "Favorecidos": pe["favorecidos"].map(inteiro), "Valor (R$ milhões)": pe["valor"].map(milhoes),
            "% do maior favorecido": pe["pct_maior"].map(pct), "% dos 3 maiores": pe["pct_top3"].map(pct)}),
            ["Favorecidos", "Valor (R$ milhões)", "% do maior favorecido", "% dos 3 maiores"])
        top_el = pe.sort_values("pct_maior", ascending=False).iloc[0]
        num["t7"]["elemento_mais_concentrado"] = f"{top_el['elemento']} ({desc_el.get(top_el['elemento'], '').lower()})"
        num["t7"]["pct_lider_mais_concentrado"] = pct(top_el["pct_maior"])
        tt7 = t7["tipos"]
        tab["t7_tipos_favorecido"] = tabela_md(pd.DataFrame({
            "Tipo de favorecido": tt7["tipo"], "Linhas": tt7["linhas"].map(inteiro),
            "Valor (R$ milhões)": tt7["valor"].map(milhoes), "% do valor": tt7["pct_valor"].map(pct)}),
            ["Linhas", "Valor (R$ milhões)", "% do valor"])
    else:
        num["t7"] = {k: nao_exec("favorecido/gnd/elemento") for k in ("favorecidos_distintos", "part_top1", "part_topn")}
        tab["t7_fornecedores_elemento"] = tab["t7_tipos_favorecido"] = nao_exec("favorecido/gnd/elemento")

    # Comparação: triagem sem o recorte em trilhas (universo amplo: positivos de aplicação direta, sem GND excluídos e sentenças)
    if t3 and d["trilha"].notna().any():
        amplo = (d["u_positivos"] & d["trilha"].isin([TRILHAS[5], TRILHAS[3], TRILHAS[4]])
                 & ~d["gnd"].isin(params["t2"]["gnd_excluidos"]) & (d["elemento"] != "91")).fillna(False).astype(bool)
        ra = triagem(d.assign(u_triagem=amplo), params)
        sa = ra["sinalizadas"]
        sa = sa[sa["cauda"] == "superior"]
        pe_a = sa.groupby("elemento").size().sort_values(ascending=False)
        num["comp"] = {
            "linhas_amplo": inteiro(amplo.sum()), "sinalizadas_amplo": inteiro(len(sa)),
            "taxa_amplo": pct(ra["resumo"]["taxa_sinalizacao_superior"]),
            "elemento_top_amplo": f"{pe_a.index[0]} ({desc_el.get(pe_a.index[0], '').lower()})" if len(pe_a) else "–",
            "pct_elemento_top_amplo": pct(pe_a.iloc[0] / len(sa)) if len(sa) else "–",
            "pct_amplo_em_pessoas": pct(d.loc[sa.index, "u_pessoas"].mean()) if len(sa) else "–",
            "reducao": pct(1 - t3["resumo"]["sinalizadas_superior"] / len(sa)) if len(sa) else "–",
        }

    # T8 (pessoal)
    t8 = nuc["t8"]
    if t8:
        r8 = t8["resumo"]
        num["t8"] = {"linhas": inteiro(r8["linhas"]), "rubricas": inteiro(r8["rubricas"]),
                     "rubricas_analisadas": inteiro(r8["rubricas_analisadas"]), "rubrica_exercicios": inteiro(r8["rubrica_exercicios"]),
                     "sinalizadas_acima": inteiro(r8["sinalizadas_acima"]), "sinalizadas_abaixo": inteiro(r8["sinalizadas_abaixo"]),
                     "favorecidos_distintos": inteiro(r8["favorecidos_distintos"]),
                     "part_top4_rubricas": pct(r8["part_top4_rubricas"]),
                     "pct_valor_positivo": pct(r8["valor"] / vpos) if vpos else "–"}
        sn = t8["sinalizadas"]
        sn = sn[sn["sinal"] == "acima"].head(10)
        if len(sn):
            maior = sn.sort_values("valor", ascending=False).iloc[0]
            num["t8"]["maior_sinal_rubrica"] = f"{maior['elemento']} ({desc_el.get(maior['elemento'], '').lower()})"
            num["t8"]["maior_sinal_exercicio"] = str(int(maior["exercicio"]))
            num["t8"]["maior_sinal_razao"] = decimal(maior["razao"], 1)
            num["t8"]["maior_sinal_valor"] = milhoes(maior["valor"])
        tab["t8_rubricas_sinalizadas"] = tabela_md(pd.DataFrame({
            "Rubrica (elemento)": sn["elemento"].map(lambda x: f"{x} {desc_el.get(x, '')}".strip()),
            "Exercício": sn["exercicio"].astype(int).astype(str), "Linhas": sn["linhas"].map(inteiro),
            "Valor (R$ milhões)": sn["valor"].map(milhoes), "Mediana dos demais exercícios (R$ milhões)": sn["mediana_demais"].map(milhoes),
            "Razão": sn["razao"].map(lambda x: decimal(x, 1))}),
            ["Linhas", "Valor (R$ milhões)", "Mediana dos demais exercícios (R$ milhões)", "Razão"]) \
            if len(sn) else "Nenhuma rubrica-exercício acima do limiar."
    else:
        num["t8"] = {k: nao_exec("gnd/elemento") for k in ("linhas", "rubricas", "sinalizadas_acima")}
        tab["t8_rubricas_sinalizadas"] = nao_exec("gnd/elemento")

    # T9 (pagamentos a pessoas)
    t9 = nuc["t9"]
    if t9:
        r9 = t9["resumo"]
        num["t9"] = {"linhas": inteiro(r9["linhas"]), "favorecidos_distintos": inteiro(r9["favorecidos_distintos"]),
                     "acumulados": inteiro(r9["acumulados"]), "acumulados_elegiveis": inteiro(r9["acumulados_elegiveis"]),
                     "estratos_elegiveis": inteiro(r9["estratos_elegiveis"]), "sinalizados": inteiro(r9["sinalizados"]),
                     "taxa": pct(r9["taxa"]), "pct_valor_sinalizados": pct(r9["pct_valor_sinalizados"]),
                     "linhas_sinalizados": inteiro(r9["linhas_sinalizados"]),
                     "razao_mediana_mediana": decimal(r9["razao_mediana_mediana"], 0),
                     "razao_mediana_max": decimal(r9["razao_mediana_max"], 0),
                     "agregados_favorecidos": inteiro(r9["agregados_favorecidos"]), "agregados_linhas": inteiro(r9["agregados_linhas"]),
                     "agregados_pct_valor": pct(r9["agregados_pct_valor"]), "individuais_favorecidos": inteiro(r9["individuais_favorecidos"]),
                     "acumulado_max": moeda(r9["acumulado_max"]), "linhas_mediana_sinalizados": decimal(r9["linhas_mediana_sinalizados"], 0)}
        sg = t9["sinalizadas"]
        por_el = sg.groupby("elemento").size().sort_values(ascending=False)
        if len(por_el):
            num["t9"]["elemento_mais_sinalizado"] = f"{por_el.index[0]} ({desc_el.get(por_el.index[0], '').lower()})"
            num["t9"]["pct_elemento_mais_sinalizado"] = pct(por_el.iloc[0] / len(sg))
        e9 = t9["estratos"]
        e9 = e9[e9["elegivel"]].sort_values(["sinalizadas_superior", "n"], ascending=False).head(10)
        tab["t9_estratos"] = tabela_md(pd.DataFrame({
            "Elemento": e9["elemento"].map(lambda x: f"{x} {desc_el.get(x, '')}".strip()),
            "Exercício": e9["exercicio"].astype(int).astype(str), "Favorecidos": e9["n"].map(inteiro),
            "Mediana do acumulado (R$)": e9["mediana_valor"].map(lambda v: decimal(v, 2)),
            "Favorecidos sinalizados": e9["sinalizadas_superior"].map(inteiro),
            "% do estrato": (e9["sinalizadas_superior"] / e9["n"]).map(pct)}),
            ["Favorecidos", "Mediana do acumulado (R$)", "Favorecidos sinalizados", "% do estrato"])
    else:
        num["t9"] = {k: nao_exec("favorecido/elemento") for k in ("linhas", "sinalizados", "taxa")}
        tab["t9_estratos"] = nao_exec("favorecido/elemento")

    # Sensibilidade
    num["sens"] = {"unidades_todo_periodo": inteiro(len(unid)),
                   "unidades_total": inteiro(can["unidade"].nunique()) if "unidade" in can else "0"}
    if sens:
        ds = sens["d"]
        lin = [
            ("Unidades orçamentárias", inteiro(can["unidade"].nunique()), inteiro(len(unid))),
            ("Linhas (U_total)", inteiro(len(d)), inteiro(len(ds))),
            ("Linhas positivas (U_positivos)", inteiro(d["u_positivos"].sum()), inteiro(ds["u_positivos"].sum())),
            ("Linhas na trilha de fornecedores", inteiro(d["u_triagem"].sum()), inteiro(ds["u_triagem"].sum())),
            ("T3 – sinalizadas (cauda superior)", inteiro(t3["resumo"]["sinalizadas_superior"]), inteiro(sens["t3"]["resumo"]["sinalizadas_superior"])),
            ("T3 – taxa de sinalização superior", pct(t3["resumo"]["taxa_sinalizacao_superior"]), pct(sens["t3"]["resumo"]["taxa_sinalizacao_superior"])),
            ("T4 – DAM (linhas)", decimal(b1["dam"], 4), decimal(sens["t4_linhas"]["dam"], 4)),
            ("T4 – faixa de Nigrini (linhas)", b1["classe"], sens["t4_linhas"]["classe"]),
            ("T5 – participação média de dezembro", pct(r5["part_dezembro_media"]), pct(sens["t5"]["resumo"]["part_dezembro_media"])),
            ("T5 – mês de maior valor", r5["mes_maior_valor"], sens["t5"]["resumo"]["mes_maior_valor"]),
            ("T7 – participação dos " + str(params["t7"]["top_n"]) + " maiores fornecedores", pct(t7["part_topn"]), pct(sens["t7"]["part_topn"])),
            ("T8 – rubricas-exercício acima do limiar", inteiro(t8["resumo"]["sinalizadas_acima"]), inteiro(sens["t8"]["resumo"]["sinalizadas_acima"])),
            ("T9 – favorecidos com acumulado atípico", inteiro(t9["resumo"]["sinalizados"]), inteiro(sens["t9"]["resumo"]["sinalizados"])),
        ]
        tab["sensibilidade_escopo"] = tabela_md(pd.DataFrame(lin, columns=["Indicador", "Escopo completo", "Unidades presentes em todo o período"]),
                                                ["Escopo completo", "Unidades presentes em todo o período"])
        num["sens"]["pct_linhas_restrito"] = pct(len(ds) / len(d))
        num["sens"]["sinalizadas_restrito"] = inteiro(sens["t3"]["resumo"]["sinalizadas_superior"])
        num["sens"]["taxa_restrito"] = pct(sens["t3"]["resumo"]["taxa_sinalizacao_superior"])
        num["sens"]["dam_restrito"] = decimal(sens["t4_linhas"]["dam"], 4)
        num["sens"]["classe_restrito"] = sens["t4_linhas"]["classe"]
        num["sens"]["dez_restrito"] = pct(sens["t5"]["resumo"]["part_dezembro_media"])
        num["sens"]["mes_maior_restrito"] = sens["t5"]["resumo"]["mes_maior_valor"]
    else:
        tab["sensibilidade_escopo"] = "não executado (campo unidade ausente)"

    num["param"] = {
        "t2": {"gnd_excluidos": ", ".join(map(str, params["t2"]["gnd_excluidos"])),
               "elementos_nao_fornecedor": ", ".join(params["t2"]["elementos_nao_fornecedor"]),
               "elementos_pessoal_odc": ", ".join(params["t2"]["elementos_pessoal_odc"]),
               "elementos_pagamento_pessoa": ", ".join(params["t2"]["elementos_pagamento_pessoa"]),
               "modalidades_incluidas": " e ".join(params["t2"]["modalidades_incluidas"]),
               "deflacionar": "sim" if params["t2"]["deflacionar"] else "não"},
        "t3": {"min_grupo": inteiro(params["t3"]["min_grupo"]), "limiar": decimal(params["t3"]["limiar"], 1)},
        "t4": {"valor_minimo": moeda(params["t4"]["valor_minimo"])},
        "t7": {"top_n": str(params["t7"]["top_n"])},
        "t8": {"razao_limiar": decimal(params["t8"]["razao_limiar"], 1), "min_exercicios": str(params["t8"]["min_exercicios"])},
        "t9": {"min_grupo": inteiro(params["t9"]["min_grupo"]), "limiar": decimal(params["t9"]["limiar"], 1)},
    }
    return num, tab

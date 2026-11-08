"""Painel do produto: aplica o protocolo de trilhas (Capítulo 4) a qualquer base de empenhos.

Execução: streamlit run app_streamlit.py
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import yaml

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

from protocolo_ac.canonico import CAMPOS  # noqa: E402
from protocolo_ac.config import carregar_params, carregar_perfil  # noqa: E402
from protocolo_ac.io import amostra_arquivo  # noqa: E402
from protocolo_ac.matriz import carregar_matriz  # noqa: E402
from protocolo_ac.pipeline import executar  # noqa: E402
from protocolo_ac.resumo import NOME_PRODUTO, carregar_numeros  # noqa: E402
from protocolo_ac.sintetico import gerar, gravar_excel_siga  # noqa: E402
from protocolo_ac.t0_perfil import sugerir_mapeamento  # noqa: E402

AVISO = "Os sinais servem para priorizar exames. Não comprovam erro, fraude ou irregularidade."
SEM = "(não há na base)"

st.set_page_config(page_title=NOME_PRODUTO, layout="wide")
st.title(NOME_PRODUTO)
st.caption("Aplica o protocolo de trilhas analíticas a qualquer base de empenhos: verifica o que a base permite, "
           "recorta a base pela natureza da despesa e indica o que examinar primeiro em cada trilha. " + AVISO)

if "tmp" not in st.session_state:
    st.session_state.tmp = Path(tempfile.mkdtemp(prefix="painel_ac_"))
TMP: Path = st.session_state.tmp


# ---------------------------------------------------------------- 1. Base
st.sidebar.header("1. Base de empenhos")
fonte = st.sidebar.radio("Origem", ["Enviar arquivos (CSV ou Excel)", "Base de demonstração (sintética)"])
arquivos: list[Path] = []
if fonte.startswith("Enviar"):
    enviados = st.sidebar.file_uploader("Um ou mais arquivos (ex.: um por exercício)", type=["csv", "xlsx", "xls"],
                                        accept_multiple_files=True)
    for f in enviados or []:
        destino = TMP / "entrada" / f.name
        destino.parent.mkdir(parents=True, exist_ok=True)
        if not destino.exists() or destino.stat().st_size != f.size:
            destino.write_bytes(f.getbuffer())
        arquivos.append(destino)
else:
    demo = TMP / "entrada_demo" / "base_demonstracao.xlsx"
    if not demo.exists():
        demo.parent.mkdir(parents=True, exist_ok=True)
        base, _ = gerar(n_por_estrato=300)
        gravar_excel_siga(base, demo)
    arquivos = [demo]
    st.sidebar.info("Base sintética no leiaute do SIGA Brasil, com anomalias conhecidas.")

# ---------------------------------------------------------------- 2. Perfil
st.sidebar.header("2. Perfil de entrada")
perfis = {p.stem: p for p in sorted((RAIZ / "config" / "perfis").glob("*.yaml"))}
opcoes = list(perfis) + ["mapear colunas na tela"]
padrao = opcoes.index("siga_brasil") if "siga_brasil" in opcoes else 0
escolha = st.sidebar.selectbox("Perfil", opcoes, index=padrao,
                               help="O perfil associa as colunas da sua base aos campos do protocolo.")
perfil: dict | None = None
if escolha != "mapear colunas na tela":
    perfil = carregar_perfil(perfis[escolha])
elif arquivos:
    sep = st.sidebar.text_input("Separador (CSV)", ";")
    try:
        amostra = amostra_arquivo(arquivos[0], separador=sep)
    except Exception as exc:  # noqa: BLE001
        st.sidebar.error(f"Não foi possível ler a amostra: {exc}")
        amostra = None
    if amostra is not None:
        colunas = list(amostra.columns)
        sugestao = sugerir_mapeamento(colunas)
        mapa = {}
        with st.sidebar.expander("Campos do protocolo × colunas da base", expanded=True):
            for campo, info in CAMPOS.items():
                lista = [SEM] + colunas
                ini = lista.index(sugestao[campo]) if campo in sugestao else 0
                esc = st.selectbox(f"{campo} – {info['descricao']}", lista, index=ini, key=f"map_{campo}")
                if esc != SEM:
                    mapa[campo] = esc
        ausentes = st.sidebar.text_input("Textos que significam 'valor ausente' (separados por ;)", "NÃO APLICÁVEL;-")
        derivar = st.sidebar.selectbox("Derivar modalidade de aplicação do código de 8 dígitos da natureza da despesa",
                                       [SEM] + colunas, help="Use quando a base não tiver a modalidade como coluna.")
        perfil = {"nome": "mapeado_no_painel", "leitura": {"separador": sep, "encoding": "utf-8"}, "colunas": mapa,
                  "valores_ausentes": [x.strip() for x in ausentes.split(";") if x.strip()]}
        if derivar != SEM and "modalidade_aplicacao" not in mapa:
            perfil["derivacoes"] = {"modalidade_aplicacao": {"coluna": derivar, "inicio": 2, "fim": 4,
                                                             "conferir": {"gnd": [1, 2], "elemento": [4, 6]}}}
        st.sidebar.download_button("Baixar este perfil (YAML)", yaml.safe_dump(perfil, allow_unicode=True, sort_keys=False),
                                   "perfil.yaml")

# ---------------------------------------------------------------- 3. Parâmetros
st.sidebar.header("3. Parâmetros")
params = carregar_params(RAIZ / "config" / "params.yaml")
with st.sidebar.expander("Ajustar parâmetros (ficam registrados na execução)"):
    params["t3"]["limiar"] = st.number_input("T3 – limiar do escore robusto", 2.0, 10.0, float(params["t3"]["limiar"]), 0.5)
    params["t3"]["min_grupo"] = int(st.number_input("T3 – linhas mínimas por estrato", 5, 500, int(params["t3"]["min_grupo"]), 5))
    params["t7"]["top_n"] = int(st.number_input("T7 – número de maiores fornecedores", 1, 100, int(params["t7"]["top_n"])))
    params["t8"]["razao_limiar"] = st.number_input("T8 – razão sobre a mediana dos demais anos", 1.1, 10.0,
                                                   float(params["t8"]["razao_limiar"]), 0.1)
    params["t9"]["limiar"] = st.number_input("T9 – limiar do escore do acumulado", 2.0, 10.0, float(params["t9"]["limiar"]), 0.5)
    for chave, rotulo in (("elementos_pagamento_pessoa", "Elementos da trilha de pagamentos a pessoas"),
                          ("elementos_pessoal_odc", "Elementos de benefícios pagos em folha (trilha de pessoal)"),
                          ("elementos_nao_fornecedor", "Elementos de outras despesas (não fornecedores)")):
        txt = st.text_input(rotulo, ", ".join(params["t2"][chave]))
        params["t2"][chave] = [x.strip().zfill(2) for x in txt.split(",") if x.strip()]

executar_btn = st.sidebar.button("Executar protocolo", type="primary", disabled=not (arquivos and perfil))
if executar_btn:
    with st.spinner("Executando T0–T9 (bases grandes em Excel podem levar alguns minutos)..."):
        try:
            st.session_state.run = executar(arquivos, perfil, params, {}, TMP / "saida", usar_cache=False)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Erro na execução: {exc}")

run: Path | None = st.session_state.get("run")
if not run:
    st.info("Escolha a base, o perfil e clique em **Executar protocolo**. Sem dados próprios, use a base de demonstração.")
    st.stop()


@st.cache_data(show_spinner=False)
def aba(caminho: str, nome: str) -> pd.DataFrame:
    try:
        df = pd.read_excel(caminho, sheet_name=nome)
    except ValueError:
        return pd.DataFrame()
    mistas = [c for c in df.columns if df[c].dtype == object]
    return df.astype({c: "string" for c in mistas})


xlsx = str(run / "resultados_auditoria.xlsx")
n = carregar_numeros(run)
t0, t1, t2, t3, t4, t5, t6, t7, t8, t9 = (n.get(k, {}) for k in ("t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9"))

MATRIZ = carregar_matriz()


def procedimentos(trilha: str) -> None:
    """Mostra as linhas da matriz de procedimentos da trilha."""
    with st.expander("Procedimentos de verificação"):
        for _, r in MATRIZ[MATRIZ["trilha"] == trilha].iterrows():
            st.markdown(chr(10).join([
                f"**{r['procedimento']}** – {r['questao']}", "",
                f"- *Critério:* {r['criterio']}",
                f"- *Informações requeridas:* {r['informacoes']}",
                f"- *Verificação:* {r['verificacao']}",
                f"- *Possíveis achados:* {r['achados']}",
            ]))


guias = st.tabs(["Visão geral", "Trilhas", "Fornecedores", "Pessoal", "Pagamentos a pessoas", "Transversais", "Exportar"])

with guias[0]:
    c = st.columns(4)
    c[0].metric("Linhas", t1.get("linhas", "–"))
    c[1].metric("Empenhos distintos", t1.get("empenhos_distintos", "–"))
    c[2].metric("Procedimentos executáveis", f"{t0.get('procedimentos_executaveis', '–')} de {t0.get('procedimentos_total', '–')}")
    c[3].metric("Tempo de execução", n.get("exec", {}).get("tempo", "–"))
    st.subheader("O que a base permite (T0)")
    st.dataframe(aba(xlsx, "T0_executabilidade"), use_container_width=True, hide_index=True)
    st.subheader("Qualidade e cobertura por exercício (T1)")
    st.dataframe(aba(xlsx, "T1_cobertura"), use_container_width=True, hide_index=True)

with guias[1]:
    tr = aba(xlsx, "T2_trilhas")
    if tr.empty:
        st.warning("Recorte não executado: a base não tem GND e elemento.")
    else:
        st.markdown("Cada linha com valor positivo pertence a uma única trilha, definida pela natureza da despesa.")
        g = tr.melt(id_vars="trilha", value_vars=["pct_linhas", "pct_valor"], var_name="medida", value_name="participação")
        g["medida"] = g["medida"].map({"pct_linhas": "% das linhas", "pct_valor": "% do valor"})
        st.plotly_chart(px.bar(g, x="participação", y="trilha", color="medida", barmode="group", orientation="h"),
                        use_container_width=True)
        st.dataframe(tr, use_container_width=True, hide_index=True)

with guias[2]:
    st.markdown("**Pergunta:** que empenho tem valor incomum para seu grupo (T3) e que fornecedores concentram o gasto (T7)?")
    procedimentos("Fornecedores")
    c = st.columns(3)
    c[0].metric("Empenhos sinalizados (T3)", t3.get("sinalizadas_superior", "–"), t3.get("taxa_sinalizacao_superior"))
    c[1].metric("Fornecedores", t7.get("favorecidos_distintos", "–"))
    c[2].metric(f"Valor nos {params['t7']['top_n']} maiores", t7.get("part_topn", "–"))
    s3 = aba(xlsx, "T3_sinalizadas")
    if not s3.empty:
        s3 = s3[s3["cauda"] == "superior"]
        f1, f2 = st.columns(2)
        el = f1.multiselect("Elemento", sorted(s3["elemento"].astype(str).unique()))
        ex = f2.multiselect("Exercício", sorted(s3["exercicio"].unique()))
        if el:
            s3 = s3[s3["elemento"].astype(str).isin(el)]
        if ex:
            s3 = s3[s3["exercicio"].isin(ex)]
        cols = [c for c in ("numero_empenho", "data_emissao", "favorecido", "unidade", "gnd", "elemento", "exercicio",
                            "valor_empenhado", "linhas_no_estrato", "z") if c in s3]
        st.subheader("Empenhos priorizados (cauda superior, maior escore primeiro)")
        st.dataframe(s3[cols], use_container_width=True, hide_index=True)
    st.subheader("Concentração por elemento (T7)")
    st.dataframe(aba(xlsx, "T7_por_elemento"), use_container_width=True, hide_index=True)
    with st.expander("Maiores fornecedores da trilha"):
        st.dataframe(aba(xlsx, "T7_favorecidos"), use_container_width=True, hide_index=True)

with guias[3]:
    st.markdown("**Pergunta:** que rubrica de pessoal variou fora do padrão em um exercício (T8)?")
    procedimentos("Pessoal")
    r8 = aba(xlsx, "T8_rubricas")
    c = st.columns(2)
    c[0].metric("Rubricas-exercício acima do padrão", t8.get("sinalizadas_acima", "–"))
    c[1].metric("Abaixo do padrão", t8.get("sinalizadas_abaixo", "–"))
    if not r8.empty:
        r8["elemento"] = r8["elemento"].astype(str).str.zfill(2)
        st.plotly_chart(px.line(r8, x="exercicio", y="valor", color="elemento", markers=True, log_y=True,
                                labels={"valor": "valor empenhado (escala log)", "exercicio": "exercício"}),
                        use_container_width=True)
        st.dataframe(r8[r8["sinal"].notna() & (r8["sinal"] != "")].sort_values("razao", ascending=False),
                     use_container_width=True, hide_index=True)
    st.caption("Sem a folha individualizada (CPF, rubrica, competência), a análise é por rubrica, não por servidor.")

with guias[4]:
    st.markdown("**Pergunta:** quem acumulou valor atípico em uma rubrica e exercício (T9)?")
    procedimentos("Pagamentos a pessoas")
    c = st.columns(3)
    c[0].metric("Beneficiários sinalizados", t9.get("sinalizados", "–"), t9.get("taxa"))
    c[1].metric("Favorecidos de pagamento agregado", t9.get("agregados_favorecidos", "–"))
    c[2].metric("Valor em pagamento agregado", t9.get("agregados_pct_valor", "–"))
    st.dataframe(aba(xlsx, "T9_sinalizados"), use_container_width=True, hide_index=True)
    with st.expander("Pagamentos agregados (favorecido é unidade ou órgão) – conferir a regra"):
        st.dataframe(aba(xlsx, "T9_pagamentos_agregados"), use_container_width=True, hide_index=True)

with guias[5]:
    c = st.columns(3)
    c[0].metric("Benford – DAM (linhas)", t4.get("dam_linhas", "–"), t4.get("classe_nigrini_linhas"), delta_color="off")
    c[1].metric("Mês de maior valor", t5.get("mes_maior_valor", "–"), t5.get("part_mes_maior_valor"), delta_color="off")
    c[2].metric("Linhas repetidas", t6.get("linhas_repetidas", "–"))
    procedimentos("Transversal")
    fb = aba(xlsx, "T4_frequencias").head(9)
    if not fb.empty:
        st.plotly_chart(px.bar(fb, x="digito", y=["observada", "esperada"], barmode="group",
                               labels={"value": "frequência", "digito": "1º dígito"}), use_container_width=True)
    fig = run / "figuras" / "t5_heatmap_exercicio_mes.png"
    if fig.exists():
        st.image(str(fig), caption="Participação de cada mês no valor empenhado do exercício (%)")

with guias[6]:
    st.download_button("Relatório completo (Excel)", Path(xlsx).read_bytes(), "resultados_auditoria.xlsx")
    st.download_button("Metadados da execução (JSON)", (run / "metadados.json").read_bytes(), "metadados.json")
    st.download_button("Registro de exclusões (CSV)", (run / "log_exclusoes.csv").read_bytes(), "log_exclusoes.csv")
    buf = io.StringIO()
    yaml.safe_dump(params, buf, allow_unicode=True, sort_keys=False)
    st.download_button("Parâmetros usados (YAML)", buf.getvalue(), "params.yaml")
    st.json(json.loads((run / "metadados.json").read_text(encoding="utf-8")), expanded=False)

st.caption(AVISO)

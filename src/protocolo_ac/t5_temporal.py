"""T5 – Distribuição temporal. Universo: U_positivos com data válida. Unidade: linhas e soma do valor.

A série exercício × mês usa as linhas cujo ano da data coincide com o exercício;
linhas marcadas como restos a pagar (ano da data < exercício) são contadas à parte.
"""
from __future__ import annotations

import pandas as pd

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


def temporal(d: pd.DataFrame) -> dict:
    base = d.loc[d["u_positivos"] & d["data_emissao"].notna()].copy()
    ano = base["data_emissao"].dt.year
    corrente = base.loc[ano == base["exercicio"]].copy()
    rap = base.loc[base["flag_rap"]]
    posterior = base.loc[ano > base["exercicio"]]
    corrente["mes"] = corrente["data_emissao"].dt.month
    em = corrente.groupby(["exercicio", "mes"]).agg(linhas=("valor_empenhado", "size"),
                                                    valor=("valor_empenhado", "sum")).reset_index()
    em["pct_valor_exercicio"] = em["valor"] / em.groupby("exercicio")["valor"].transform("sum")
    em["pct_linhas_exercicio"] = em["linhas"] / em.groupby("exercicio")["linhas"].transform("sum")

    dez = em[em["mes"] == 12].set_index("exercicio")["pct_valor_exercicio"]
    exercicios = sorted(em["exercicio"].unique())
    dez = dez.reindex(exercicios).fillna(0.0)
    mes_mais_linhas = em.loc[em.groupby("exercicio")["linhas"].idxmax()].set_index("exercicio")["mes"]
    por_mes = corrente.groupby("mes")["valor_empenhado"].sum()
    mes_maior = int(por_mes.idxmax())
    resumo = {
        "linhas_base": int(len(base)), "linhas_exercicio_corrente": int(len(corrente)),
        "linhas_rap": int(len(rap)), "linhas_data_posterior": int(len(posterior)),
        "part_dezembro_media": float(dez.mean()), "part_dezembro_min": float(dez.min()),
        "part_dezembro_max": float(dez.max()),
        "exercicio_dezembro_min": int(dez.idxmin()), "exercicio_dezembro_max": int(dez.idxmax()),
        "exercicios_dezembro_maior_linhas": int((mes_mais_linhas == 12).sum()),
        "n_exercicios": len(exercicios),
        "mes_maior_valor": MESES[mes_maior - 1],
        "part_mes_maior_valor": float(por_mes.max() / por_mes.sum()),
        "part_dezembro_periodo": float(por_mes.get(12, 0.0) / por_mes.sum()),
        "part_linhas_dezembro_periodo": float((corrente["mes"] == 12).mean()),
    }
    comp = {}
    sub = corrente[corrente["mes"] == mes_maior]
    for campo in ("modalidade_empenho", "gnd"):
        if campo in sub and sub[campo].notna().any():
            c = sub.groupby(campo)["valor_empenhado"].agg(["size", "sum"]).rename(columns={"size": "linhas", "sum": "valor"})
            c["pct_valor"] = c["valor"] / c["valor"].sum()
            comp[campo] = c.reset_index().sort_values("valor", ascending=False)
    # composição do mês de maior valor por elemento (descritivo, ajuda a interpretar o pico)
    if "elemento" in sub:
        c = sub.groupby("elemento")["valor_empenhado"].agg(["size", "sum"]).rename(columns={"size": "linhas", "sum": "valor"})
        c["pct_valor"] = c["valor"] / c["valor"].sum()
        comp["elemento"] = c.reset_index().sort_values("valor", ascending=False)
    return {"exercicio_mes": em, "dezembro": dez, "resumo": resumo, "composicao": comp, "mes_maior": mes_maior}


def heatmap(res: dict, caminho) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    m = res["exercicio_mes"].pivot(index="exercicio", columns="mes", values="pct_valor_exercicio").reindex(columns=range(1, 13)).astype(float).fillna(0.0) * 100
    fig, ax = plt.subplots(figsize=(9, 0.45 * len(m) + 1.6), dpi=150)
    im = ax.imshow(m.values, cmap="Blues", aspect="auto", vmin=0)
    ax.set_xticks(range(12), [s[:3] for s in MESES])
    ax.set_yticks(range(len(m)), [str(i) for i in m.index])
    for i in range(m.shape[0]):
        for j in range(12):
            val = m.values[i, j]
            ax.text(j, i, f"{val:.0f}".replace(".", ","), ha="center", va="center", fontsize=7,
                    color="white" if val > m.values.max() * 0.6 else "black")
    ax.set_xlabel("Mês da data de emissão")
    ax.set_ylabel("Exercício")
    fig.colorbar(im, ax=ax, label="% do valor empenhado no exercício")
    fig.tight_layout()
    fig.savefig(caminho)
    plt.close(fig)

"""Leitura de arquivos de entrada (CSV/Excel, formato pt-BR) com cache em parquet.

Os arquivos de entrada são somente leitura. Saída: DataFrame com as colunas da origem
(unidade: linhas da extração), sem nenhuma transformação de conteúdo.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

CACHE_DIR = Path("data/interim")


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _linha_cabecalho(caminho: Path, nomes_esperados: set[str], max_linhas: int = 30) -> int:
    amostra = pd.read_excel(caminho, header=None, nrows=max_linhas, engine="openpyxl")
    melhor, idx = 0, 0
    for i, row in amostra.iterrows():
        vals = [str(v).strip() for v in row.tolist() if pd.notna(v)]
        # com perfil: linha com mais colunas do perfil; sem perfil: primeira linha com mais células de texto preenchidas
        acertos = len(set(vals) & nomes_esperados) if nomes_esperados else sum(not v.replace(".", "").replace(",", "").isdigit() for v in vals)
        if acertos > melhor:
            melhor, idx = acertos, i
    if melhor == 0:
        raise ValueError(f"Cabeçalho não localizado em {caminho.name}: nenhuma coluna do perfil encontrada")
    return int(idx)


def ler_arquivo(caminho: Path, perfil: dict) -> pd.DataFrame:
    """Lê um arquivo CSV ou Excel conforme o bloco `leitura` do perfil."""
    caminho = Path(caminho)
    leitura = perfil.get("leitura", {})
    esperados = set((perfil.get("colunas") or {}).values())
    for d in (perfil.get("derivacoes") or {}).values():
        esperados.add(d["coluna"])
    if caminho.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        h = _linha_cabecalho(caminho, esperados)
        df = pd.read_excel(caminho, header=h, engine="openpyxl")
        df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]
        df = df.dropna(how="all")
    else:
        df = pd.read_csv(
            caminho,
            sep=leitura.get("separador", ";"),
            encoding=leitura.get("encoding", "utf-8"),
            dtype=str,
            keep_default_na=False,
            na_values=[""],
        )
    df.columns = [str(c).strip() for c in df.columns]
    return df


def ler_entrada(caminhos: list[Path], perfil: dict, usar_cache: bool = True) -> tuple[pd.DataFrame, list[dict]]:
    """Lê e concatena vários arquivos. Retorna o DataFrame e a lista {arquivo, sha256, linhas}."""
    partes, info = [], []
    for c in sorted(Path(p) for p in caminhos):
        sha = sha256_arquivo(c)
        cache = CACHE_DIR / f"{sha[:16]}.parquet"
        if usar_cache and cache.exists():
            df = pd.read_parquet(cache)
        else:
            log.info("lendo %s", c.name)
            df = ler_arquivo(c, perfil)
            if usar_cache:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                df.astype({col: "string" for col in df.columns if df[col].dtype == object}).to_parquet(cache)
                df = pd.read_parquet(cache)
        partes.append(df)
        info.append({"arquivo": c.name, "sha256": sha, "linhas": int(len(df))})
    colunas = list(dict.fromkeys(col for p in partes for col in p.columns))
    df = pd.concat([p.reindex(columns=colunas) for p in partes], ignore_index=True)
    return df, info


def amostra_arquivo(caminho: Path, separador: str = ";", encoding: str = "utf-8", n: int = 200) -> pd.DataFrame:
    """Primeiras n linhas de dados (após o cabeçalho), para mapear colunas sem ler o arquivo inteiro."""
    caminho = Path(caminho)
    if caminho.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        h = _linha_cabecalho(caminho, set())
        df = pd.read_excel(caminho, header=h, nrows=n, engine="openpyxl")
        df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]
    else:
        df = pd.read_csv(caminho, sep=separador, encoding=encoding, dtype=str, nrows=n)
    df.columns = [str(c).strip() for c in df.columns]
    return df

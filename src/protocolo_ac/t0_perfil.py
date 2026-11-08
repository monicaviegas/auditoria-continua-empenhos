"""T0 – Perfil das colunas, aplicação do perfil de entrada e executabilidade.

Universo: arquivo integral (U_total). Unidade: linhas.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

import pandas as pd

from .canonico import CAMPOS, REQUISITOS, faltantes


def perfil_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por coluna da origem: tipo inferido, % de nulos, distintos, exemplo."""
    linhas = []
    n = len(df)
    for c in df.columns:
        s = df[c]
        nn = s.dropna()
        linhas.append({
            "coluna": c,
            "tipo_inferido": str(s.dtype),
            "pct_nulos": round(100 * (1 - len(nn) / n), 2) if n else 0.0,
            "valores_distintos": int(nn.nunique()),
        })
    return pd.DataFrame(linhas)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def sugerir_mapeamento(colunas: list[str]) -> dict[str, str]:
    """Sugere coluna de origem para cada campo canônico por similaridade de nomes (requer confirmação)."""
    normalizadas = {_norm(c): c for c in colunas}
    sugestao = {}
    for campo in CAMPOS:
        m = difflib.get_close_matches(campo, list(normalizadas), n=1, cutoff=0.5)
        if m:
            sugestao[campo] = normalizadas[m[0]]
    return sugestao


# ---------- normalizações ----------

def _num_ptbr(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float)
    t = s.astype("string").str.strip()
    t = t.str.replace(r"[R$\s]", "", regex=True)
    tem_virgula = t.str.contains(",", regex=False, na=False)
    t = t.where(~tem_virgula, t.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(t, errors="coerce")


def _data(s: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    return pd.to_datetime(s.astype("string"), errors="coerce", dayfirst=True)


def _codigo(s: pd.Series, digitos: int | None = None) -> pd.Series:
    t = s.astype("string").str.extract(r"^\s*(\d+)", expand=False)
    if digitos:
        t = t.str.zfill(digitos)
    return t


def aplicar_perfil(bruto: pd.DataFrame, perfil: dict) -> tuple[pd.DataFrame, dict]:
    """Converte a base de origem para o modelo canônico.

    Retorna (canonico, diagnostico). Conversões que falham ficam ausentes (NaN) e são contadas.
    """
    can = pd.DataFrame(index=bruto.index)
    diag: dict = {"falhas_conversao": {}, "derivacoes": {}, "valores_ausentes_declarados": {}}
    ausentes = {str(v).strip().upper() for v in perfil.get("valores_ausentes", [])}
    for campo, coluna in perfil.get("colunas", {}).items():
        if coluna not in bruto.columns:
            diag.setdefault("colunas_ausentes", []).append(f"{campo} <- {coluna}")
            continue
        s = bruto[coluna]
        if ausentes and not pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_datetime64_any_dtype(s):
            marc = s.astype("string").str.strip().str.upper().isin(ausentes)
            if marc.any():
                diag["valores_ausentes_declarados"][campo] = int(marc.sum())
                s = s.mask(marc)
        tipo = CAMPOS[campo]["tipo"]
        if tipo == "decimal":
            v = _num_ptbr(s)
        elif tipo == "date":
            v = _data(s)
        elif campo == "exercicio":
            v = pd.to_numeric(_codigo(s), errors="coerce").astype("Int64")
        elif campo == "gnd":
            v = pd.to_numeric(_codigo(s), errors="coerce").astype("Int64")
        elif campo in ("elemento", "modalidade_aplicacao"):
            v = _codigo(s, 2)
        elif campo == "unidade":
            v = _codigo(s)
            v = v.where(v.notna(), s.astype("string"))
        else:
            v = s.astype("string").str.strip()
            v = v.where(v != "", pd.NA)
        falhas = int(s.notna().sum() - v.notna().sum())
        if falhas:
            diag["falhas_conversao"][campo] = falhas
        can[campo] = v
    for campo, d in (perfil.get("derivacoes") or {}).items():
        if campo in can.columns or d["coluna"] not in bruto.columns:
            continue
        cod = bruto[d["coluna"]].astype("string").str.extract(r"^\s*(\d{8})", expand=False)
        can[campo] = cod.str.slice(d["inicio"], d["fim"])
        conf = {}
        for alvo, (i, f) in (d.get("conferir") or {}).items():
            if alvo not in can.columns:
                continue
            parte = cod.str.slice(i, f)
            alvo_s = can[alvo].astype("string").str.zfill(f - i)
            ok = parte.notna() & alvo_s.notna()
            conf[alvo] = {"comparadas": int(ok.sum()), "divergentes": int((parte[ok] != alvo_s[ok]).sum())}
        diag["derivacoes"][campo] = {"origem": d["coluna"], "linhas_com_codigo": int(cod.notna().sum()), "conferencia": conf}
    return can, diag


def executabilidade(presentes: set[str]) -> pd.DataFrame:
    linhas = []
    for proc, (desc, _req) in REQUISITOS.items():
        f = faltantes(proc, presentes)
        linhas.append({
            "procedimento": proc,
            "descricao": desc,
            "executavel": "sim" if not f else "não",
            "campos_faltantes": ", ".join(f) if f else "–",
        })
    return pd.DataFrame(linhas)


def campos_presentes(can: pd.DataFrame) -> set[str]:
    """Campo presente = coluna mapeada com ao menos um valor não nulo."""
    return {c for c in can.columns if can[c].notna().any()}


__all__ = ["perfil_colunas", "sugerir_mapeamento", "aplicar_perfil", "executabilidade", "campos_presentes"]

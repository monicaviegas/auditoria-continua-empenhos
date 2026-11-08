"""Interface de linha de comando: python -m protocolo_ac <perfil|rodar|preencher> ..."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .config import carregar_caso, carregar_params, carregar_perfil


def _entradas(padroes: list[str]) -> list[Path]:
    arqs: list[Path] = []
    for p in padroes:
        pp = Path(p)
        arqs.extend(sorted(pp.parent.glob(pp.name)) if any(ch in pp.name for ch in "*?[") else [pp])
    if not arqs:
        raise SystemExit("Nenhum arquivo de entrada encontrado")
    return arqs


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="protocolo_ac")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("perfil", help="T0: perfil das colunas e sugestão de mapeamento")
    a.add_argument("--entrada", nargs="+", required=True)

    b = sub.add_parser("rodar", help="executa T0–T7")
    b.add_argument("--entrada", nargs="+", required=True)
    b.add_argument("--perfil", required=True)
    b.add_argument("--params", default="config/params.yaml")
    b.add_argument("--caso", default="config/caso.yaml")
    b.add_argument("--saida", default="outputs")
    b.add_argument("--sem-cache", action="store_true")

    c = sub.add_parser("preencher", help="preenche o modelo-mestre do capítulo")
    c.add_argument("--run", required=True)
    c.add_argument("--modelo", nargs="+", required=True)
    c.add_argument("--caso", default="config/caso.yaml")
    c.add_argument("--extras", nargs="*", default=[], help="JSONs adicionais (ex.: avaliacao_sintetica.json)")

    args = ap.parse_args(argv)
    if args.cmd == "perfil":
        from .io import ler_arquivo
        from .t0_perfil import perfil_colunas, sugerir_mapeamento
        df = ler_arquivo(_entradas(args.entrada)[0], {"colunas": {}, "leitura": {}})
        print(perfil_colunas(df).to_string(index=False))
        print("\nSugestão de mapeamento (confirme e salve em config/perfis/<nome>.yaml):")
        print(json.dumps(sugerir_mapeamento(list(df.columns)), ensure_ascii=False, indent=2))
    elif args.cmd == "rodar":
        from .pipeline import executar
        run = executar(_entradas(args.entrada), carregar_perfil(args.perfil), carregar_params(args.params),
                       carregar_caso(args.caso), Path(args.saida), usar_cache=not args.sem_cache)
        print(run)
    elif args.cmd == "preencher":
        from .preencher import preencher
        extras: dict = {}
        for e in args.extras:
            extras.update(json.loads(Path(e).read_text(encoding="utf-8")))
        for m in args.modelo:
            print(preencher(Path(m), Path(args.run), carregar_caso(args.caso), extras))


if __name__ == "__main__":
    main()

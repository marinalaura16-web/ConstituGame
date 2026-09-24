"""Linha de comando.

    python -m robo.cli importar exportacao_expedit.xlsx
    python -m robo.cli triar
    python -m robo.cli resumo            # mostra na tela
    python -m robo.cli resumo --enviar   # envia por e-mail a cada responsável
    python -m robo.cli rodar-dia exportacao_expedit.xlsx --enviar
    python -m robo.cli painel
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .banco import Banco
from .config import carregar


def _triador(cfg, banco):
    from .fontes import drive
    from .fontes.advbox import PlanilhaAdvbox
    from .interpretador import Interpretador
    from .triagem import Triador

    advbox = PlanilhaAdvbox(cfg.planilha_advbox, cfg.planilhas["advbox"])
    if not advbox.carregada:
        print("aviso: planilha do Advbox não carregada (ADVBOX_PLANILHA no .env)", file=sys.stderr)
    return Triador(cfg, banco, Interpretador(cfg.providencias, cfg.modelo, cfg.esforco), advbox, drive.criar(cfg))


def cmd_importar(cfg, banco, arquivo: Path) -> None:
    from .fontes.expedit import importar_arquivo

    pubs, erros = importar_arquivo(arquivo, cfg.planilhas["expedit"])
    novas = sum(banco.inserir_publicacao(p) for p in pubs)
    print(f"{len(pubs)} publicações lidas, {novas} novas, {len(pubs) - novas} já existentes.")
    for e in erros:
        print(f"  ignorada — {e}", file=sys.stderr)


def cmd_triar(cfg, banco) -> None:
    feitas = _triador(cfg, banco).triar_pendentes()
    for t in feitas:
        prazo = f"interno {t.prazo.interno:%d/%m/%Y}" if t.prazo else "sem prazo"
        flag = " [TRIAGEM MANUAL]" if t.erro_interpretacao else ""
        print(f"- {t.publicacao_id}: {t.peca or t.providencia} ({prazo}) -> {t.responsavel}{flag}")
    print(f"{len(feitas)} publicação(ões) triada(s).")


def cmd_resumo(cfg, banco, enviar: bool) -> None:
    from . import resumo

    hoje = date.today()
    for resp in banco.responsaveis():
        texto, html = resumo.montar(banco.triagens(responsavel=resp), banco, hoje, cfg.painel_url)
        if enviar:
            if "@" not in resp:
                print(f"responsável '{resp}' não é e-mail; resumo não enviado", file=sys.stderr)
                continue
            resumo.enviar(cfg.smtp, resp, f"Publicações e prazos — {hoje:%d/%m/%Y}", texto, html)
            print(f"resumo enviado para {resp}")
        else:
            print(f"\n===== {resp} =====\n{texto}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="robo", description="Triagem de publicações previdenciárias")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("importar").add_argument("arquivo", type=Path)
    sub.add_parser("triar")
    r = sub.add_parser("resumo")
    r.add_argument("--enviar", action="store_true")
    d = sub.add_parser("rodar-dia", help="importar + triar + resumo")
    d.add_argument("arquivo", type=Path)
    d.add_argument("--enviar", action="store_true")
    p = sub.add_parser("painel")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--porta", type=int, default=8000)
    a = ap.parse_args(argv)

    cfg = carregar()
    banco = Banco(cfg.banco)
    if a.cmd == "importar":
        cmd_importar(cfg, banco, a.arquivo)
    elif a.cmd == "triar":
        cmd_triar(cfg, banco)
    elif a.cmd == "resumo":
        cmd_resumo(cfg, banco, a.enviar)
    elif a.cmd == "rodar-dia":
        cmd_importar(cfg, banco, a.arquivo)
        cmd_triar(cfg, banco)
        cmd_resumo(cfg, banco, a.enviar)
    elif a.cmd == "painel":
        import uvicorn

        from .web.app import criar_app

        uvicorn.run(criar_app(cfg, banco), host=a.host, port=a.porta)


if __name__ == "__main__":
    main()

"""Linha de comando.

    python -m robo.cli djen --oab 12345/PR --de 23/09/2026 --ate 24/09/2026 [--interpretar]
    python -m robo.cli interpretar publicacao.txt --disponibilizacao 24/09/2026
    python -m robo.cli importar exportacao_expedit.xlsx
    python -m robo.cli triar
    python -m robo.cli resumo            # mostra na tela
    python -m robo.cli resumo --enviar   # envia por e-mail a cada responsável
    python -m robo.cli rodar-dia exportacao_expedit.xlsx --enviar
    python -m robo.cli painel
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

from .banco import Banco
from .config import carregar


def _exigir_chave() -> None:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        sys.exit(
            "Falta a chave da IA. Crie uma em https://console.anthropic.com (API Keys) e coloque "
            "ANTHROPIC_API_KEY=... no arquivo .env ou nas variáveis de ambiente."
        )


def _triador(cfg, banco):
    from .fontes import drive
    from .fontes.advbox import PlanilhaAdvbox
    from .interpretador import Interpretador
    from .triagem import Triador

    _exigir_chave()
    advbox = PlanilhaAdvbox(None, cfg.planilhas["advbox"])
    drv = None
    if cfg.etapa >= 2:
        advbox = PlanilhaAdvbox(cfg.planilha_advbox, cfg.planilhas["advbox"])
        if not advbox.carregada:
            print("aviso: planilha do Advbox não carregada (ADVBOX_PLANILHA no .env)", file=sys.stderr)
        drv = drive.criar(cfg)
    return Triador(cfg, banco, Interpretador(cfg.providencias, cfg.modelo, cfg.esforco), advbox, drv)


def cmd_interpretar(cfg, banco, arquivo: Path | None, disponibilizacao: str | None, tribunal: str | None) -> None:
    """Etapa 1 sem Expedit: cola-se o texto de uma publicação e vê-se peça e prazo na hora."""
    from .modelos import Publicacao

    if arquivo:
        texto = arquivo.read_text(encoding="utf-8")
    else:
        print("Cole o texto da publicação e termine com uma linha vazia seguida de Ctrl+D (Ctrl+Z no Windows):",
              file=sys.stderr)
        texto = sys.stdin.read()
    if not texto.strip():
        sys.exit("texto vazio")
    disp = datetime.strptime(disponibilizacao, "%d/%m/%Y").date() if disponibilizacao else date.today()
    pub = Publicacao(id=f"manual-{datetime.now():%Y%m%d%H%M%S}", data_disponibilizacao=disp,
                     tribunal=tribunal, texto=texto, origem="manual")
    banco.inserir_publicacao(pub)
    t = _triador(cfg, banco).triar(pub)
    banco.salvar_triagem(t)
    _imprimir(t)


ORIGENS = {"publicacao": "prazo dado na publicação", "padrao_do_escritorio": "prazo legal padrão",
           "seguranca": "prazo de segurança — confirmar"}


def _imprimir(t) -> None:
    i = t.interpretacao
    print("\n" + "=" * 70)
    if t.erro_interpretacao:
        print(f"TRIAGEM MANUAL: {t.erro_interpretacao}")
    if i:
        print(f"RESUMO: {i.resumo}")
        print(f"ATO: {i.tipo_ato} | RITO: {i.rito} | CONFIANÇA DA IA: {i.confianca}")
        print(f"TRECHO: \"{i.trecho_determinante}\"")
    print(f"PEÇA: {t.peca or 'sem peça'}")
    if t.prazo:
        p = t.prazo
        print(f"PRAZO: {p.dias} dias {'úteis' if p.contagem == 'uteis' else 'corridos'} "
              f"({ORIGENS[p.origem]}), contando de {p.inicio_contagem:%d/%m/%Y}")
        print(f"PRAZO FATAL:   {p.fatal:%d/%m/%Y}{'  <<< VENCIDO' if p.vencido else ''}")
        print(f"PRAZO INTERNO: {p.interno:%d/%m/%Y}")
    if i and i.pontos_de_atencao:
        print("ATENÇÃO: " + " | ".join(i.pontos_de_atencao))
    print("-" * 70)
    for item in t.checklist:
        print(f"[ ] {item.titulo}\n    {item.detalhe}")
    print("=" * 70)


def cmd_djen(cfg, banco, oabs: list[str], de: str | None, ate: str | None, interpretar: bool) -> None:
    """Baixa do DJEN as publicações das OABs do escritório e grava as novas."""
    from datetime import timedelta

    from .fontes.djen import OAB, ClienteDJEN, ErroDJEN

    oabs = oabs or [o for o in os.environ.get("DJEN_OABS", "").split(",") if o.strip()]
    if not oabs:
        sys.exit("Informe --oab 12345/PR ou DJEN_OABS=12345/PR,6789/SC no .env")
    br = lambda s: datetime.strptime(s, "%d/%m/%Y").date()  # noqa: E731
    fim = br(ate) if ate else date.today()
    inicio = br(de) if de else fim - timedelta(days=3)  # cobre fim de semana/feriado
    bruto = cfg.banco.parent / "djen_ultima_resposta.json"
    cliente = ClienteDJEN(salvar_bruto=bruto)
    novas = []
    for texto in oabs:
        oab = OAB.de_texto(texto)
        try:
            pubs = cliente.buscar(oab, inicio, fim)
        except ErroDJEN as e:
            sys.exit(f"Falha no DJEN para OAB {oab.numero}/{oab.uf}: {e}")
        n = [p for p in pubs if banco.inserir_publicacao(p)]
        novas += n
        print(f"OAB {oab.numero}/{oab.uf}: {len(pubs)} publicações de {inicio:%d/%m} a {fim:%d/%m}, {len(n)} novas.")
    for p in novas:
        print(f"  - {p.data_disponibilizacao:%d/%m/%Y} {p.tribunal or ''} {p.numero_processo or ''} — {p.cliente_nome or 'cliente ?'}")
    print(f"(resposta bruta do DJEN salva em {bruto})")
    if interpretar and novas:
        triador = _triador(cfg, banco)
        for p in novas:
            t = triador.triar(p)
            banco.salvar_triagem(t)
            print(f"\n>>> {p.numero_processo or p.id} — {p.cliente_nome or ''}")
            _imprimir(t)


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
    dj = sub.add_parser("djen", help="baixar publicações do DJEN pelas OABs do escritório")
    dj.add_argument("--oab", action="append", default=[], help="12345/PR (pode repetir)")
    dj.add_argument("--de", help="DD/MM/AAAA (padrão: 3 dias atrás)")
    dj.add_argument("--ate", help="DD/MM/AAAA (padrão: hoje)")
    dj.add_argument("--interpretar", action="store_true", help="já passar pela IA e calcular prazo")
    i = sub.add_parser("interpretar", help="colar/ler UMA publicação e ver peça e prazo")
    i.add_argument("arquivo", type=Path, nargs="?")
    i.add_argument("--disponibilizacao", help="DD/MM/AAAA (padrão: hoje)")
    i.add_argument("--tribunal", help="ex.: TRF4, JEF, TJSP — define o calendário de feriados")
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
    if a.cmd == "djen":
        cmd_djen(cfg, banco, a.oab, a.de, a.ate, a.interpretar)
    elif a.cmd == "interpretar":
        cmd_interpretar(cfg, banco, a.arquivo, a.disponibilizacao, a.tribunal)
    elif a.cmd == "importar":
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

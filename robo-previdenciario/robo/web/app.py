"""Painel web: fila de publicações triadas, checklist e registro de teste de senha."""
from __future__ import annotations

import secrets
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from ..banco import Banco
from ..config import Config, carregar
from ..texto import normalizar_cpf

seguranca = HTTPBasic()


def criar_app(cfg: Config | None = None, banco: Banco | None = None) -> FastAPI:
    cfg = cfg or carregar()
    banco = banco or Banco(cfg.banco)
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    templates.env.filters["br"] = lambda d: d.strftime("%d/%m/%Y") if d else "—"
    app = FastAPI(title="Robô de triagem previdenciária", docs_url=None, redoc_url=None)

    def usuario(cred: HTTPBasicCredentials = Depends(seguranca)) -> str:
        """Login único do escritório; o nome digitado identifica quem marcou cada passo."""
        if not cfg.painel_senha:
            raise HTTPException(503, "Defina PAINEL_SENHA no .env para liberar o painel.")
        if not secrets.compare_digest(cred.password.encode(), cfg.painel_senha.encode()):
            raise HTTPException(401, "Senha incorreta", headers={"WWW-Authenticate": "Basic"})
        return cred.username

    @app.get("/", response_class=HTMLResponse)
    def fila(request: Request, responsavel: str | None = None, concluidas: bool = False, quem: str = Depends(usuario)):
        triagens = banco.triagens(responsavel=responsavel, incluir_concluidas=concluidas)
        linhas = [(t, banco.publicacao(t.publicacao_id)) for t in triagens]
        return templates.TemplateResponse(request, "fila.html", {
            "linhas": linhas, "responsaveis": banco.responsaveis(), "filtro": responsavel,
            "concluidas": concluidas, "hoje": date.today(), "quem": quem,
            "providencias": cfg.providencias,
        })

    @app.get("/p/{pid}", response_class=HTMLResponse)
    def detalhe(request: Request, pid: str, quem: str = Depends(usuario)):
        t, pub = banco.triagem(pid), banco.publicacao(pid)
        if not t or not pub:
            raise HTTPException(404)
        cpf = pub.cliente_cpf
        return templates.TemplateResponse(request, "detalhe.html", {
            "t": t, "pub": pub, "hoje": date.today(), "quem": quem,
            "testes": banco.testes_senha(cpf) if cpf else [],
            "providencias": cfg.providencias,
        })

    @app.post("/p/{pid}/item/{item_id}")
    def marcar(pid: str, item_id: str, quem: str = Depends(usuario)):
        t = banco.triagem(pid)
        if not t:
            raise HTTPException(404)
        for item in t.checklist:
            if item.id == item_id:
                item.feito = not item.feito
                item.feito_por = quem if item.feito else None
        banco.salvar_triagem(t)
        return RedirectResponse(f"/p/{pid}", status_code=303)

    @app.post("/p/{pid}/concluir")
    def concluir(pid: str, quem: str = Depends(usuario)):
        t = banco.triagem(pid)
        if not t:
            raise HTTPException(404)
        t.concluida = not t.concluida
        banco.salvar_triagem(t)
        return RedirectResponse("/" if t.concluida else f"/p/{pid}", status_code=303)

    @app.post("/p/{pid}/reclassificar")
    def reclassificar(pid: str, providencia: str = Form(...), quem: str = Depends(usuario)):
        """O advogado corrige a classificação da IA; prazo e checklist são refeitos."""
        from ..triagem import Triador  # import tardio: evita ciclo com o CLI
        from ..fontes import drive as drive_mod
        from ..fontes.advbox import PlanilhaAdvbox

        pub, anterior = banco.publicacao(pid), banco.triagem(pid)
        if not pub or not anterior or providencia not in cfg.providencias:
            raise HTTPException(400)

        class Fixo:  # reaproveita a leitura da IA, trocando só a providência
            def interpretar(self, _):
                if anterior.interpretacao is None:
                    from ..interpretador import InterpretacaoFalhou
                    raise InterpretacaoFalhou("reclassificado manualmente sem leitura da IA")
                return anterior.interpretacao.model_copy(update={"providencia": providencia, "confianca": "alta"})

        advbox = PlanilhaAdvbox(cfg.planilha_advbox, cfg.planilhas["advbox"])
        nova = Triador(cfg, banco, Fixo(), advbox, drive_mod.criar(cfg)).triar(pub)
        nova.providencia, nova.peca = providencia, cfg.providencias[providencia].get("peca")
        banco.salvar_triagem(nova)
        return RedirectResponse(f"/p/{pid}", status_code=303)

    @app.post("/senha")
    def registrar_senha(
        cpf: str = Form(...), resultado: str = Form(...), observacao: str = Form(""),
        voltar: str = Form("/"), quem: str = Depends(usuario),
    ):
        if resultado not in ("funcionou", "falhou", "nova_senha_agencia"):
            raise HTTPException(400)
        banco.registrar_teste_senha(normalizar_cpf(cpf), resultado, quem, observacao or None)
        # Atualiza o item de senha de todas as triagens abertas deste CPF.
        from ..triagem import avaliar_senha_govbr
        for t in banco.triagens():
            pub = banco.publicacao(t.publicacao_id)
            if pub and pub.cliente_cpf == normalizar_cpf(cpf):
                av = avaliar_senha_govbr(banco.testes_senha(pub.cliente_cpf), False, date.today(),
                                         cfg.data_migracao, cfg.fluxos.get("senha_valida_por_dias", 30))
                for item in t.checklist:
                    if item.id == "senha_govbr":
                        item.status, item.detalhe = av.status, av.detalhe
                banco.salvar_triagem(t)
        destino = voltar if voltar.startswith("/") and not voltar.startswith("//") else "/"
        return RedirectResponse(destino, status_code=303)

    return app

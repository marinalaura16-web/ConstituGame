from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

from robo.banco import Banco
from robo.config import carregar
from robo.fontes.advbox import PlanilhaAdvbox
from robo.fontes.drive import DriveLocal
from robo.fontes.expedit import importar_arquivo
from robo.interpretador import InterpretacaoFalhou
from robo.modelos import Interpretacao
from robo.triagem import Triador, avaliar_senha_govbr

EXEMPLO = Path(__file__).resolve().parent.parent / "exemplos" / "expedit_exemplo.csv"
HOJE = date(2026, 9, 24)


def interp(**kw):
    base = dict(
        resumo="r", tipo_ato="despacho", providencia="manifestacao_laudo", prazo_dias_informado=15,
        contagem_informada=None, rito="jef", numero_processo=None, cliente_nome=None, beneficio=None,
        documentos_mencionados=[], pontos_de_atencao=[], trecho_determinante="t", confianca="alta",
    )
    base.update(kw)
    return Interpretacao(**base)


class IAFalsa:
    def __init__(self, respostas):
        self.respostas = respostas

    def interpretar(self, pub):
        r = self.respostas[pub.id]
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def ambiente(tmp_path):
    cfg = carregar()
    banco = Banco(tmp_path / "t.db")
    wb = Workbook()
    ws = wb.active
    ws.append(["Nome", "CPF", "Processo", "Telefone", "Endereço", "Benefício", "NB", "Senha INSS"])
    ws.append(["MARIA APARECIDA DA SILVA", 12345678909, "5001234-56.2026.4.04.7000", "(41) 99999-0000",
               "Rua A, 1", "Aux. incapacidade", "123", "segredo123"])
    ws.append(["Joao Pereira", "98765432100", "", "", "", "", "", ""])
    xlsx = tmp_path / "advbox.xlsx"
    wb.save(xlsx)
    advbox = PlanilhaAdvbox(xlsx, cfg.planilhas["advbox"])

    pasta = tmp_path / "drive" / "Maria Aparecida da Silva - 123.456.789-09"
    pasta.mkdir(parents=True)
    (pasta / "Laudo pericial evento 32.pdf").write_text("x")
    drive = DriveLocal(tmp_path / "drive")
    return cfg, banco, advbox, drive


def test_importa_csv_do_expedit():
    cfg = carregar()
    pubs, erros = importar_arquivo(EXEMPLO, cfg.planilhas["expedit"])
    assert not erros
    assert [p.id for p in pubs] == ["1001", "1002", "1003"]
    assert pubs[0].cliente_cpf == "12345678909"
    assert pubs[0].data_disponibilizacao == date(2026, 9, 24)


def test_triagem_completa(ambiente):
    cfg, banco, advbox, drive = ambiente
    pubs, _ = importar_arquivo(EXEMPLO, cfg.planilhas["expedit"])
    for p in pubs:
        banco.inserir_publicacao(p)
    ia = IAFalsa({
        "1001": interp(),
        "1002": interp(providencia="apelacao", prazo_dias_informado=None, rito="comum"),
        "1003": InterpretacaoFalhou("teste"),
    })
    triagens = {t.publicacao_id: t for t in Triador(cfg, banco, ia, advbox, drive).triar_pendentes(HOJE)}

    laudo = triagens["1001"]
    assert laudo.peca == "Manifestação sobre o laudo pericial"
    assert laudo.prazo.fatal == date(2026, 10, 19)
    assert laudo.prazo.interno == date(2026, 10, 15)
    itens = {i.id: i for i in laudo.checklist}
    assert itens["drive"].status == "atencao"          # laudo achado, documentos médicos não
    assert "Laudo pericial" in itens["drive"].detalhe
    assert itens["advbox"].status == "ok"
    assert "NÃO é preciso ligar" in itens["advbox"].detalhe
    assert "segredo123" not in laudo.model_dump_json()  # senha nunca vaza
    assert "senha_govbr" not in itens                   # laudo não exige Meu INSS

    apel = triagens["1002"]
    assert apel.prazo.origem == "padrao_do_escritorio" and apel.prazo.dias == 15
    assert apel.prazo.fatal == date(2026, 10, 19) and apel.prazo.interno == date(2026, 10, 14)  # margem 3
    itens = {i.id: i for i in apel.checklist}
    assert itens["advbox"].status == "atencao" and "telefone" in itens["advbox"].detalhe

    falha = triagens["1003"]
    assert falha.providencia == "outro" and falha.prazo.origem == "seguranca"
    assert any(i.id == "peca" and i.status == "atencao" for i in falha.checklist)


def test_senha_regras():
    mig, hoje = date(2026, 6, 1), date(2026, 9, 24)
    assert avaliar_senha_govbr([], True, hoje, mig, 30).status == "pendente"
    assert avaliar_senha_govbr([], False, hoje, mig, 30).status == "atencao"
    ok = [{"resultado": "funcionou", "testado_em": "2026-09-20", "testado_por": "ana"}]
    assert avaliar_senha_govbr(ok, False, hoje, mig, 30).status == "ok"
    velho = [{"resultado": "funcionou", "testado_em": "2026-07-01", "testado_por": None}]
    assert avaliar_senha_govbr(velho, False, hoje, mig, 30).status == "pendente"
    duas = [{"resultado": "falhou", "testado_em": "2026-09-22", "testado_por": None}] * 2
    assert "agência" in avaliar_senha_govbr(duas, False, hoje, mig, 30).detalhe


def test_painel(ambiente, monkeypatch):
    from fastapi.testclient import TestClient

    from robo.web.app import criar_app

    cfg, banco, advbox, drive = ambiente
    cfg.painel_senha = "x"
    pubs, _ = importar_arquivo(EXEMPLO, cfg.planilhas["expedit"])
    banco.inserir_publicacao(pubs[0])
    Triador(cfg, banco, IAFalsa({"1001": interp()}), advbox, drive).triar_pendentes(HOJE)
    c = TestClient(criar_app(cfg, banco))
    assert c.get("/").status_code == 401
    auth = ("ana", "x")
    assert "Maria Aparecida" in c.get("/", auth=auth).text
    assert "Checklist do fluxo" in c.get("/p/1001", auth=auth).text
    c.post("/p/1001/item/sistema", auth=auth)
    assert banco.triagem("1001").checklist[0].feito_por == "ana"
    c.post("/senha", auth=auth, data={"cpf": "12345678909", "resultado": "falhou"})
    assert banco.testes_senha("12345678909")[0]["resultado"] == "falhou"

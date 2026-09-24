import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from robo.fontes.djen import OAB, ClienteDJEN, converter


def item(i):
    return {
        "id": 1000 + i,
        "data_disponibilizacao": "2026-09-24",
        "siglaTribunal": "TRF4",
        "tipoComunicacao": "Intimação",
        "nomeOrgao": "1ª Vara Federal de Curitiba / JEF",
        "texto": "<p>Intime-se a parte autora para, no prazo de 15 dias,<br>manifestar-se sobre o laudo.</p>",
        "numero_processo": "50012345620264047000",
        "numeroprocessocommascara": "5001234-56.2026.4.04.7000",
        "tipoDocumento": "Despacho",
        "nomeClasse": "PROCEDIMENTO DO JUIZADO ESPECIAL CÍVEL",
        "destinatarios": [
            {"nome": "INSTITUTO NACIONAL DO SEGURO SOCIAL - INSS", "polo": "P"},
            {"nome": "MARIA APARECIDA DA SILVA", "polo": "A"},
        ],
        "destinatarioadvogados": [{"advogado": {"nome": "FULANA ADVOGADA", "numero_oab": "12345", "uf_oab": "PR"}}],
    }


class DJENFalso(BaseHTTPRequestHandler):
    chamadas = []

    def do_GET(self):
        q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        DJENFalso.chamadas.append(q)
        if len(DJENFalso.chamadas) == 1:  # primeira chamada: "muitas requisições"
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.end_headers()
            return
        pagina = int(q["pagina"])
        total = 130
        ini = (pagina - 1) * 100
        itens = [item(i) for i in range(ini, min(ini + 100, total))]
        corpo = json.dumps({"status": "success", "count": total, "items": itens}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


@pytest.fixture
def servidor():
    DJENFalso.chamadas = []
    srv = HTTPServer(("127.0.0.1", 0), DJENFalso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/api/v1/comunicacao"
    srv.shutdown()


def test_oab():
    assert OAB.de_texto("12345/PR") == OAB("12345", "PR")
    assert OAB.de_texto("PR 12345") == OAB("12345", "PR")
    with pytest.raises(ValueError):
        OAB.de_texto("abc")


def test_converter_item():
    p = converter(item(0))
    assert p.id == "djen-1000"
    assert p.numero_processo == "5001234-56.2026.4.04.7000"
    assert p.cliente_nome == "MARIA APARECIDA DA SILVA"  # ignora o INSS
    assert p.data_disponibilizacao == date(2026, 9, 24)
    assert "<p>" not in p.texto and "manifestar-se sobre o laudo" in p.texto
    assert "FULANA ADVOGADA (OAB 12345/PR)" in p.texto


def test_busca_paginada_com_retentativa(servidor, tmp_path):
    bruto = tmp_path / "bruto.json"
    pubs = ClienteDJEN(url=servidor, pausa=0, salvar_bruto=bruto).buscar(
        OAB("12345", "PR"), date(2026, 9, 24), date(2026, 9, 24))
    assert len(pubs) == 130
    q = DJENFalso.chamadas[-1]
    assert q["numeroOab"] == "12345" and q["ufOab"] == "PR" and q["dataDisponibilizacaoInicio"] == "2026-09-24"
    assert [c["pagina"] for c in DJENFalso.chamadas] == ["1", "1", "2"]  # 429, depois páginas 1 e 2
    assert len(json.loads(bruto.read_text())) == 130

"""Busca direta no DJEN (Diário de Justiça Eletrônico Nacional — CNJ).

Usa a consulta pública de comunicações processuais (sem login):
    GET https://comunicaapi.pje.jus.br/api/v1/comunicacao
        ?numeroOab=12345&ufOab=PR
        &dataDisponibilizacaoInicio=AAAA-MM-DD&dataDisponibilizacaoFim=AAAA-MM-DD
        &pagina=1&itensPorPagina=100

Os nomes dos campos da resposta variam um pouco entre versões da API, por isso
cada campo é lido por uma lista de apelidos. Use `salvar_bruto` na primeira
execução real para conferir.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..modelos import Publicacao
from ..texto import normalizar_nome

URL = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
POR_PAGINA = 100

# Partes que nunca são o nosso cliente (o escritório representa o segurado).
NAO_CLIENTES = ("INSTITUTO NACIONAL DO SEGURO SOCIAL", "INSS", "UNIAO", "FAZENDA NACIONAL", "MINISTERIO PUBLICO")


class ErroDJEN(Exception):
    pass


@dataclass
class OAB:
    numero: str
    uf: str

    @classmethod
    def de_texto(cls, s: str) -> "OAB":
        """Aceita '12345/PR', '12345-PR' ou 'PR12345'."""
        s = s.strip().upper().replace("OAB", "").strip()
        m = re.fullmatch(r"(\d+)\s*[/\-\s]\s*([A-Z]{2})", s) or re.fullmatch(r"([A-Z]{2})\s*(\d+)", s)
        if not m:
            raise ValueError(f"OAB inválida: {s!r} (use 12345/PR)")
        a, b = m.groups()
        return cls(numero=a, uf=b) if a.isdigit() else cls(numero=b, uf=a)


def _campo(item: dict, *nomes, padrao=None):
    for n in nomes:
        if item.get(n) not in (None, ""):
            return item[n]
    return padrao


def _limpar_html(texto: str) -> str:
    texto = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", texto or "")
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = html.unescape(texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    return re.sub(r"\n\s*\n+", "\n\n", texto).strip()


def _data(valor) -> date:
    return date.fromisoformat(str(valor)[:10])


def _cliente(item: dict) -> str | None:
    """Primeira parte do polo ativo que não seja o INSS/ente público."""
    partes = _campo(item, "destinatarios", padrao=[]) or []
    candidatas = sorted(partes, key=lambda p: 0 if str(p.get("polo", "")).upper() in ("A", "ATIVO") else 1)
    for p in candidatas:
        nome = p.get("nome") or ""
        if nome and not any(x in normalizar_nome(nome) for x in NAO_CLIENTES):
            return nome.strip()
    return None


def _advogados(item: dict) -> list[str]:
    saida = []
    for d in _campo(item, "destinatarioadvogados", "destinatarioAdvogados", padrao=[]) or []:
        adv = d.get("advogado", d)
        if adv.get("nome"):
            saida.append(f"{adv['nome']} (OAB {adv.get('numero_oab', '?')}/{adv.get('uf_oab', '?')})")
    return saida


def converter(item: dict) -> Publicacao:
    processo = _campo(item, "numeroprocessocommascara", "numero_processo", "numeroProcesso")
    texto = _limpar_html(_campo(item, "texto", "conteudo", padrao=""))
    cabecalho = [
        f"Tipo: {_campo(item, 'tipoComunicacao', 'tipo_comunicacao', padrao='')}",
        f"Documento: {_campo(item, 'tipoDocumento', 'tipo_documento', padrao='')}",
        f"Classe: {_campo(item, 'nomeClasse', 'nome_classe', padrao='')}",
    ]
    advs = _advogados(item)
    if advs:
        cabecalho.append("Advogados intimados: " + "; ".join(advs))
    return Publicacao(
        id=f"djen-{_campo(item, 'id', 'hash')}",
        data_disponibilizacao=_data(_campo(item, "data_disponibilizacao", "datadisponibilizacao", "dataDisponibilizacao")),
        numero_processo=processo and str(processo),
        cliente_nome=_cliente(item),
        tribunal=_campo(item, "siglaTribunal", "sigla_tribunal"),
        orgao=_campo(item, "nomeOrgao", "nome_orgao"),
        texto="\n".join(c for c in cabecalho if not c.endswith(": ")) + "\n\n" + texto,
        origem="djen",
    )


class ClienteDJEN:
    def __init__(self, url: str = URL, pausa: float = 1.0, tentativas: int = 4, salvar_bruto: Path | None = None):
        self.url, self.pausa, self.tentativas, self.salvar_bruto = url, pausa, tentativas, salvar_bruto

    def _get(self, params: dict) -> dict:
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "robo-previdenciario/1.0"})
        espera = 2.0
        for tentativa in range(1, self.tentativas + 1):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                # 429 = muitas consultas seguidas; 5xx = instabilidade do CNJ. Espera e tenta de novo.
                if e.code in (429, 500, 502, 503, 504) and tentativa < self.tentativas:
                    time.sleep(float(e.headers.get("Retry-After") or espera))
                    espera *= 2
                    continue
                raise ErroDJEN(f"DJEN respondeu {e.code} para {url}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                if tentativa < self.tentativas:
                    time.sleep(espera)
                    espera *= 2
                    continue
                raise ErroDJEN(f"sem acesso ao DJEN ({e})") from e
        raise ErroDJEN("DJEN indisponível")

    def buscar(self, oab: OAB, inicio: date, fim: date) -> list[Publicacao]:
        publicacoes, pagina, brutos = {}, 1, []
        while True:
            dados = self._get({
                "numeroOab": oab.numero, "ufOab": oab.uf,
                "dataDisponibilizacaoInicio": inicio.isoformat(), "dataDisponibilizacaoFim": fim.isoformat(),
                "pagina": pagina, "itensPorPagina": POR_PAGINA,
            })
            itens = _campo(dados, "items", "itens", padrao=[]) or []
            brutos += itens
            for item in itens:
                p = converter(item)
                publicacoes[p.id] = p
            total = int(_campo(dados, "count", "total", padrao=0) or 0)
            if not itens or len(itens) < POR_PAGINA or (total and pagina * POR_PAGINA >= total):
                break
            pagina += 1
            time.sleep(self.pausa)
        if self.salvar_bruto:
            self.salvar_bruto.parent.mkdir(parents=True, exist_ok=True)
            self.salvar_bruto.write_text(json.dumps(brutos, ensure_ascii=False, indent=2), encoding="utf-8")
        return list(publicacoes.values())


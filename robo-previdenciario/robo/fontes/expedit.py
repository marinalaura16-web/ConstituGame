"""Entrada de publicações vindas do Expedit.

Hoje: importação do arquivo exportado pelo Expedit (CSV/XLSX).
O Expedit não publica uma API aberta; se o fornecedor liberar acesso (API ou
webhook), basta implementar `ExpeditAPI.buscar` devolvendo `Publicacao`.
"""
from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from ..modelos import Publicacao
from ..texto import normalizar_cpf
from .planilha import ler_linhas, mapear, para_data


def importar_arquivo(caminho: Path, cfg_planilha: dict) -> tuple[list[Publicacao], list[str]]:
    """Lê a exportação. Devolve (publicações, erros por linha)."""
    publicacoes, erros = [], []
    for n, linha in enumerate(ler_linhas(caminho, cfg_planilha.get("aba")), start=2):
        dados = mapear(linha, cfg_planilha["colunas"])
        try:
            texto = dados.get("texto")
            if not texto:
                raise ValueError("sem texto da publicação")
            disp = para_data(dados.get("data_disponibilizacao"))
            if not disp:
                raise ValueError("sem data de disponibilização")
            ident = dados.get("id") or _id_estavel(dados.get("numero_processo"), disp, str(texto))
            publicacoes.append(
                Publicacao(
                    id=str(ident),
                    data_disponibilizacao=disp,
                    data_publicacao=para_data(dados.get("data_publicacao")),
                    numero_processo=dados.get("numero_processo") and str(dados["numero_processo"]),
                    cliente_nome=dados.get("cliente_nome"),
                    cliente_cpf=normalizar_cpf(dados.get("cliente_cpf")) or None,
                    tribunal=dados.get("tribunal"),
                    orgao=dados.get("orgao"),
                    texto=str(texto),
                    responsavel=dados.get("responsavel"),
                )
            )
        except ValueError as e:
            erros.append(f"linha {n}: {e}")
    return publicacoes, erros


def _id_estavel(processo: object, disp: date, texto: str) -> str:
    """Sem ID no arquivo, gera um a partir do conteúdo para não importar em dobro."""
    base = f"{processo}|{disp.isoformat()}|{texto.strip()[:2000]}"
    return "exp-" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


class ExpeditAPI:
    """Ponto de extensão para quando o Expedit liberar integração."""

    def buscar(self, desde: date) -> list[Publicacao]:
        raise NotImplementedError(
            "Solicite ao suporte do Expedit acesso à API/webhook de publicações e implemente aqui."
        )

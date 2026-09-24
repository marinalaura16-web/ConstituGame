"""Consulta à planilha antiga do Advbox, para não ligar para o cliente à toa."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..texto import normalizar_cpf, normalizar_nome, normalizar_processo
from .planilha import ler_linhas, mapear


@dataclass
class FichaAdvbox:
    dados: dict            # campos visíveis (sem os sigilosos)
    tem_senha_govbr: bool  # só informa se consta, nunca o valor
    faltando: list[str]    # campos essenciais vazios -> motivo real para contatar o cliente
    encontrado_por: str


class PlanilhaAdvbox:
    def __init__(self, caminho: Path | None, cfg: dict):
        self.cfg = cfg
        self.registros: list[dict] = []
        if caminho and Path(caminho).exists():
            self.registros = [mapear(l, cfg["colunas"]) for l in ler_linhas(caminho, cfg.get("aba"))]
        self._por_cpf = {normalizar_cpf(r.get("cpf")): r for r in self.registros if r.get("cpf")}
        self._por_processo: dict[str, dict] = {}
        for r in self.registros:
            # A célula de processo pode ter mais de um número separado por ; , ou quebra de linha.
            for numero in str(r.get("processo") or "").replace(";", "\n").replace(",", "\n").splitlines():
                if normalizar_processo(numero):
                    self._por_processo[normalizar_processo(numero)] = r
        self._por_nome = {normalizar_nome(r.get("nome")): r for r in self.registros if r.get("nome")}

    @property
    def carregada(self) -> bool:
        return bool(self.registros)

    def buscar(self, *, cpf: str | None = None, processo: str | None = None, nome: str | None = None) -> FichaAdvbox | None:
        tentativas = [
            ("CPF", self._por_cpf.get(normalizar_cpf(cpf)) if cpf else None),
            ("nº do processo", self._por_processo.get(normalizar_processo(processo)) if processo else None),
            ("nome", self._por_nome.get(normalizar_nome(nome)) if nome else None),
        ]
        for criterio, registro in tentativas:
            if registro:
                return self._ficha(registro, criterio)
        return None

    def _ficha(self, r: dict, criterio: str) -> FichaAdvbox:
        sigilosos = set(self.cfg.get("sigilosos", []))
        visiveis = {k: v for k, v in r.items() if k not in sigilosos and v not in (None, "")}
        faltando = [c for c in self.cfg.get("essenciais", []) if r.get(c) in (None, "")]
        return FichaAdvbox(
            dados=visiveis,
            tem_senha_govbr=bool(r.get("senha_govbr")),
            faltando=faltando,
            encontrado_por=criterio,
        )

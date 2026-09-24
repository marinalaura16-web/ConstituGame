"""Estruturas de dados que circulam pelo robô."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["ok", "pendente", "atencao", "nao_se_aplica"]


class Publicacao(BaseModel):
    id: str
    data_disponibilizacao: date
    data_publicacao: date | None = None
    numero_processo: str | None = None
    cliente_nome: str | None = None
    cliente_cpf: str | None = None
    tribunal: str | None = None
    orgao: str | None = None
    texto: str
    responsavel: str | None = None
    origem: str = "expedit"


class Interpretacao(BaseModel):
    """O que a IA extraiu da publicação. As datas são calculadas pelo código, não pela IA."""

    resumo: str
    tipo_ato: str
    providencia: str
    prazo_dias_informado: int | None
    contagem_informada: Literal["uteis", "corridos"] | None
    rito: Literal["jef", "comum", "administrativo", "desconhecido"]
    numero_processo: str | None
    cliente_nome: str | None
    beneficio: str | None
    documentos_mencionados: list[str]
    pontos_de_atencao: list[str]
    trecho_determinante: str
    confianca: Literal["alta", "media", "baixa"]


class ItemChecklist(BaseModel):
    id: str
    titulo: str
    detalhe: str
    status: Status
    feito: bool = False
    feito_por: str | None = None


class Prazo(BaseModel):
    dias: int
    contagem: Literal["uteis", "corridos"]
    origem: Literal["publicacao", "padrao_do_escritorio", "seguranca"]
    inicio_contagem: date
    fatal: date
    interno: date
    vencido: bool
    dias_uteis_ate_interno: int


class Triagem(BaseModel):
    publicacao_id: str
    criada_em: datetime
    responsavel: str
    interpretacao: Interpretacao | None
    erro_interpretacao: str | None = None
    providencia: str
    peca: str | None
    prazo: Prazo | None
    checklist: list[ItemChecklist] = Field(default_factory=list)
    concluida: bool = False

"""Configurações: variáveis de ambiente (.env) + arquivos YAML em config/."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent


def _carregar_env(caminho: Path) -> None:
    """Lê um .env simples (CHAVE=valor) sem sobrescrever o ambiente."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


@dataclass
class Config:
    fluxos: dict
    planilhas: dict
    banco: Path
    planilha_advbox: Path | None
    drive_modo: str  # "local" | "api" | "desligado"
    drive_pasta_local: Path | None
    drive_pasta_id: str | None
    drive_credenciais: Path | None
    modelo: str
    esforco: str
    etapa: int = 1
    smtp: dict = field(default_factory=dict)
    painel_usuario: str = "escritorio"
    painel_senha: str | None = None
    painel_url: str = "http://localhost:8000"
    feriados_extras: list[date] = field(default_factory=list)

    @property
    def providencias(self) -> dict:
        return self.fluxos["providencias"]

    @property
    def data_migracao(self) -> date:
        return self.fluxos["data_migracao_sistema"]


def _caminho(valor: str | None) -> Path | None:
    if not valor:
        return None
    p = Path(valor).expanduser()
    return p if p.is_absolute() else RAIZ / p


@lru_cache
def carregar() -> Config:
    _carregar_env(RAIZ / ".env")
    pasta_cfg = RAIZ / "config"
    fluxos = yaml.safe_load((pasta_cfg / "fluxos.yaml").read_text(encoding="utf-8"))
    planilhas = yaml.safe_load((pasta_cfg / "planilhas.yaml").read_text(encoding="utf-8"))
    feriados_arq = pasta_cfg / "feriados_locais.yaml"
    feriados = []
    if feriados_arq.exists():
        feriados = yaml.safe_load(feriados_arq.read_text(encoding="utf-8")) or []
    e = os.environ.get
    return Config(
        fluxos=fluxos,
        planilhas=planilhas,
        banco=_caminho(e("ROBO_BANCO", "dados/robo.db")),
        planilha_advbox=_caminho(e("ADVBOX_PLANILHA")),
        drive_modo=e("DRIVE_MODO", "local"),
        drive_pasta_local=_caminho(e("DRIVE_PASTA_LOCAL")),
        drive_pasta_id=e("DRIVE_PASTA_CLIENTES_ID"),
        drive_credenciais=_caminho(e("GOOGLE_CREDENCIAIS")),
        modelo=e("ROBO_MODELO", "claude-opus-5"),
        esforco=e("ROBO_ESFORCO", "high"),
        etapa=int(e("ROBO_ETAPA", "1")),
        smtp={
            "host": e("SMTP_HOST"),
            "porta": int(e("SMTP_PORTA", "587")),
            "usuario": e("SMTP_USUARIO"),
            "senha": e("SMTP_SENHA"),
            "remetente": e("SMTP_REMETENTE", e("SMTP_USUARIO", "")),
        },
        painel_usuario=e("PAINEL_USUARIO", "escritorio"),
        painel_senha=e("PAINEL_SENHA"),
        painel_url=e("PAINEL_URL", "http://localhost:8000"),
        feriados_extras=[d if isinstance(d, date) else date.fromisoformat(str(d)) for d in feriados],
    )

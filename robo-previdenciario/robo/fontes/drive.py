"""Verifica, no Google Drive, se a documentação do cliente já existe.

Dois modos:
* "local": pasta sincronizada pelo Google Drive para computador (ex.: G:\\Meu Drive\\Clientes).
  Mais simples, sem credenciais.
* "api": Google Drive API com conta de serviço (compartilhe a pasta de clientes com o
  e-mail da conta de serviço). Requer `pip install google-api-python-client google-auth`.

A pasta de cada cliente é localizada pelo CPF ou pelo nome no nome da pasta.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..texto import normalizar_cpf, normalizar_nome, sem_acento

PASTA_MIME = "application/vnd.google-apps.folder"


@dataclass
class ResultadoDrive:
    pasta: str | None                    # nome/caminho da pasta do cliente
    link: str | None
    encontrados: dict[str, list[str]]    # chave do documento -> arquivos que batem
    faltando: list[str]                  # chaves de documentos não encontrados
    arquivos_total: int


def _achar_pasta(pastas: list[tuple[str, object]], cpf: str | None, nome: str | None):
    cpf_n = normalizar_cpf(cpf) if cpf else ""
    nome_n = normalizar_nome(nome)
    if cpf_n:
        for rotulo, ref in pastas:
            if cpf_n in normalizar_cpf(rotulo):
                return rotulo, ref
    if nome_n:
        # Nome completo primeiro; depois nome + último sobrenome (pastas às vezes abreviam).
        for rotulo, ref in pastas:
            if nome_n in normalizar_nome(rotulo):
                return rotulo, ref
        partes = nome_n.split()
        if len(partes) >= 2:
            for rotulo, ref in pastas:
                r = normalizar_nome(rotulo)
                if partes[0] in r.split() and partes[-1] in r.split():
                    return rotulo, ref
    return None, None


def _classificar(arquivos: list[str], exigidos: list[str], catalogo: dict) -> tuple[dict, list[str]]:
    nomes_n = [(a, sem_acento(a).lower()) for a in arquivos]
    encontrados, faltando = {}, []
    for chave in exigidos:
        palavras = [sem_acento(p).lower() for p in catalogo.get(chave, {}).get("palavras", [chave])]
        achados = [orig for orig, n in nomes_n if any(p in n for p in palavras)]
        if achados:
            encontrados[chave] = achados[:5]
        else:
            faltando.append(chave)
    return encontrados, faltando


class DriveLocal:
    def __init__(self, raiz: Path | None):
        self.raiz = Path(raiz) if raiz else None

    def verificar(self, *, cpf, nome, exigidos, catalogo) -> ResultadoDrive | None:
        if not self.raiz or not self.raiz.is_dir():
            return None
        pastas = [(p.name, p) for p in self.raiz.iterdir() if p.is_dir()]
        rotulo, pasta = _achar_pasta(pastas, cpf, nome)
        if not pasta:
            return ResultadoDrive(None, None, {}, list(exigidos), 0)
        arquivos = [str(p.relative_to(pasta)) for p in pasta.rglob("*") if p.is_file()]
        enc, falt = _classificar(arquivos, exigidos, catalogo)
        return ResultadoDrive(rotulo, str(pasta), enc, falt, len(arquivos))


class DriveAPI:
    def __init__(self, pasta_raiz_id: str, credenciais: Path):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        cred = service_account.Credentials.from_service_account_file(
            str(credenciais), scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        self.svc = build("drive", "v3", credentials=cred, cache_discovery=False)
        self.raiz = pasta_raiz_id
        self._pastas_clientes: list[tuple[str, object]] | None = None

    def _listar(self, pai: str) -> list[dict]:
        itens, token = [], None
        while True:
            r = self.svc.files().list(
                q=f"'{pai}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, webViewLink)",
                pageSize=1000,
                pageToken=token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            itens += r.get("files", [])
            token = r.get("nextPageToken")
            if not token:
                return itens

    def _arquivos_recursivo(self, pasta_id: str, prefixo: str = "", profundidade: int = 3) -> list[str]:
        saida = []
        for f in self._listar(pasta_id):
            if f["mimeType"] == PASTA_MIME:
                if profundidade > 0:
                    saida += self._arquivos_recursivo(f["id"], f"{prefixo}{f['name']}/", profundidade - 1)
            else:
                saida.append(prefixo + f["name"])
        return saida

    def verificar(self, *, cpf, nome, exigidos, catalogo) -> ResultadoDrive | None:
        if self._pastas_clientes is None:
            self._pastas_clientes = [
                (f["name"], f) for f in self._listar(self.raiz) if f["mimeType"] == PASTA_MIME
            ]
        rotulo, pasta = _achar_pasta(self._pastas_clientes, cpf, nome)
        if not pasta:
            return ResultadoDrive(None, None, {}, list(exigidos), 0)
        arquivos = self._arquivos_recursivo(pasta["id"])
        enc, falt = _classificar(arquivos, exigidos, catalogo)
        return ResultadoDrive(rotulo, pasta.get("webViewLink"), enc, falt, len(arquivos))


def criar(cfg) -> DriveLocal | DriveAPI | None:
    if cfg.drive_modo == "api" and cfg.drive_pasta_id and cfg.drive_credenciais:
        return DriveAPI(cfg.drive_pasta_id, cfg.drive_credenciais)
    if cfg.drive_modo == "local":
        return DriveLocal(cfg.drive_pasta_local)
    return None

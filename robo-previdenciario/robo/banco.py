"""Persistência em SQLite (um arquivo, sem servidor)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from .modelos import Publicacao, Triagem

ESQUEMA = """
CREATE TABLE IF NOT EXISTS publicacoes (
    id TEXT PRIMARY KEY,
    dados TEXT NOT NULL,
    importada_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS triagens (
    publicacao_id TEXT PRIMARY KEY REFERENCES publicacoes(id),
    dados TEXT NOT NULL,
    responsavel TEXT,
    prazo_interno TEXT,
    concluida INTEGER NOT NULL DEFAULT 0,
    atualizada_em TEXT NOT NULL
);
-- Só o RESULTADO do teste da senha gov.br. A senha em si nunca é gravada aqui.
CREATE TABLE IF NOT EXISTS testes_senha_govbr (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cpf TEXT NOT NULL,
    resultado TEXT NOT NULL CHECK (resultado IN ('funcionou', 'falhou', 'nova_senha_agencia')),
    testado_em TEXT NOT NULL,
    testado_por TEXT,
    observacao TEXT
);
CREATE INDEX IF NOT EXISTS ix_senha_cpf ON testes_senha_govbr(cpf, testado_em);
"""


class Banco:
    def __init__(self, caminho: Path):
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self.caminho = str(caminho)
        with self._con() as c:
            c.executescript(ESQUEMA)

    @contextmanager
    def _con(self):
        con = sqlite3.connect(self.caminho)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # ---- publicações ---------------------------------------------------------
    def inserir_publicacao(self, p: Publicacao) -> bool:
        """True se era nova."""
        with self._con() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO publicacoes (id, dados, importada_em) VALUES (?, ?, ?)",
                (p.id, p.model_dump_json(), datetime.now().isoformat(timespec="seconds")),
            )
            return cur.rowcount == 1

    def publicacao(self, pid: str) -> Publicacao | None:
        with self._con() as c:
            r = c.execute("SELECT dados FROM publicacoes WHERE id = ?", (pid,)).fetchone()
        return Publicacao.model_validate_json(r["dados"]) if r else None

    def publicacoes_sem_triagem(self) -> list[Publicacao]:
        with self._con() as c:
            rows = c.execute(
                "SELECT p.dados FROM publicacoes p LEFT JOIN triagens t ON t.publicacao_id = p.id "
                "WHERE t.publicacao_id IS NULL ORDER BY p.importada_em"
            ).fetchall()
        return [Publicacao.model_validate_json(r["dados"]) for r in rows]

    # ---- triagens ------------------------------------------------------------
    def salvar_triagem(self, t: Triagem) -> None:
        with self._con() as c:
            c.execute(
                "INSERT INTO triagens (publicacao_id, dados, responsavel, prazo_interno, concluida, atualizada_em) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(publicacao_id) DO UPDATE SET "
                "dados = excluded.dados, responsavel = excluded.responsavel, prazo_interno = excluded.prazo_interno, "
                "concluida = excluded.concluida, atualizada_em = excluded.atualizada_em",
                (
                    t.publicacao_id,
                    t.model_dump_json(),
                    t.responsavel,
                    t.prazo.interno.isoformat() if t.prazo else None,
                    int(t.concluida),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def triagem(self, pid: str) -> Triagem | None:
        with self._con() as c:
            r = c.execute("SELECT dados FROM triagens WHERE publicacao_id = ?", (pid,)).fetchone()
        return Triagem.model_validate_json(r["dados"]) if r else None

    def triagens(self, *, responsavel: str | None = None, incluir_concluidas: bool = False) -> list[Triagem]:
        sql = "SELECT dados FROM triagens WHERE 1=1"
        args: list = []
        if not incluir_concluidas:
            sql += " AND concluida = 0"
        if responsavel:
            sql += " AND responsavel = ?"
            args.append(responsavel)
        # Sem prazo (ex.: ciência) vai para o fim; o resto por prazo interno.
        sql += " ORDER BY prazo_interno IS NULL, prazo_interno"
        with self._con() as c:
            return [Triagem.model_validate_json(r["dados"]) for r in c.execute(sql, args)]

    def responsaveis(self) -> list[str]:
        with self._con() as c:
            return [r[0] for r in c.execute("SELECT DISTINCT responsavel FROM triagens WHERE concluida = 0 ORDER BY 1")]

    # ---- senha gov.br --------------------------------------------------------
    def registrar_teste_senha(self, cpf: str, resultado: str, por: str | None, obs: str | None = None, quando: date | None = None):
        with self._con() as c:
            c.execute(
                "INSERT INTO testes_senha_govbr (cpf, resultado, testado_em, testado_por, observacao) VALUES (?, ?, ?, ?, ?)",
                (cpf, resultado, (quando or date.today()).isoformat(), por, obs),
            )

    def testes_senha(self, cpf: str) -> list[dict]:
        with self._con() as c:
            rows = c.execute(
                "SELECT resultado, testado_em, testado_por, observacao FROM testes_senha_govbr "
                "WHERE cpf = ? ORDER BY testado_em DESC, id DESC",
                (cpf,),
            ).fetchall()
        return [dict(r) for r in rows]

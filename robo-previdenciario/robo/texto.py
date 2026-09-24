"""Normalização de nomes, CPFs e números de processo para cruzar as bases."""
from __future__ import annotations

import re
import unicodedata


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalizar_nome(s: str | None) -> str:
    if not s:
        return ""
    s = sem_acento(str(s)).upper()
    s = re.sub(r"[^A-Z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def so_digitos(s: object) -> str:
    return re.sub(r"\D", "", str(s)) if s is not None else ""


def normalizar_cpf(s: object) -> str:
    d = so_digitos(s)
    if not d:
        return ""
    return d.zfill(11) if len(d) <= 11 else d  # Excel costuma comer zeros à esquerda


def normalizar_processo(s: object) -> str:
    """Número CNJ só com dígitos (20 dígitos)."""
    return so_digitos(s)


def processos_no_texto(texto: str) -> list[str]:
    return re.findall(r"\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}", texto or "")

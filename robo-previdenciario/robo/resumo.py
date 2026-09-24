"""Resumo diário por colaborador (e-mail)."""
from __future__ import annotations

import smtplib
from collections import defaultdict
from datetime import date
from email.message import EmailMessage
from html import escape

from .banco import Banco
from .modelos import Triagem


def _faixa(t: Triagem, hoje: date) -> str:
    if not t.prazo:
        return "sem_prazo"
    if t.prazo.vencido:
        return "vencido"
    if t.prazo.interno <= hoje:
        return "hoje"
    if t.prazo.dias_uteis_ate_interno <= 2:
        return "proximos"
    return "demais"


TITULOS = {
    "vencido": "🚨 PRAZO FATAL VENCIDO — avisar o advogado agora",
    "hoje": "🔴 Prazo interno hoje (ou já passou)",
    "proximos": "🟠 Prazo interno nos próximos 2 dias úteis",
    "demais": "🟢 Demais prazos",
    "sem_prazo": "⚪ Sem prazo (ciência, audiência, implantação)",
}


def montar(triagens: list[Triagem], banco: Banco, hoje: date, url_painel: str) -> tuple[str, str]:
    """Devolve (texto, html) do resumo."""
    grupos: dict[str, list[Triagem]] = defaultdict(list)
    for t in triagens:
        grupos[_faixa(t, hoje)].append(t)
    linhas, html = [], ["<div style='font-family:Arial,sans-serif'>"]
    for faixa, titulo in TITULOS.items():
        if not grupos.get(faixa):
            continue
        linhas.append(f"\n{titulo}")
        html.append(f"<h3>{escape(titulo)}</h3><ul>")
        for t in grupos[faixa]:
            pub = banco.publicacao(t.publicacao_id)
            cliente = pub.cliente_nome if pub else "—"
            processo = pub.numero_processo if pub else "—"
            prazo = f"interno {t.prazo.interno:%d/%m} | fatal {t.prazo.fatal:%d/%m}" if t.prazo else "sem prazo"
            pendentes = sum(1 for i in t.checklist if not i.feito and i.status != "nao_se_aplica")
            alertas = sum(1 for i in t.checklist if not i.feito and i.status == "atencao")
            o_que = t.peca or t.providencia
            linhas.append(f"- {cliente} ({processo}): {o_que} — {prazo} — {pendentes} passos, {alertas} alertas")
            link = f"{url_painel}/p/{t.publicacao_id}"
            html.append(
                f"<li><b>{escape(cliente or '—')}</b> ({escape(processo or '—')}): {escape(o_que)} — {prazo} — "
                f"{pendentes} passos, {alertas} alertas — <a href='{escape(link)}'>abrir checklist</a></li>"
            )
        html.append("</ul>")
    html.append(f"<p><a href='{escape(url_painel)}'>Abrir o painel</a></p></div>")
    return "\n".join(linhas).strip(), "".join(html)


def enviar(smtp: dict, para: str, assunto: str, texto: str, html: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = smtp["remetente"], para, assunto
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(smtp["host"], smtp["porta"], timeout=30) as s:
        s.starttls()
        if smtp.get("usuario"):
            s.login(smtp["usuario"], smtp["senha"])
        s.send_message(msg)

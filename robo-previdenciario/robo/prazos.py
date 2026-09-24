"""Cálculo de prazos processuais e administrativos.

Regras aplicadas (conferir sempre — o robô NÃO substitui a checagem do advogado):

* Diário eletrônico / DJEN (Lei 11.419/06, art. 4º, §§3º e 4º): considera-se
  publicado no primeiro dia útil seguinte à disponibilização, e o prazo começa no
  primeiro dia útil seguinte à publicação.
* Prazo judicial em dias úteis (CPC, art. 219), excluindo o dia do começo
  (art. 224); suspensão entre 20/12 e 20/01, inclusive (art. 220).
* Justiça Federal (Lei 5.010/66, art. 62): também são feriados quarta e quinta
  da Semana Santa, 11/08, 01/11 e 08/12.
* Prazo administrativo (Lei 9.784/99, art. 66): dias corridos a partir da
  ciência, excluído o primeiro dia; se vencer em dia sem expediente, prorroga
  para o primeiro dia útil seguinte. O recesso forense não se aplica.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

FIXOS_NACIONAIS = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)]
FIXOS_JUSTICA_FEDERAL = [(8, 11), (11, 1), (12, 8)]


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


@lru_cache
def feriados_do_ano(ano: int, justica_federal: bool) -> frozenset[date]:
    p = pascoa(ano)
    dias = {date(ano, m, d) for m, d in FIXOS_NACIONAIS}
    dias |= {
        p - timedelta(days=48),  # segunda de Carnaval
        p - timedelta(days=47),  # terça de Carnaval
        p - timedelta(days=2),   # Sexta-feira Santa
        p + timedelta(days=60),  # Corpus Christi
    }
    if justica_federal:
        dias |= {date(ano, m, d) for m, d in FIXOS_JUSTICA_FEDERAL}
        dias |= {p - timedelta(days=4), p - timedelta(days=3)}  # quarta e quinta santas
    return frozenset(dias)


class Calendario:
    def __init__(self, justica_federal: bool = True, feriados_extras: list[date] | None = None):
        self.justica_federal = justica_federal
        self.extras = set(feriados_extras or [])

    def sem_expediente(self, d: date) -> bool:
        return d.weekday() >= 5 or d in self.extras or d in feriados_do_ano(d.year, self.justica_federal)

    @staticmethod
    def em_recesso(d: date) -> bool:
        return (d.month == 12 and d.day >= 20) or (d.month == 1 and d.day <= 20)

    def dia_util(self, d: date, considerar_recesso: bool = True) -> bool:
        if self.sem_expediente(d):
            return False
        return not (considerar_recesso and self.em_recesso(d))

    def proximo_dia_util(self, d: date, considerar_recesso: bool = True) -> date:
        """Primeiro dia útil ESTRITAMENTE posterior a `d`."""
        d += timedelta(days=1)
        while not self.dia_util(d, considerar_recesso):
            d += timedelta(days=1)
        return d

    def somar_dias_uteis(self, inicio: date, n: int) -> date:
        """`inicio` é o 1º dia do prazo (já útil); devolve o n-ésimo dia útil."""
        d, contados = inicio, 1
        while contados < n:
            d = self.proximo_dia_util(d)
            contados += 1
        return d

    def subtrair_dias_uteis(self, d: date, n: int) -> date:
        # O prazo interno só olha expediente (não recesso), para não "pular" o recesso para trás.
        while n > 0:
            d -= timedelta(days=1)
            if not self.sem_expediente(d):
                n -= 1
        return d

    def dias_uteis_entre(self, a: date, b: date) -> int:
        """Quantidade de dias com expediente em (a, b]. Negativo se b < a."""
        if b < a:
            return -self.dias_uteis_entre(b, a)
        n, d = 0, a
        while d < b:
            d += timedelta(days=1)
            if not self.sem_expediente(d):
                n += 1
        return n


def data_publicacao(disponibilizacao: date, cal: Calendario) -> date:
    """DJEN: publicação = primeiro dia útil após a disponibilização."""
    return cal.proximo_dia_util(disponibilizacao, considerar_recesso=False)


def calcular_prazo_fatal(
    *,
    ciencia: date,
    dias: int,
    contagem: str,
    cal: Calendario,
) -> tuple[date, date]:
    """Devolve (início da contagem, prazo fatal).

    `ciencia` é a data da publicação (judicial) ou da ciência (administrativo).
    """
    if contagem == "uteis":
        inicio = cal.proximo_dia_util(ciencia)
        return inicio, cal.somar_dias_uteis(inicio, dias)
    inicio = ciencia + timedelta(days=1)
    fatal = ciencia + timedelta(days=dias)
    while cal.sem_expediente(fatal):
        fatal += timedelta(days=1)
    return inicio, fatal


def calcular_prazo_interno(fatal: date, margem: int, hoje: date, cal: Calendario) -> date:
    interno = cal.subtrair_dias_uteis(fatal, margem)
    # Nunca marca prazo interno no passado se o fatal ainda não venceu.
    if interno < hoje <= fatal:
        return hoje
    return interno


def eh_justica_federal(tribunal: str | None, orgao: str | None) -> bool:
    texto = f"{tribunal or ''} {orgao or ''}".upper()
    # Na dúvida, calendário estadual: tem menos feriados, então o prazo calculado
    # vence mais cedo (erro a favor da segurança).
    return any(s in texto for s in ("TRF", "JEF", "FEDERAL", "TNU", "TURMA RECURSAL", "JF"))

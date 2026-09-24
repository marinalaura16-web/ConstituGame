from datetime import date

from robo.prazos import (
    Calendario, calcular_prazo_fatal, calcular_prazo_interno, data_publicacao, eh_justica_federal, pascoa,
)

JF = Calendario(justica_federal=True)
EST = Calendario(justica_federal=False)


def test_pascoa():
    assert pascoa(2026) == date(2026, 4, 5)
    assert pascoa(2027) == date(2027, 3, 28)


def test_15_dias_uteis_com_feriado_de_12_de_outubro():
    # Disponibilizada qui 24/09 -> publicada sex 25/09 -> começa seg 28/09.
    pub = data_publicacao(date(2026, 9, 24), JF)
    assert pub == date(2026, 9, 25)
    inicio, fatal = calcular_prazo_fatal(ciencia=pub, dias=15, contagem="uteis", cal=JF)
    assert inicio == date(2026, 9, 28)
    assert fatal == date(2026, 10, 19)  # 12/10 (segunda) não conta


def test_recesso_forense_suspende_prazo():
    pub = data_publicacao(date(2026, 12, 17), JF)  # publicada sex 18/12
    inicio, fatal = calcular_prazo_fatal(ciencia=pub, dias=5, contagem="uteis", cal=JF)
    assert inicio == date(2027, 1, 21)
    assert fatal == date(2027, 1, 27)


def test_semana_santa_so_na_justica_federal():
    # 2026: quarta santa 01/04, quinta santa 02/04, sexta santa 03/04.
    assert not JF.dia_util(date(2026, 4, 1))
    assert EST.dia_util(date(2026, 4, 1))
    assert not EST.dia_util(date(2026, 4, 3))


def test_prazo_administrativo_corridos_prorroga_para_dia_util():
    # Ciência sex 02/10/2026 + 30 corridos = dom 01/11 -> seg 02/11 é feriado -> ter 03/11.
    _, fatal = calcular_prazo_fatal(ciencia=date(2026, 10, 2), dias=30, contagem="corridos", cal=EST)
    assert fatal == date(2026, 11, 3)


def test_prazo_interno_margem_e_nunca_no_passado():
    fatal = date(2026, 10, 19)
    assert calcular_prazo_interno(fatal, 2, date(2026, 9, 24), JF) == date(2026, 10, 15)
    # Se já passou do interno mas o fatal não venceu, o interno vira "hoje".
    assert calcular_prazo_interno(fatal, 2, date(2026, 10, 16), JF) == date(2026, 10, 16)


def test_identifica_justica_federal():
    assert eh_justica_federal("TRF4", None)
    assert eh_justica_federal(None, "1º JEF de Curitiba")
    assert not eh_justica_federal("TJSP", "2ª Vara Cível")
    assert not eh_justica_federal(None, None)

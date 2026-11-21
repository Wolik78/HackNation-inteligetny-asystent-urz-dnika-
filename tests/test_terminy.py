from datetime import date

import pytest

from asystent.terminy import (dodaj_dni_robocze, dodaj_miesiace, jest_dniem_wolnym, koniec_terminu, swieta,
                              wielkanoc)


@pytest.mark.parametrize('rok, oczekiwana', [(2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)),
                                             (2026, date(2026, 4, 5)), (2027, date(2027, 3, 28))])
def test_wielkanoc(rok, oczekiwana):
    assert wielkanoc(rok) == oczekiwana


def test_swieta_2026():
    dni = swieta(2026)
    assert dni[date(2026, 6, 4)] == 'Boże Ciało'
    assert dni[date(2026, 5, 24)] == 'Zielone Świątki'
    assert dni[date(2026, 12, 24)] == 'Wigilia'
    assert date(2024, 12, 24) not in swieta(2024)   # Wigilia wolna dopiero od 2025 r.


def test_dni_wolne():
    assert jest_dniem_wolnym(date(2026, 11, 21))      # sobota
    assert jest_dniem_wolnym(date(2026, 11, 11))      # Święto Niepodległości (środa)
    assert not jest_dniem_wolnym(date(2026, 11, 20))  # piątek


def test_termin_14_dni_bez_przesuniecia():
    assert koniec_terminu(date(2026, 11, 5), dni=14) == (date(2026, 11, 19), '')


def test_termin_w_sobote_przesuwa_sie_na_poniedzialek():
    koniec, opis = koniec_terminu(date(2026, 11, 7), dni=14)   # 21.11.2026 to sobota
    assert koniec == date(2026, 11, 23)
    assert 'sobota' in opis and '57 § 4' in opis


def test_termin_w_swieto_i_weekend():
    # 28.10 + 14 = 11.11 (święto, środa) → 12.11
    assert koniec_terminu(date(2026, 10, 28), dni=14)[0] == date(2026, 11, 12)
    # 10.12 + 14 = 24.12 (Wigilia) → 25, 26 święta, 27 niedziela → 28.12
    assert koniec_terminu(date(2026, 12, 10), dni=14)[0] == date(2026, 12, 28)


def test_termin_w_miesiacach():
    assert dodaj_miesiace(date(2026, 12, 31), 2) == date(2027, 2, 28)   # brak 31 lutego
    assert dodaj_miesiace(date(2026, 11, 5), 2) == date(2027, 1, 5)
    assert koniec_terminu(date(2026, 11, 5), miesiace=2)[0] == date(2027, 1, 5)


def test_dni_robocze():
    piatek = date(2026, 11, 20)
    assert dodaj_dni_robocze(piatek, 1) == date(2026, 11, 23)
    assert dodaj_dni_robocze(date(2026, 11, 23), -1) == piatek
    assert dodaj_dni_robocze(date(2026, 11, 21), 0) == date(2026, 11, 23)   # sobota → poniedziałek

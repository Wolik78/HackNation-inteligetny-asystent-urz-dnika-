"""Dane wnioskodawcy z treści wniosku (podpowiedź do pól „Wnioskodawca” i „Kontakt”)."""

import pytest

from asystent.pliki import wyciagnij_tekst
from asystent.wnioskodawca import DaneWnioskodawcy, dane_wnioskodawcy
from tests.conftest import WNIOSEK_TESTOWY, WNIOSEK_Z_DANYMI


@pytest.mark.parametrize('plik, oczekiwane', [
    (WNIOSEK_TESTOWY, DaneWnioskodawcy('Jan Testowy', 'jan.testowy@example.com')),
    (WNIOSEK_Z_DANYMI, DaneWnioskodawcy('Katarzyna Wiśniewska', 'k.wisniewska@example.com')),
])
def test_wnioski_testowe(plik, oczekiwane):
    assert dane_wnioskodawcy(wyciagnij_tekst(plik).tekst) == oczekiwane


def test_organizacja_i_adres_gdy_brak_emaila():
    tekst = 'Fundacja Przejrzyste Miasto\nul. Długa 5, 85-001 Bydgoszcz\n\nWNIOSEK o udostępnienie informacji'
    assert dane_wnioskodawcy(tekst) == DaneWnioskodawcy('Fundacja Przejrzyste Miasto', 'ul. Długa 5, 85-001 Bydgoszcz')


def test_podpis_gdy_brak_naglowka():
    tekst = 'Szanowni Państwo,\nproszę o informację o wydatkach.\nZ poważaniem\nPiotr Zieliński'
    assert dane_wnioskodawcy(tekst).wnioskodawca == 'Piotr Zieliński'


def test_brak_danych():
    assert dane_wnioskodawcy('Proszę o informację.') == DaneWnioskodawcy()

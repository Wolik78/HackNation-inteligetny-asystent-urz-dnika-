"""Dane demonstracyjne: archiwum testowe w Bazie wiedzy i wnioski testowe – jednym wywołaniem, bez duplikatów."""

import pytest

from asystent import demo, rejestr
from asystent.pliki import Kategoria, MagazynPlikow
from tests.conftest import ARCHIWUM_TESTOWE


@pytest.fixture
def czysty_rejestr(tmp_path, monkeypatch):
    monkeypatch.setattr(rejestr, 'PLIK_REJESTRU', tmp_path / 'rejestr.json')
    monkeypatch.setattr(rejestr, '_wnioski', [])
    rejestr._wczytaj()


def test_archiwum_testowe_wgrywa_sie_raz(tmp_path):
    magazyn = MagazynPlikow(tmp_path / 'dane')
    liczba = len(list(ARCHIWUM_TESTOWE.glob('*.txt')))

    pierwszy = demo.wczytaj_archiwum_testowe(magazyn)
    drugi = demo.wczytaj_archiwum_testowe(magazyn)

    assert (pierwszy.nowe, pierwszy.pominiete) == (liczba, 0)
    assert (drugi.nowe, drugi.pominiete) == (0, liczba)
    assert len(magazyn.lista(Kategoria.ARCHIWUM)) == liczba


def test_przygotuj_demo_odtwarza_wnioski_i_archiwum(tmp_path, czysty_rejestr):
    magazyn = MagazynPlikow(tmp_path / 'dane')
    wynik = demo.przygotuj_demo(magazyn)
    assert wynik.nowe > 0
    assert sum(w.testowy for w in rejestr.wszystkie()) == 10


def test_brak_folderu_danych_testowych(tmp_path):
    with pytest.raises(FileNotFoundError):
        demo.wczytaj_archiwum_testowe(MagazynPlikow(tmp_path / 'dane'), tmp_path / 'nie_ma')

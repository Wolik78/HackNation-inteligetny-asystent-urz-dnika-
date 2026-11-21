from datetime import date

import pytest

from asystent import rejestr


@pytest.fixture
def czysty_rejestr(tmp_path, monkeypatch):
    monkeypatch.setattr(rejestr, 'PLIK_REJESTRU', tmp_path / 'rejestr.json')
    monkeypatch.setattr(rejestr, '_wnioski', [])
    rejestr._wczytaj_dane_testowe()


def _dodaj(nr: str) -> rejestr.Wniosek:
    return rejestr.dodaj(nr=nr, temat='Test', wnioskodawca='Jan Testowy',
                         data_wplywu=date.today(), kto='AK')


def test_numeracja_kolejnego_wniosku(czysty_rejestr):
    assert rejestr.nastepny_numer() == f'UDIP.11.{date.today().year}'


def test_dodany_wniosek_przetrwa_restart(czysty_rejestr, monkeypatch):
    wniosek = _dodaj('UDIP.11.2026')

    monkeypatch.setattr(rejestr, '_wnioski', [])  # symulacja ponownego uruchomienia
    rejestr._wczytaj_dane_testowe()
    rejestr._wczytaj_zapisane()

    wczytany = rejestr.pobierz(wniosek.id)
    assert wczytany == wniosek
    assert len(rejestr.wszystkie()) == 11


def test_numer_wniosku_musi_byc_unikalny(czysty_rejestr):
    _dodaj('UDIP.11.2026')
    with pytest.raises(ValueError, match='już istnieje'):
        _dodaj('UDIP.11.2026')


def test_lista_od_najstarszych(czysty_rejestr):
    daty = [w.data_wplywu for w in rejestr.wszystkie()]
    assert daty == sorted(daty)

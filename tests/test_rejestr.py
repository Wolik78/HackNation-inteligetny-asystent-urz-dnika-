import json
from datetime import date, timedelta

import pytest

from asystent import rejestr
from asystent.terminy import jest_dniem_wolnym


@pytest.fixture
def czysty_rejestr(tmp_path, monkeypatch):
    monkeypatch.setattr(rejestr, 'PLIK_REJESTRU', tmp_path / 'rejestr.json')
    monkeypatch.setattr(rejestr, '_wnioski', [])
    rejestr._wczytaj()


def _dodaj(nr: str = 'UDIP.11.2026', **zmiany) -> rejestr.Wniosek:
    dane = dict(nr=nr, temat='Test', wnioskodawca='Jan Testowy', data_wplywu=date(2026, 11, 5), kto='AK')
    dane.update(zmiany)
    return rejestr.dodaj(**dane)


def _restart(monkeypatch):
    monkeypatch.setattr(rejestr, '_wnioski', [])
    rejestr._wczytaj()


# --- dane testowe i zapis ---

def test_pierwsze_uruchomienie_tworzy_10_wnioskow_testowych(czysty_rejestr):
    wnioski = rejestr.wszystkie()
    assert len(wnioski) == 10
    daty = [w.data_wplywu for w in wnioski]
    assert daty == sorted(daty)
    assert {w.pilnosc for w in wnioski} >= {'po_terminie', 'wyslano', 'ok'}
    assert all(not jest_dniem_wolnym(w.termin) for w in wnioski)


def test_zmiany_wnioskow_testowych_przetrwaja_restart(czysty_rejestr, monkeypatch):
    w = rejestr.pobierz(4)
    rejestr.zmien_status(w, 'wydzialy')
    _restart(monkeypatch)
    assert rejestr.pobierz(4).status == 'wydzialy'


def test_dodany_wniosek_przetrwa_restart(czysty_rejestr, monkeypatch):
    wniosek = _dodaj()
    _restart(monkeypatch)
    assert rejestr.pobierz(wniosek.id) == wniosek
    assert len(rejestr.wszystkie()) == 11


def test_migracja_starego_formatu(tmp_path, monkeypatch):
    plik = tmp_path / 'rejestr.json'
    plik.write_text(json.dumps([{  # wersja 1: lista dodanych wniosków, kwerenda jako status
        'id': 11, 'nr': 'UDIP.11.2026', 'temat': 'Stary', 'wnioskodawca': 'X', 'data_wplywu': '2026-11-05',
        'kto': 'AK', 'status': 'kwerenda', 'kwerenda': True, 'kontakt': '', 'data_odpowiedzi': None,
        'sugerowane_wydzialy': [], 'uzasadnienie_wydzialu': '', 'testowy': False}]), 'utf-8')
    monkeypatch.setattr(rejestr, 'PLIK_REJESTRU', plik)
    monkeypatch.setattr(rejestr, '_wnioski', [])
    rejestr._wczytaj()

    assert len(rejestr.wszystkie()) == 11                      # 10 testowych + stary
    stary = rejestr.pobierz(11)
    assert stary.status == 'brak' and stary.kwerenda
    assert json.loads(plik.read_text('utf-8'))['wersja'] == 2


def test_przywrocenie_danych_testowych_zostawia_wnioski_urzednika(czysty_rejestr):
    wlasny = _dodaj()
    rejestr.usun(rejestr.pobierz(1))
    rejestr.przywroc_dane_testowe()
    assert len(rejestr.wszystkie()) == 11
    assert rejestr.pobierz(wlasny.id) is wlasny


# --- numeracja, rok ---

def test_numeracja_i_unikalnosc(czysty_rejestr):
    assert rejestr.nastepny_numer() == f'UDIP.11.{date.today().year}'
    _dodaj(nr='UDIP.11.2026')
    with pytest.raises(ValueError, match='już istnieje'):
        _dodaj(nr='UDIP.11.2026')


def test_filtr_roku(czysty_rejestr):
    _dodaj(nr='UDIP.1.2025', data_wplywu=date(2025, 3, 1))
    assert [w.nr for w in rejestr.wszystkie(2025)] == ['UDIP.1.2025']
    assert 2025 in rejestr.lata() and date.today().year in rejestr.lata()


# --- terminy ---

def test_termin_przesuniety_z_soboty(czysty_rejestr):
    w = _dodaj(data_wplywu=date(2026, 11, 7))   # +14 = sobota 21.11
    assert w.termin == date(2026, 11, 23)
    assert 'art. 57' in w.uwaga_o_terminie


def test_kwerenda(czysty_rejestr):
    w = _dodaj(data_wplywu=date(2026, 11, 5))
    rejestr.ustaw_kwerende(w, True)
    assert w.termin == date(2027, 1, 5) and w.dni_kwerendy == (date(2027, 1, 5) - date(2026, 11, 19)).days

    rejestr.ustaw_kwerende(w, True, date(2026, 12, 15))
    assert w.termin == date(2026, 12, 15)
    with pytest.raises(ValueError, match='2 miesięcy'):
        rejestr.ustaw_kwerende(w, True, date(2027, 1, 20))
    with pytest.raises(ValueError, match='późniejszy'):
        rejestr.ustaw_kwerende(w, True, date(2026, 11, 10))

    rejestr.ustaw_kwerende(w, False)
    assert w.termin == date(2026, 11, 19)


# --- statusy i historia ---

def test_statusy_i_historia(czysty_rejestr):
    w = _dodaj()
    assert rejestr.awansuj_status(w, 'wydzialy', 'wgrano odpowiedź wydziału')
    assert not rejestr.awansuj_status(w, 'brak', 'automat nie cofa statusu')
    assert rejestr.zmien_status(w, 'wyslana', data_odpowiedzi=date(2026, 11, 18))
    assert w.data_odpowiedzi == date(2026, 11, 18) and w.pilnosc == 'wyslano'

    rejestr.zmien_status(w, 'przygotowana')            # ręcznie można cofnąć
    assert w.data_odpowiedzi is None
    zdarzenia = [h['zdarzenie'] for h in w.historia]
    assert zdarzenia[0] == 'Zarejestrowano wniosek'
    assert 'Status: Zapytania wysłane do wydziałów – wgrano odpowiedź wydziału' in zdarzenia
    assert 'Status: Odpowiedź wysłana (18.11.2026)' in zdarzenia


def test_edycja_i_usuwanie(czysty_rejestr):
    w = _dodaj()
    rejestr.aktualizuj(w, temat='Nowy temat', wnioskodawca='Jan Testowy', kontakt='jan@example.com',
                       data_wplywu=date(2026, 11, 5), kto='MN')
    assert w.temat == 'Nowy temat' and w.kto == 'MN'
    assert w.historia[-1]['zdarzenie'] == 'Zmieniono temat, kontakt, prowadzącego'
    with pytest.raises(ValueError):
        rejestr.aktualizuj(w, temat=' ', wnioskodawca='X', kontakt='', data_wplywu=date(2026, 11, 5), kto='MN')

    rejestr.usun(w)
    assert rejestr.pobierz(w.id) is None


def test_pilnosc_najblizszy_dzien_roboczy(czysty_rejestr, monkeypatch):
    class Piatek(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 20)
    monkeypatch.setattr(rejestr, 'date', Piatek)
    w = _dodaj(data_wplywu=date(2026, 11, 9))   # termin poniedziałek 23.11
    assert w.pilnosc == 'jutro'
    assert w.pozostalo.startswith('poniedziałek')
    assert date(2026, 11, 20) + timedelta(days=3) == w.termin

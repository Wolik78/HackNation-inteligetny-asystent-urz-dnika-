"""Klasyfikacja wniosku i ścieżka postępowania: reguły, odpowiedź modelu, pismo wg rodzaju, zapis w rejestrze."""

import json
from datetime import date

import httpx
import pytest

from asystent import klasyfikacja, rejestr
from tests.test_bielik_service import odpowiedz_czatu, serwis, uruchom


# --- rozpoznanie odpowiedzi modelu ---

@pytest.mark.parametrize('odpowiedz, klucz', [
    ('przetworzona', 'przetworzona'),
    ('W BIP', 'w_bip'),
    ('Informacja dostępna w BIP', 'w_bip'),
    ('nie jest informacją publiczną', 'nie_publiczna'),
    ('Inny tryb dostępu', 'inny_tryb'),
    ('do doprecyzowania', 'doprecyzowanie'),
    ('zwykła', 'zwykla'),
    ('coś innego', None),
    (None, None),
])
def test_rozpoznanie_rodzaju_z_odpowiedzi_modelu(odpowiedz, klucz):
    assert klasyfikacja.rozpoznaj_klucz(odpowiedz) == klucz


def test_kazdy_rodzaj_ma_sciezke_pismo_i_opis_dla_modelu():
    assert klasyfikacja.DOMYSLNY in klasyfikacja.RODZAJE
    assert set(klasyfikacja.OPISY_DLA_MODELU) == set(klasyfikacja.RODZAJE)
    for r in klasyfikacja.RODZAJE.values():
        assert r.sciezka and r.pismo and r.nazwa
    assert klasyfikacja.rodzaj('nieznany').klucz == klasyfikacja.DOMYSLNY


# --- reguły (bez modelu) ---

@pytest.mark.parametrize('tekst, klucz', [
    ('Proszę o kopie wszystkich umów zawartych w latach 2015-2025.', 'przetworzona'),
    ('Wnoszę o zestawienie wydatków z ostatnich 10 lat w podziale na wydziały.', 'przetworzona'),
    ('Dlaczego w mojej sprawie o pozwolenie na budowę nie ma jeszcze decyzji?', 'nie_publiczna'),
    ('Proszę o wgląd w akta sprawy dotyczącej mojej działki.', 'inny_tryb'),
    ('Ile wydano na promocję miasta w 2025 roku?', 'zwykla'),
])
def test_podpowiedz_regulami(tekst, klucz):
    wynik, uzasadnienie = klasyfikacja.podpowiedz_regulami(tekst)
    assert wynik == klucz
    assert bool(uzasadnienie) == (klucz != klasyfikacja.DOMYSLNY)


@pytest.mark.parametrize('model, oczekiwany', [
    ('przetworzona', 'przetworzona'),   # szczególny rodzaj od modelu zostaje
    ('zwykla', 'nie_publiczna'),        # model wybrał domyślny, ale reguły widzą sprawę indywidualną
    (None, 'nie_publiczna'),            # model nie odpowiedział
])
def test_ustal_rodzaj_laczy_model_i_reguly(model, oczekiwany):
    tekst = 'Dlaczego w mojej sprawie o pozwolenie na budowę nie wydano decyzji? Proszę o poradę.'
    assert klasyfikacja.ustal_rodzaj(tekst, model, 'z modelu')[0] == oczekiwany


def test_ustal_rodzaj_zwykly_wniosek_zostaje_zwykly():
    assert klasyfikacja.ustal_rodzaj('Ile drzew wycięto w parku?', 'zwykla', 'dane w wydziale') == \
        ('zwykla', 'dane w wydziale')


# --- Bielik ---

def test_analiza_zwraca_rodzaj_i_wysyla_liste_rodzajow():
    wyslane = {}

    def obsluga(request, payload):
        wyslane.update(payload)
        return odpowiedz_czatu('{"skrocony_opis": "Umowy z 10 lat", "czy_wymaga_kwerendy": true, '
                               '"rodzaj": "przetworzona", "uzasadnienie_rodzaju": "Wymaga zestawienia umów."}')

    analiza = uruchom(serwis(obsluga).analizuj_wniosek('Proszę o wszystkie umowy z 10 lat.'))
    assert analiza.rodzaj == 'przetworzona'
    assert analiza.uzasadnienie_rodzaju == 'Wymaga zestawienia umów.'
    system = wyslane['messages'][0]['content']
    assert all(klucz in system for klucz in klasyfikacja.RODZAJE)


def test_analiza_bez_rodzaju_daje_none():
    analiza = uruchom(serwis(lambda r, p: odpowiedz_czatu('{"skrocony_opis": "X"}')).analizuj_wniosek('w'))
    assert analiza.rodzaj is None


def _zbierz_pismo(rodzaj: str) -> dict:
    wyslane = {}

    def obsluga(request, payload):
        wyslane.update(payload)
        linia = json.dumps({'choices': [{'delta': {'content': 'Szanowny Panie,'}}]})
        return httpx.Response(200, content=f'data: {linia}\n\ndata: [DONE]\n\n'.encode(),
                              headers={'content-type': 'text/event-stream'})

    async def zbierz():
        return ''.join([k async for k in serwis(obsluga).generuj_odpowiedz(
            wniosek='Proszę o wszystkie umowy z 10 lat.', informacje_wydzialow='1 240 000 zł', rodzaj=rodzaj,
            dane_sprawy='Numer sprawy: UDIP.1.2026')])

    assert uruchom(zbierz()) == 'Szanowny Panie,'
    return wyslane


def test_informacja_przetworzona_daje_wezwanie_do_wykazania_interesu():
    wyslane = _zbierz_pismo('przetworzona')
    system, tresc = wyslane['messages'][0]['content'], wyslane['messages'][1]['content']
    assert 'szczególnie istotnego interesu publicznego' in system and 'art. 3 ust. 1 pkt 1' in system
    assert 'UDIP.1.2026' in tresc and '1 240 000 zł' not in tresc   # dane wydziałów nie są tu potrzebne


@pytest.mark.parametrize('rodzaj, fraza', [
    ('w_bip', 'art. 10 ust. 1'),
    ('nie_publiczna', 'nie decyzja'),
    ('inny_tryb', 'art. 1 ust. 2'),
    ('doprecyzowanie', 'doprecyzowania'),
])
def test_pismo_wg_rodzaju(rodzaj, fraza):
    assert fraza in _zbierz_pismo(rodzaj)['messages'][0]['content']


def test_zwykla_informacja_to_odpowiedz_z_danymi_wydzialow():
    tresc = _zbierz_pismo('zwykla')['messages'][1]['content']
    assert '1 240 000 zł' in tresc


# --- rejestr ---

@pytest.fixture
def czysty_rejestr(tmp_path, monkeypatch):
    monkeypatch.setattr(rejestr, 'PLIK_REJESTRU', tmp_path / 'rejestr.json')
    monkeypatch.setattr(rejestr, '_wnioski', [])
    rejestr._wczytaj()


def test_rodzaj_zapisywany_w_rejestrze_i_w_przebiegu_sprawy(czysty_rejestr, monkeypatch):
    w = rejestr.dodaj(nr='UDIP.50.2026', temat='Umowy', wnioskodawca='Jan', data_wplywu=date(2026, 11, 5), kto='AK',
                      rodzaj='przetworzona', uzasadnienie_rodzaju='Wymaga zestawienia.')
    assert w.rodzaj == 'przetworzona'
    assert not rejestr.ustaw_rodzaj(w, 'przetworzona', 'Informacja przetworzona')   # bez zmiany
    assert rejestr.ustaw_rodzaj(w, 'zwykla', 'Informacja publiczna')
    assert w.historia[-1]['zdarzenie'] == 'Rodzaj sprawy: Informacja publiczna'
    assert w.uzasadnienie_rodzaju == ''                    # uzasadnienie asystenta nie pasuje do zmienionego rodzaju

    monkeypatch.setattr(rejestr, '_wnioski', [])
    rejestr._wczytaj()
    assert rejestr.pobierz(w.id).rodzaj == 'zwykla'


def test_stare_wnioski_bez_rodzaju_sa_zwykla_informacja(czysty_rejestr):
    assert all(w.rodzaj == klasyfikacja.DOMYSLNY for w in rejestr.wszystkie())

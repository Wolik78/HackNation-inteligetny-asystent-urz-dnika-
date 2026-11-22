"""Wyszukiwanie podobnych spraw (J1): archiwum testowe z dane_testowe/archiwum, bez prawdziwego modelu."""

import asyncio
import json
from datetime import date, timedelta

import httpx
import pytest

from asystent import rejestr
from asystent.ai import BielikService
from asystent.archiwum import (RODZAJ_ARCHIWUM, RODZAJ_WNIOSEK, Archiwum, opis_dokumentu, waga_znaczenia)
from asystent.pliki import Kategoria, MagazynPlikow
from asystent.pliki.ekstrakcja import wyciagnij_tekst
from tests.conftest import ARCHIWUM_TESTOWE, WNIOSEK_TESTOWY

TEMATY = ('promoc', 'drzew', 'dotac', 'mandat', 'zimow', 'szkol')


def uruchom(korutyna):
    return asyncio.run(korutyna)


def model_testowy(zapytania: list[list[str]]) -> httpx.MockTransport:
    """Udawany model embeddingów: wektor = ile razy w tekście występują słowa z TEMATY (+ stała)."""
    def obsluga(request: httpx.Request) -> httpx.Response:
        teksty = json.loads(request.content)['input']
        zapytania.append(teksty)
        dane = [{'index': i, 'embedding': [t.lower().count(s) for s in TEMATY] + [1.0]} for i, t in enumerate(teksty)]
        return httpx.Response(200, json={'data': dane})
    return httpx.MockTransport(obsluga)


@pytest.fixture
def magazyn(tmp_path) -> MagazynPlikow:
    magazyn = MagazynPlikow(tmp_path / 'dane')
    for plik in sorted(ARCHIWUM_TESTOWE.glob('*.txt')):
        magazyn.zapisz(plik.read_bytes(), plik.name, Kategoria.ARCHIWUM)
    return magazyn


def archiwum(magazyn, tmp_path, zapytania=None, *, transport=None) -> Archiwum:
    bielik = BielikService('http://lm.test/v1', 'bielik',
                           transport=transport or model_testowy(zapytania if zapytania is not None else []))
    return Archiwum(magazyn, bielik, katalog_indeksu=tmp_path, model='text-embedding-nomic-embed-text-v1.5')


def pierwsze_archiwalne(wynik):
    return next(t for t in wynik.trafienia if t.dokument.rodzaj == RODZAJ_ARCHIWUM)


# --- opis dokumentu ---

def test_opis_archiwalnej_odpowiedzi():
    tekst = (ARCHIWUM_TESTOWE / 'UDIP.112.2025_wydatki_na_promocje_miasta_2024.txt').read_text('utf-8')
    temat, nr, data = opis_dokumentu(tekst, 'cokolwiek.txt')
    assert nr == 'UDIP.112.2025'
    assert data == date(2025, 3, 12)
    assert temat == 'W sprawie wydatków na promocję miasta w 2024 r'


def test_opis_bez_naglowka_bierze_nazwe_pliku():
    temat, nr, data = opis_dokumentu('Krótka notatka bez nagłówka.', 'UDIP.7.2024_koszty_festiwalu.txt')
    assert (temat, nr, data) == ('Koszty festiwalu', 'UDIP.7.2024', None)


# --- trafność (same słowa – działa bez LM Studio) ---

@pytest.mark.parametrize('zapytanie, oczekiwany', [
    ('Proszę o informację, ile drzew wycięto w 2025 r. w parku Kochanowskiego i jaki był koszt.', 'UDIP.240.2024'),
    ('Ile kosztowało odśnieżanie ulic zimą?', 'UDIP.301.2024'),
    ('Wnoszę o wykaz dotacji przyznanych stowarzyszeniom.', 'UDIP.15.2025'),
    ('Ile mandatów wystawiła straż miejska za złe parkowanie?', 'UDIP.140.2025'),
    ('Proszę o zestawienie wszystkich umów cywilnoprawnych zawartych przez Urząd w latach 2015–2025.', 'UDIP.251.2025'),
])
def test_wlasciwa_sprawa_na_pierwszym_miejscu(magazyn, tmp_path, zapytanie, oczekiwany):
    wynik = uruchom(archiwum(magazyn, tmp_path).szukaj(zapytanie, uzyj_ai=False))
    assert wynik.tryb == 'slowa'
    assert pierwsze_archiwalne(wynik).dokument.nr == oczekiwany


def test_wniosek_testowy_znajduje_odpowiedz_o_promocji_i_proponuje_ja_jako_wzor(magazyn, tmp_path):
    wniosek = wyciagnij_tekst(WNIOSEK_TESTOWY).tekst
    wynik = uruchom(archiwum(magazyn, tmp_path).szukaj(wniosek, uzyj_ai=False))

    najlepszy = pierwsze_archiwalne(wynik)
    assert najlepszy.dokument.nr == 'UDIP.112.2025'
    assert 'promocję' in najlepszy.wspolne_slowa
    assert not {'ustawy', 'art', 'udostępnienie'} & set(najlepszy.wspolne_slowa)   # bez urzędowych formułek
    assert najlepszy.fragment.startswith('w 2024 r. Miasto Bydgoszcz wydało')       # sedno, nie „na podstawie…”
    assert wynik.najlepszy_wzor is najlepszy


def test_niezwiazane_pytanie_nie_daje_wynikow(magazyn, tmp_path):
    wynik = uruchom(archiwum(magazyn, tmp_path).szukaj('Ile psów adoptowano ze schroniska?', uzyj_ai=False))
    assert wynik.trafienia == [] and wynik.najlepszy_wzor is None
    assert wynik.liczba_dokumentow >= 11


# --- znaczenie (embeddingi) ---

def test_tryb_hybrydowy_i_wektory_liczone_raz(magazyn, tmp_path):
    zapytania: list[list[str]] = []
    szukajka = archiwum(magazyn, tmp_path, zapytania)
    wynik = uruchom(szukajka.szukaj('wycinka drzew w parku'))

    assert wynik.tryb == 'hybryda' and pierwsze_archiwalne(wynik).dokument.nr == 'UDIP.240.2024'
    dokumenty_wyslane = sum(len(z) for z in zapytania[:-1])
    assert dokumenty_wyslane == wynik.liczba_dokumentow
    assert zapytania[-1][0].startswith('search_query: ')       # prefiksy wymagane przez nomic-embed
    assert zapytania[0][0].startswith('search_document: ')

    zapytania.clear()
    uruchom(archiwum(magazyn, tmp_path, zapytania).szukaj('dotacje'))  # nowa instancja – indeks z pliku
    assert zapytania == [[zapytania[0][0]]] and len(zapytania[0]) == 1  # tylko pytanie, dokumenty z indeksu


def test_bez_lm_studio_wyszukiwanie_po_slowach(magazyn, tmp_path):
    def brak_serwera(request):
        raise httpx.ConnectError('connection refused', request=request)
    wynik = uruchom(archiwum(magazyn, tmp_path, transport=httpx.MockTransport(brak_serwera))
                    .szukaj('Ile mandatów wystawiła straż miejska?'))
    assert wynik.tryb == 'slowa' and 'tylko po słowach' in wynik.komunikat
    assert pierwsze_archiwalne(wynik).dokument.nr == 'UDIP.140.2025'


def test_waga_znaczenia_zalezy_od_modelu():
    assert waga_znaczenia('text-embedding-nomic-embed-text-v1.5') < waga_znaczenia('text-embedding-bge-m3')


# --- wnioski z rejestru (I3) ---

def test_wnioski_z_rejestru_z_ostatniego_roku(magazyn, tmp_path):
    szukajka = archiwum(magazyn, tmp_path)
    wnioski = rejestr.wszystkie()
    biezacy = wnioski[0]

    dokumenty = szukajka.dokumenty(pomin_wniosek=biezacy.id)
    z_rejestru = [d for d in dokumenty if d.rodzaj == RODZAJ_WNIOSEK]
    assert len(z_rejestru) == len(wnioski) - 1                       # bez wniosku, nad którym pracujemy
    assert all(d.wniosek_id != biezacy.id for d in z_rejestru)

    za_rok = max(w.data_wplywu for w in wnioski) + timedelta(days=400)
    assert not [d for d in szukajka.dokumenty(dzis=za_rok) if d.rodzaj == RODZAJ_WNIOSEK]  # starsze niż rok

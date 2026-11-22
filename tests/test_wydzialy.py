"""Dobór wydziałów: algorytm (dobor_wydzialow.py + wykaz z BIP) i jego podłączenie do aplikacji – bez modelu."""

import asyncio
import urllib.error
from datetime import date

import pytest

from asystent.ai import DaneSprawy, Intencja, Urzedus, WynikDoboru
from asystent.ai import dobor_wydzialow as algorytm
from asystent.ai import wydzialy as dobor
from asystent.ai.wydzialy import ZRODLO_BIELIK, ZRODLO_RANKING, Propozycja


def skroty(wynik: WynikDoboru) -> list[str]:
    return [p.skrot for p in wynik.propozycje]


@pytest.fixture
def bez_lm_studio(monkeypatch):
    def brak_polaczenia(*_args, **_kwargs):
        raise urllib.error.URLError('connection refused')
    monkeypatch.setattr(algorytm, 'wyslij', brak_polaczenia)


# --- lista wydziałów z BIP ---

def test_lista_wydzialow_z_bip_jest_wczytana():
    lista = dobor.wydzialy()
    assert len(lista) >= 19
    assert {'WGK', 'WOŚ', 'WZB', 'WZP', 'WUK'} <= {w['skrot'] for w in lista}
    assert all(w['zadania'] for w in lista)
    assert 'Wydział Zieleni i Gospodarki Komunalnej (WGK)' in dobor.nazwy_wydzialow()


def test_brak_pliku_z_wydzialami_nie_wywraca_aplikacji(monkeypatch, tmp_path):
    monkeypatch.setattr(algorytm, 'SCIEZKA_WYDZIALOW', str(tmp_path / 'brak.md'))
    dobor.wydzialy.cache_clear()
    try:
        wynik = dobor.dobierz('Ile drzew wycięto?', uzyj_llm=False)
        assert wynik.propozycje == [] and 'Brak listy wydziałów' in wynik.komunikat
    finally:
        dobor.wydzialy.cache_clear()


# --- ranking słów (bez Bielika) ---

@pytest.mark.parametrize('tekst, oczekiwany', [
    ('Proszę o informację, ile drzew wycięto w 2025 r. w parku Kochanowskiego.', 'WGK'),
    ('Ile zgłoszeń dotyczących smogu i kopciuchów wpłynęło w 2025 r.?', 'WOŚ'),
    ('Proszę o kopię umowy zawartej w trybie zamówienia publicznego (przetarg) na remont ulicy.', 'WZP'),
    ('Ile praw jazdy wydano w 2025 roku?', 'WUK'),
])
def test_ranking_wskazuje_wlasciwy_wydzial(tekst, oczekiwany):
    wynik = dobor.dobierz(tekst, uzyj_llm=False)
    assert wynik.zrodlo == ZRODLO_RANKING
    assert skroty(wynik)[0] == oczekiwany


def test_pytanie_o_koszty_trafia_tez_do_budzetu():
    wynik = dobor.dobierz('Ile drzew wycięto w parku i jaki był koszt wycinki?', uzyj_llm=False)
    assert 'WGK' in skroty(wynik) and 'WZB' in skroty(wynik)


def test_uzasadnienie_jest_czytelne():
    wynik = dobor.dobierz('Ile drzew wycięto w parku Kochanowskiego?', uzyj_llm=False)
    wgk = wynik.propozycje[0]
    assert wgk.uzasadnienie.startswith('pasujące: ')
    slowa = wgk.uzasadnienie.removeprefix('pasujące: ').split(', ')
    assert 'park' in slowa and len(slowa) == len(set(slowa))       # bez powtórzeń
    assert not any(znak in wgk.uzasadnienie for znak in '(?\\')     # bez resztek wyrażeń regularnych
    assert wynik.uzasadnienie.startswith('WGK – pasujące:')
    assert wynik.etykiety[0] == 'Wydział Zieleni i Gospodarki Komunalnej (WGK)'


def test_pusty_tekst():
    wynik = dobor.dobierz('   ', uzyj_llm=False)
    assert wynik.propozycje == [] and wynik.komunikat


# --- z Bielikiem (podstawiona odpowiedź modelu) ---

def test_bielik_wybiera_sposrod_kandydatow(monkeypatch):
    monkeypatch.setattr(algorytm, 'wyslij', lambda *_: {
        'wydzialy': [{'skrot': 'WGK', 'uzasadnienie': 'wycinka drzew w parku'}, {'skrot': 'XYZ'}]})
    wynik = dobor.dobierz('Ile drzew wycięto w parku Kochanowskiego?')
    assert wynik.zrodlo == ZRODLO_BIELIK
    assert wynik.propozycje[0] == Propozycja('WGK', 'Wydział Zieleni i Gospodarki Komunalnej', 'wycinka drzew w parku')
    assert 'XYZ' not in skroty(wynik)  # skrót spoza listy kandydatów jest odrzucany


def test_lider_rankingu_nie_ginie_gdy_bielik_go_pominie(monkeypatch):
    monkeypatch.setattr(algorytm, 'wyslij', lambda *_: {'wydzialy': [{'skrot': 'WIM', 'uzasadnienie': 'inwestycja'}]})
    wynik = dobor.dobierz('Ile drzew i krzewów wycięto w parku przy skwerze?')
    assert skroty(wynik)[0] == 'WGK' and 'pominięty przez Bielika' in wynik.propozycje[0].uzasadnienie


def test_bez_lm_studio_wynik_z_rankingu(bez_lm_studio):
    wynik = dobor.dobierz('Ile drzew wycięto w parku Kochanowskiego?')
    assert wynik.zrodlo == ZRODLO_RANKING
    assert skroty(wynik)[0] == 'WGK'
    assert 'LM Studio' in wynik.komunikat


def test_bledna_odpowiedz_modelu_daje_ranking(monkeypatch):
    monkeypatch.setattr(algorytm, 'wyslij', lambda *_: {})
    wynik = dobor.dobierz('Ile drzew wycięto w parku Kochanowskiego?')
    assert wynik.zrodlo == ZRODLO_RANKING and skroty(wynik)[0] == 'WGK'


# --- Urzęduś ---

def test_urzedus_proponuje_wydzialy_z_modulu(monkeypatch):
    async def dobor_testowy(tekst: str) -> WynikDoboru:
        return WynikDoboru([Propozycja('WGK', 'Wydział Zieleni i Gospodarki Komunalnej', 'wycinka drzew')],
                           ZRODLO_BIELIK)
    urzedus = Urzedus(bielik=None, dobor_wydzialow=dobor_testowy)
    sprawa = DaneSprawy(nr='UDIP.1.2026', temat='Wycinka', data_wplywu=date.today(),
                        termin=date.today(), tekst_wniosku='Ile drzew wycięto?')
    wynik = asyncio.run(urzedus.obsluz('Do których wydziałów to wysłać?', sprawa))
    assert wynik.intencja == Intencja.WYDZIALY
    assert 'Wydział Zieleni i Gospodarki Komunalnej (WGK) – wycinka drzew' in wynik.tekst
    assert wynik.wydzialy.etykiety == ['Wydział Zieleni i Gospodarki Komunalnej (WGK)']

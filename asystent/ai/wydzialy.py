"""Dobór wydziałów – most między aplikacją a modułem kolegi (`program2.py` + `wydzialy.md` w katalogu repozytorium).

Sam algorytm jest w `program2.py`: ranking słów kluczowych i opisów zadań z BIP, a potem Bielik wybiera
spośród najlepszych kandydatów (bez Bielika – wynik z rankingu). Tutaj tylko:
- lista wydziałów wczytywana raz,
- wynik w postaci wygodnej dla GUI i czatu,
- wersja asynchroniczna (zapytanie do Bielika w `program2` jest blokujące, więc idzie w osobnym wątku).
"""

from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

KATALOG_REPOZYTORIUM = Path(__file__).resolve().parents[2]
if str(KATALOG_REPOZYTORIUM) not in sys.path:
    sys.path.insert(0, str(KATALOG_REPOZYTORIUM))

import program2  # noqa: E402  – moduł kolegi, celowo w katalogu głównym (uruchamiany też z terminala)

ZRODLO_BIELIK = 'bielik'
ZRODLO_RANKING = 'ranking'


@dataclass(frozen=True)
class Propozycja:
    skrot: str
    nazwa: str
    uzasadnienie: str = ''

    @property
    def etykieta(self) -> str:
        return f'{self.nazwa} ({self.skrot})'


@dataclass(frozen=True)
class WynikDoboru:
    propozycje: list[Propozycja] = field(default_factory=list)
    zrodlo: str = ZRODLO_RANKING      # 'bielik' – wybrał model, 'ranking' – same słowa kluczowe
    komunikat: str = ''               # np. dlaczego nie ma wyniku od Bielika

    @property
    def etykiety(self) -> list[str]:
        return [p.etykieta for p in self.propozycje]

    @property
    def uzasadnienie(self) -> str:
        """Jedna linia na wydział: „SKRÓT – uzasadnienie” (zapisywane w rejestrze przy wniosku)."""
        return '\n'.join(f'{p.skrot} – {p.uzasadnienie}' for p in self.propozycje if p.uzasadnienie)

    @property
    def opis_zrodla(self) -> str:
        return 'wybrał Bielik spośród wydziałów z BIP' if self.zrodlo == ZRODLO_BIELIK \
            else 'dopasowanie słów kluczowych do zadań wydziałów z BIP'


@lru_cache(maxsize=1)
def wydzialy() -> tuple[dict, ...]:
    """Wydziały z `wydzialy.md` (nazwa, skrot, zadania, rejestry). Pusta krotka, gdy pliku brak."""
    try:
        return tuple(program2.wczytaj_wydzialy(program2.SCIEZKA_WYDZIALOW))
    except (OSError, SystemExit):  # program2 kończy się sys.exit, gdy plik jest pusty
        return ()


def nazwy_wydzialow() -> list[str]:
    """Etykiety wszystkich wydziałów – „Wydział Zieleni i Gospodarki Komunalnej (WGK)”."""
    return [f"{w['nazwa']} ({w['skrot']})" for w in wydzialy()]


def _czytelne(uzasadnienie: str) -> str:
    """Bez powtórzeń na liście „pasujące: drzew, park, drzew”."""
    poczatek, dwukropek, slowa = uzasadnienie.partition('pasujące: ')
    if not dwukropek:
        return uzasadnienie.strip()
    unikalne = list(dict.fromkeys(s.strip() for s in slowa.split(',') if s.strip()))
    return f'{poczatek}{dwukropek}{", ".join(unikalne)}'.strip()


def dobierz(tekst: str, *, uzyj_llm: bool = True) -> WynikDoboru:
    """Wydziały, do których trzeba skierować prośbę o informacje (blokujące – w GUI przez `run.io_bound`)."""
    lista = list(wydzialy())
    if not lista:
        return WynikDoboru(komunikat=f'Brak listy wydziałów ({program2.SCIEZKA_WYDZIALOW}).')
    if not tekst.strip():
        return WynikDoboru(komunikat='Brak tekstu wniosku.')
    wybrane, zrodlo, komunikat = program2.dobierz(tekst, lista, uzyj_llm)
    propozycje = [Propozycja(w['skrot'], w['nazwa'], _czytelne(uzasadnienie)) for w, uzasadnienie in wybrane]
    return WynikDoboru(propozycje, zrodlo, re.sub(r'\s+', ' ', komunikat).strip())


async def dobierz_async(tekst: str, *, uzyj_llm: bool = True) -> WynikDoboru:
    return await asyncio.to_thread(dobierz, tekst, uzyj_llm=uzyj_llm)

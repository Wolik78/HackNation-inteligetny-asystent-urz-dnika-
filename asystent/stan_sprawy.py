"""Zapis i odczyt roboczego stanu sprawy: projekt pisma, anonimizacja, wynik kontroli jakości.

Plik `stan.json` leży w katalogu sprawy, obok jej dokumentów. Zapis jest atomowy (najpierw plik tymczasowy,
potem podmiana), więc przerwanie w trakcie – np. zamknięcie okna – nie uszkodzi zapisanego stanu.
"""

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .ai.bielik_service import Zadanie
from .kontrola import Problem, Wartosc, WynikKontroli

log = logging.getLogger(__name__)

NAZWA_PLIKU = 'stan.json'
WERSJA = 1


def serializuj(stan: dict) -> str:
    """Stan widoku sprawy jako JSON – tylko to, co warto zachować między uruchomieniami."""
    kontrola: WynikKontroli | None = stan.get('kontrola')
    kompletnosc = stan.get('kompletnosc')
    if isinstance(kompletnosc, list):
        kompletnosc = [asdict(z) for z in kompletnosc]
    elif kompletnosc == 'trwa':
        kompletnosc = None  # przerwana ocena – po powrocie urzędnik uruchomi ją ponownie
    dane = {
        'wersja': WERSJA,
        'projekt': stan.get('projekt', ''),
        'ukryte': sorted(stan.get('ukryte', ())),
        'wykryte': dict(stan.get('wykryte', {})),
        'kontrola': asdict(kontrola) if kontrola else None,
        'kontrola_tekst': stan.get('kontrola_tekst'),
        'kompletnosc': kompletnosc,
        'wzor': stan.get('wzor'),  # plik archiwalnej odpowiedzi użytej jako wzór pisma
    }
    return json.dumps(dane, ensure_ascii=False, indent=2)


def zapisz(katalog_sprawy: Path, stan: dict) -> Path:
    katalog_sprawy.mkdir(parents=True, exist_ok=True)
    sciezka = katalog_sprawy / NAZWA_PLIKU
    tymczasowy = sciezka.with_suffix('.tmp')
    tymczasowy.write_text(serializuj(stan), 'utf-8')
    os.replace(tymczasowy, sciezka)
    return sciezka


def wczytaj(katalog_sprawy: Path) -> dict:
    """Zapisany stan sprawy albo {} – gdy go nie ma lub plik jest uszkodzony (wtedy odkładamy go na bok)."""
    sciezka = katalog_sprawy / NAZWA_PLIKU
    if not sciezka.exists():
        return {}
    try:
        dane = json.loads(sciezka.read_text('utf-8'))
        stan = {
            'projekt': str(dane.get('projekt', '')),
            'ukryte': set(dane.get('ukryte', [])),
            'wykryte': dict(dane.get('wykryte', {})),
            'kontrola_tekst': dane.get('kontrola_tekst'),
            'kontrola': _wynik_kontroli(dane.get('kontrola')),
            'kompletnosc': _kompletnosc(dane.get('kompletnosc')),
            'wzor': dane.get('wzor') if isinstance(dane.get('wzor'), str) else None,
        }
    except (ValueError, TypeError, KeyError, AttributeError):
        uszkodzony = sciezka.with_name(f'{NAZWA_PLIKU}.uszkodzony-{datetime.now():%Y%m%d-%H%M%S}')
        log.warning('Uszkodzony stan sprawy %s – odkładam jako %s', sciezka, uszkodzony.name)
        os.replace(sciezka, uszkodzony)
        return {}
    stan['zapisano'] = datetime.fromtimestamp(sciezka.stat().st_mtime)
    return stan


def _wynik_kontroli(dane: dict | None) -> WynikKontroli | None:
    if not dane:
        return None
    return WynikKontroli(wartosci=[Wartosc(**w) for w in dane.get('wartosci', [])],
                         problemy=[Problem(**p) for p in dane.get('problemy', [])])


def _kompletnosc(dane: list | str | None) -> list[Zadanie] | str | None:
    if isinstance(dane, list):
        return [Zadanie(**z) for z in dane]
    return dane

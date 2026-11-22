"""Dane demonstracyjne: 10 wniosków testowych w kalendarzu i archiwum testowe w Bazie wiedzy.

Przed pokazem jedno kliknięcie w Ustawieniach przygotowuje aplikację tak, żeby od razu było na czym szukać
podobnych spraw. Wszystkie dokumenty w `dane_testowe/` są fikcyjne.
"""

from dataclasses import dataclass
from pathlib import Path

from . import rejestr
from .konfiguracja import KATALOG_PROJEKTU
from .pliki import Kategoria, MagazynPlikow

ARCHIWUM_TESTOWE = KATALOG_PROJEKTU / 'dane_testowe' / 'archiwum'


@dataclass
class WynikDemo:
    nowe: int          # dodane archiwalne odpowiedzi
    pominiete: int     # były już w Bazie wiedzy


def wczytaj_archiwum_testowe(magazyn: MagazynPlikow, katalog: Path = ARCHIWUM_TESTOWE) -> WynikDemo:
    """Wgrywa archiwalne odpowiedzi z `dane_testowe/archiwum` do Bazy wiedzy (powtórnie – bez duplikatów)."""
    if not katalog.is_dir():
        raise FileNotFoundError(f'Brak folderu z danymi testowymi: {katalog}')
    nowe = pominiete = 0
    for plik in sorted(katalog.glob('*.txt')):
        if magazyn.zapisz(plik.read_bytes(), plik.name, Kategoria.ARCHIWUM).duplikat:
            pominiete += 1
        else:
            nowe += 1
    return WynikDemo(nowe, pominiete)


def przygotuj_demo(magazyn: MagazynPlikow) -> WynikDemo:
    """Odtwarza wnioski testowe (terminy liczone od dziś) i wgrywa archiwum testowe."""
    rejestr.przywroc_dane_testowe()
    return wczytaj_archiwum_testowe(magazyn)

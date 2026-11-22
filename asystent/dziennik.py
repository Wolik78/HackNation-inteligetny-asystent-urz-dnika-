"""Dziennik działań AI: co zaproponował asystent, co zatwierdził urzędnik i kiedy.

Plik `dziennik_ai.jsonl` w folderze danych – jeden wpis na linię, tylko dopisywanie (rozliczalność, art. 5 ust. 2
RODO). We wpisach są wyłącznie metadane: numer sprawy, rodzaj czynności, liczby i skróty wydziałów – nigdy treść
dokumentów, pism ani dane osobowe.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .konfiguracja import KATALOG_DANYCH

log = logging.getLogger(__name__)

PLIK = KATALOG_DANYCH / 'dziennik_ai.jsonl'
AI = 'AI (Bielik)'
ASYSTENT = 'asystent (reguły)'
URZEDNIK = 'urzędnik'
_blokada = threading.Lock()


@dataclass(frozen=True)
class Wpis:
    kiedy: str
    kto: str
    czynnosc: str
    sprawa: str = ''
    szczegoly: str = ''


def zapisz(czynnosc: str, *, kto: str = AI, sprawa: str = '', szczegoly: str = '', plik: Path | None = None) -> None:
    """Dopisuje wpis. Błąd zapisu nie przerywa pracy urzędnika – trafia tylko do logu aplikacji."""
    wpis = Wpis(datetime.now().isoformat(timespec='seconds'), kto, czynnosc, sprawa, szczegoly)
    sciezka = plik or PLIK
    try:
        with _blokada:
            sciezka.parent.mkdir(parents=True, exist_ok=True)
            with sciezka.open('a', encoding='utf-8') as f:
                f.write(json.dumps(asdict(wpis), ensure_ascii=False) + '\n')
    except OSError:
        log.exception('Nie udało się zapisać wpisu w dzienniku AI')


def wpisy(*, sprawa: str | None = None, limit: int = 500, plik: Path | None = None) -> list[Wpis]:
    """Najnowsze wpisy (od najnowszego), opcjonalnie tylko jednej sprawy."""
    sciezka = plik or PLIK
    if not sciezka.exists():
        return []
    wynik = []
    for linia in reversed(sciezka.read_text('utf-8').splitlines()):
        try:
            wpis = Wpis(**json.loads(linia))
        except (ValueError, TypeError):
            continue  # uszkodzona linia nie blokuje reszty dziennika
        if sprawa and wpis.sprawa != sprawa:
            continue
        wynik.append(wpis)
        if len(wynik) >= limit:
            break
    return wynik

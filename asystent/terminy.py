"""Liczenie terminów urzędowych: dni robocze, święta, art. 57 KPA.

- termin w dniach: nie liczy się dnia wpływu (art. 57 § 1 KPA),
- termin w miesiącach: kończy się w dniu odpowiadającym dniowi początkowemu, a gdy go brak – w ostatnim dniu
  miesiąca (art. 57 § 3 KPA),
- koniec terminu w sobotę lub dzień ustawowo wolny przesuwa się na najbliższy dzień roboczy (art. 57 § 4 KPA).
"""

import calendar
from datetime import date, timedelta
from functools import lru_cache

NAZWY_DNI = ('poniedziałek', 'wtorek', 'środa', 'czwartek', 'piątek', 'sobota', 'niedziela')
NAZWY_DNI_KROTKIE = ('pon.', 'wt.', 'śr.', 'czw.', 'pt.', 'sob.', 'niedz.')
NAZWY_MIESIECY = ('styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec', 'lipiec', 'sierpień', 'wrzesień',
                  'październik', 'listopad', 'grudzień')


def wielkanoc(rok: int) -> date:
    """Data Wielkanocy (algorytm Gaussa w wersji Meeusa/Jonesa/Butchera)."""
    a, b, c = rok % 19, rok // 100, rok % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    miesiac = (h + l - 7 * m + 114) // 31
    dzien = (h + l - 7 * m + 114) % 31 + 1
    return date(rok, miesiac, dzien)


@lru_cache(maxsize=None)
def swieta(rok: int) -> dict[date, str]:
    """Dni ustawowo wolne od pracy w Polsce."""
    pierwszy_dzien = wielkanoc(rok)
    dni = {
        date(rok, 1, 1): 'Nowy Rok',
        date(rok, 1, 6): 'Trzech Króli',
        pierwszy_dzien: 'Wielkanoc',
        pierwszy_dzien + timedelta(days=1): 'Poniedziałek Wielkanocny',
        date(rok, 5, 1): 'Święto Pracy',
        date(rok, 5, 3): 'Święto Konstytucji 3 Maja',
        pierwszy_dzien + timedelta(days=49): 'Zielone Świątki',
        pierwszy_dzien + timedelta(days=60): 'Boże Ciało',
        date(rok, 8, 15): 'Wniebowzięcie NMP',
        date(rok, 11, 1): 'Wszystkich Świętych',
        date(rok, 11, 11): 'Święto Niepodległości',
        date(rok, 12, 25): 'Boże Narodzenie',
        date(rok, 12, 26): 'Drugi dzień Bożego Narodzenia',
    }
    if rok >= 2025:
        dni[date(rok, 12, 24)] = 'Wigilia'  # dzień wolny od 2025 r.
    return dni


def jest_dniem_wolnym(dzien: date) -> bool:
    """Sobota, niedziela albo święto – wtedy termin nie może się skończyć (art. 57 § 4 KPA)."""
    return dzien.weekday() >= 5 or dzien in swieta(dzien.year)


def powod_wolnego(dzien: date) -> str:
    return swieta(dzien.year).get(dzien) or NAZWY_DNI[dzien.weekday()]


def najblizszy_roboczy(dzien: date) -> date:
    """Ten sam dzień, jeśli jest roboczy, w przeciwnym razie następny roboczy."""
    while jest_dniem_wolnym(dzien):
        dzien += timedelta(days=1)
    return dzien


def nastepny_roboczy(dzien: date) -> date:
    return najblizszy_roboczy(dzien + timedelta(days=1))


def dodaj_dni_robocze(dzien: date, ile: int) -> date:
    """Przesunięcie o `ile` dni roboczych (ujemne – wstecz); 0 = najbliższy roboczy."""
    if ile == 0:
        return najblizszy_roboczy(dzien)
    krok = 1 if ile > 0 else -1
    pozostalo = abs(ile)
    while pozostalo:
        dzien += timedelta(days=krok)
        if not jest_dniem_wolnym(dzien):
            pozostalo -= 1
    return dzien


def dodaj_miesiace(dzien: date, miesiace: int) -> date:
    """Art. 57 § 3 KPA: ten sam dzień miesiąca, a gdy go brak – ostatni dzień miesiąca."""
    indeks = dzien.month - 1 + miesiace
    rok, miesiac = dzien.year + indeks // 12, indeks % 12 + 1
    return date(rok, miesiac, min(dzien.day, calendar.monthrange(rok, miesiac)[1]))


def koniec_terminu(poczatek: date, *, dni: int = 0, miesiace: int = 0) -> tuple[date, str]:
    """Koniec terminu liczonego od zdarzenia (np. wpływu wniosku) i ewentualny opis przesunięcia."""
    koniec = dodaj_miesiace(poczatek, miesiace) + timedelta(days=dni)
    if not jest_dniem_wolnym(koniec):
        return koniec, ''
    przesuniety = najblizszy_roboczy(koniec)
    return przesuniety, (f'Termin przypadał na {koniec:%d.%m} ({powod_wolnego(koniec)}) – przesunięty na '
                         f'{NAZWY_DNI[przesuniety.weekday()]} {przesuniety:%d.%m} (art. 57 § 4 KPA).')

"""Kontrola jakości projektu pisma – bez AI: natychmiastowa i przewidywalna.

Najważniejsza część to sprawdzanie liczb: każda kwota, data i liczba w piśmie musi mieć pokrycie
w źródłach (wniosek, odpowiedzi wydziałów, dane sprawy). Wartość „znikąd” to najczęstszy objaw
halucynacji modelu – urzędnik widzi ją na czerwono, a potwierdzone wartości na zielono ze wskazaniem źródła.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from .anonimizacja import wykryj_wzorce

MIESIACE = {
    'stycznia': 1, 'lutego': 2, 'marca': 3, 'kwietnia': 4, 'maja': 5, 'czerwca': 6, 'lipca': 7,
    'sierpnia': 8, 'września': 9, 'października': 10, 'listopada': 11, 'grudnia': 12,
}

# Wartości, które w piśmie urzędowym są zawsze uzasadnione (nie pochodzą ze źródeł sprawy):
# data ustawy o dostępie do informacji publicznej, termin 14 dni, data KPA.
ZAWSZE_DOZWOLONE = {'D:2001-09-06', 'N:2001', 'N:14', 'D:1960-06-14', 'N:1960'}

_POMIJANE = [re.compile(w, re.IGNORECASE) for w in (
    r'\b(art|ust|pkt|poz|lit|nr)\.?\s*\d+[a-z]?\b',          # odwołania do przepisów
    r'§\s*\d+',
    r'\bDz\.\s?U\.[^\n]{0,30}',
    r'\bUDIP[.\-/]\d+[.\-/]\d{2,4}\b',                       # numer sprawy
    r'(?m)^\s*\d{1,2}[.)](?=\s)',                            # numeracja punktów
)]
_DATA_LICZBOWA = re.compile(r'(?<!\d)(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})(?!\d)')
_DATA_SLOWNA = re.compile(r'(?<!\d)(\d{1,2})\s+(' + '|'.join(MIESIACE) + r')\s+(\d{4})(?!\d)', re.IGNORECASE)
_LICZBA = re.compile(r'(?<![\w,])\d{1,3}(?:[  .]\d{3})+(?:,\d+)?(?!\w)|(?<![\w,])\d+(?:,\d+)?(?!\w)')
_JEDNOSTKA = re.compile(r'\s*(zł|pln|%|proc|tys|mln|mld|osób|os\.|etat|egz)', re.IGNORECASE)
_POLE_DO_UZUPELNIENIA = re.compile(r'\[[^\]\n]{2,80}\]')


@dataclass
class Wartosc:
    tekst: str             # tak jak w piśmie, np. „1 240 000”
    klucz: str             # postać znormalizowana, np. „N:1240000”, „D:2026-11-20”
    zrodlo: str | None     # nazwa źródła, w którym występuje; None = brak pokrycia


@dataclass
class Problem:
    waga: str              # 'blad' albo 'ostrzezenie'
    opis: str
    fragment: str = ''     # tekst w piśmie, którego dotyczy (do podświetlenia)


@dataclass
class WynikKontroli:
    wartosci: list[Wartosc] = field(default_factory=list)
    problemy: list[Problem] = field(default_factory=list)

    @property
    def bledy(self) -> list[Problem]:
        return [p for p in self.problemy if p.waga == 'blad']

    @property
    def ostrzezenia(self) -> list[Problem]:
        return [p for p in self.problemy if p.waga == 'ostrzezenie']

    @property
    def potwierdzone(self) -> list[Wartosc]:
        return [w for w in self.wartosci if w.zrodlo]


def wyciagnij_wartosci(tekst: str) -> list[tuple[str, str]]:
    """Daty i liczby z tekstu jako pary (tekst oryginalny, klucz). Odwołania do przepisów są pomijane."""
    zamaskowany = tekst
    for wzorzec in _POMIJANE:
        zamaskowany = wzorzec.sub(lambda m: ' ' * len(m.group()), zamaskowany)

    wartosci: list[tuple[str, str]] = []

    def dodaj_date(m: re.Match, miesiac: int) -> None:
        dzien, rok = int(m.group(1)), int(m.group(3))
        if 1 <= dzien <= 31 and 1 <= miesiac <= 12:
            wartosci.append((tekst[m.start():m.end()], f'D:{rok:04d}-{miesiac:02d}-{dzien:02d}'))

    for m in _DATA_LICZBOWA.finditer(zamaskowany):
        dodaj_date(m, int(m.group(2)))
    for m in _DATA_SLOWNA.finditer(zamaskowany):
        dodaj_date(m, MIESIACE[m.group(2).lower()])
    for wzorzec in (_DATA_LICZBOWA, _DATA_SLOWNA):
        zamaskowany = wzorzec.sub(lambda m: ' ' * len(m.group()), zamaskowany)

    for m in _LICZBA.finditer(zamaskowany):
        oryginal = tekst[m.start():m.end()]
        cyfry = re.sub(r'[  .]', '', oryginal).replace(',', '.')
        z_jednostka = bool(_JEDNOSTKA.match(zamaskowany, m.end()))
        if '.' not in cyfry and int(cyfry) < 10 and not z_jednostka:
            continue  # „w 2 kampaniach” – małe liczebniki pomijamy
        wartosci.append((oryginal, f'N:{cyfry.lstrip("0") or "0"}'))
    return wartosci


def sprawdz_pismo(projekt: str, zrodla: Iterable[tuple[str, str]], *, do_pokrycia: Iterable[tuple[str, str]] = (),
                  ukryte: Iterable[str] = (), dane_sprawy: Iterable[str] = ()) -> WynikKontroli:
    """Sprawdza projekt pisma.

    zrodla – pary (nazwa, tekst), z których pismo może czerpać wartości (np. wniosek).
    do_pokrycia – odpowiedzi wydziałów: też są źródłem, a dodatkowo ich wartości powinny trafić do pisma
                  (pominięta kwota to ostrzeżenie – model potrafi „zgubić” część danych).
    dane_sprawy – dodatkowe dozwolone wartości (numer sprawy, data wpływu, termin, dzisiejsza data).
    ukryte – dane osobowe już zatwierdzone do ukrycia w anonimizacji.
    """
    wynik = WynikKontroli()
    if not projekt.strip():
        wynik.problemy.append(Problem('blad', 'Projekt odpowiedzi jest pusty.'))
        return wynik
    zrodla, do_pokrycia = list(zrodla), list(do_pokrycia)

    pochodzenie: dict[str, str] = {}
    for nazwa, tekst in [*do_pokrycia, *zrodla, ('dane sprawy', ' '.join(dane_sprawy))]:
        for _, klucz in wyciagnij_wartosci(tekst):
            pochodzenie.setdefault(klucz, nazwa)

    wartosci_pisma = wyciagnij_wartosci(projekt)
    widziane = set()
    for oryginal, klucz in wartosci_pisma:
        zrodlo = pochodzenie.get(klucz) or ('przepisy' if klucz in ZAWSZE_DOZWOLONE else None)
        wynik.wartosci.append(Wartosc(oryginal, klucz, zrodlo))
        if zrodlo is None and klucz not in widziane:
            widziane.add(klucz)
            rodzaj = 'daty' if klucz.startswith('D:') else 'wartości'
            wynik.problemy.append(Problem(
                'blad', f'„{oryginal}” – tej {rodzaj} nie ma we wniosku ani w odpowiedziach wydziałów. '
                        'Sprawdź, skąd się wzięła.', oryginal))

    klucze_pisma = {klucz for _, klucz in wartosci_pisma}
    for nazwa, tekst in do_pokrycia:
        dane_osobowe = list(wykryj_wzorce(tekst))
        for oryginal, klucz in wyciagnij_wartosci(tekst):
            if klucz.startswith('D:') or klucz in klucze_pisma or any(oryginal in d for d in dane_osobowe):
                continue  # daty pism wydziałów i dane osobowe nie muszą trafić do odpowiedzi
            klucze_pisma.add(klucz)
            wynik.problemy.append(Problem('ostrzezenie', f'W odpowiedzi wydziału ({nazwa}) jest wartość „{oryginal}”, '
                                                         'której nie ma w piśmie – czy na pewno ją pominąć?'))

    for pole in dict.fromkeys(_POLE_DO_UZUPELNIENIA.findall(projekt)):
        wynik.problemy.append(Problem('blad', f'Pole do uzupełnienia: {pole}', pole))

    ukryte = set(ukryte)
    for ciag, typ in wykryj_wzorce(projekt).items():
        if ciag not in ukryte:
            wynik.problemy.append(Problem('ostrzezenie', f'Nieukryte dane osobowe: {ciag} ({typ}) – '
                                                         'sprawdź krok „Anonimizacja”.', ciag))

    if not re.search(r'\bart\.\s*\d', projekt):
        wynik.problemy.append(Problem('ostrzezenie', 'Brak podstawy prawnej (np. art. 2 ust. 1 i art. 10 ust. 1 '
                                                     'ustawy o dostępie do informacji publicznej).'))
    if 'szanown' not in projekt[:400].lower():
        wynik.problemy.append(Problem('ostrzezenie', 'Brak zwrotu grzecznościowego na początku pisma.'))
    if 'z poważaniem' not in projekt.lower():
        wynik.problemy.append(Problem('ostrzezenie', 'Brak formuły „Z poważaniem” na końcu pisma.'))
    if '**' in projekt or re.search(r'(?m)^#{1,6}\s', projekt):
        wynik.problemy.append(Problem('ostrzezenie', 'W piśmie zostało formatowanie Markdown (** albo #).'))
    if len(projekt.strip()) < 150:
        wynik.problemy.append(Problem('ostrzezenie', 'Pismo jest bardzo krótkie – sprawdź, czy jest kompletne.'))
    return wynik

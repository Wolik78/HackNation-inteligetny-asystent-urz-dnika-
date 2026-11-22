"""Rejestr wniosków UDIP – kalendarz spraw z terminami i statusami.

Wszystkie wnioski (także 10 testowych) są zapisywane w pliku JSON w katalogu danych. Przy pierwszym
uruchomieniu powstają wnioski testowe z terminami ustawionymi względem dzisiejszej daty; można je odświeżyć
w Ustawieniach. Później można to podmienić na bazę danych, nie zmieniając funkcji publicznych modułu.

Statusy (instrukcja działania, pkt 11): brak działań → zapytania wysłane do wydziałów → odpowiedź
przygotowana → odpowiedź wysłana. Kwerenda to osobne oznaczenie z własnym terminem (do 2 miesięcy).
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from .konfiguracja import KATALOG_DANYCH, TERMIN_DNI
from .terminy import NAZWY_DNI, dodaj_dni_robocze, koniec_terminu, nastepny_roboczy

log = logging.getLogger(__name__)

PLIK_REJESTRU = KATALOG_DANYCH / 'rejestr_wnioskow.json'
WERSJA_PLIKU = 2
MIESIACE_KWERENDY = 2  # art. 13 ust. 2 UDIP

STATUSY = {
    'brak': 'Brak działań',
    'wydzialy': 'Zapytania wysłane do wydziałów',
    'przygotowana': 'Odpowiedź przygotowana',
    'wyslana': 'Odpowiedź wysłana',
}
KOLEJNOSC = list(STATUSY)


@dataclass
class Wniosek:
    id: int
    nr: str
    temat: str
    wnioskodawca: str
    data_wplywu: date
    kto: str
    status: str = 'brak'
    kwerenda: bool = False
    termin_kwerendy: date | None = None   # wybrany przy kwerendzie; None = najpóźniejszy dopuszczalny
    kontakt: str = ''
    data_odpowiedzi: date | None = None
    sugerowane_wydzialy: list[str] = field(default_factory=list)  # podpowiedź Bielika
    uzasadnienie_wydzialu: str = ''
    historia: list[dict] = field(default_factory=list)            # {'kiedy': ISO, 'zdarzenie': tekst}
    rodzaj: str = 'zwykla'                                        # klasyfikacja (asystent/klasyfikacja.py)
    uzasadnienie_rodzaju: str = ''
    testowy: bool = False

    # --- terminy ---

    @property
    def termin_podstawowy(self) -> date:
        return koniec_terminu(self.data_wplywu, dni=TERMIN_DNI)[0]

    @property
    def termin_maksymalny_kwerendy(self) -> date:
        return koniec_terminu(self.data_wplywu, miesiace=MIESIACE_KWERENDY)[0]

    @property
    def termin(self) -> date:
        if self.kwerenda:
            return self.termin_kwerendy or self.termin_maksymalny_kwerendy
        return self.termin_podstawowy

    @property
    def dni_kwerendy(self) -> int:
        """O ile dni kwerenda wydłużyła termin (instrukcja, pkt 11c: „kwerenda + ilość dni”)."""
        return (self.termin - self.termin_podstawowy).days if self.kwerenda else 0

    @property
    def uwaga_o_terminie(self) -> str:
        if self.kwerenda:
            return (f'Kwerenda: termin wydłużony o {self.dni_kwerendy} dni (art. 13 ust. 2 UDIP, '
                    f'najpóźniej {self.termin_maksymalny_kwerendy:%d.%m.%Y}).')
        return koniec_terminu(self.data_wplywu, dni=TERMIN_DNI)[1]

    @property
    def dni_do_terminu(self) -> int:
        return (self.termin - date.today()).days

    @property
    def pilnosc(self) -> str:
        """Jedno z: wyslano, po_terminie, dzis, jutro (najbliższy dzień roboczy), blisko (do 3 dni roboczych), ok."""
        if self.status == 'wyslana':
            return 'wyslano'
        dzis = date.today()
        if self.termin < dzis:
            return 'po_terminie'
        if self.termin == dzis:
            return 'dzis'
        if self.termin <= nastepny_roboczy(dzis):
            return 'jutro'
        return 'blisko' if self.termin <= dodaj_dni_robocze(dzis, 3) else 'ok'

    @property
    def pozostalo(self) -> str:
        dni = self.dni_do_terminu
        if self.pilnosc == 'jutro' and dni > 1:
            return f'{NAZWY_DNI[self.termin.weekday()]} (najbliższy dzień roboczy)'
        return {
            'wyslano': '—',
            'po_terminie': f'po terminie ({-dni} d.)',
            'dzis': 'dziś',
            'jutro': 'jutro',
        }.get(self.pilnosc, f'za {dni} dni')

    @property
    def status_opis(self) -> str:
        return STATUSY[self.status]


_wnioski: list[Wniosek] = []


def oblicz_termin(data_wplywu: date, kwerenda: bool = False) -> tuple[date, str]:
    """Termin odpowiedzi dla nowego wniosku i opis ewentualnego przesunięcia (np. do formularza)."""
    if kwerenda:
        return koniec_terminu(data_wplywu, miesiace=MIESIACE_KWERENDY)
    return koniec_terminu(data_wplywu, dni=TERMIN_DNI)


# --- odczyt ------------------------------------------------------------------------

def wszystkie(rok: int | None = None) -> list[Wniosek]:
    """Wnioski od najstarszych do najnowszych (opcjonalnie tylko z danego roku wpływu)."""
    wynik = [w for w in _wnioski if rok is None or w.data_wplywu.year == rok]
    return sorted(wynik, key=lambda w: (w.data_wplywu, w.id))


def lata() -> list[int]:
    """Lata, z których są wnioski (zawsze z bieżącym), od najnowszego."""
    return sorted({w.data_wplywu.year for w in _wnioski} | {date.today().year}, reverse=True)


def pobierz(id: int) -> Wniosek | None:
    return next((w for w in _wnioski if w.id == id), None)


def nastepny_numer(rok: int | None = None) -> str:
    rok = rok or date.today().year
    zajete = {w.nr for w in _wnioski}
    numer = sum(w.data_wplywu.year == rok for w in _wnioski) + 1
    while f'UDIP.{numer}.{rok}' in zajete:
        numer += 1
    return f'UDIP.{numer}.{rok}'


# --- zmiany ------------------------------------------------------------------------

def dodaj(*, nr: str, temat: str, wnioskodawca: str, data_wplywu: date, kto: str,
          kwerenda: bool = False, kontakt: str = '', sugerowane_wydzialy: list[str] | None = None,
          uzasadnienie_wydzialu: str = '', rodzaj: str = 'zwykla', uzasadnienie_rodzaju: str = '') -> Wniosek:
    if any(w.nr == nr for w in _wnioski):
        raise ValueError(f'Wniosek o numerze {nr} już istnieje.')
    wniosek = Wniosek(
        id=max((w.id for w in _wnioski), default=0) + 1,
        nr=nr, temat=temat, wnioskodawca=wnioskodawca, data_wplywu=data_wplywu, kto=kto,
        kwerenda=kwerenda, kontakt=kontakt,
        sugerowane_wydzialy=list(sugerowane_wydzialy or []), uzasadnienie_wydzialu=uzasadnienie_wydzialu,
        rodzaj=rodzaj, uzasadnienie_rodzaju=uzasadnienie_rodzaju,
    )
    _odnotuj(wniosek, 'Zarejestrowano wniosek' + (' (z kwerendą)' if kwerenda else ''))
    _wnioski.append(wniosek)
    _zapisz()
    return wniosek


def zmien_status(wniosek: Wniosek, status: str, *, data_odpowiedzi: date | None = None,
                 powod: str = '') -> bool:
    """Ustawia status (także „wstecz”). Zwraca False, jeśli nic się nie zmieniło."""
    if status not in STATUSY:
        raise ValueError(f'Nieznany status: {status}')
    if status == wniosek.status and (status != 'wyslana' or data_odpowiedzi in (None, wniosek.data_odpowiedzi)):
        return False
    wniosek.status = status
    wniosek.data_odpowiedzi = (data_odpowiedzi or date.today()) if status == 'wyslana' else None
    opis = f'Status: {STATUSY[status]}'
    if status == 'wyslana':
        opis += f' ({wniosek.data_odpowiedzi:%d.%m.%Y})'
    _odnotuj(wniosek, opis + (f' – {powod}' if powod else ''))
    _zapisz()
    return True


def awansuj_status(wniosek: Wniosek, status: str, powod: str) -> bool:
    """Automatyczna zmiana statusu po czynności urzędnika – tylko „do przodu”, nigdy wstecz."""
    if KOLEJNOSC.index(status) <= KOLEJNOSC.index(wniosek.status):
        return False
    return zmien_status(wniosek, status, powod=powod)


def ustaw_kwerende(wniosek: Wniosek, wlaczona: bool, termin: date | None = None) -> None:
    """Kwerenda wydłuża termin – najdłużej do 2 miesięcy od dnia złożenia wniosku."""
    if wlaczona and termin is not None:
        if termin <= wniosek.termin_podstawowy:
            raise ValueError(f'Termin kwerendy musi być późniejszy niż {wniosek.termin_podstawowy:%d.%m.%Y}.')
        if termin > wniosek.termin_maksymalny_kwerendy:
            raise ValueError('Kwerenda może wydłużyć termin najwyżej do 2 miesięcy od złożenia wniosku '
                             f'({wniosek.termin_maksymalny_kwerendy:%d.%m.%Y}).')
    wniosek.kwerenda = wlaczona
    wniosek.termin_kwerendy = termin if wlaczona else None
    _odnotuj(wniosek, f'Kwerenda – nowy termin {wniosek.termin:%d.%m.%Y}' if wlaczona else 'Wyłączono kwerendę')
    _zapisz()


def ustaw_rodzaj(wniosek: Wniosek, rodzaj: str, nazwa: str, uzasadnienie: str = '') -> bool:
    """Zmienia rodzaj sprawy (klasyfikację). Zwraca False, jeśli nic się nie zmieniło."""
    if wniosek.rodzaj == rodzaj:
        return False
    wniosek.rodzaj, wniosek.uzasadnienie_rodzaju = rodzaj, uzasadnienie
    _odnotuj(wniosek, f'Rodzaj sprawy: {nazwa}')
    _zapisz()
    return True


def aktualizuj(wniosek: Wniosek, *, temat: str, wnioskodawca: str, kontakt: str, data_wplywu: date,
               kto: str) -> None:
    """Edycja danych wniosku (numeru nie zmieniamy – od niego zależy katalog z dokumentami sprawy)."""
    if not temat.strip() or not wnioskodawca.strip():
        raise ValueError('Temat i wnioskodawca nie mogą być puste.')
    nowe = {'temat': temat.strip(), 'wnioskodawca': wnioskodawca.strip(), 'kontakt': kontakt.strip(),
            'data_wplywu': data_wplywu, 'kto': kto.strip()}
    zmienione = [pole for pole, wartosc in nowe.items() if getattr(wniosek, pole) != wartosc]
    if not zmienione:
        return
    for pole in zmienione:
        setattr(wniosek, pole, nowe[pole])
    if wniosek.kwerenda and wniosek.termin_kwerendy and wniosek.termin_kwerendy > wniosek.termin_maksymalny_kwerendy:
        wniosek.termin_kwerendy = None  # po zmianie daty wpływu wybrany termin mógł przestać być dopuszczalny
    nazwy = {'temat': 'temat', 'wnioskodawca': 'wnioskodawcę', 'kontakt': 'kontakt', 'data_wplywu': 'datę wpływu',
             'kto': 'prowadzącego'}
    _odnotuj(wniosek, 'Zmieniono ' + ', '.join(nazwy[p] for p in zmienione))
    _zapisz()


def usun(wniosek: Wniosek) -> None:
    _wnioski.remove(wniosek)
    _zapisz()


def zapisz_zmiany() -> None:
    """Utrwala zmiany wprowadzone bezpośrednio w obiektach Wniosek (np. podpowiedzi AI)."""
    _zapisz()


def przywroc_dane_testowe() -> None:
    """Usuwa wnioski testowe i tworzy je od nowa z terminami względem dzisiejszej daty (przed pokazem)."""
    _wnioski[:] = [w for w in _wnioski if not w.testowy]
    _dodaj_dane_testowe()
    _zapisz()


def odnotuj(wniosek: Wniosek, zdarzenie: str) -> None:
    """Dopisuje zdarzenie do przebiegu sprawy (np. zapisane zawiadomienie) i zapisuje rejestr."""
    _odnotuj(wniosek, zdarzenie)
    _zapisz()


def _odnotuj(wniosek: Wniosek, zdarzenie: str, kiedy: datetime | None = None) -> None:
    wniosek.historia.append({'kiedy': (kiedy or datetime.now()).isoformat(timespec='minutes'),
                             'zdarzenie': zdarzenie})


# --- zapis i odczyt -----------------------------------------------------------------

_POLA_DAT = ('data_wplywu', 'data_odpowiedzi', 'termin_kwerendy')


def _zapisz() -> None:
    rekordy = []
    for w in _wnioski:
        rekord = asdict(w)
        for pole in _POLA_DAT:
            rekord[pole] = rekord[pole].isoformat() if rekord[pole] else None
        rekordy.append(rekord)
    PLIK_REJESTRU.parent.mkdir(parents=True, exist_ok=True)
    tymczasowy = PLIK_REJESTRU.with_suffix('.tmp')
    tymczasowy.write_text(json.dumps({'wersja': WERSJA_PLIKU, 'wnioski': rekordy}, ensure_ascii=False, indent=2),
                          'utf-8')
    os.replace(tymczasowy, PLIK_REJESTRU)


def _z_rekordu(rekord: dict) -> Wniosek:
    for pole in _POLA_DAT:
        if rekord.get(pole):
            rekord[pole] = date.fromisoformat(rekord[pole])
    if rekord.get('status') == 'kwerenda':  # stary format: kwerenda była statusem
        rekord['status'], rekord['kwerenda'] = 'brak', True
    znane = Wniosek.__dataclass_fields__
    return Wniosek(**{k: v for k, v in rekord.items() if k in znane})


def _wczytaj() -> None:
    _wnioski.clear()
    if not PLIK_REJESTRU.exists():
        _dodaj_dane_testowe()
        _zapisz()
        return
    dane = json.loads(PLIK_REJESTRU.read_text('utf-8'))
    if isinstance(dane, list):  # wersja 1: tylko wnioski dodane przez urzędnika, testowe były w pamięci
        _dodaj_dane_testowe()
        _wnioski.extend(_z_rekordu(r) for r in dane)
        _zapisz()
        return
    _wnioski.extend(_z_rekordu(r) for r in dane.get('wnioski', []))


def _dodaj_dane_testowe() -> None:
    """10 wniosków testowych z terminami ustawionymi względem dziś (w dniach roboczych)."""
    dzis = date.today()
    zajete_id = {w.id for w in _wnioski}
    # (termin za ile dni roboczych | None, kwerenda, status, inicjały, temat, wnioskodawca)
    surowe = [
        (-2, False, 'wydzialy', 'AK', 'Wydatki na promocję miasta w 2025 r.', 'Jan Kowalski'),
        (0, False, 'wydzialy', 'AK', 'Umowy na zimowe utrzymanie dróg', 'Fundacja Przejrzyste Miasto'),
        (0, False, 'przygotowana', 'MN', 'Liczba etatów w Urzędzie Miasta', 'Anna Nowak'),
        (1, False, 'brak', 'PW', 'Koszt organizacji Dni Bydgoszczy', 'Redakcja Gazety Lokalnej'),
        (3, False, 'wydzialy', 'MN', 'Wykaz dotacji dla NGO w 2025 r.', 'Stowarzyszenie Aktywni'),
        (None, True, 'wydzialy', 'AK', 'Decyzje środowiskowe 2015–2025', 'Piotr Zieliński'),
        (5, False, 'brak', 'PW', 'Wynagrodzenia w spółkach miejskich', 'Katarzyna Wiśniewska'),
        (8, False, 'brak', 'AK', 'Plan remontów szkół na 2027 r.', 'Rada Rodziców SP 12'),
        (10, False, 'brak', 'MN', 'Umowy z kancelariami prawnymi', 'Tomasz Lewandowski'),
        (None, False, 'wyslana', 'PW', 'Koszt remontu ul. Gdańskiej', 'Marek Wójcik'),
    ]
    for i, (za_ile, kwerenda, status, kto, temat, wnioskodawca) in enumerate(surowe, start=1):
        if za_ile is not None:
            # termin to dzień roboczy, więc wpływ 14 dni wcześniej daje dokładnie ten termin
            data_wplywu = dodaj_dni_robocze(dzis, za_ile) - timedelta(days=TERMIN_DNI)
        else:
            data_wplywu = dzis - timedelta(days=30 if kwerenda else 20)
        wniosek = Wniosek(
            id=i if i not in zajete_id else max(zajete_id | {10}) + i,
            nr=f'UDIP.{i}.{dzis.year}', temat=temat, wnioskodawca=wnioskodawca, data_wplywu=data_wplywu,
            kto=kto, status=status, kwerenda=kwerenda, testowy=True,
            data_odpowiedzi=dzis - timedelta(days=8) if status == 'wyslana' else None,
        )
        _odnotuj(wniosek, 'Zarejestrowano wniosek', datetime.combine(data_wplywu, datetime.min.time()))
        if status != 'brak':
            _odnotuj(wniosek, f'Status: {STATUSY[status]}')
        _wnioski.append(wniosek)


_wczytaj()

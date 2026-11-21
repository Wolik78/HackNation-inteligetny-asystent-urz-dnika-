"""Rejestr wniosków UDIP.

Tymczasowo: 10 wniosków testowych w pamięci + wnioski dodane przez urzędnika zapisywane do pliku JSON
w katalogu danych. Później podmienimy to na bazę danych, nie zmieniając funkcji publicznych modułu.
"""

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from .konfiguracja import KATALOG_DANYCH, TERMIN_DNI, TERMIN_KWERENDA

PLIK_REJESTRU = KATALOG_DANYCH / 'rejestr_wnioskow.json'

STATUSY = {
    'brak': 'Brak działań',
    'wydzialy': 'Zapytania do wydziałów',
    'kwerenda': 'Kwerenda',
    'przygotowana': 'Odpowiedź przygotowana',
    'wyslana': 'Odpowiedź wysłana',
}


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
    kontakt: str = ''
    data_odpowiedzi: date | None = None
    testowy: bool = False

    @property
    def termin(self) -> date:
        # TODO: przesuwanie terminu z soboty/święta na następny dzień roboczy (art. 57 § 4 KPA)
        return self.data_wplywu + timedelta(days=TERMIN_KWERENDA if self.kwerenda else TERMIN_DNI)

    @property
    def dni_do_terminu(self) -> int:
        return (self.termin - date.today()).days

    @property
    def pilnosc(self) -> str:
        """Jedno z: wyslano, po_terminie, dzis, jutro, blisko, ok."""
        if self.status == 'wyslana':
            return 'wyslano'
        dni = self.dni_do_terminu
        if dni < 0:
            return 'po_terminie'
        return {0: 'dzis', 1: 'jutro'}.get(dni, 'blisko' if dni <= 3 else 'ok')

    @property
    def pozostalo(self) -> str:
        dni = self.dni_do_terminu
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


def wszystkie() -> list[Wniosek]:
    """Wnioski od najstarszych do najnowszych."""
    return sorted(_wnioski, key=lambda w: (w.data_wplywu, w.id))


def pobierz(id: int) -> Wniosek | None:
    return next((w for w in _wnioski if w.id == id), None)


def nastepny_numer(rok: int | None = None) -> str:
    rok = rok or date.today().year
    return f'UDIP.{sum(w.data_wplywu.year == rok for w in _wnioski) + 1}.{rok}'


def dodaj(*, nr: str, temat: str, wnioskodawca: str, data_wplywu: date, kto: str,
          kwerenda: bool = False, kontakt: str = '') -> Wniosek:
    if any(w.nr == nr for w in _wnioski):
        raise ValueError(f'Wniosek o numerze {nr} już istnieje.')
    wniosek = Wniosek(
        id=max((w.id for w in _wnioski), default=0) + 1,
        nr=nr, temat=temat, wnioskodawca=wnioskodawca, data_wplywu=data_wplywu, kto=kto,
        status='kwerenda' if kwerenda else 'brak', kwerenda=kwerenda, kontakt=kontakt,
    )
    _wnioski.append(wniosek)
    _zapisz()
    return wniosek


def _zapisz() -> None:
    dane = []
    for w in _wnioski:
        if w.testowy:
            continue
        rekord = asdict(w)
        rekord['data_wplywu'] = w.data_wplywu.isoformat()
        rekord['data_odpowiedzi'] = w.data_odpowiedzi.isoformat() if w.data_odpowiedzi else None
        dane.append(rekord)
    PLIK_REJESTRU.parent.mkdir(parents=True, exist_ok=True)
    PLIK_REJESTRU.write_text(json.dumps(dane, ensure_ascii=False, indent=2), 'utf-8')


def _wczytaj_zapisane() -> None:
    if not PLIK_REJESTRU.exists():
        return
    for rekord in json.loads(PLIK_REJESTRU.read_text('utf-8')):
        rekord['data_wplywu'] = date.fromisoformat(rekord['data_wplywu'])
        if rekord.get('data_odpowiedzi'):
            rekord['data_odpowiedzi'] = date.fromisoformat(rekord['data_odpowiedzi'])
        _wnioski.append(Wniosek(**rekord))


def _wczytaj_dane_testowe() -> None:
    dzis = date.today()
    # (dni temu wpłynął, kwerenda?, status, inicjały, temat, wnioskodawca, dni temu wysłano)
    surowe = [
        (16, False, 'wydzialy', 'AK', 'Wydatki na promocję miasta w 2025 r.', 'Jan Kowalski', None),
        (14, False, 'wydzialy', 'AK', 'Umowy na zimowe utrzymanie dróg', 'Fundacja Przejrzyste Miasto', None),
        (14, False, 'przygotowana', 'MN', 'Liczba etatów w Urzędzie Miasta', 'Anna Nowak', None),
        (13, False, 'brak', 'PW', 'Koszt organizacji Dni Bydgoszczy', 'Redakcja Gazety Lokalnej', None),
        (11, False, 'wydzialy', 'MN', 'Wykaz dotacji dla NGO w 2025 r.', 'Stowarzyszenie Aktywni', None),
        (30, True, 'kwerenda', 'AK', 'Decyzje środowiskowe 2015–2025', 'Piotr Zieliński', None),
        (9, False, 'brak', 'PW', 'Wynagrodzenia w spółkach miejskich', 'Katarzyna Wiśniewska', None),
        (6, False, 'brak', 'AK', 'Plan remontów szkół na 2027 r.', 'Rada Rodziców SP 12', None),
        (3, False, 'brak', 'MN', 'Umowy z kancelariami prawnymi', 'Tomasz Lewandowski', None),
        (20, False, 'wyslana', 'PW', 'Koszt remontu ul. Gdańskiej', 'Marek Wójcik', 8),
    ]
    for i, (temu, kwerenda, status, kto, temat, wnioskodawca, wyslano) in enumerate(surowe, start=1):
        _wnioski.append(Wniosek(
            id=i, nr=f'UDIP.{i}.{dzis.year}', temat=temat, wnioskodawca=wnioskodawca,
            data_wplywu=dzis - timedelta(days=temu), kto=kto, status=status, kwerenda=kwerenda,
            data_odpowiedzi=dzis - timedelta(days=wyslano) if wyslano is not None else None,
            testowy=True,
        ))


_wczytaj_dane_testowe()
_wczytaj_zapisane()

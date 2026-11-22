"""Eksport rejestru wniosków: Excel (.xlsx) do sprawozdań i terminy do kalendarza Outlooka (.ics).

Plik kalendarza nie zawiera danych osobowych (kalendarze bywają synchronizowane z chmurą): tylko numer sprawy,
skrócony temat, status i termin. Excel to wewnętrzny rejestr urzędu – zawiera też wnioskodawcę.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from . import klasyfikacja
from .rejestr import Wniosek

KOLUMNY = (('Nr', 16), ('Temat', 50), ('Wnioskodawca', 28), ('Data wpływu', 13), ('Termin', 13), ('Kwerenda', 10),
           ('Status', 30), ('Rodzaj sprawy', 30), ('Prowadzi', 10), ('Data odpowiedzi', 15), ('W terminie', 11),
           ('Wydziały', 24))
FORMAT_DATY = 'DD.MM.YYYY'


def _skroty_wydzialow(wydzialy: Iterable[str]) -> str:
    """„Wydział Zieleni i Gospodarki Komunalnej (WGK)” → „WGK”."""
    return ', '.join(m[1] if (m := re.search(r'\(([^()]+)\)\s*$', w)) else w for w in wydzialy)


def _w_terminie(w: Wniosek) -> str:
    if w.data_odpowiedzi is None:
        return ''
    return 'tak' if w.data_odpowiedzi <= w.termin else 'nie'


def do_excela(wnioski: Iterable[Wniosek], sciezka: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    skoroszyt = Workbook()
    arkusz = skoroszyt.active
    arkusz.title = 'Rejestr wniosków'
    arkusz.append([nazwa for nazwa, _ in KOLUMNY])
    for komorka in arkusz[1]:
        komorka.font = Font(bold=True, color='FFFFFF')
        komorka.fill = PatternFill('solid', fgColor='1F4E79')
        komorka.alignment = Alignment(vertical='center')
    for w in wnioski:
        arkusz.append([w.nr, w.temat, w.wnioskodawca, w.data_wplywu, w.termin, 'tak' if w.kwerenda else '',
                       w.status_opis, klasyfikacja.rodzaj(w.rodzaj).nazwa, w.kto, w.data_odpowiedzi, _w_terminie(w),
                       _skroty_wydzialow(w.sugerowane_wydzialy)])
    for kolumna, (_, szerokosc) in enumerate(KOLUMNY, start=1):
        litera = arkusz.cell(row=1, column=kolumna).column_letter
        arkusz.column_dimensions[litera].width = szerokosc
    for wiersz in arkusz.iter_rows(min_row=2):
        for komorka in wiersz:
            if isinstance(komorka.value, date):
                komorka.number_format = FORMAT_DATY
    arkusz.freeze_panes = 'A2'
    arkusz.auto_filter.ref = arkusz.dimensions
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    skoroszyt.save(sciezka)
    return sciezka


# --- iCalendar (RFC 5545) ------------------------------------------------------------------

def _tekst_ics(tekst: str) -> str:
    return (tekst.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
            .replace('\r\n', '\\n').replace('\n', '\\n'))


def _zawin(linia: str) -> list[str]:
    """Linie dłuższe niż 75 bajtów są dzielone (kontynuacja zaczyna się spacją), bez rozcinania znaków UTF-8."""
    czesci, obecna = [], ''
    for znak in linia:
        limit = 75 if not czesci else 74
        if len((obecna + znak).encode('utf-8')) > limit:
            czesci.append(obecna)
            obecna = ''
        obecna += znak
    czesci.append(obecna)
    return [czesci[0]] + [' ' + c for c in czesci[1:]]


def do_kalendarza(wnioski: Iterable[Wniosek], sciezka: Path, *, teraz: datetime | None = None) -> Path:
    """Terminy spraw w toku jako wydarzenia całodniowe z przypomnieniem dzień wcześniej."""
    znacznik = (teraz or datetime.now(UTC)).strftime('%Y%m%dT%H%M%SZ')
    linie = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Cyfrowy Ratusz//UM Bydgoszcz//PL', 'CALSCALE:GREGORIAN',
             'X-WR-CALNAME:Terminy wniosków UDIP']
    for w in wnioski:
        if w.status == 'wyslana':
            continue
        opis = f'Status: {w.status_opis}. Rodzaj: {klasyfikacja.rodzaj(w.rodzaj).nazwa}. Prowadzi: {w.kto}.'
        if w.kwerenda:
            opis += ' Termin przedłużony (kwerenda).'
        linie += [
            'BEGIN:VEVENT',
            f'UID:udip-{re.sub(r"[^0-9A-Za-z.-]", "-", w.nr)}@cyfrowy-ratusz',
            f'DTSTAMP:{znacznik}',
            f'DTSTART;VALUE=DATE:{w.termin:%Y%m%d}',
            f'DTEND;VALUE=DATE:{w.termin + timedelta(days=1):%Y%m%d}',
            f'SUMMARY:{_tekst_ics(f"Termin odpowiedzi {w.nr}: {w.temat}")}',
            f'DESCRIPTION:{_tekst_ics(opis)}',
            'TRANSP:TRANSPARENT',
            'BEGIN:VALARM', 'ACTION:DISPLAY', 'TRIGGER:-P1D',
            f'DESCRIPTION:{_tekst_ics(f"Jutro mija termin odpowiedzi na wniosek {w.nr}")}',
            'END:VALARM',
            'END:VEVENT',
        ]
    linie.append('END:VCALENDAR')
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    sciezka.write_bytes(('\r\n'.join(z for linia in linie for z in _zawin(linia)) + '\r\n').encode('utf-8'))
    return sciezka

"""Eksport rejestru: Excel do sprawozdań i terminy do kalendarza (.ics)."""

from datetime import UTC, date, datetime

import pytest

from asystent import rejestr
from asystent.eksport_rejestru import do_excela, do_kalendarza


@pytest.fixture
def wnioski(tmp_path, monkeypatch):
    monkeypatch.setattr(rejestr, 'PLIK_REJESTRU', tmp_path / 'rejestr.json')
    monkeypatch.setattr(rejestr, '_wnioski', [])
    rejestr._wczytaj()
    w = rejestr.dodaj(nr='UDIP.50.2026', temat='Wycinka drzew; park, Kochanowskiego', wnioskodawca='Jan Testowy',
                      data_wplywu=date(2026, 11, 5), kto='AK', rodzaj='przetworzona',
                      sugerowane_wydzialy=['Wydział Zieleni i Gospodarki Komunalnej (WGK)'])
    wyslany = rejestr.dodaj(nr='UDIP.51.2026', temat='Mandaty', wnioskodawca='Anna Nowak',
                            data_wplywu=date(2026, 11, 2), kto='MN')
    rejestr.zmien_status(wyslany, 'wyslana', data_odpowiedzi=date(2026, 11, 10))
    return [w, wyslany]


def test_excel(wnioski, tmp_path):
    from openpyxl import load_workbook
    arkusz = load_workbook(do_excela(wnioski, tmp_path / 'rejestr.xlsx')).active
    assert [c.value for c in arkusz[1]][:3] == ['Nr', 'Temat', 'Wnioskodawca']
    wiersz = {arkusz.cell(1, k).value: arkusz.cell(2, k) for k in range(1, arkusz.max_column + 1)}
    assert wiersz['Nr'].value == 'UDIP.50.2026'
    assert wiersz['Rodzaj sprawy'].value == 'Informacja przetworzona'
    assert wiersz['Wydziały'].value == 'WGK'
    assert wiersz['Termin'].value.date() == wnioski[0].termin and wiersz['Termin'].number_format == 'DD.MM.YYYY'
    assert arkusz.cell(3, 11).value == 'tak'          # odpowiedź wysłana w terminie
    assert arkusz.freeze_panes == 'A2'


def test_kalendarz_ics(wnioski, tmp_path):
    sciezka = do_kalendarza(wnioski, tmp_path / 'terminy.ics', teraz=datetime(2026, 11, 22, 10, tzinfo=UTC))
    surowe = sciezka.read_bytes()
    tekst = surowe.decode('utf-8')
    assert tekst.startswith('BEGIN:VCALENDAR\r\n') and tekst.endswith('END:VCALENDAR\r\n')
    assert tekst.count('BEGIN:VEVENT') == 1                       # wysłana sprawa nie trafia do kalendarza
    assert f'DTSTART;VALUE=DATE:{wnioski[0].termin:%Y%m%d}' in tekst
    assert r'Wycinka drzew\; park\, Kochanowskiego' in tekst.replace('\r\n ', '')   # znaki specjalne
    assert 'Jan Testowy' not in tekst                              # bez danych osobowych
    assert 'TRIGGER:-P1D' in tekst
    assert all(len(linia) <= 75 for linia in surowe.split(b'\r\n'))  # zawijanie linii wg RFC 5545

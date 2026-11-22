"""Dziennik działań AI (tylko metadane) i statystyki pulpitu „Na dziś”."""

from datetime import date, timedelta

import pytest

from asystent import dziennik, rejestr
from asystent.statystyki import policz


def test_dziennik_zapis_i_odczyt(tmp_path):
    plik = tmp_path / 'dziennik.jsonl'
    dziennik.zapisz('Analiza wniosku', sprawa='UDIP.1.2026', szczegoly='rodzaj: zwykła', plik=plik)
    dziennik.zapisz('Eksport pisma', kto=dziennik.URZEDNIK, sprawa='UDIP.2.2026', plik=plik)
    with plik.open('a', encoding='utf-8') as f:
        f.write('to nie jest json\n')                                  # uszkodzona linia nie psuje dziennika

    wszystkie = dziennik.wpisy(plik=plik)
    assert [w.czynnosc for w in wszystkie] == ['Eksport pisma', 'Analiza wniosku']   # od najnowszego
    assert wszystkie[1].kto == dziennik.AI
    assert [w.sprawa for w in dziennik.wpisy(sprawa='UDIP.1.2026', plik=plik)] == ['UDIP.1.2026']
    assert dziennik.wpisy(plik=tmp_path / 'brak.jsonl') == []


@pytest.fixture
def czysty_rejestr(tmp_path, monkeypatch):
    monkeypatch.setattr(rejestr, 'PLIK_REJESTRU', tmp_path / 'rejestr.json')
    monkeypatch.setattr(rejestr, '_wnioski', [])
    rejestr._wczytaj()
    for w in list(rejestr.wszystkie()):
        rejestr.usun(w)


def test_statystyki(czysty_rejestr):
    dzis = date.today()
    po_terminie = rejestr.dodaj(nr='UDIP.1.2026', temat='A', wnioskodawca='X', data_wplywu=dzis - timedelta(days=40),
                                kto='AK')
    w_toku = rejestr.dodaj(nr='UDIP.2.2026', temat='B', wnioskodawca='X', data_wplywu=dzis, kto='AK',
                           rodzaj='przetworzona')
    rejestr.zmien_status(w_toku, 'wydzialy')
    wyslany = rejestr.dodaj(nr='UDIP.3.2026', temat='C', wnioskodawca='X', data_wplywu=dzis - timedelta(days=30),
                            kto='MN')
    rejestr.zmien_status(wyslany, 'wyslana', data_odpowiedzi=dzis - timedelta(days=20))

    s = policz(rejestr.wszystkie())
    assert (s.wszystkie, s.w_toku, s.wyslane) == (3, 2, 1)
    assert s.po_terminie == [po_terminie]
    assert s.czekamy_na_wydzialy == [w_toku]
    assert s.w_terminie_procent == 100 and s.sredni_czas_dni == 10.0
    assert len(s.miesiecznie) == 12 and s.miesiecznie[-1][1] >= 1
    assert dict(s.wg_rodzaju) == {'Informacja publiczna': 2, 'Informacja przetworzona': 1}

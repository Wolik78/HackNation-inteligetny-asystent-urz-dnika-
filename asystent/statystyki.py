"""Statystyki do pulpitu „Na dziś”: pilne sprawy, sprawy czekające na wydziały, terminowość, czas odpowiedzi."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from . import klasyfikacja
from .rejestr import Wniosek
from .terminy import NAZWY_MIESIECY


@dataclass
class Statystyki:
    wszystkie: int = 0
    w_toku: int = 0
    wyslane: int = 0
    po_terminie: list[Wniosek] = field(default_factory=list)
    na_dzis: list[Wniosek] = field(default_factory=list)
    na_jutro: list[Wniosek] = field(default_factory=list)
    czekamy_na_wydzialy: list[Wniosek] = field(default_factory=list)
    kwerendy: int = 0
    w_terminie_procent: int | None = None      # odpowiedzi wysłane w terminie / wszystkie wysłane
    sredni_czas_dni: float | None = None       # od wpływu do wysłania odpowiedzi
    miesiecznie: list[tuple[str, int]] = field(default_factory=list)   # (miesiąc, liczba wpływów) – ostatnie 12
    wg_rodzaju: list[tuple[str, int]] = field(default_factory=list)


def _ostatnie_miesiace(dzis: date, ile: int = 12) -> list[tuple[int, int]]:
    miesiace, rok, miesiac = [], dzis.year, dzis.month
    for _ in range(ile):
        miesiace.append((rok, miesiac))
        rok, miesiac = (rok - 1, 12) if miesiac == 1 else (rok, miesiac - 1)
    return list(reversed(miesiace))


def policz(wnioski: list[Wniosek], dzis: date | None = None) -> Statystyki:
    dzis = dzis or date.today()
    s = Statystyki(wszystkie=len(wnioski))
    wyslane = [w for w in wnioski if w.status == 'wyslana']
    w_toku = [w for w in wnioski if w.status != 'wyslana']
    s.wyslane, s.w_toku = len(wyslane), len(w_toku)
    s.po_terminie = sorted((w for w in w_toku if w.pilnosc == 'po_terminie'), key=lambda w: w.termin)
    s.na_dzis = [w for w in w_toku if w.pilnosc == 'dzis']
    s.na_jutro = [w for w in w_toku if w.pilnosc == 'jutro']
    s.czekamy_na_wydzialy = sorted((w for w in w_toku if w.status == 'wydzialy'), key=lambda w: w.termin)
    s.kwerendy = sum(1 for w in w_toku if w.kwerenda)

    z_data = [w for w in wyslane if w.data_odpowiedzi]
    if z_data:
        s.w_terminie_procent = round(100 * sum(w.data_odpowiedzi <= w.termin for w in z_data) / len(z_data))
        s.sredni_czas_dni = round(sum((w.data_odpowiedzi - w.data_wplywu).days for w in z_data) / len(z_data), 1)

    wplywy = Counter((w.data_wplywu.year, w.data_wplywu.month) for w in wnioski)
    s.miesiecznie = [(f'{NAZWY_MIESIECY[m - 1][:3]} {r % 100:02d}', wplywy.get((r, m), 0))
                     for r, m in _ostatnie_miesiace(dzis)]
    rodzaje = Counter(klasyfikacja.rodzaj(w.rodzaj).nazwa for w in wnioski)
    s.wg_rodzaju = rodzaje.most_common()
    return s

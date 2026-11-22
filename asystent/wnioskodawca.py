"""Dane wnioskodawcy odczytane z treści wniosku – podpowiedź do pól „Wnioskodawca” i „Kontakt” (bez AI).

Korzysta z tych samych wzorców co anonimizacja. Nadawca jest w nagłówku pisma (imię i nazwisko albo nazwa
organizacji), a gdy go tam nie ma – w podpisie pod „Z poważaniem”. Kontakt: e-mail, a gdy go brak – adres.
Urzędnik zawsze widzi i może poprawić wpisane wartości.
"""

import re
from dataclasses import dataclass

from .anonimizacja import wykryj_wzorce

NAGLOWEK = 800   # znaków od początku – tu zwykle są dane nadawcy
_ORGANIZACJA = re.compile(
    r'^[ \t]*((?:Fundacja|Stowarzyszenie|Związek|Spółdzielnia|Kancelaria|Redakcja|Komitet|Klub|Towarzystwo|'
    r'Instytut|Ośrodek|Rada|Polskie|Polski|Ogólnopolsk\w*)\b[^\n,]{2,80})', re.MULTILINE)


@dataclass(frozen=True)
class DaneWnioskodawcy:
    wnioskodawca: str = ''
    kontakt: str = ''


def _jedna_linia(tekst: str) -> str:
    return ' '.join(tekst.split())


def _pierwsze(tekst: str, wykryte: dict[str, str], typ: str) -> str:
    """Najwcześniej występujący w tekście ciąg danego typu."""
    kandydaci = [c for c, t in wykryte.items() if t == typ]
    return min(kandydaci, key=tekst.find, default='')


def dane_wnioskodawcy(tekst: str) -> DaneWnioskodawcy:
    naglowek = tekst[:NAGLOWEK]
    w_naglowku = wykryj_wzorce(naglowek)

    if organizacja := _ORGANIZACJA.search(naglowek):
        wnioskodawca = organizacja[1].strip()
    else:
        # imię i nazwisko (dwa słowa) z nagłówka; inaczej ostatnia osoba w piśmie – podpis
        osoby = [c for c, t in w_naglowku.items() if t == 'Imię i nazwisko' and len(c.split()) >= 2]
        wnioskodawca = min(osoby, key=naglowek.find, default='')
        if not wnioskodawca:
            w_calym = [c for c, t in wykryj_wzorce(tekst).items() if t == 'Imię i nazwisko' and len(c.split()) >= 2]
            wnioskodawca = max(w_calym, key=tekst.rfind, default='')

    email = _pierwsze(tekst, wykryj_wzorce(tekst), 'E-mail')
    if email:
        kontakt = email
    else:
        czesci = (_pierwsze(naglowek, w_naglowku, typ) for typ in ('Adres', 'Kod pocztowy i miejscowość'))
        kontakt = ', '.join(c for c in czesci if c)
    return DaneWnioskodawcy(_jedna_linia(wnioskodawca), _jedna_linia(kontakt))

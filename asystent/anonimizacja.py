"""Anonimizacja: wykrywanie danych osobowych wzorcami, podział tekstu na fragmenty i maskowanie.

Wzorce (PESEL, e-mail, telefon, konto) działają natychmiast i deterministycznie – uzupełniają
Bielika, który wskazuje imiona, nazwiska i adresy. Ostateczną decyzję podejmuje urzędnik.
"""

import re
from collections.abc import Iterable

MASKA = '██████'

WZORCE = {
    'PESEL': r'(?<!\d)\d{11}(?!\d)',
    'E-mail': r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+',
    # komórkowy 601 234 567 albo stacjonarny z numerem kierunkowym 52 123 45 67 / (52) 123-45-67
    'Telefon': r'(?<![\d\w])(?:\+48[ -]?)?(?:\d{3}[ -]?\d{3}[ -]?\d{3}|\(?\d{2}\)?[ -]?\d{3}[ -]?\d{2}[ -]?\d{2})'
               r'(?![\d\w])',
    'Nr konta': r'(?<![\d\w])(?:PL ?)?\d{2}(?: ?\d{4}){6}(?![\d\w])',
    'Dowód osobisty': r'\b[A-Z]{3} ?\d{6}\b',
}


def wykryj_wzorce(tekst: str) -> dict[str, str]:
    """Zwraca {znaleziony ciąg: typ danych}."""
    wynik: dict[str, str] = {}
    for typ, wzorzec in WZORCE.items():
        for dopasowanie in re.finditer(wzorzec, tekst):
            wynik.setdefault(dopasowanie.group().strip(), typ)
    return wynik


def podziel_na_fragmenty(tekst: str, do_ukrycia: Iterable[str]) -> list[tuple[str, bool]]:
    """Dzieli tekst na kolejne fragmenty: (tekst, czy_dane_do_ukrycia). Złączone dają oryginał."""
    ciagi = sorted({c for c in do_ukrycia if c}, key=len, reverse=True)  # dłuższe najpierw
    if not ciagi:
        return [(tekst, False)] if tekst else []
    wzorzec = re.compile('|'.join(re.escape(c) for c in ciagi))
    fragmenty, pozycja = [], 0
    for dopasowanie in wzorzec.finditer(tekst):
        if dopasowanie.start() > pozycja:
            fragmenty.append((tekst[pozycja:dopasowanie.start()], False))
        fragmenty.append((dopasowanie.group(), True))
        pozycja = dopasowanie.end()
    if pozycja < len(tekst):
        fragmenty.append((tekst[pozycja:], False))
    return fragmenty


def zamaskuj(tekst: str, ukryte: Iterable[str], maska: str = MASKA) -> str:
    """Zastępuje wszystkie wystąpienia zatwierdzonych ciągów maską."""
    return ''.join(maska if ukryj else fragment for fragment, ukryj in podziel_na_fragmenty(tekst, ukryte))

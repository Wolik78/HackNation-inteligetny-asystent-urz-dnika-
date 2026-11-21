"""Anonimizacja: wykrywanie danych osobowych bez AI, podział tekstu na fragmenty i maskowanie.

Wzorce działają natychmiast, deterministycznie i bez LM Studio (test jury J3):
- PESEL, e-mail, telefon, numer konta, dowód osobisty, NIP, REGON, data urodzenia,
- imię i nazwisko (słownik popularnych polskich imion w odmianie + nazwisko po imieniu; „Pan/Pani Nazwisko”),
- adres (ul./al./os./pl. z numerem) oraz kod pocztowy z miejscowością.
Bielik uzupełnia je o dane, których wzorce nie złapią. Wszystko to są propozycje – decyzję podejmuje urzędnik
(np. nazwisk osób pełniących funkcje publiczne się nie ukrywa).
"""

import re
from collections.abc import Iterable

MASKA = '██████'

_DUZA = 'A-ZĄĆĘŁŃÓŚŹŻ'
_MALA = 'a-ząćęłńóśźż'

WZORCE = {
    'PESEL': r'(?<!\d)\d{11}(?!\d)',
    'E-mail': r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+',
    # komórkowy 601 234 567 albo stacjonarny z numerem kierunkowym 52 123 45 67 / (52) 123-45-67
    'Telefon': r'(?<![\d\w])(?:\+48[ -]?)?(?:\d{3}[ -]?\d{3}[ -]?\d{3}|\(?\d{2}\)?[ -]?\d{3}[ -]?\d{2}[ -]?\d{2})'
               r'(?![\d\w])',
    'Nr konta': r'(?<![\d\w])(?:PL ?)?\d{2}(?: ?\d{4}){6}(?![\d\w])',
    'Dowód osobisty': r'\b[A-Z]{3} ?\d{6}\b',
    'NIP': r'\bNIP:?\s*(?:PL)?\d{3}-?\d{3}-?\d{2}-?\d{2}\b',
    'REGON': r'\bREGON:?\s*\d{9}(?:\d{5})?\b',
    'Data urodzenia': r'\b(?:ur\.|urodzon[yaei]\w*|data urodzenia:?)\s*(?:dnia\s*)?'
                      r'\d{1,2}(?:[.\-/]\d{1,2}[.\-/]|\s+[' + _MALA + r']+\s+)\d{4}(?:\s*r\.)?',
    'Adres': r'\b(?:ul\.|ulica|ulicy|al\.|aleja|alei|os\.|osiedle|pl\.|plac)\s*'
             r'[' + _DUZA + r'0-9][\w' + _MALA + r'.\-]*(?:\s+[' + _DUZA + r'][\w' + _MALA + r'.\-]*){0,3}'
             r'\s+\d+[a-zA-Z]?(?:\s*/\s*\d+[a-zA-Z]?)?(?:\s+m\.\s*\d+)?',
    'Kod pocztowy i miejscowość': r'(?<![\d-])\d{2}-\d{3}\s+[' + _DUZA + r'][' + _MALA + r']+'
                                  r'(?:[ -][' + _DUZA + r'][' + _MALA + r']+)?',
}

# Najpopularniejsze polskie imiona (mianownik) – podstawa wykrywania „Imię Nazwisko” bez AI.
IMIONA = '''
Adam Adrian Agata Agnieszka Aleksander Aleksandra Alicja Amelia Andrzej Aneta Anna Antoni Antonina Arkadiusz Artur
Barbara Bartłomiej Bartosz Beata Bogdan Bogusław Bożena Cezary Czesław Damian Daniel Danuta Dariusz Dawid Dominik
Dominika Dorota Edward Edyta Elżbieta Emilia Ewa Ewelina Filip Franciszek Gabriela Grażyna Grzegorz Halina Hanna
Helena Henryk Hubert Igor Ilona Irena Iwona Izabela Jacek Jadwiga Jakub Jan Janina Janusz Jarosław Jerzy Joanna
Jolanta Józef Julia Julian Justyna Kacper Kamil Kamila Karol Karolina Katarzyna Kazimierz Kinga Klaudia Konrad
Krystyna Krzysztof Laura Lena Leszek Lucyna Ludwik Łucja Łukasz Maciej Magdalena Maja Małgorzata Marcin Marek Maria
Marian Mariusz Marta Marzena Mateusz Michał Mikołaj Milena Mirosław Monika Natalia Nikola Norbert Oliwia Oliwer Oskar
Patrycja Patryk Paula Paulina Paweł Piotr Przemysław Radosław Rafał Renata Robert Roman Ryszard Sebastian Stanisław
Stefan Sylwia Szymon Tadeusz Teresa Tomasz Urszula Wanda Weronika Wiesław Wiktor Wiktoria Witold Władysław
Włodzimierz Wojciech Zbigniew Zdzisław Zenon Zofia Zuzanna Zygmunt
'''.split()

# Słowa po „Pan/Pani”, które są funkcją, a nie nazwiskiem.
_FUNKCJE = ('Prezydent', 'Dyrektor', 'Burmistrz', 'Skarbnik', 'Sekretarz', 'Naczelnik', 'Radn', 'Kierownik',
            'Minister', 'Wojewod', 'Marszał', 'Starost', 'Wójt', 'Przewodnicząc', 'Komendant', 'Prezes', 'Poseł',
            'Senator', 'Rzecznik', 'Inspektor', 'Doktor', 'Profesor', 'Mecenas')


def _odmiany(imie: str) -> str:
    """Wyrażenie dla imienia w odmianie: Anna/Anny/Annie/Annę, Marek/Marka/Markowi, Paweł/Pawła."""
    if imie.endswith('a'):
        return re.escape(imie[:-1]) + f'[{_MALA}]{{1,3}}'
    if imie.endswith(('ek', 'eł')):  # e ruchome: Marek – Marka, Paweł – Pawła
        return f'(?:{re.escape(imie)}|{re.escape(imie[:-2] + imie[-1])}[{_MALA}]{{1,3}})'
    return re.escape(imie) + f'[{_MALA}]{{0,3}}'


_NAZWISKO = f'[{_DUZA}][{_MALA}]+(?:-[{_DUZA}][{_MALA}]+)?'
_IMIE_NAZWISKO = re.compile(r'\b(?:' + '|'.join(_odmiany(i) for i in IMIONA) + r')\s+' + _NAZWISKO + r'\b')
_PAN_NAZWISKO = re.compile(r'\b(?:Pan|Pani|Pana|Panu|Panem|Panią)\s+(' + _NAZWISKO + r')\b')


def _osoby(tekst: str) -> list[str]:
    znalezione = [m.group() for m in _IMIE_NAZWISKO.finditer(tekst)]
    for m in _PAN_NAZWISKO.finditer(tekst):
        nazwisko = m.group(1)
        if not nazwisko.startswith(_FUNKCJE) and not any(nazwisko in z for z in znalezione):
            znalezione.append(nazwisko)
    return znalezione


def wykryj_wzorce(tekst: str) -> dict[str, str]:
    """Zwraca {znaleziony ciąg: typ danych}."""
    wynik: dict[str, str] = {}
    for typ, wzorzec in WZORCE.items():
        for dopasowanie in re.finditer(wzorzec, tekst):
            wynik.setdefault(dopasowanie.group().strip(), typ)
    for osoba in _osoby(tekst):
        if not any(osoba in ciag for ciag in wynik):  # „Jana Pawła” w adresie „ul. Jana Pawła II 12” to nie osoba
            wynik.setdefault(osoba, 'Imię i nazwisko')
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

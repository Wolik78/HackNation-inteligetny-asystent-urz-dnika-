"""Walidacja wgrywanych plików: typ, rozmiar, zawartość i bezpieczna nazwa."""

import io
import os
import re
import zipfile

from ..konfiguracja import DOZWOLONE_ROZSZERZENIA, MAKS_ROZMIAR_PLIKU


class BladPliku(Exception):
    """Błąd pliku z komunikatem, który można pokazać urzędnikowi."""


# Pierwsze bajty plików – nie ufamy samemu rozszerzeniu.
SYGNATURY = {
    '.pdf': b'%PDF-',
    '.docx': b'PK\x03\x04',
    '.doc': b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1',
}

# Ochrona przed „zip bombą” – DOCX to archiwum ZIP.
MAKS_ROZMIAR_ROZPAKOWANEGO_DOCX = 200 * 1024 * 1024


def bezpieczna_nazwa(nazwa: str, maks_dlugosc: int = 100) -> str:
    """Zwraca nazwę pliku bez ścieżek i znaków specjalnych (zostawia polskie litery)."""
    nazwa = nazwa.replace('\\', '/').rsplit('/', 1)[-1]
    rdzen, rozszerzenie = os.path.splitext(nazwa)
    rdzen = re.sub(r'[^\w\-.]+', '_', rdzen).strip('._') or 'plik'
    rozszerzenie = re.sub(r'[^\w.]', '', rozszerzenie.lower())
    return rdzen[:maks_dlugosc] + rozszerzenie


def sprawdz_plik(nazwa: str, dane: bytes, *,
                 dozwolone: tuple[str, ...] = DOZWOLONE_ROZSZERZENIA,
                 maks_rozmiar: int = MAKS_ROZMIAR_PLIKU) -> str:
    """Sprawdza plik i zwraca jego rozszerzenie. Rzuca BladPliku, jeśli pliku nie można przyjąć."""
    rozszerzenie = os.path.splitext(nazwa)[1].lower()
    if rozszerzenie not in dozwolone:
        dozwolone_tekst = ', '.join(r.lstrip('.').upper() for r in dozwolone)
        raise BladPliku(f'Nieobsługiwany typ pliku „{rozszerzenie or "bez rozszerzenia"}”. '
                        f'Dozwolone: {dozwolone_tekst}.')
    if not dane:
        raise BladPliku('Plik jest pusty.')
    if len(dane) > maks_rozmiar:
        raise BladPliku(f'Plik jest za duży ({len(dane) / 1024 / 1024:.1f} MB). '
                        f'Limit to {maks_rozmiar // 1024 // 1024} MB.')

    sygnatura = SYGNATURY.get(rozszerzenie)
    if sygnatura and not dane.startswith(sygnatura):
        raise BladPliku(f'Zawartość pliku nie pasuje do formatu {rozszerzenie.upper()}. '
                        'Plik może być uszkodzony albo mieć zmienione rozszerzenie.')
    if rozszerzenie == '.docx':
        _sprawdz_docx(dane)
    return rozszerzenie


def _sprawdz_docx(dane: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(dane)) as archiwum:
            pliki = archiwum.infolist()
            if 'word/document.xml' not in {p.filename for p in pliki}:
                raise BladPliku('To nie jest poprawny dokument Word (.docx).')
            if sum(p.file_size for p in pliki) > MAKS_ROZMIAR_ROZPAKOWANEGO_DOCX:
                raise BladPliku('Dokument Word po rozpakowaniu jest podejrzanie duży – odrzucono.')
    except zipfile.BadZipFile as blad:
        raise BladPliku('Dokument Word (.docx) jest uszkodzony.') from blad

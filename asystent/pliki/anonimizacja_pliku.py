"""Anonimizacja pliku w jego własnym formacie (test jury J3).

- PDF z tekstem – zaczernienie (redakcja PyMuPDF): tekst pod czarnym prostokątem jest usuwany z pliku,
  nie tylko zakryty; skan PDF – prostokąty w miejscach słów wskazanych przez OCR, piksele obrazu zamalowane,
- zdjęcie JPG/PNG – czarne prostokąty na słowach z OCR, zapis jako PNG (bez metadanych EXIF),
- Word (DOCX) – maska ██████ w akapitach, tabelach, nagłówkach i stopkach; metadane autora wyczyszczone,
- TXT – maska; stary Word (DOC) – zanonimizowany tekst zapisany jako DOCX.
Na koniec plik wynikowy jest odczytywany ponownie i sprawdzane jest, czy żadna z ukrytych danych w nim nie została.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ..anonimizacja import MASKA, zamaskuj
from . import ocr
from .eksport import eksportuj
from .ekstrakcja import wyciagnij_tekst

CZARNY = (0, 0, 0)
MARGINES = 2  # px / pt wokół zaczernianego słowa


@dataclass
class WynikAnonimizacji:
    sciezka: Path
    zakryte: int                                   # ile miejsc zaczerniono / zamaskowano
    nieznalezione: list[str] = field(default_factory=list)   # dane, których nie udało się zlokalizować w pliku
    pozostale: list[str] = field(default_factory=list)       # dane, które kontrola znalazła w pliku wynikowym
    uwagi: list[str] = field(default_factory=list)

    @property
    def bezpieczny(self) -> bool:
        return not self.pozostale and not self.nieznalezione


def _norm(tekst: str) -> str:
    return ' '.join(tekst.split())


def nazwa_wyniku(zrodlo: Path, rozszerzenie: str | None = None) -> str:
    return f'{zrodlo.stem}_zanonimizowany{rozszerzenie or zrodlo.suffix.lower()}'


def zanonimizuj_plik(zrodlo: Path, ukryte: Iterable[str], katalog: Path) -> WynikAnonimizacji:
    """Tworzy zanonimizowaną kopię pliku w `katalog`. Oryginał zostaje bez zmian."""
    ciagi = sorted({_norm(c) for c in ukryte if c and c.strip()}, key=len, reverse=True)
    katalog.mkdir(parents=True, exist_ok=True)
    rozszerzenie = zrodlo.suffix.lower()
    if rozszerzenie == '.pdf':
        wynik = _pdf(zrodlo, ciagi, katalog / nazwa_wyniku(zrodlo))
    elif rozszerzenie in ('.jpg', '.jpeg', '.png'):
        wynik = _obraz(zrodlo, ciagi, katalog / nazwa_wyniku(zrodlo, '.png'))
    elif rozszerzenie == '.docx':
        wynik = _docx(zrodlo, ciagi, katalog / nazwa_wyniku(zrodlo))
    else:  # .txt, .doc – zanonimizowany tekst
        tekst = wyciagnij_tekst(zrodlo).tekst
        zakryte = sum(len(re.findall(re.escape(c), _norm(tekst))) for c in ciagi)
        cel = katalog / nazwa_wyniku(zrodlo, '.txt' if rozszerzenie == '.txt' else '.docx')
        eksportuj(zamaskuj(tekst, ciagi), cel)
        wynik = WynikAnonimizacji(cel, zakryte)
        if rozszerzenie == '.doc':
            wynik.uwagi.append('Stary format Word (.doc) – zapisano zanonimizowany tekst jako .docx (bez formatowania).')
    wynik.pozostale = _kontrola(wynik.sciezka, ciagi)
    return wynik


def _kontrola(sciezka: Path, ciagi: list[str]) -> list[str]:
    """Które z ukrytych danych nadal da się odczytać z pliku wynikowego (także OCR-em)."""
    tekst = _norm(wyciagnij_tekst(sciezka).tekst)
    return [c for c in ciagi if c in tekst]


# --- PDF ------------------------------------------------------------------------------------

def _pdf(zrodlo: Path, ciagi: list[str], cel: Path) -> WynikAnonimizacji:
    import pymupdf

    zakryte, znalezione = 0, set()
    with pymupdf.open(zrodlo) as pdf:
        for strona in pdf:
            if len(strona.get_text().strip()) >= ocr.MIN_ZNAKOW_STRONY:
                for ciag in ciagi:
                    for prostokat in strona.search_for(ciag):
                        strona.add_redact_annot(prostokat, fill=CZARNY)
                        zakryte += 1
                        znalezione.add(ciag)
            elif ocr.dostepny():  # skan – położenie słów z OCR
                pix = strona.get_pixmap(dpi=ocr.DPI)
                skala = strona.rect.width / pix.width
                for ciag, (x0, y0, x1, y1) in _prostokaty_ocr(pix.tobytes('png'), ciagi):
                    prostokat = pymupdf.Rect(x0 * skala, y0 * skala, x1 * skala, y1 * skala)
                    strona.add_redact_annot(prostokat + (-MARGINES, -MARGINES, MARGINES, MARGINES), fill=CZARNY)
                    zakryte += 1
                    znalezione.add(ciag)
            strona.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)  # usuwa tekst, zamalowuje piksele
        pdf.set_metadata({})  # autor, program, daty – też mogą zawierać dane osobowe
        pdf.save(cel, garbage=4, deflate=True)
    return WynikAnonimizacji(cel, zakryte, [c for c in ciagi if c not in znalezione])


# --- zdjęcia ----------------------------------------------------------------------------------

def _prostokaty_ocr(obraz: bytes, ciagi: list[str]) -> list[tuple[str, tuple[float, float, float, float]]]:
    """(ciąg, prostokąt w pikselach) dla każdego wystąpienia ciągu w liniach rozpoznanych przez OCR."""
    wynik = []
    for slowa in ocr.linie_ze_slowami(obraz):
        tekst, poczatki = '', []
        for slowo in slowa:
            poczatki.append(len(tekst) + (1 if tekst else 0))
            tekst += (' ' if tekst else '') + slowo[0]
        for ciag in ciagi:
            for m in re.finditer(re.escape(ciag), tekst):
                objete = [s for s, p in zip(slowa, poczatki) if p < m.end() and p + len(s[0]) > m.start()]
                if objete:
                    wynik.append((ciag, (min(s[1] for s in objete), min(s[2] for s in objete),
                                         max(s[3] for s in objete), max(s[4] for s in objete))))
    return wynik


def _obraz(zrodlo: Path, ciagi: list[str], cel: Path) -> WynikAnonimizacji:
    from PIL import Image, ImageDraw

    dane = zrodlo.read_bytes()
    obraz = Image.open(io.BytesIO(dane)).convert('RGB')  # nowy obraz – bez metadanych EXIF (np. GPS)
    pedzel = ImageDraw.Draw(obraz)
    prostokaty = _prostokaty_ocr(dane, ciagi) if ocr.dostepny() else []
    for _, (x0, y0, x1, y1) in prostokaty:
        pedzel.rectangle((x0 - MARGINES, y0 - MARGINES, x1 + MARGINES, y1 + MARGINES), fill=CZARNY)
    obraz.save(cel, 'PNG')
    znalezione = {c for c, _ in prostokaty}
    wynik = WynikAnonimizacji(cel, len(prostokaty), [c for c in ciagi if c not in znalezione])
    if not ocr.dostepny():
        wynik.uwagi.append('OCR niedostępny – nie da się zlokalizować danych na zdjęciu.')
    return wynik


# --- Word -------------------------------------------------------------------------------------

def _akapity(dokument):
    """Wszystkie akapity dokumentu: treść, tabele (także zagnieżdżone), nagłówki i stopki."""
    def z_kontenera(kontener):
        yield from kontener.paragraphs
        for tabela in getattr(kontener, 'tables', []):
            for wiersz in tabela.rows:
                for komorka in wiersz.cells:
                    yield from z_kontenera(komorka)
    yield from z_kontenera(dokument)
    for sekcja in dokument.sections:
        for czesc in (sekcja.header, sekcja.footer, sekcja.first_page_header, sekcja.first_page_footer):
            yield from z_kontenera(czesc)


def _docx(zrodlo: Path, ciagi: list[str], cel: Path) -> WynikAnonimizacji:
    import docx

    dokument = docx.Document(str(zrodlo))
    zakryte, znalezione = 0, set()
    for akapit in _akapity(dokument):
        tekst = akapit.text
        trafione = [c for c in ciagi if c in _norm(tekst) or c in tekst]
        if not trafione:
            continue
        nowy = zamaskuj(tekst, trafione)
        if nowy == tekst:  # różnica w odstępach – maskujemy na tekście ze zwykłymi spacjami
            nowy = zamaskuj(_norm(tekst), trafione)
        zakryte += nowy.count(MASKA) - tekst.count(MASKA)
        znalezione.update(trafione)
        # treść trafia do pierwszego fragmentu (zachowuje jego formatowanie), pozostałe są czyszczone
        if akapit.runs:
            akapit.runs[0].text = nowy
            for run in akapit.runs[1:]:
                run.text = ''
        else:
            akapit.text = nowy
    wlasciwosci = dokument.core_properties
    wlasciwosci.author = wlasciwosci.last_modified_by = wlasciwosci.comments = ''
    dokument.save(str(cel))
    wynik = WynikAnonimizacji(cel, zakryte, [c for c in ciagi if c not in znalezione])
    if any(c.content_type.startswith('image/') for c in dokument.part.related_parts.values()):
        wynik.uwagi.append('Dokument zawiera obrazy – nie są zaczerniane. Sprawdź je przed wysłaniem.')
    return wynik

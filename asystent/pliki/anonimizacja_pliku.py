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

from ..anonimizacja import MASKA, wykryj_wzorce, zamaskuj
from . import ocr
from .eksport import eksportuj
from .ekstrakcja import normalizuj_znaki, wyciagnij_tekst

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
    """Pojedyncze zwykłe spacje i ujednolicone łączniki – tak samo jak w odczytanym tekście."""
    return ' '.join(normalizuj_znaki(tekst).replace('\xad', '-').split())


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
            wynik.uwagi.append('Stary format Word (.doc) – zapisano zanonimizowany tekst jako .docx (bez '
                               'formatowania).')
    wynik.pozostale = _kontrola(wynik.sciezka, ciagi)
    return wynik


@dataclass
class WynikWsadowy:
    nazwa: str
    wynik: WynikAnonimizacji | None = None
    wykryte: int = 0
    blad: str = ''


def zanonimizuj_wsadowo(pliki: Iterable[Path], katalog: Path) -> list[WynikWsadowy]:
    """Tryb wsadowy (np. archiwum przed publikacją): w każdym pliku ukrywane są wszystkie dane wykryte wzorcami
    (bez AI i bez przeglądu – dlatego wynik zawsze trzeba przejrzeć). Błąd jednego pliku nie przerywa reszty."""
    wyniki = []
    for plik in pliki:
        try:
            wykryte = wykryj_wzorce(wyciagnij_tekst(plik).tekst)
            wyniki.append(WynikWsadowy(plik.name, zanonimizuj_plik(plik, wykryte, katalog), len(wykryte)))
        except Exception as blad:  # uszkodzony plik, brak OCR, błąd zapisu – opis trafia do tabeli wyników
            wyniki.append(WynikWsadowy(plik.name, blad=str(blad) or type(blad).__name__))
    return wyniki


def _kontrola(sciezka: Path, ciagi: list[str]) -> list[str]:
    """Które z ukrytych danych nadal da się odczytać z pliku wynikowego (także OCR-em)."""
    tekst = _norm(wyciagnij_tekst(sciezka).tekst)
    return [c for c in ciagi if c in tekst]


# --- PDF ------------------------------------------------------------------------------------

Prostokat = tuple[float, float, float, float]
Znak = tuple[str, Prostokat | None, int]   # (znak, jego prostokąt, numer linii)


def _sekwencja(linie: Iterable[Iterable[tuple[str, Prostokat]]]) -> list[Znak]:
    """Tekst strony jako ciąg znaków z położeniem. Odstępy i łączniki ujednolicone jak w odczytanym tekście,
    linie połączone spacją – więc „ul. Fordońska 120 m. 4” znajdzie się także wtedy, gdy przechodzi do nowej linii.

    Fragment to pojedynczy znak (PDF z tekstem) albo słowo ze spacją na końcu (OCR – znaki mają prostokąt słowa).
    """
    znaki: list[Znak] = []
    for nr, linia in enumerate(linie):
        for tekst, prostokat in linia:
            for z in normalizuj_znaki(tekst).replace('\xad', '-'):
                if not z.isspace():
                    znaki.append((z, prostokat, nr))
                elif znaki and znaki[-1][0] != ' ':
                    znaki.append((' ', None, nr))
        if znaki and znaki[-1][0] != ' ':
            znaki.append((' ', None, nr))
    return znaki


def _lokalizuj(znaki: list[Znak], ciagi: list[str]) -> list[tuple[str, Prostokat]]:
    """(ciąg, prostokąt) dla każdego wystąpienia – osobny prostokąt w każdej linii, przez którą ciąg przechodzi."""
    tekst = ''.join(z for z, _, _ in znaki)
    wynik = []
    for ciag in ciagi:
        for m in re.finditer(re.escape(ciag), tekst):
            linie: dict[int, list[Prostokat]] = {}
            for _, prostokat, nr in znaki[m.start():m.end()]:
                if prostokat is not None:
                    linie.setdefault(nr, []).append(prostokat)
            for p in linie.values():
                wynik.append((ciag, (min(r[0] for r in p), min(r[1] for r in p),
                                     max(r[2] for r in p), max(r[3] for r in p))))
    return wynik


def _linie_ocr(obraz: bytes) -> list[list[tuple[str, Prostokat]]]:
    return [[(s[0] + ' ', (s[1], s[2], s[3], s[4])) for s in slowa] for slowa in ocr.linie_ze_slowami(obraz)]


# --- PDF ------------------------------------------------------------------------------------

def _linie_pdf(strona) -> list[list[tuple[str, Prostokat]]]:
    """Znaki strony PDF z prostokątami (PyMuPDF „rawdict”), linia po linii."""
    linie = []
    for blok in strona.get_text('rawdict')['blocks']:
        for linia in blok.get('lines', []):
            linie.append([(z['c'], tuple(z['bbox'])) for span in linia['spans'] for z in span['chars']])
    return linie


def _pdf(zrodlo: Path, ciagi: list[str], cel: Path) -> WynikAnonimizacji:
    import pymupdf

    zakryte, znalezione = 0, set()
    with pymupdf.open(zrodlo) as pdf:
        for strona in pdf:
            if len(strona.get_text().strip()) >= ocr.MIN_ZNAKOW_STRONY:
                trafienia, skala, margines = _lokalizuj(_sekwencja(_linie_pdf(strona)), ciagi), 1.0, 0
            elif ocr.dostepny():  # skan – położenie słów z OCR
                pix = strona.get_pixmap(dpi=ocr.DPI)
                trafienia = _lokalizuj(_sekwencja(_linie_ocr(pix.tobytes('png'))), ciagi)
                skala, margines = strona.rect.width / pix.width, MARGINES
            else:
                trafienia = []
            for ciag, (x0, y0, x1, y1) in trafienia:
                prostokat = pymupdf.Rect(x0 * skala - margines, y0 * skala - margines,
                                         x1 * skala + margines, y1 * skala + margines)
                strona.add_redact_annot(prostokat, fill=CZARNY)
                zakryte += 1
                znalezione.add(ciag)
            strona.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)  # usuwa tekst, zamalowuje piksele
        pdf.set_metadata({})  # autor, program, daty – też mogą zawierać dane osobowe
        pdf.save(cel, garbage=4, deflate=True)
    return WynikAnonimizacji(cel, zakryte, [c for c in ciagi if c not in znalezione])


# --- zdjęcia ----------------------------------------------------------------------------------

def _obraz(zrodlo: Path, ciagi: list[str], cel: Path) -> WynikAnonimizacji:
    from PIL import Image, ImageDraw

    dane = zrodlo.read_bytes()
    obraz = Image.open(io.BytesIO(dane)).convert('RGB')  # nowy obraz – bez metadanych EXIF (np. GPS)
    pedzel = ImageDraw.Draw(obraz)
    prostokaty = _lokalizuj(_sekwencja(_linie_ocr(dane)), ciagi) if ocr.dostepny() else []
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

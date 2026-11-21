"""Wyciąganie tekstu z wgranych dokumentów (PDF, DOCX, DOC, TXT, zdjęcia JPG/PNG).

Skany, zdjęcia i Wordy z wklejonym zdjęciem kartki są odczytywane OCR-em (moduł `ocr`).
Wszystko działa lokalnie, bez wysyłania plików na zewnątrz.
"""

import logging
import re
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import ocr
from .walidacja import BladPliku

log = logging.getLogger(__name__)


@dataclass
class WynikEkstrakcji:
    tekst: str
    liczba_stron: int | None = None
    ostrzezenia: list[str] = field(default_factory=list)


def wyciagnij_tekst(sciezka: Path) -> WynikEkstrakcji:
    """Zwraca tekst dokumentu. Rzuca BladPliku, jeśli dokumentu nie da się odczytać."""
    obsluga = {
        '.pdf': _z_pdf,
        '.docx': _z_docx,
        '.doc': _z_doc,
        '.txt': _z_txt,
        '.jpg': _z_obrazu,
        '.jpeg': _z_obrazu,
        '.png': _z_obrazu,
    }.get(sciezka.suffix.lower())
    if obsluga is None:
        raise BladPliku(f'Nie umiem odczytać plików {sciezka.suffix}.')

    try:
        wynik = obsluga(sciezka)
    except BladPliku:
        raise
    except Exception as blad:  # biblioteki parsujące rzucają różne wyjątki przy uszkodzonych plikach
        log.exception('Błąd odczytu pliku %s', sciezka)
        raise BladPliku('Nie udało się odczytać pliku – może być uszkodzony.') from blad

    wynik.tekst = _normalizuj(wynik.tekst)
    if not wynik.tekst and not wynik.ostrzezenia:
        wynik.ostrzezenia.append('W pliku nie znaleziono żadnego tekstu.')
    return wynik


def _normalizuj(tekst: str) -> str:
    tekst = unicodedata.normalize('NFC', tekst)  # PDF-y czasem rozbijają „ą” na „a” + ogonek
    tekst = tekst.replace('\r\n', '\n').replace('\r', '\n').replace('\x00', '')
    tekst = '\n'.join(linia.rstrip() for linia in tekst.split('\n'))
    tekst = re.sub(r'\n{3,}', '\n\n', tekst)
    return tekst.strip()


# --- PDF ---------------------------------------------------------------------

def _z_pdf(sciezka: Path) -> WynikEkstrakcji:
    from pypdf import PdfReader

    czytnik = PdfReader(sciezka)
    if czytnik.is_encrypted:
        try:
            odszyfrowano = czytnik.decrypt('')  # wiele PDF-ów ma tylko hasło właściciela
        except Exception:
            odszyfrowano = 0
        if not odszyfrowano:
            raise BladPliku('PDF jest zabezpieczony hasłem. Zdejmij zabezpieczenie i wgraj plik ponownie.')

    strony = [(strona.extract_text() or '') for strona in czytnik.pages]
    ostrzezenia = []
    do_ocr = [nr for nr, s in enumerate(strony) if len(s.strip()) < ocr.MIN_ZNAKOW_STRONY]
    if do_ocr and ocr.dostepny():
        odczytane = 0
        for nr, tekst in ocr.strony_pdf_do_ocr(sciezka, do_ocr).items():
            if len(tekst.strip()) > len(strony[nr].strip()):
                strony[nr] = tekst
                odczytane += 1
        if odczytane:
            ostrzezenia.append(_ostrzezenie_ocr(f'{odczytane} z {len(strony)} stron' if len(strony) > 1 else 'skan'))

    puste = sum(1 for s in strony if not s.strip())
    if strony and puste == len(strony):
        ostrzezenia.append('PDF nie ma warstwy tekstowej (prawdopodobnie skan), a OCR nie odczytał tekstu.'
                           if ocr.dostepny() else
                           'PDF nie ma warstwy tekstowej (prawdopodobnie skan), a OCR jest niedostępny na tym komputerze.')
    elif puste:
        ostrzezenia.append(f'{puste} z {len(strony)} stron nie zawiera tekstu (możliwe skany).')
    return WynikEkstrakcji('\n\n'.join(strony), len(strony), ostrzezenia)


def _ostrzezenie_ocr(co: str) -> str:
    return f'Tekst odczytany OCR-em ({co}) – sprawdź go z oryginałem, zwłaszcza liczby, nazwiska i pismo odręczne.'


# --- DOCX --------------------------------------------------------------------

def _z_docx(sciezka: Path) -> WynikEkstrakcji:
    import docx
    from docx.table import Table

    dokument = docx.Document(str(sciezka))
    czesci = []
    for blok in dokument.iter_inner_content():  # akapity i tabele w kolejności z dokumentu
        if isinstance(blok, Table):
            czesci.extend(_tabela_na_tekst(blok))
        else:
            czesci.append(blok.text)
    tekst = '\n'.join(czesci)
    if len(tekst.strip()) >= ocr.MIN_ZNAKOW_STRONY or not ocr.dostepny():
        return WynikEkstrakcji(tekst)
    # Word z wklejonym zdjęciem kartki – odczytujemy zdjęcia OCR-em
    obrazy = [czesc.blob for czesc in dokument.part.related_parts.values()
              if czesc.content_type.startswith('image/')]
    odczytane = [t for t in (ocr.rozpoznaj_obraz(blob) for blob in obrazy) if t.strip()]
    if not odczytane:
        return WynikEkstrakcji(tekst)
    return WynikEkstrakcji('\n\n'.join([tekst, *odczytane]),
                           ostrzezenia=[_ostrzezenie_ocr(f'zdjęcia w dokumencie: {len(odczytane)}')])


def _tabela_na_tekst(tabela) -> list[str]:
    wiersze = []
    for wiersz in tabela.rows:
        komorki = []
        for komorka in wiersz.cells:
            tekst = komorka.text.strip()
            if not komorki or komorki[-1] != tekst:  # scalone komórki powtarzają się w python-docx
                komorki.append(tekst)
        wiersze.append(' | '.join(komorki))
    return wiersze


# --- DOC (stary format Word) --------------------------------------------------

def _znajdz_libreoffice() -> str | None:
    kandydaci = [
        shutil.which('soffice'),
        r'C:\Program Files\LibreOffice\program\soffice.exe',
        r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
    ]
    return next((k for k in kandydaci if k and Path(k).exists()), None)


def _z_doc(sciezka: Path) -> WynikEkstrakcji:
    soffice = _znajdz_libreoffice()
    if soffice is None:
        raise BladPliku('Stary format Word (.doc) wymaga LibreOffice do odczytu. '
                        'Zapisz plik w Wordzie jako .docx albo zainstaluj LibreOffice.')
    with tempfile.TemporaryDirectory() as katalog:
        katalog = Path(katalog)
        profil = (katalog / 'profil').as_uri()  # osobny profil – działa też przy otwartym LibreOffice
        subprocess.run(
            [soffice, f'-env:UserInstallation={profil}', '--headless',
             '--convert-to', 'txt:Text (encoded):UTF8', '--outdir', str(katalog), str(sciezka)],
            check=True, timeout=120, capture_output=True,
        )
        wynik = katalog / f'{sciezka.stem}.txt'
        if not wynik.exists():
            raise BladPliku('LibreOffice nie zdołał przekonwertować pliku .doc.')
        return WynikEkstrakcji(wynik.read_text('utf-8-sig', errors='replace'))


# --- TXT ---------------------------------------------------------------------

def _z_txt(sciezka: Path) -> WynikEkstrakcji:
    dane = sciezka.read_bytes()
    for kodowanie in ('utf-8-sig', 'cp1250'):  # cp1250 – polskie pliki z Windows
        try:
            return WynikEkstrakcji(dane.decode(kodowanie))
        except UnicodeDecodeError:
            continue
    return WynikEkstrakcji(dane.decode('utf-8', errors='replace'),
                           ostrzezenia=['Nierozpoznane kodowanie znaków – część liter może być błędna.'])


# --- zdjęcia (JPG / PNG) -------------------------------------------------------

def _z_obrazu(sciezka: Path) -> WynikEkstrakcji:
    if not ocr.dostepny():
        return WynikEkstrakcji('', 1, ['Zdjęcie – OCR jest niedostępny na tym komputerze, tekstu nie odczytano.'])
    tekst = ocr.rozpoznaj_obraz(sciezka.read_bytes())
    if not tekst.strip():
        return WynikEkstrakcji('', 1, ['OCR nie odczytał tekstu ze zdjęcia (za słaba jakość?).'])
    return WynikEkstrakcji(tekst, 1, [_ostrzezenie_ocr('zdjęcie')])

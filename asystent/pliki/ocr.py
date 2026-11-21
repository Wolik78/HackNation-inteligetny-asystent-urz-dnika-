"""OCR skanów i zdjęć – lokalnie, silnikiem OCR wbudowanym w Windows (język polski, bez pobierania modeli).

To samo podejście co w `program2.py` (Czarek): Windows.Media.Ocr przez `winocr`, strony PDF renderowane
przez PyMuPDF w 300 DPI. Nic nie wychodzi poza komputer.

Uwaga: OCR Windows dobrze czyta druk i skany pism; pismo odręczne – słabo. Dlatego tekst z OCR jest
zawsze oznaczany ostrzeżeniem do sprawdzenia przez urzędnika.
"""

from __future__ import annotations

import io
import logging
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

JEZYK = 'pl'
DPI = 300                    # rozdzielczość renderowania strony PDF do OCR
MIN_ZNAKOW_STRONY = 40       # strona PDF z mniejszą ilością tekstu = zdjęcie kartki -> OCR
MAKS_BOK_OBRAZU = 9000       # limit silnika Windows – większe obrazy są zmniejszane


class OcrNiedostepny(Exception):
    """Na tym komputerze nie ma OCR (brak bibliotek albo polskiego pakietu OCR w Windows)."""


@lru_cache(maxsize=1)
def dostepny() -> bool:
    """Czy da się uruchomić OCR: biblioteki + polski język OCR w Windows."""
    try:
        import pymupdf  # noqa: F401 – renderowanie stron PDF
        import winocr  # noqa: F401
        from winrt.windows.media.ocr import OcrEngine
        jezyki = [j.language_tag.lower() for j in OcrEngine.available_recognizer_languages]
    except Exception as blad:  # brak bibliotek albo system inny niż Windows
        log.info('OCR niedostępny: %s', blad)
        return False
    return any(j.startswith(JEZYK) for j in jezyki)


def rozpoznaj_obraz(obraz: bytes) -> str:
    """Tekst z obrazu (PNG/JPG – bajty). Rzuca OcrNiedostepny, gdy OCR nie działa na tym komputerze.

    Wywołuj poza pętlą zdarzeń (w GUI przez `run.io_bound`) – `winocr` uruchamia własną pętlę asyncio.
    """
    if not dostepny():
        raise OcrNiedostepny('OCR niedostępny – zainstaluj pakiety z requirements.txt i polski pakiet OCR Windows.')
    import winocr
    from PIL import Image

    img = Image.open(io.BytesIO(obraz))
    img = img.convert('RGBA')
    if max(img.size) > MAKS_BOK_OBRAZU:
        img.thumbnail((MAKS_BOK_OBRAZU, MAKS_BOK_OBRAZU))
    wynik = winocr.recognize_pil_sync(img, lang=JEZYK)
    return '\n'.join(linia['text'] for linia in wynik['lines'])


Slowo = tuple[str, float, float, float, float]   # (tekst, x0, y0, x1, y1) w pikselach obrazu


def linie_ze_slowami(obraz: bytes) -> list[list[Slowo]]:
    """Linie tekstu z położeniem każdego słowa – do zaczerniania danych na skanach i zdjęciach."""
    if not dostepny():
        raise OcrNiedostepny('OCR niedostępny na tym komputerze.')
    import winocr
    from PIL import Image

    img = Image.open(io.BytesIO(obraz)).convert('RGBA')
    skala = 1.0
    if max(img.size) > MAKS_BOK_OBRAZU:
        szerokosc = img.width
        img.thumbnail((MAKS_BOK_OBRAZU, MAKS_BOK_OBRAZU))
        skala = szerokosc / img.width
    wynik = winocr.recognize_pil_sync(img, lang=JEZYK)
    linie = []
    for linia in wynik['lines']:
        slowa = []
        for slowo in linia['words']:
            r = slowo['bounding_rect']
            slowa.append((slowo['text'], r['x'] * skala, r['y'] * skala,
                          (r['x'] + r['width']) * skala, (r['y'] + r['height']) * skala))
        linie.append(slowa)
    return linie


def strony_pdf_do_ocr(sciezka: Path, numery: list[int]) -> dict[int, str]:
    """OCR wskazanych stron PDF (numeracja od 0) -> {nr strony: tekst}."""
    import pymupdf

    wyniki = {}
    with pymupdf.open(sciezka) as pdf:
        for nr in numery:
            obraz = pdf[nr].get_pixmap(dpi=DPI).tobytes('png')
            wyniki[nr] = rozpoznaj_obraz(obraz)
    return wyniki

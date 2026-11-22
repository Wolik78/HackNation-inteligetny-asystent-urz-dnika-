"""OCR skanów i zdjęć (silnik Windows). Testy z prawdziwym OCR są pomijane, gdy nie ma go na komputerze."""

import io
from pathlib import Path

import pytest

from asystent.pliki import BladPliku, wyciagnij_tekst
from asystent.pliki import ocr
from asystent.pliki.walidacja import sprawdz_plik
from tests.conftest import WNIOSEK_TESTOWY

pymupdf = pytest.importorskip('pymupdf')
WNIOSEK = WNIOSEK_TESTOWY
z_ocr = pytest.mark.skipif(not ocr.dostepny(), reason='OCR Windows z językiem polskim niedostępny')


def zdjecie_wniosku(dpi: int = 200) -> bytes:
    """PNG – „zdjęcie” pierwszej strony testowego wniosku."""
    with pymupdf.open(WNIOSEK) as pdf:
        return pdf[0].get_pixmap(dpi=dpi).tobytes('png')


def skan_pdf(sciezka: Path) -> Path:
    """PDF ze stroną jako obrazem – bez warstwy tekstowej, jak ze skanera."""
    with pymupdf.open(WNIOSEK) as zrodlo, pymupdf.open() as skan:
        strona = skan.new_page(width=zrodlo[0].rect.width, height=zrodlo[0].rect.height)
        strona.insert_image(strona.rect, stream=zdjecie_wniosku())
        skan.save(sciezka)
    return sciezka


@z_ocr
def test_skan_pdf_jest_odczytywany_ocr(tmp_path):
    wynik = wyciagnij_tekst(skan_pdf(tmp_path / 'skan.pdf'))

    assert 'informacji publicznej' in wynik.tekst
    assert 'promocję miasta Bydgoszczy' in wynik.tekst      # polskie znaki
    assert '601 234 567' in wynik.tekst                      # liczby – ważne dla anonimizacji
    assert any('OCR' in o for o in wynik.ostrzezenia)       # urzędnik wie, że to tekst z OCR


@z_ocr
@pytest.mark.parametrize('nazwa', ['zdjecie.png', 'zdjecie.jpg'])
def test_zdjecie_wniosku_jest_odczytywane(tmp_path, nazwa):
    dane = zdjecie_wniosku()
    if nazwa.endswith('.jpg'):
        from PIL import Image
        bufor = io.BytesIO()
        Image.open(io.BytesIO(dane)).convert('RGB').save(bufor, 'JPEG', quality=85)
        dane = bufor.getvalue()
    sciezka = tmp_path / nazwa
    sciezka.write_bytes(dane)

    wynik = wyciagnij_tekst(sciezka)
    assert 'WNIOSEK o udostępnienie informacji publicznej' in wynik.tekst
    assert wynik.liczba_stron == 1 and any('OCR' in o for o in wynik.ostrzezenia)


@z_ocr
def test_word_z_wklejonym_zdjeciem_kartki(tmp_path):
    import docx
    dokument = docx.Document()
    dokument.add_picture(io.BytesIO(zdjecie_wniosku()))
    sciezka = tmp_path / 'wniosek.docx'
    dokument.save(sciezka)

    wynik = wyciagnij_tekst(sciezka)
    assert 'informacji publicznej' in wynik.tekst
    assert any('zdjęcia w dokumencie' in o for o in wynik.ostrzezenia)


def test_bez_ocr_skan_dostaje_ostrzezenie(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, 'dostepny', lambda: False)
    wynik = wyciagnij_tekst(skan_pdf(tmp_path / 'skan.pdf'))
    assert wynik.tekst == ''
    assert any('OCR jest niedostępny' in o for o in wynik.ostrzezenia)


def test_bez_ocr_zdjecie_dostaje_ostrzezenie(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, 'dostepny', lambda: False)
    sciezka = tmp_path / 'zdjecie.png'
    sciezka.write_bytes(zdjecie_wniosku(dpi=50))
    wynik = wyciagnij_tekst(sciezka)
    assert wynik.tekst == '' and any('OCR jest niedostępny' in o for o in wynik.ostrzezenia)


def test_zdjecia_przechodza_walidacje():
    assert sprawdz_plik('skan.PNG', zdjecie_wniosku(dpi=50)) == '.png'
    assert sprawdz_plik('foto.jpg', b'\xFF\xD8\xFF\xE0' + b'0' * 100) == '.jpg'
    with pytest.raises(BladPliku, match='nie pasuje'):
        sprawdz_plik('wirus.png', b'MZ\x90\x00' + b'0' * 100)

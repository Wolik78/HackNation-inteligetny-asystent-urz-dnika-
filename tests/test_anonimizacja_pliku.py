"""Anonimizacja pliku w jego formacie (J3): PDF, skan, zdjęcie, Word, TXT – i kontrola pliku wynikowego."""

from pathlib import Path

import pytest

from asystent.anonimizacja import MASKA, wykryj_wzorce
from asystent.pliki import ocr, wyciagnij_tekst
from asystent.pliki.anonimizacja_pliku import zanonimizuj_plik
from tests.conftest import WNIOSEK_TESTOWY, WNIOSEK_Z_DANYMI, WNIOSEK_Z_DANYMI_SKAN

pymupdf = pytest.importorskip('pymupdf')
WNIOSEK = WNIOSEK_TESTOWY
DANE = ('Jan Testowy', 'ul. Przykładowa 12/4', '85-001 Bydgoszcz', '601 234 567', 'jan.testowy@example.com')
z_ocr = pytest.mark.skipif(not ocr.dostepny(), reason='OCR Windows z językiem polskim niedostępny')


def anonimizuj(plik: Path, katalog: Path):
    ukryte = wykryj_wzorce(wyciagnij_tekst(plik).tekst)
    assert set(DANE) <= set(ukryte)              # wzorce bez AI znajdują wszystkie dane z wniosku testowego
    wynik = zanonimizuj_plik(plik, ukryte, katalog / 'wynik')
    tekst = wyciagnij_tekst(wynik.sciezka).tekst
    return wynik, tekst


def test_pdf_z_tekstem_dane_usuniete_z_pliku(tmp_path):
    wynik, tekst = anonimizuj(WNIOSEK, tmp_path)
    assert wynik.sciezka.suffix == '.pdf' and wynik.bezpieczny and wynik.zakryte >= len(DANE)
    assert not any(d in tekst for d in DANE)                     # tekst usunięty, nie tylko zakryty
    assert 'informacji publicznej' in tekst                       # reszta pisma została
    assert WNIOSEK.exists()                                       # oryginał bez zmian
    with pymupdf.open(wynik.sciezka) as pdf:
        assert not (pdf.metadata or {}).get('author')


@z_ocr
def test_skan_pdf_zaczerniony_w_miejscach_z_ocr(tmp_path):
    with pymupdf.open(WNIOSEK) as zrodlo, pymupdf.open() as skan:
        strona = skan.new_page(width=zrodlo[0].rect.width, height=zrodlo[0].rect.height)
        strona.insert_image(strona.rect, stream=zrodlo[0].get_pixmap(dpi=200).tobytes('png'))
        skan.save(tmp_path / 'skan.pdf')
    wynik, tekst = anonimizuj(tmp_path / 'skan.pdf', tmp_path)
    assert wynik.bezpieczny and not any(d in tekst for d in DANE)
    assert 'informacji publicznej' in tekst


@z_ocr
def test_zdjecie_zaczernione_i_zapisane_jako_png(tmp_path):
    with pymupdf.open(WNIOSEK) as zrodlo:
        (tmp_path / 'zdjecie.jpg').write_bytes(zrodlo[0].get_pixmap(dpi=200).tobytes('jpeg'))
    wynik, tekst = anonimizuj(tmp_path / 'zdjecie.jpg', tmp_path)
    assert wynik.sciezka.suffix == '.png' and wynik.bezpieczny
    assert not any(d in tekst for d in DANE)


def test_word_z_tabela(tmp_path):
    import docx
    dokument = docx.Document()
    for linia in wyciagnij_tekst(WNIOSEK).tekst.splitlines():
        dokument.add_paragraph(linia)
    tabela = dokument.add_table(rows=1, cols=2)
    tabela.cell(0, 0).text, tabela.cell(0, 1).text = 'Wnioskodawca', 'Jan Testowy, tel. 601 234 567'
    dokument.core_properties.author = 'Jan Testowy'
    dokument.save(tmp_path / 'wniosek.docx')

    wynik, tekst = anonimizuj(tmp_path / 'wniosek.docx', tmp_path)
    assert wynik.sciezka.suffix == '.docx' and wynik.bezpieczny
    assert not any(d in tekst for d in DANE) and MASKA in tekst
    assert docx.Document(str(wynik.sciezka)).core_properties.author == ''


def test_txt(tmp_path):
    (tmp_path / 'wniosek.txt').write_text(wyciagnij_tekst(WNIOSEK).tekst, 'utf-8')
    wynik, tekst = anonimizuj(tmp_path / 'wniosek.txt', tmp_path)
    assert wynik.sciezka.suffix == '.txt' and wynik.bezpieczny and tekst.count(MASKA) >= len(DANE)


def test_dane_ktorych_nie_ma_w_pliku_sa_zglaszane(tmp_path):
    wynik = zanonimizuj_plik(WNIOSEK, {'Jan Testowy', 'Ktoś Spoza Pliku'}, tmp_path / 'wynik')
    assert wynik.nieznalezione == ['Ktoś Spoza Pliku'] and not wynik.bezpieczny


TYPY_W_PLIKU_TESTOWYM = {'PESEL', 'E-mail', 'Telefon', 'Nr konta', 'Dowód osobisty', 'NIP', 'Data urodzenia', 'Adres',
                         'Kod pocztowy i miejscowość', 'Imię i nazwisko'}


@pytest.mark.parametrize('plik', [
    WNIOSEK_Z_DANYMI,
    pytest.param(WNIOSEK_Z_DANYMI_SKAN, marks=z_ocr),
])
def test_plik_testowy_z_danymi_osobowymi(tmp_path, plik):
    """Plik dla jury (J3): twarde spacje, dane przełamane między liniami, metadane autora – wszystko ukryte."""
    wykryte = wykryj_wzorce(wyciagnij_tekst(plik).tekst)
    assert set(wykryte.values()) == TYPY_W_PLIKU_TESTOWYM
    wynik = zanonimizuj_plik(plik, wykryte, tmp_path / 'wynik')
    assert wynik.bezpieczny, (wynik.nieznalezione, wynik.pozostale)
    assert 'dodatek mieszkaniowy' in wyciagnij_tekst(wynik.sciezka).tekst

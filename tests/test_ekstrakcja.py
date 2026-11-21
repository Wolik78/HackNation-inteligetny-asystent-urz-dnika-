import pytest
from pypdf import PdfReader, PdfWriter

from asystent.pliki import BladPliku, wyciagnij_tekst
from asystent.pliki import ekstrakcja
from tests.conftest import TEKST_PL, zrob_docx, zrob_pdf


def test_pdf_z_polskimi_znakami(tmp_path, ma_polska_czcionke):
    sciezka = tmp_path / 'wniosek.pdf'
    sciezka.write_bytes(zrob_pdf(strony=2))
    wynik = wyciagnij_tekst(sciezka)

    assert wynik.liczba_stron == 2
    assert 'informacji publicznej' in wynik.tekst
    if ma_polska_czcionke:
        assert 'zażółć gęślą jaźń' in wynik.tekst
    assert not wynik.ostrzezenia


def test_pdf_bez_tekstu_daje_ostrzezenie_o_skanie(tmp_path):
    sciezka = tmp_path / 'skan.pdf'
    sciezka.write_bytes(zrob_pdf(tekst=None))
    wynik = wyciagnij_tekst(sciezka)

    assert wynik.tekst == ''
    assert any('skan' in o for o in wynik.ostrzezenia)


def test_pdf_z_haslem_jest_odrzucany(tmp_path):
    zrodlo = tmp_path / 'jawny.pdf'
    zrodlo.write_bytes(zrob_pdf())
    pisarz = PdfWriter(clone_from=PdfReader(zrodlo))
    pisarz.encrypt(user_password='tajne', owner_password='tajne')
    zaszyfrowany = tmp_path / 'zaszyfrowany.pdf'
    with open(zaszyfrowany, 'wb') as f:
        pisarz.write(f)

    with pytest.raises(BladPliku, match='hasłem'):
        wyciagnij_tekst(zaszyfrowany)


def test_uszkodzony_pdf(tmp_path):
    sciezka = tmp_path / 'zepsuty.pdf'
    sciezka.write_bytes(b'%PDF-1.7\n to nie jest prawdziwy pdf')
    with pytest.raises(BladPliku):
        wyciagnij_tekst(sciezka)


def test_docx_z_tabela(tmp_path):
    sciezka = tmp_path / 'odpowiedz.docx'
    sciezka.write_bytes(zrob_docx(
        [TEKST_PL, 'Drugi akapit.'],
        tabela=[['Rok', 'Kwota'], ['2025', '1 240 000 zł']],
    ))
    wynik = wyciagnij_tekst(sciezka)

    assert 'zażółć gęślą jaźń' in wynik.tekst
    assert 'Drugi akapit.' in wynik.tekst
    assert '2025 | 1 240 000 zł' in wynik.tekst


@pytest.mark.parametrize('kodowanie', ['utf-8', 'cp1250'])
def test_txt_w_roznych_kodowaniach(tmp_path, kodowanie):
    sciezka = tmp_path / 'wniosek.txt'
    sciezka.write_bytes(TEKST_PL.encode(kodowanie))
    assert wyciagnij_tekst(sciezka).tekst == TEKST_PL


def test_doc_bez_libreoffice_daje_czytelny_blad(tmp_path, monkeypatch):
    monkeypatch.setattr(ekstrakcja, '_znajdz_libreoffice', lambda: None)
    sciezka = tmp_path / 'stary.doc'
    sciezka.write_bytes(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1' + b'\x00' * 100)
    with pytest.raises(BladPliku, match='.docx'):
        wyciagnij_tekst(sciezka)


def test_normalizacja_bialych_znakow(tmp_path):
    sciezka = tmp_path / 'brudny.txt'
    sciezka.write_bytes('Linia 1   \r\n\r\n\r\n\r\nLinia 2\x00'.encode())
    assert wyciagnij_tekst(sciezka).tekst == 'Linia 1\n\nLinia 2'

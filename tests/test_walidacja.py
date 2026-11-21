import io
import zipfile

import pytest

from asystent.pliki import BladPliku, bezpieczna_nazwa, sprawdz_plik
from tests.conftest import zrob_docx, zrob_pdf


@pytest.mark.parametrize('wejscie, oczekiwane', [
    ('wniosek.pdf', 'wniosek.pdf'),
    ('Wniosek Kowalskiego.PDF', 'Wniosek_Kowalskiego.pdf'),
    ('../../Windows/System32/zły plik.docx', 'zły_plik.docx'),
    (r'C:\Users\x\Pulpit\odpowiedź.docx', 'odpowiedź.docx'),
    ('___.pdf', 'plik.pdf'),
    ('a<b>c|d?.txt', 'a_b_c_d.txt'),
])
def test_bezpieczna_nazwa(wejscie, oczekiwane):
    assert bezpieczna_nazwa(wejscie) == oczekiwane


def test_bezpieczna_nazwa_przycina_dlugie_nazwy():
    assert bezpieczna_nazwa('a' * 500 + '.pdf') == 'a' * 100 + '.pdf'


def test_przyjmuje_poprawne_pliki():
    assert sprawdz_plik('w.pdf', zrob_pdf()) == '.pdf'
    assert sprawdz_plik('w.docx', zrob_docx(['test'])) == '.docx'
    assert sprawdz_plik('w.txt', 'treść'.encode()) == '.txt'


@pytest.mark.parametrize('nazwa', ['wirus.exe', 'arkusz.xlsx', 'bez_rozszerzenia'])
def test_odrzuca_nieobslugiwane_typy(nazwa):
    with pytest.raises(BladPliku, match='Nieobsługiwany typ'):
        sprawdz_plik(nazwa, b'cokolwiek')


def test_odrzuca_pusty_plik():
    with pytest.raises(BladPliku, match='pusty'):
        sprawdz_plik('w.pdf', b'')


def test_odrzuca_za_duzy_plik():
    with pytest.raises(BladPliku, match='za duży'):
        sprawdz_plik('w.txt', b'x' * 2048, maks_rozmiar=1024)


def test_odrzuca_plik_z_falszywym_rozszerzeniem():
    with pytest.raises(BladPliku, match='nie pasuje do formatu'):
        sprawdz_plik('faktura.pdf', b'MZ\x90\x00 to jest program .exe')


def test_odrzuca_zip_udajacy_docx():
    bufor = io.BytesIO()
    with zipfile.ZipFile(bufor, 'w') as archiwum:
        archiwum.writestr('cos.txt', 'nie word')
    with pytest.raises(BladPliku, match='poprawny dokument Word'):
        sprawdz_plik('w.docx', bufor.getvalue())

import pytest

from asystent.pliki import eksportuj, nazwa_pliku_odpowiedzi, wyciagnij_tekst

PISMO = 'Szanowny Panie,\n\nuprzejmie informuję, że wydatki wyniosły 1 240 000 zł.\nZ poważaniem'


@pytest.mark.parametrize('rozszerzenie', ['.docx', '.txt'])
def test_eksport_i_ponowny_odczyt(tmp_path, rozszerzenie):
    sciezka = eksportuj(PISMO, tmp_path / 'eksport' / f'odpowiedz{rozszerzenie}')

    assert sciezka.exists()
    assert wyciagnij_tekst(sciezka).tekst == PISMO


def test_nieobslugiwany_format(tmp_path):
    with pytest.raises(ValueError):
        eksportuj(PISMO, tmp_path / 'odpowiedz.pdf')


def test_nazwa_pliku_odpowiedzi():
    assert nazwa_pliku_odpowiedzi('UDIP/1/2026', 'docx') == 'Odpowiedz_UDIP_1_2026.docx'

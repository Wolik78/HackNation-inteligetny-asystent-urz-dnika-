import pytest

from asystent.pliki import BladPliku, Kategoria, MagazynPlikow
from tests.conftest import zrob_docx, zrob_pdf


@pytest.fixture
def magazyn(tmp_path):
    return MagazynPlikow(tmp_path / 'dane')


def test_zapis_wniosku_do_przychodzacych(magazyn):
    plik = magazyn.zapisz(zrob_pdf(), 'Wniosek Kowalski.pdf', Kategoria.WNIOSEK)

    assert plik.sciezka.parent == magazyn.katalog / 'przychodzace'
    assert plik.sciezka.exists() and plik.sciezka_meta.exists()
    assert plik.nazwa_oryginalna == 'Wniosek Kowalski.pdf'
    assert plik.typ == 'PDF'
    assert plik.liczba_stron == 1
    assert 'informacji publicznej' in plik.tekst()
    assert plik.liczba_znakow == len(plik.tekst())


def test_lista_odczytuje_metadane_z_dysku(magazyn, tmp_path):
    magazyn.zapisz(zrob_docx(['pierwszy']), 'a.docx', Kategoria.USTAWA)
    magazyn.zapisz(zrob_docx(['drugi']), 'b.docx', Kategoria.USTAWA)

    nowy_magazyn = MagazynPlikow(tmp_path / 'dane')  # np. po restarcie aplikacji
    pliki = nowy_magazyn.lista(Kategoria.USTAWA)

    assert [p.nazwa_oryginalna for p in pliki] == ['a.docx', 'b.docx']
    assert pliki[0].tekst() == 'pierwszy'
    assert nowy_magazyn.lista(Kategoria.ZARZADZENIE) == []


def test_duplikat_nie_jest_zapisywany_drugi_raz(magazyn):
    dane = zrob_pdf()
    pierwszy = magazyn.zapisz(dane, 'w.pdf', Kategoria.ARCHIWUM)
    drugi = magazyn.zapisz(dane, 'kopia w.pdf', Kategoria.ARCHIWUM)

    assert drugi.duplikat
    assert drugi.plik == pierwszy.plik
    assert len(magazyn.lista(Kategoria.ARCHIWUM)) == 1


def test_odpowiedzi_wydzialow_trafiaja_do_sprawy(magazyn):
    plik = magazyn.zapisz(zrob_docx(['odp']), 'odp.docx', Kategoria.ODPOWIEDZ_WYDZIALU,
                          sprawa='UDIP/7/2026', opis='Wydział Finansów')

    assert plik.sciezka.parent == magazyn.katalog / 'sprawy' / 'UDIP_7_2026' / 'odpowiedzi'
    assert magazyn.lista(Kategoria.ODPOWIEDZ_WYDZIALU, sprawa='UDIP/7/2026')[0].opis == 'Wydział Finansów'


def test_odpowiedz_bez_sprawy_jest_bledem(magazyn):
    with pytest.raises(ValueError):
        magazyn.zapisz(zrob_docx(['odp']), 'odp.docx', Kategoria.ODPOWIEDZ_WYDZIALU)


def test_przeniesienie_wniosku_do_sprawy(magazyn):
    plik = magazyn.zapisz(zrob_pdf(), 'w.pdf', Kategoria.WNIOSEK)
    magazyn.przenies_do_sprawy(plik, 'UDIP.11.2026')

    assert magazyn.lista(Kategoria.WNIOSEK) == []
    w_sprawie = magazyn.lista(Kategoria.WNIOSEK, sprawa='UDIP.11.2026')
    assert len(w_sprawie) == 1
    assert w_sprawie[0].sprawa == 'UDIP.11.2026'
    assert 'informacji publicznej' in w_sprawie[0].tekst()


def test_usuniecie_kasuje_plik_i_metadane(magazyn):
    plik = magazyn.zapisz(zrob_pdf(), 'w.pdf', Kategoria.WNIOSEK)
    magazyn.usun(plik)

    assert not plik.sciezka.exists()
    assert not plik.sciezka_meta.exists()
    assert not plik.sciezka_tekstu.exists()


def test_odrzucony_plik_nie_zostaje_na_dysku(magazyn):
    with pytest.raises(BladPliku):
        magazyn.zapisz(b'%PDF-1.7 uszkodzony', 'w.pdf', Kategoria.WNIOSEK)
    katalog = magazyn.katalog / 'przychodzace'
    assert not katalog.exists() or not any(katalog.iterdir())

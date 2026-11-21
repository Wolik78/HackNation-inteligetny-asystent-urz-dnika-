from asystent.kontrola import sprawdz_pismo, wyciagnij_wartosci

WNIOSEK = 'Bydgoszcz, 20.11.2026. Wnoszę o informację, ile wydano na promocję miasta w 2025 roku.'
ODPOWIEDZ_WYDZIALU = ('W 2025 r. na promocję wydano łącznie 1 240 000 zł brutto. Kampania „Bydgoszcz nad wodą” – '
                      '740 000 zł. Sprawę prowadziła Anna Przykładowa, tel. 52 123 45 67.')
ZRODLA = [('wniosek', WNIOSEK), ('odpowiedz_wydzialu.docx', ODPOWIEDZ_WYDZIALU)]

DOBRE_PISMO = (
    'Szanowny Panie,\n\nw odpowiedzi na wniosek z dnia 20 listopada 2026 r. uprzejmie informuję, że w 2025 roku '
    'na promocję miasta wydano łącznie 1.240.000 zł brutto, w tym na kampanię „Bydgoszcz nad wodą” 740 000 zł.\n\n'
    'Podstawa prawna: art. 2 ust. 1 i art. 10 ust. 1 ustawy z dnia 6 września 2001 r. o dostępie do informacji '
    'publicznej.\n\nZ poważaniem'
)


def test_wyciaganie_wartosci_pomija_przepisy_i_normalizuje():
    klucze = [k for _, k in wyciagnij_wartosci('Kwota 1 240 000 zł (art. 13 ust. 2), z 20.11.2026 i 3 kampanie.')]
    assert klucze == ['D:2026-11-20', 'N:1240000']


def test_ta_sama_data_zapisana_inaczej():
    assert [k for _, k in wyciagnij_wartosci('20 listopada 2026')] == [k for _, k in wyciagnij_wartosci('20.11.2026')]


def test_poprawne_pismo_bez_bledow():
    wynik = sprawdz_pismo(DOBRE_PISMO, ZRODLA)

    assert wynik.bledy == []
    assert wynik.ostrzezenia == []
    zrodla = {w.tekst: w.zrodlo for w in wynik.wartosci}
    assert zrodla['1.240.000'] == 'odpowiedz_wydzialu.docx'   # inny zapis tej samej kwoty
    assert zrodla['20 listopada 2026'] == 'wniosek'
    assert zrodla['6 września 2001'] == 'przepisy'   # data ustawy


def test_zmyslona_kwota_i_data_sa_bledem():
    pismo = DOBRE_PISMO.replace('740 000 zł', '780 000 zł') + '\nInformacje przekazano 15.12.2025.'
    wynik = sprawdz_pismo(pismo, ZRODLA)

    zle = {p.fragment for p in wynik.bledy}
    assert zle == {'780 000', '15.12.2025'}


def test_pola_do_uzupelnienia():
    wynik = sprawdz_pismo(DOBRE_PISMO + '\n[Imię i Nazwisko]\n[UZUPEŁNIĆ: stanowisko]', ZRODLA)
    assert {p.fragment for p in wynik.bledy} == {'[Imię i Nazwisko]', '[UZUPEŁNIĆ: stanowisko]'}


def test_forma_pisma():
    wynik = sprawdz_pismo('**Odpowiedź**\nWydano 1 240 000 zł.', ZRODLA)
    opisy = ' '.join(p.opis for p in wynik.ostrzezenia)
    for oczekiwane in ('podstawy prawnej', 'grzecznościowego', 'Z poważaniem', 'Markdown', 'krótkie'):
        assert oczekiwane in opisy


def test_nieukryte_dane_osobowe():
    pismo = DOBRE_PISMO + '\nSprawę prowadziła Anna Przykładowa, tel. 52 123 45 67.'
    ostrzezenia = [p.opis for p in sprawdz_pismo(pismo, ZRODLA).ostrzezenia if 'Nieukryte' in p.opis]
    assert any('52 123 45 67' in o for o in ostrzezenia) and any('Anna Przykładowa' in o for o in ostrzezenia)
    ukryte = {'52 123 45 67', 'Anna Przykładowa'}
    assert not any('Nieukryte' in p.opis for p in sprawdz_pismo(pismo, ZRODLA, ukryte=ukryte).ostrzezenia)


def test_dane_sprawy_sa_dozwolone():
    pismo = DOBRE_PISMO + '\nTermin udzielenia odpowiedzi: 04.12.2026.'
    assert sprawdz_pismo(pismo, ZRODLA).bledy
    assert not sprawdz_pismo(pismo, ZRODLA, dane_sprawy=['04.12.2026']).bledy


def test_pominieta_wartosc_z_odpowiedzi_wydzialu():
    odpowiedz = ODPOWIEDZ_WYDZIALU + ' Kampania „Kultura w mieście” – 500 000 zł. Pismo z dnia 18.11.2026.'
    wynik = sprawdz_pismo(DOBRE_PISMO, [('wniosek', WNIOSEK)], do_pokrycia=[('BKS.docx', odpowiedz)])

    pominiete = [p.opis for p in wynik.ostrzezenia if 'czy na pewno ją pominąć' in p.opis]
    assert len(pominiete) == 1 and '500 000' in pominiete[0]   # bez telefonu i daty pisma wydziału
    assert wynik.bledy == []


def test_pusty_projekt():
    assert sprawdz_pismo('   ', ZRODLA).bledy

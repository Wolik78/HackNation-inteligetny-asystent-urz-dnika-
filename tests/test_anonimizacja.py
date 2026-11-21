from asystent.anonimizacja import MASKA, podziel_na_fragmenty, wykryj_wzorce, zamaskuj

TEKST = ('Jan Kowalski (PESEL 85010112345), tel. +48 601 234 567, e-mail jan.kowalski@example.com, '
         'konto PL61 1090 1014 0000 0712 1981 2874, dowód ABC 123456. Wydatki: 1 240 000 zł.')


def test_wykrywa_dane_wzorcami():
    wynik = wykryj_wzorce(TEKST)
    assert wynik['85010112345'] == 'PESEL'
    assert wynik['jan.kowalski@example.com'] == 'E-mail'
    assert wynik['+48 601 234 567'] == 'Telefon'
    assert wynik['PL61 1090 1014 0000 0712 1981 2874'] == 'Nr konta'
    assert wynik['ABC 123456'] == 'Dowód osobisty'


def test_telefon_stacjonarny():
    wynik = wykryj_wzorce('Kontakt: tel. 52 123 45 67 lub (52) 123-45-67.')
    assert wynik.get('52 123 45 67') == 'Telefon'
    assert wynik.get('(52) 123-45-67') == 'Telefon'


def test_kwoty_nie_sa_danymi_osobowymi():
    assert '1 240 000' not in ' '.join(wykryj_wzorce('Wydatki wyniosły 1 240 000 zł w 2025 r.'))


def test_fragmenty_skladaja_sie_w_oryginal():
    fragmenty = podziel_na_fragmenty(TEKST, ['Jan Kowalski', '85010112345'])
    assert ''.join(f for f, _ in fragmenty) == TEKST
    assert ('Jan Kowalski', True) in fragmenty


def test_dluzszy_ciag_ma_pierwszenstwo():
    fragmenty = podziel_na_fragmenty('Jan Kowalski mieszka', ['Jan', 'Jan Kowalski'])
    assert fragmenty[0] == ('Jan Kowalski', True)


def test_maskowanie_wszystkich_wystapien():
    wynik = zamaskuj('Jan Kowalski pisze. Pan Jan Kowalski prosi.', ['Jan Kowalski'])
    assert wynik == f'{MASKA} pisze. Pan {MASKA} prosi.'
    assert zamaskuj('bez zmian', []) == 'bez zmian'

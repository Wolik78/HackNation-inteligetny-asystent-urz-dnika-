"""Klasyfikacja wniosku i ścieżka postępowania (ustawa o dostępie do informacji publicznej).

Rodzaj sprawy podpowiada Bielik przy analizie wniosku (zamknięta lista), a gdy model nie odpowie – proste reguły
poniżej. Rodzaj decyduje o tym, jakie pismo przygotować; urzędnik zawsze może go zmienić.
"""

import re
from dataclasses import dataclass

from .ai.tekst import normalizuj


@dataclass(frozen=True)
class Rodzaj:
    klucz: str
    nazwa: str
    sciezka: str      # co zrobić – krótko, z podstawą prawną
    pismo: str        # jakie pismo przygotowuje „Generuj projekt”
    kolor: str
    ikona: str


RODZAJE: dict[str, Rodzaj] = {r.klucz: r for r in (
    Rodzaj('zwykla', 'Informacja publiczna',
           'Zbierz informacje od wydziałów i udostępnij je w ciągu 14 dni (art. 13 ust. 1). Gdy to niemożliwe – '
           'zawiadom o przyczynach opóźnienia i nowym terminie, najdalej 2 miesiące (art. 13 ust. 2).',
           'odpowiedź z informacją', 'primary', 'description'),
    Rodzaj('przetworzona', 'Informacja przetworzona',
           'Przygotowanie informacji wymaga analizy lub zestawienia wielu danych. Wezwij wnioskodawcę do wykazania '
           'szczególnie istotnego interesu publicznego (art. 3 ust. 1 pkt 1); bez niego – decyzja o odmowie (art. 16).',
           'wezwanie do wykazania szczególnie istotnego interesu publicznego', 'orange', 'analytics'),
    Rodzaj('w_bip', 'Informacja dostępna w BIP',
           'Informacja opublikowana w Biuletynie Informacji Publicznej nie jest udostępniana na wniosek '
           '(art. 10 ust. 1) – wskaż wnioskodawcy, gdzie ją znajdzie.',
           'pismo wskazujące, gdzie w BIP jest informacja', 'teal', 'public'),
    Rodzaj('nie_publiczna', 'To nie jest informacja publiczna',
           'Żądanie dotyczy np. indywidualnej sprawy wnioskodawcy, porady prawnej albo opinii. Poinformuj o tym '
           'zwykłym pismem – bez wydawania decyzji.',
           'pismo informujące, że żądanie nie dotyczy informacji publicznej', 'grey-7', 'block'),
    Rodzaj('inny_tryb', 'Inny tryb dostępu',
           'Dostęp do tej informacji regulują przepisy szczególne (art. 1 ust. 2), np. wgląd w akta sprawy '
           '(KPA), informacja o środowisku, dane z rejestrów. Poinformuj wnioskodawcę o właściwym trybie.',
           'pismo informujące o właściwym trybie dostępu', 'brown', 'alt_route'),
    Rodzaj('doprecyzowanie', 'Wniosek do doprecyzowania',
           'Wniosek jest niejasny albo zbyt ogólny. Wezwij do doprecyzowania; termin na odpowiedź biegnie '
           'od dnia doprecyzowania wniosku.',
           'wezwanie do doprecyzowania wniosku', 'purple', 'help_outline'),
)}
DOMYSLNY = 'zwykla'

# Krótkie opisy rodzajów dla modelu (prompt analizy wniosku).
OPISY_DLA_MODELU = {
    'zwykla': 'zwykła informacja publiczna, którą urząd ma albo zbierze od wydziałów',
    'przetworzona': 'wymaga zestawienia, analizy lub zsumowania wielu danych, np. wszystkich umów z wielu lat',
    'w_bip': 'informacja z natury publikowana w BIP: uchwały, zarządzenia, budżet, oświadczenia majątkowe',
    'nie_publiczna': 'indywidualna sprawa wnioskodawcy, prośba o poradę, opinię lub interpretację',
    'inny_tryb': 'wgląd w akta sprawy, odpisy z rejestrów – dostęp na podstawie przepisów szczególnych',
    'doprecyzowanie': 'wniosek niejasny lub tak ogólny, że nie wiadomo, o jaką informację chodzi',
}


def rodzaj(klucz: str | None) -> Rodzaj:
    return RODZAJE.get(klucz or DOMYSLNY, RODZAJE[DOMYSLNY])


def rozpoznaj_klucz(odpowiedz_modelu: object) -> str | None:
    """Klucz rodzaju z odpowiedzi modelu – toleruje nazwy, polskie znaki i wielkość liter."""
    tekst = normalizuj(str(odpowiedz_modelu or '')).replace(' ', '_')
    if tekst in RODZAJE:
        return tekst
    for klucz, r in RODZAJE.items():
        if normalizuj(r.nazwa).replace(' ', '_') == tekst:
            return klucz
    synonimy = {'przetworz': 'przetworzona', 'bip': 'w_bip', 'nie_jest': 'nie_publiczna', 'niepubl': 'nie_publiczna',
                'tryb': 'inny_tryb', 'doprecyz': 'doprecyzowanie', 'niejasn': 'doprecyzowanie', 'zwykl': 'zwykla',
                'prost': 'zwykla'}
    return next((k for fragment, k in synonimy.items() if fragment in tekst), None)


# Reguły na wypadek, gdy model nie odpowie (tekst bez polskich znaków, małe litery).
_REGULY: tuple[tuple[str, str, str], ...] = (
    ('nie_publiczna', r'\b(moj(ej|ego|a|ich) (sprawy|sprawie|wniosku|decyzji)|w mojej sprawie|porad\w*|'
                      r'opini\w* prawn\w*|interpretacj\w*)\b',
     'wniosek dotyczy indywidualnej sprawy, porady albo opinii'),
    ('inny_tryb', r'\b(wglad\w* w akta|dostep\w* do akt|kopi\w* akt (mojej )?sprawy|ksieg\w* wieczyst\w*|'
                  r'akt\w* stanu cywilnego|odpis\w* aktu)\b',
     'dostęp do akt albo rejestrów regulują przepisy szczególne'),
    ('przetworzona', r'\b(wszystki\w+ (umow|decyzj|faktur|dokument|uchwal|pism)\w*|zestawieni\w*|analiz\w*|'
                     r'z ostatnich \d+ lat|w latach (19|20)\d\d\s*[-–]\s*(19|20)\d\d|porownani\w*|statystyk\w*)\b',
     'przygotowanie wymaga zestawienia lub analizy wielu danych'),
)


def podpowiedz_regulami(tekst: str) -> tuple[str, str]:
    """(klucz rodzaju, uzasadnienie) bez modelu – ostrożnie: domyślnie zwykła informacja publiczna."""
    znormalizowany = normalizuj(tekst)
    for klucz, wzorzec, uzasadnienie in _REGULY:
        if re.search(wzorzec, znormalizowany):
            return klucz, f'Wykryto w treści: {uzasadnienie}.'
    return DOMYSLNY, ''


def ustal_rodzaj(tekst: str, rodzaj_modelu: str | None, uzasadnienie_modelu: str = '') -> tuple[str, str]:
    """Rodzaj sprawy z odpowiedzi modelu i reguł.

    Mały model chętnie odpowiada „zwykla” (wartość domyślna) – gdy reguły wyraźnie wskazują inny rodzaj
    (np. „w mojej sprawie”, „wszystkich umów z lat…”), wygrywają reguły. Szczególny rodzaj od modelu zostaje.
    """
    regula, uzasadnienie_reguly = podpowiedz_regulami(tekst)
    if rodzaj_modelu and rodzaj_modelu != DOMYSLNY:
        return rodzaj_modelu, uzasadnienie_modelu
    if regula != DOMYSLNY:
        return regula, uzasadnienie_reguly
    return DOMYSLNY, uzasadnienie_modelu if rodzaj_modelu else ''

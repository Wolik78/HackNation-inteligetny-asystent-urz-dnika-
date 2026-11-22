"""Prompty dla Bielika. Trzymane osobno, żeby łatwo je dostrajać bez ruszania logiki klienta."""

SYSTEM_URZEDNIK = (
    'Jesteś doświadczonym urzędnikiem Urzędu Miasta Bydgoszczy, który obsługuje wnioski '
    'o udostępnienie informacji publicznej (ustawa z dnia 6 września 2001 r. o dostępie do informacji publicznej).'
)

FORMAT_TYLKO_JSON = ('Odpowiadasz WYŁĄCZNIE poprawnym obiektem JSON – bez komentarzy, bez bloków kodu, '
                     'bez tekstu przed i po.')


def _cytat(tekst: str) -> str:
    return f'"""\n{tekst.strip()}\n"""'


def analiza_wniosku(tekst: str, rodzaje: dict[str, str] | None = None) -> list[dict]:
    # Wydziałów tu nie ma – dobiera je asystent/ai/wydzialy.py (lista z BIP). Krótszy prompt = szybsza odpowiedź.
    rodzaje = rodzaje or {}
    system = (
        f'{SYSTEM_URZEDNIK} Analizujesz wniosek. {FORMAT_TYLKO_JSON} Format:\n'
        '{"skrocony_opis": "...", "czy_wymaga_kwerendy": false, "rodzaj": "zwykla", "uzasadnienie_rodzaju": "..."}\n'
        'Zasady:\n'
        '- skrocony_opis: jedno zdanie (do 15 słów), czego dotyczy wniosek, bez danych osobowych wnioskodawcy;\n'
        '- czy_wymaga_kwerendy: true tylko wtedy, gdy przygotowanie informacji wymaga przeszukania dużej liczby '
        'dokumentów lub danych z wielu lat (przedłużenie terminu do 2 miesięcy, art. 13 ust. 2);\n'
        '- rodzaj: dokładnie jeden klucz z listy (w razie wątpliwości „zwykla”):\n'
        + ''.join(f'  {klucz} – {opis};\n' for klucz, opis in rodzaje.items()) +
        '- uzasadnienie_rodzaju: jedno krótkie zdanie, dlaczego ten rodzaj.'
    )
    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': f'Treść wniosku:\n{_cytat(tekst)}'},
    ]


def dane_osobowe(tekst: str) -> list[dict]:
    system = (
        'Jesteś inspektorem ochrony danych w Urzędzie Miasta Bydgoszczy. Wskazujesz w tekście dane osobowe '
        'OSÓB PRYWATNYCH, które trzeba zanonimizować przed udostępnieniem dokumentu (RODO): imiona i nazwiska, '
        'adresy zamieszkania, numery PESEL, numery dowodów osobistych, numery telefonów, adresy e-mail, '
        'numery kont bankowych, numery rejestracyjne pojazdów.\n'
        'NIE wskazuj danych osób pełniących funkcje publiczne, gdy występują w związku z tą funkcją '
        '(np. Prezydent Miasta, zastępca prezydenta, skarbnik, sekretarz, dyrektor wydziału, radny), '
        'ani nazw firm, urzędów i instytucji.\n'
        'Każdy element przepisz DOKŁADNIE tak, jak występuje w tekście (znak w znak).\n'
        f'{FORMAT_TYLKO_JSON} Format: {{"do_ukrycia": ["...", "..."]}}. '
        'Jeśli nie ma takich danych, zwróć {"do_ukrycia": []}.'
    )
    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': f'Tekst do sprawdzenia:\n{_cytat(tekst)}'},
    ]


def kompletnosc(wniosek: str, projekt: str) -> list[dict]:
    system = (
        f'{SYSTEM_URZEDNIK} Sprawdzasz, czy projekt odpowiedzi odpowiada na WSZYSTKIE żądania z wniosku.\n'
        'Wypisz każde żądanie z wniosku osobno (zwykle 1–5, każde do 8 słów). Dla każdego oceń, czy projekt '
        'na nie odpowiada. Jeśli tak – w polu "fragment" przepisz DOSŁOWNIE krótki fragment projektu (do 10 słów), '
        'który zawiera odpowiedź. Jeśli projekt nie zawiera odpowiedzi – "odpowiedziano": false i pusty "fragment".\n'
        f'{FORMAT_TYLKO_JSON} Format:\n'
        '{"zadania": [{"zadanie": "czego żąda wnioskodawca", "odpowiedziano": true, "fragment": "..."}]}'
    )
    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': f'WNIOSEK:\n{_cytat(wniosek)}\n\nPROJEKT ODPOWIEDZI:\n{_cytat(projekt)}'},
    ]


def projekt_odpowiedzi(wniosek: str, informacje_wydzialow: str, wzor: str | None = None) -> list[dict]:
    system = (
        f'{SYSTEM_URZEDNIK} Piszesz projekt odpowiedzi na wniosek. Zasady:\n'
        '- pisz formalną polszczyzną urzędową, zwracając się do wnioskodawcy w formie grzecznościowej;\n'
        '- korzystaj WYŁĄCZNIE z informacji przekazanych przez wydziały – nie wymyślaj kwot, dat, nazw ani liczb;\n'
        '- jeśli jakiejś informacji brakuje, wstaw w jej miejsce [UZUPEŁNIĆ: czego brakuje];\n'
        '- powołaj się na wniosek, przekaż żądane informacje, wskaż podstawę prawną '
        '(art. 2 ust. 1 i art. 10 ust. 1 ustawy o dostępie do informacji publicznej) – bez podawania '
        'publikatora (Dz.U.), roku ani pozycji;\n'
        '- zakończ formułą „Z poważaniem”;\n'
        '- pisz zwykłym tekstem, bez formatowania Markdown (bez gwiazdek, krzyżyków i podkreśleń);\n'
        '- zwróć wyłącznie treść pisma, bez komentarzy i wyjaśnień.'
    )
    tresc = f'WNIOSEK:\n{_cytat(wniosek)}\n\nINFORMACJE PRZEKAZANE PRZEZ WYDZIAŁY:\n{_cytat(informacje_wydzialow)}\n\n'
    if wzor:
        tresc += ('WZÓR PODOBNEJ ODPOWIEDZI Z ARCHIWUM '
                  '(tylko jako wzór stylu i układu – nie przepisuj z niego danych):\n'
                  f'{_cytat(wzor)}\n\n')
    tresc += 'Napisz projekt odpowiedzi.'
    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': tresc},
    ]


# Pisma dla spraw, które nie kończą się zwykłym udostępnieniem informacji (klucze jak w asystent/klasyfikacja.py).
PISMA_WG_RODZAJU = {
    'przetworzona': (
        'wezwanie do wykazania szczególnie istotnego interesu publicznego',
        'Wyjaśnij, że żądana informacja ma charakter informacji przetworzonej, bo jej przygotowanie wymaga '
        '[dopasuj do wniosku: zestawienia / analizy / zsumowania danych]. Powołaj art. 3 ust. 1 pkt 1 ustawy o '
        'dostępie '
        'do informacji publicznej i wezwij do wykazania, w terminie 14 dni od otrzymania pisma, szczególnie istotnego '
        'interesu publicznego. Uprzedź, że brak odpowiedzi spowoduje wydanie decyzji o odmowie (art. 16).',
    ),
    'w_bip': (
        'pismo wskazujące, gdzie w Biuletynie Informacji Publicznej jest żądana informacja',
        'Wyjaśnij, że informacja została udostępniona w Biuletynie Informacji Publicznej Urzędu Miasta Bydgoszczy, '
        'wskaż miejsce jej publikacji jako [UZUPEŁNIĆ: adres strony BIP] i powołaj art. 10 ust. 1 ustawy o dostępie '
        'do informacji publicznej (informacja udostępniona w BIP nie podlega udostępnieniu na wniosek).',
    ),
    'nie_publiczna': (
        'pismo informujące, że żądanie nie dotyczy informacji publicznej',
        'Wyjaśnij uprzejmie, że żądanie nie dotyczy informacji publicznej w rozumieniu art. 1 ust. 1 ustawy '
        'o dostępie do informacji publicznej (dopasuj powód do wniosku: sprawa indywidualna, prośba o poradę, '
        'opinię lub interpretację). Jeśli to możliwe, wskaż, gdzie wnioskodawca może załatwić sprawę. '
        'To zwykłe pismo, nie decyzja.',
    ),
    'inny_tryb': (
        'pismo informujące o właściwym trybie dostępu do informacji',
        'Wyjaśnij, że dostęp do żądanej informacji regulują przepisy szczególne (art. 1 ust. 2 ustawy o dostępie do '
        'informacji publicznej) i wskaż właściwy tryb, np. wgląd w akta sprawy na podstawie art. 73 Kodeksu '
        'postępowania administracyjnego – dopasuj do treści wniosku, a gdy nie masz pewności, wstaw [UZUPEŁNIĆ].',
    ),
    'doprecyzowanie': (
        'wezwanie do doprecyzowania wniosku',
        'Wskaż konkretnie, które elementy wniosku są niejasne lub zbyt ogólne (np. okres, zakres dokumentów) '
        'i poproś o ich uściślenie. Poinformuj, że termin na udostępnienie informacji biegnie od dnia doprecyzowania.',
    ),
}


def pismo_wg_rodzaju(rodzaj: str, wniosek: str, dane_sprawy: str) -> list[dict]:
    rodzaj_pisma, instrukcja = PISMA_WG_RODZAJU[rodzaj]
    system = (
        f'{SYSTEM_URZEDNIK} Piszesz {rodzaj_pisma}. {instrukcja}\n'
        'Zasady: formalna polszczyzna urzędowa, zwrot grzecznościowy na początku, formuła „Z poważaniem” na końcu; '
        'powołuj przepisy bez publikatora (Dz.U.); brakujące dane oznacz [UZUPEŁNIĆ: ...]; nie wymyślaj faktów; '
        'zwykły tekst bez Markdown; zwróć wyłącznie treść pisma.'
    )
    tresc = f'DANE SPRAWY:\n{_cytat(dane_sprawy)}\n\nWNIOSEK:\n{_cytat(wniosek)}'
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': tresc}]

"""Podręcznik aplikacji – z niego Urzęduś odpowiada na pytania „do czego służy…”, „jak zrobić…”.

Typowe pytania dostają odpowiedź od razu (dopasowanie po słowach kluczowych), bez czekania na model.
Uwaga: przy zmianach w aplikacji zaktualizuj też ten opis.
"""

import re
from dataclasses import dataclass

from .tekst import normalizuj


@dataclass(frozen=True)
class Sekcja:
    tytul: str
    slowa: tuple[str, ...]  # rdzenie słów bez polskich znaków
    tekst: str


SEKCJE = (
    Sekcja('Wnioski', ('wnioski', 'lista', 'kalendarz', 'ekran glown', 'tabel', 'kolor', 'kafel', 'pilnos',
                       'rok', 'miesiac', 'filtr', 'termin'), (
        'Wnioski to ekran główny – kalendarz wniosków od najstarszych do najnowszych. Kolory pokazują pilność: '
        'czerwony – termin dziś albo już minął, pomarańczowy – termin w najbliższy dzień roboczy, żółty – do 3 dni '
        'roboczych, szary – odpowiedź wysłana. Terminy liczą się same: 14 dni od wpływu, a gdy wypadają w sobotę, '
        'niedzielę lub święto – przesuwają się na najbliższy dzień roboczy (ikonka „i” przy terminie). '
        'Możesz filtrować (pilne, w toku, kwerendy, wysłane), szukać po numerze, temacie i wnioskodawcy, wybrać rok '
        'i prowadzącego, a kliknięcie kafelka pokazuje te wnioski. Przełącznik „Miesiąc” pokazuje siatkę kalendarza '
        'z wnioskami w dniach terminu.'
    )),
    Sekcja('Statusy', ('status', 'etap', 'wyslan', 'kwerend', 'przedluz', 'edytuj', 'usun', 'przebieg',
                       'histori'), (
        'Status sprawy widać na kolorowym przycisku w nagłówku sprawy – kliknij, żeby go zmienić. Zmienia się też '
        'sam: po wgraniu odpowiedzi wydziału na „Zapytania wysłane do wydziałów”, po zapisaniu pisma na „Odpowiedź '
        'przygotowana”, a „Oznacz jako wysłane” w kroku Eksport zamyka sprawę z datą odpowiedzi. Menu „⋮” obok '
        'statusu pozwala edytować dane wniosku, ustawić kwerendę (nowy termin, najwyżej 2 miesiące od złożenia) '
        'albo usunąć wniosek. Każda zmiana trafia do „Przebiegu sprawy” w kroku Wniosek.'
    )),
    Sekcja('Nowy wniosek', ('nowy wniosek', 'nowego wniosku', 'dodac wniosek', 'dodaj wniosek', 'wgrac wniosek',
                            'wgrac plik', 'zarejestr', 'przeciagn'), (
        'Nowy wniosek: przeciągnij plik PDF albo Word na pole po lewej (albo kliknij je i wybierz plik). '
        'Aplikacja odczyta tekst, a Bielik sam zaproponuje skrócony opis, wydziały i oceni, czy potrzebna jest '
        'kwerenda. Uzupełnij wnioskodawcę, sprawdź dane i kliknij „Zatwierdź i dodaj do listy” – wniosek trafi '
        'do kalendarza, a plik do dokumentów sprawy.'
    )),
    Sekcja('Sprawa', ('sprawa', 'sprawy', 'krok', 'etap', 'stepper', 'wydzial', 'odpowiedzi wydzial',
                      'podobne sprawy'), (
        'Otwarta sprawa ma 7 kroków: 1. Wniosek – dane i treść wniosku; 2. Podobne sprawy z archiwum; '
        '3. Wydziały – propozycja Bielika i gotowa prośba do skopiowania; 4. Odpowiedzi wydziałów – tu wgrywasz '
        'pliki od wydziałów; 5. Projekt odpowiedzi; 6. Anonimizacja; 7. Eksport. Między krokami przechodzisz '
        'przyciskami „Dalej”/„Wstecz” albo klikając nazwę kroku. Praca w sprawie (projekt pisma, anonimizacja, '
        'kontrola jakości) zapisuje się automatycznie – po powrocie albo ponownym uruchomieniu aplikacji wszystko '
        'na Ciebie czeka.'
    )),
    Sekcja('Projekt odpowiedzi', ('projekt', 'generuj', 'pismo', 'zatrzymaj', 'uzupelnic'), (
        'Projekt odpowiedzi (krok 5): kliknij „Generuj projekt (Bielik)” – pismo powstaje na żywo na podstawie '
        'wniosku i odpowiedzi wydziałów, opcjonalnie ze wzorem z archiwum. Możesz je zatrzymać przyciskiem '
        '„Zatrzymaj” i dowolnie poprawić. Miejsca oznaczone [UZUPEŁNIĆ] wymagają Twoich danych. '
        'Projekt możesz też poprosić mnie w czacie i wstawić przyciskiem „Wstaw do projektu”.'
    )),
    Sekcja('Kontrola jakości', ('kontrol', 'sprawdz pism', 'sprawdzi pism', 'halucyn', 'kompletn', 'zielon',
                                'czerwon liczb'), (
        'Kontrola jakości jest w kroku „Projekt odpowiedzi” (przycisk „Sprawdź pismo”, uruchamia się też sama po '
        'wygenerowaniu pisma). Każda kwota, data i liczba w piśmie jest szukana we wniosku i odpowiedziach wydziałów: '
        'zielona ma źródło (najedź, żeby zobaczyć które), czerwona nie ma pokrycia – to może być błąd albo halucynacja AI. '
        'Kontrola wskazuje też pola [UZUPEŁNIĆ], nieukryte dane osobowe i braki w formie pisma, a Bielik sprawdza, '
        'czy pismo odpowiada na każde żądanie wnioskodawcy. Stan kontroli widać też w kroku „Eksport”.'
    )),
    Sekcja('Archiwum', ('archiwum', 'archiwaln', 'wyszukiw', 'szukaj', 'podobn'), (
        'Archiwum odpowiedzi służy do wyszukiwania podobnych spraw z poprzednich lat – żeby nie pisać odpowiedzi '
        'od zera, tylko skorzystać z tego, co urząd już kiedyś odpowiedział. Archiwalne odpowiedzi dodajesz w Bazie '
        'wiedzy (rodzaj „Archiwalna odpowiedź”), a w kroku „Projekt odpowiedzi” możesz wybrać jedną jako wzór. '
        'Uwaga: w obecnej wersji wyniki wyszukiwania w Archiwum są przykładowe – wyszukiwanie po znaczeniu jest '
        'w przygotowaniu.'
    )),
    Sekcja('Baza wiedzy', ('baza wiedzy', 'bazie wiedzy', 'baze wiedzy', 'ustaw', 'zarzadzen', 'dokument',
                           'uczy', 'wiedz'), (
        'Baza wiedzy to dokumenty, z których korzysta asystent: ustawy, zarządzenia i archiwalne odpowiedzi. '
        'Wybierz rodzaj dokumentów i przeciągnij pliki na pole – można wiele naraz, np. całe archiwum z roku. '
        'Powtórnie wgrane pliki są wykrywane i pomijane. Na liście możesz filtrować, podglądać odczytany tekst '
        'i usuwać dokumenty.'
    )),
    Sekcja('Anonimizacja', ('anonimiz', 'dane osobow', 'zaczern', 'ukry', 'rodo', 'maskow'), (
        'Anonimizacja (krok 6): kliknij „Wykryj dane osobowe” – Bielik wskaże dane osób prywatnych, a wzorce znajdą '
        'PESEL, telefony, e-maile i numery kont. Szare pola to propozycje; kliknięcie zaczernia fragment (ukryje go), '
        'ponowne kliknięcie odkrywa. Możesz zatwierdzić wszystko naraz albo dopisać własny fragment. '
        'W eksporcie zatwierdzone fragmenty zostaną zastąpione znakami ██████.'
    )),
    Sekcja('Eksport', ('eksport', 'wyeksport', 'zapisac', 'zapisz', 'docx', 'word', 'txt', 'pobrac', 'wyslan',
                       'folder'), (
        'Eksport (krok 7): „Zapisz .docx” albo „Zapisz .txt” zapisuje pismo z zamaskowanymi danymi osobowymi – '
        'w oknie aplikacji wybierasz miejsce zapisu, a kopia zostaje w dokumentach sprawy („Otwórz folder sprawy”). '
        'Aplikacja niczego nie wysyła – pismo wysyłasz sam.'
    )),
    Sekcja('Ustawienia', ('ustawien', 'konfigur', 'polaczen', 'adres', 'model', 'katalog', 'folder danych'), (
        'Ustawienia pokazują, z jakim modelem i pod jakim adresem łączy się aplikacja (przycisk „Sprawdź połączenie”), '
        'terminy ustawowe oraz folder, w którym lokalnie przechowywane są wszystkie dokumenty.'
    )),
    Sekcja('Bielik i bezpieczeństwo', ('bielik', 'lm studio', 'offline', 'lokaln', 'bezpiecz', 'internet', 'dane wychodz',
                                       'zielon', 'czerwon', 'niedostepn'), (
        'Asystent korzysta z modelu Bielik uruchomionego lokalnie w LM Studio – żaden dokument nie opuszcza tego '
        'komputera. Zielona etykieta w prawym górnym rogu oznacza, że Bielik działa; czerwona – że LM Studio jest '
        'wyłączone (aplikacja działa wtedy dalej, tylko bez podpowiedzi AI). Wszystkie pliki leżą lokalnie '
        'w folderze danych (patrz Ustawienia).'
    )),
    # Ogólny opis – na końcu, żeby przy remisie wygrywała konkretna sekcja („jak działa anonimizacja w aplikacji”).
    Sekcja('Aplikacja', ('aplikacj', 'program', 'narzedz', 'system', 'asystent udip'), (
        'Asystent UDIP pomaga obsługiwać wnioski o dostęp do informacji publicznej w Urzędzie Miasta Bydgoszczy. '
        'Prowadzi kalendarz wniosków z terminami (ekran Wnioski), odczytuje wgrane pliki PDF i Word, z pomocą '
        'lokalnego modelu Bielik proponuje wydziały i pisze projekt odpowiedzi, wskazuje dane osobowe '
        'do anonimizacji i zapisuje gotowe pismo do Worda. Ma też Bazę wiedzy (ustawy, zarządzenia, archiwalne '
        'odpowiedzi) i Archiwum do szukania podobnych spraw. Działa w całości na tym komputerze i niczego '
        'nie wysyła – decyzje zawsze podejmuje urzędnik.'
    )),
)


def znajdz_sekcje(pytanie: str) -> Sekcja | None:
    """Sekcja podręcznika najlepiej pasująca do pytania (po słowach kluczowych) albo None.

    Pierwsze dwa słowa sekcji (jej nazwa) ważą podwójnie – „jak wyeksportować dokument” to Eksport, nie Baza wiedzy.
    """
    tekst = normalizuj(pytanie)
    wyniki = [(sum((2 if i < 2 else 1) for i, slowo in enumerate(s.slowa)
                   if re.search(r'\b' + re.escape(slowo), tekst)), s) for s in SEKCJE]
    najlepszy_wynik = max(w for w, _ in wyniki)
    if najlepszy_wynik == 0:
        return None
    return next(s for w, s in wyniki if w == najlepszy_wynik)


CALY_PODRECZNIK = '\n'.join(f'{s.tytul}: {s.tekst}' for s in SEKCJE)

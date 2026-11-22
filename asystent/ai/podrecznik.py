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
        'z wnioskami w dniach terminu. Ikona pobierania obok wyboru roku eksportuje rejestr do Excela, a terminy '
        'spraw w toku – do kalendarza Outlooka (.ics, z przypomnieniem dzień wcześniej, bez danych osobowych).'
    )),
    Sekcja('Eksport rejestru', ('excel', 'rejestr', 'outlook', 'ics', 'kalendarz outlook', 'xlsx', 'sprawozdan'), (
        'Rejestr wniosków wyeksportujesz na ekranie Wnioski: ikona pobierania obok wyboru roku → „Rejestr do Excela” '
        '(numer, temat, wnioskodawca, daty, status, rodzaj sprawy, terminowość, wydziały) albo „Terminy do kalendarza '
        'Outlook” – plik .ics z terminami spraw w toku i przypomnieniem dzień wcześniej, bez danych osobowych.'
    )),
    Sekcja('Na dziś', ('na dzis', 'pulpit', 'statystyk', 'podsumowan', 'terminowos', 'sredni czas', 'w terminie'), (
        'Ekran „Na dziś” to pulpit: ile spraw jest w toku, co ma termin dziś lub jutro, co jest po terminie, '
        'na które sprawy czekamy od wydziałów, jaki odsetek odpowiedzi wysłano w terminie i średni czas odpowiedzi. '
        'Kliknięcie sprawy na liście ją otwiera. Wykres pokazuje wpływ wniosków w ostatnich 12 miesiącach.'
    )),
    Sekcja('Dziennik AI', ('dziennik', 'audyt', 'rozliczaln', 'kto zatwierdzil', 'historia ai', 'log'), (
        'Dziennik AI (menu po lewej) pokazuje, co zaproponował asystent i co zatwierdził urzędnik – kiedy i w której '
        'sprawie: analiza wniosku, dobór wydziałów, projekt pisma, kontrola jakości, propozycje danych osobowych, '
        'eksport pisma, anonimizacja pliku, czynności czatu. Zapisywane są tylko metadane – bez treści dokumentów '
        'i bez danych osobowych. Można filtrować po numerze sprawy.'
    )),
    Sekcja('Autopilot', ('autopilot', 'automatycz', 'samo', 'sam napisze'), (
        'Autopilot: gdy wgrasz odpowiedź wydziału, a projekt pisma jeszcze nie powstał, Bielik od razu pisze projekt, '
        'aplikacja robi kontrolę jakości i zaznacza dane osobowe do sprawdzenia w kroku „Anonimizacja”. Niczego nie '
        'ukrywa ani nie wysyła sam – wszystko zatwierdzasz Ty. Wyłączenie: zmienna UDIP_AUTOPILOT=0.'
    )),
    Sekcja('Statusy', ('status', 'etap', 'wyslan', 'kwerend', 'przedluz', 'zawiadom', 'edytuj', 'usun', 'przebieg',
                       'histori'), (
        'Status sprawy widać na kolorowym przycisku w nagłówku sprawy – kliknij, żeby go zmienić. Zmienia się też '
        'sam: po wgraniu odpowiedzi wydziału na „Zapytania wysłane do wydziałów”, po zapisaniu pisma na „Odpowiedź '
        'przygotowana”, a „Oznacz jako wysłane” w kroku Eksport zamyka sprawę z datą odpowiedzi. Menu „⋮” obok '
        'statusu pozwala edytować dane wniosku, ustawić kwerendę (nowy termin, najwyżej 2 miesiące od złożenia) '
        'albo usunąć wniosek. Po ustawieniu kwerendy asystent od razu proponuje zawiadomienie wnioskodawcy '
        'o przedłużeniu terminu (art. 13 ust. 2) – do poprawienia i zapisania jako .docx w sprawie; jest też '
        'w menu „⋮”. Każda zmiana trafia do „Przebiegu sprawy” w kroku Wniosek.'
    )),
    Sekcja('Nowy wniosek', ('nowy wniosek', 'nowego wniosku', 'dodac wniosek', 'dodaj wniosek', 'wgrac wniosek',
                            'ocr', 'skan', 'zdjec',
                            'wgrac plik', 'zarejestr', 'przeciagn'), (
        'Nowy wniosek: przeciągnij plik PDF, Word albo zdjęcie (JPG/PNG) na pole po lewej (albo kliknij je i wybierz '
        'plik). Skany i zdjęcia aplikacja odczyta OCR-em – sprawdź taki tekst z oryginałem, zwłaszcza pismo odręczne. '
        'Od razu dopasuje też wydziały z wykazu BIP, a Bielik zaproponuje skrócony opis, doprecyzuje wydziały '
        'i oceni, czy potrzebna jest kwerenda. Uzupełnij wnioskodawcę, sprawdź dane i kliknij „Zatwierdź i dodaj '
        'do listy” – wniosek trafi do kalendarza, a plik do dokumentów sprawy.'
    )),
    Sekcja('Sprawa', ('sprawa', 'sprawy', 'krok', 'etap', 'stepper', 'wydzial', 'odpowiedzi wydzial',
                      'podobne sprawy'), (
        'Otwarta sprawa ma 7 kroków: 1. Wniosek – dane i treść wniosku; 2. Podobne sprawy z archiwum; '
        '3. Wydziały – propozycja z wykazu wydziałów w BIP (możesz ją poprawić) i gotowa prośba do skopiowania; '
        '4. Odpowiedzi wydziałów – tu wgrywasz pliki od wydziałów; 5. Projekt odpowiedzi; 6. Anonimizacja; '
        '7. Eksport. Między krokami przechodzisz przyciskami „Dalej”/„Wstecz” albo klikając nazwę kroku. Praca w '
        'sprawie (projekt pisma, anonimizacja, '
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
        'zielona ma źródło (najedź, żeby zobaczyć które), czerwona nie ma pokrycia – to może być błąd albo halucynacja '
        'AI. '
        'Kontrola wskazuje też pola [UZUPEŁNIĆ], nieukryte dane osobowe i braki w formie pisma, a Bielik sprawdza, '
        'czy pismo odpowiada na każde żądanie wnioskodawcy. Stan kontroli widać też w kroku „Eksport”.'
    )),
    Sekcja('Archiwum', ('archiwum', 'archiwaln', 'wyszukiw', 'szukaj', 'podobn'), (
        'Archiwum odpowiedzi służy do wyszukiwania podobnych spraw – żeby nie pisać odpowiedzi od zera, tylko '
        'skorzystać z tego, co urząd już kiedyś odpowiedział. Szuka w archiwalnych odpowiedziach z Bazy wiedzy '
        'i we wnioskach z rejestru z ostatniego roku, po wspólnych słowach i po znaczeniu; trafność widać w '
        'procentach. '
        'W sprawie podobne sprawy szukają się same (krok 2), a najlepsza archiwalna odpowiedź od razu trafia jako wzór '
        'do kroku „Projekt odpowiedzi” – możesz go zmienić. Na ekranie Archiwum wpisz temat albo fragment wniosku.'
    )),
    Sekcja('Rodzaj sprawy', ('rodzaj sprawy', 'rodzaj', 'klasyfik', 'sklasyfik', 'przetworzon', 'sciezk', 'bip',
                             'nie jest informacj', 'interes publiczn', 'odmow', 'inny tryb'), (
        'Rodzaj sprawy (krok 1 sprawy, także przy rejestracji wniosku) to klasyfikacja wniosku: zwykła informacja '
        'publiczna, informacja przetworzona, informacja dostępna w BIP, to nie jest informacja publiczna, inny tryb '
        'dostępu albo wniosek do doprecyzowania. Podpowiada go Bielik (a gdy nie odpowie – reguły), Ty zatwierdzasz. '
        'Przy każdym rodzaju widać ścieżkę postępowania z podstawą prawną, a „Generuj projekt” pisze właściwe pismo – '
        'np. przy informacji przetworzonej wezwanie do wykazania szczególnie istotnego interesu publicznego.'
    )),
    Sekcja('Anonimizacja pliku', ('anonimizacja pliku', 'anonimizowac plik', 'zanonimizowac plik', 'czarne pol',
                                  'dowolny plik', 'zaczernic plik', 'pdf'), (
        'Anonimizacja pliku (menu po lewej) działa na dowolnym dokumencie: przeciągnij PDF (także skan), Word, TXT '
        'albo zdjęcie. Dane osobowe są zaznaczane od razu – także bez Bielika (imiona i nazwiska w odmianie, adresy, '
        'kody pocztowe, PESEL, telefony, e-maile, NIP, daty urodzenia). Zatwierdź, co ukryć, i kliknij „Utwórz '
        'zanonimizowany plik” – powstanie plik w tym samym formacie z czarnymi polami; dane są z niego usuwane, a nie '
        'tylko zakrywane, i aplikacja sprawdza to, odczytując plik ponownie. Sekcja „Wiele plików naraz” anonimizuje '
        'cały folder (wszystkie dane wykryte wzorcami, bez przeglądu) i pozwala zapisać wynik jako ZIP.'
    )),
    Sekcja('Baza wiedzy', ('baza wiedzy', 'bazie wiedzy', 'baze wiedzy', 'ustaw', 'zarzadzen', 'dokument',
                           'uczy', 'wiedz'), (
        'Baza wiedzy to dokumenty, z których korzysta asystent: ustawy, zarządzenia i archiwalne odpowiedzi. '
        'Wybierz rodzaj dokumentów i przeciągnij pliki na pole – można wiele naraz, np. całe archiwum z roku. '
        'Powtórnie wgrane pliki są wykrywane i pomijane. Na liście możesz filtrować, podglądać odczytany tekst '
        'i usuwać dokumenty.'
    )),
    Sekcja('Anonimizacja', ('anonimiz', 'dane osobow', 'zaczern', 'ukry', 'rodo', 'maskow'), (
        'Anonimizacja (krok 6): kliknij „Wykryj dane osobowe” – od razu, bez AI, zaznaczą się imiona i nazwiska, '
        'adresy, PESEL, telefony, e-maile i numery kont, a Bielik dołoży to, czego wzorce nie złapały. Dowolny plik '
        'zanonimizujesz na ekranie „Anonimizacja pliku”. Szare pola to propozycje; kliknięcie zaczernia fragment '
        '(ukryje go), '
        'ponowne kliknięcie odkrywa. Możesz zatwierdzić wszystko naraz albo dopisać własny fragment. '
        'W eksporcie zatwierdzone fragmenty zostaną zastąpione znakami ██████.'
    )),
    Sekcja('Eksport', ('eksport', 'wyeksport', 'zapisac', 'zapisz', 'docx', 'word', 'txt', 'pobrac', 'wyslan',
                       'folder'), (
        'Eksport (krok 7): „Zapisz .docx” albo „Zapisz .txt” zapisuje pismo z zamaskowanymi danymi osobowymi – '
        'w oknie aplikacji wybierasz miejsce zapisu, a kopia zostaje w dokumentach sprawy („Otwórz folder sprawy”). '
        'Aplikacja niczego nie wysyła – pismo wysyłasz sam.'
    )),
    Sekcja('Ustawienia', ('ustawien', 'konfigur', 'polaczen', 'adres', 'model', 'katalog', 'folder danych',
                          'demo', 'dane testow', 'pokaz'), (
        'Ustawienia pokazują, z jakim modelem i pod jakim adresem łączy się aplikacja (przycisk „Sprawdź połączenie”), '
        'terminy ustawowe oraz folder, w którym lokalnie przechowywane są wszystkie dokumenty. Przycisk „Wczytaj dane '
        'demonstracyjne” przygotowuje pokaz: 10 wniosków testowych w kalendarzu i archiwum przykładowych odpowiedzi.'
    )),
    Sekcja('Bielik i bezpieczeństwo', ('bielik', 'lm studio', 'offline', 'lokaln', 'bezpiecz', 'internet', 'dane '
                                                                                                           'wychodz',
                                       'zielon', 'czerwon', 'niedostepn'), (
        'Asystent korzysta z modelu Bielik uruchomionego lokalnie w LM Studio – żaden dokument nie opuszcza tego '
        'komputera. Zielona etykieta w prawym górnym rogu oznacza, że Bielik działa; czerwona – że LM Studio jest '
        'wyłączone (aplikacja działa wtedy dalej, tylko bez podpowiedzi AI). Wszystkie pliki leżą lokalnie '
        'w folderze danych (patrz Ustawienia).'
    )),
    # Ogólny opis – na końcu, żeby przy remisie wygrywała konkretna sekcja („jak działa anonimizacja w aplikacji”).
    Sekcja('Aplikacja', ('aplikacj', 'program', 'narzedz', 'system', 'cyfrowy ratusz', 'asystent udip'), (
        'Cyfrowy Ratusz pomaga obsługiwać wnioski o dostęp do informacji publicznej w Urzędzie Miasta Bydgoszczy. '
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

# HackNation-inteligetny-asystent-urz-dnika-
HackNation 2026 – Inteligentny asystent urzędnika (wnioski UDIP, UM Bydgoszcz)

## Uruchomienie

Najprościej: dwuklik na `uruchom.bat`. Za pierwszym razem tworzy środowisko `.venv`
i instaluje biblioteki (a potem doinstalowuje je, gdy zmieni się `requirements.txt`), następnie otwiera aplikację w oknie.

- `uruchom.bat` – aplikacja desktopowa (własne okno Windows, działa lokalnie)
- `uruchom.bat --web` – to samo w przeglądarce na http://127.0.0.1:8080 (wygodne do debugowania)

**VS Code:** biblioteki są tylko w `.venv`, nie w globalnym Pythonie. Otwórz w VS Code
folder repozytorium (nie folder nad nim) albo wybierz interpreter ręcznie:
`Ctrl+Shift+P` → *Python: Select Interpreter* → `.venv\Scripts\python.exe`.

## Struktura

```
GUI.py                    punkt startowy
program2.py               dobór wydziałów (ranking słów + Bielik) – działa też samodzielnie z terminala
wydzialy.md               wykaz wydziałów UM Bydgoszczy z BIP: zadania, rejestry
asystent/
  konfiguracja.py         ścieżki, limity, terminy
  rejestr.py              kalendarz wniosków: terminy, statusy, kwerenda, historia (zapis w JSON)
  terminy.py              dni robocze, święta, liczenie terminów wg art. 57 KPA
  uslugi.py               wspólne instancje (magazyn plików, klient Bielika, archiwum)
  archiwum.py             wyszukiwanie podobnych spraw: słowa (TF-IDF) + znaczenie (embeddingi), indeks wektorów
  klasyfikacja.py         rodzaj sprawy i ścieżka postępowania (zwykła, przetworzona, w BIP, …)
  anonimizacja.py         dane osobowe bez AI (imiona i nazwiska, adresy, PESEL…), podział tekstu, maskowanie
  kontrola.py             kontrola jakości pisma bez AI (liczby, daty, forma)
  stan_sprawy.py          autozapis pracy w sprawie (stan.json w katalogu sprawy)
  ai/
    bielik_service.py     asynchroniczny klient LM Studio (analiza, dane osobowe, stream pisma)
    urzedus.py            czat Urzęduś: rozpoznawanie poleceń, regulacje zakresu, czynności
    wydzialy.py           podłączenie program2.py do aplikacji (lista z BIP, dobór w tle)
    prompty.py            prompty modułów AI – do strojenia bez ruszania logiki
    prompty_czatu.py      prompty i ściąga z ustawy dla Urzędusia
  pliki/                  obsługa plików – bez zależności od GUI
    walidacja.py          typ, rozmiar, sygnatura pliku, bezpieczna nazwa
    ekstrakcja.py         tekst z PDF / DOCX / DOC / TXT / zdjęć (OCR)
    ocr.py                OCR Windows (polski, offline), położenie słów do zaczerniania
    anonimizacja_pliku.py zanonimizowany plik w tym samym formacie (czarne pola) + kontrola wyniku
    magazyn.py            lokalne przechowywanie dokumentów + metadane
    eksport.py            zapis pisma do .docx / .txt
  gui/
    aplikacja.py          układ okna, menu, routing
    czat.py               panel czatu Urzęduś
    kontekst.py           która sprawa jest otwarta w danym oknie
    komponenty.py         pole „przeciągnij i upuść”, karta pliku, …
    strony/               jeden moduł na ekran
tests/                    testy (pytest)
```

## Asystent AI – lokalny Bielik

Aplikacja korzysta z modelu **Bielik 4.5B v3.0 Instruct** uruchomionego w **LM Studio** na tym komputerze
(serwer API zgodny z OpenAI). Żaden tekst nie wychodzi poza komputer.

1. W LM Studio załaduj `bielik-4.5b-v3.0-instruct` (Context Length: 3072) i włącz *Local Server* na porcie **1235**.
2. Uruchom aplikację – w nagłówku pojawi się zielone „Bielik lokalnie · offline”.

Co robi Bielik:
- **Nowy wniosek** – po wgraniu pliku sam proponuje skrócony opis, wydziały, rodzaj sprawy i ocenę, czy potrzebna
  jest kwerenda.
- **Sprawa → Wydziały** – propozycja wydziałów z uzasadnieniem; listę można poprawić ręcznie (wykaz z BIP).
- **Sprawa → Projekt odpowiedzi** – pisze projekt pisma na żywo (stream) na podstawie wniosku, odpowiedzi
  wydziałów i opcjonalnego wzoru z archiwum.
- **Sprawa → Anonimizacja** – wskazuje dane osób prywatnych (bez urzędników pełniących funkcje publiczne);
  dodatkowo PESEL, telefony, e-maile i numery kont wykrywane są wzorcami. Urzędnik zatwierdza, eksport je maskuje.

### Podobne sprawy (Archiwum)

Krok „Podobne sprawy” szuka sam po otwarciu sprawy, ekran Archiwum – po wpisaniu tematu. Przeszukiwane są archiwalne
odpowiedzi z Bazy wiedzy i wnioski z rejestru z ostatniego roku. Trafność (%) łączy:
- **wspólne słowa** – rdzenie słów ważone rzadkością (TF-IDF), bez urzędowych formułek; działa bez LM Studio,
- **znaczenie** – embeddingi z LM Studio (`UDIP_EMBED_MODEL`, domyślnie wbudowany nomic-embed). Nomic słabo zna
  polski, więc ma wagę 25%; model wielojęzyczny (np. **bge-m3**) dostaje 50% i wyraźnie poprawia wyniki.
Wektory dokumentów liczą się raz (`dane/indeks_archiwum.json`, także w tle po wgraniu archiwum do Bazy wiedzy).
Najlepsza archiwalna odpowiedź (od 40%) trafia automatycznie jako wzór do „Projektu odpowiedzi”.
Archiwum testowe (11 fikcyjnych, zanonimizowanych odpowiedzi): `dane_testowe/archiwum/` – wgraj je w Bazie wiedzy.

### Rodzaj sprawy (klasyfikacja)

Bielik przy analizie wniosku wskazuje rodzaj z zamkniętej listy; gdy odpowie „zwykła”, a reguły wyraźnie widzą
inny rodzaj (np. „w mojej sprawie”, „wszystkich umów z lat…”), wygrywają reguły. Urzędnik zatwierdza (krok 1 sprawy).

| Rodzaj | Ścieżka | Pismo z „Generuj projekt” |
|---|---|---|
| Informacja publiczna | odpowiedź w 14 dni (art. 13) | odpowiedź z danymi od wydziałów |
| Informacja przetworzona | art. 3 ust. 1 pkt 1, ew. decyzja (art. 16) | wezwanie do wykazania szczególnie istotnego interesu publicznego |
| Informacja w BIP | art. 10 ust. 1 | pismo wskazujące BIP |
| To nie jest informacja publiczna | zwykłe pismo, bez decyzji | pismo informujące |
| Inny tryb dostępu | art. 1 ust. 2 (np. akta – KPA) | pismo o właściwym trybie |
| Do doprecyzowania | termin biegnie od doprecyzowania | wezwanie do doprecyzowania |

### Anonimizacja pliku (J3)

Ekran **Anonimizacja pliku**: przeciągnij PDF (także skan), Word, TXT albo zdjęcie → dane osobowe zaznaczają się od razu
bez AI (imiona i nazwiska w odmianie, adresy, kody pocztowe, PESEL, telefony, e-maile, NIP, REGON, daty urodzenia),
Bielik dokłada resztę → urzędnik zatwierdza → **plik w tym samym formacie z czarnymi polami**:
- PDF z tekstem – redakcja PyMuPDF (tekst pod polem jest usuwany z pliku, metadane czyszczone),
- skan PDF i zdjęcie – czarne prostokąty w miejscach słów wskazanych przez OCR (zdjęcie zapisywane jako PNG bez EXIF),
- Word – maska w akapitach, tabelach, nagłówkach i stopkach; TXT – maska.
Na koniec plik wynikowy jest odczytywany ponownie (także OCR-em) i aplikacja potwierdza, że ukrytych danych w nim nie ma.

### Dobór wydziałów (lista z BIP)

Wykaz 19 wydziałów z zadaniami i rejestrami jest w `wydzialy.md`, algorytm w `program2.py`:
1. **ranking słów** – słowa kluczowe wydziałów + podobieństwo wniosku do opisu zadań (działa bez modelu,
   od razu po wgraniu pliku); pytania o koszty trafiają też do Wydziału Zarządzania Budżetem Miasta,
2. **Bielik wybiera** spośród 6 najlepszych kandydatów i podaje uzasadnienie; lider rankingu z wyraźnymi
   słowami kluczowymi nie zostanie pominięty,
3. gdy LM Studio jest wyłączone – zostaje wynik rankingu.

Z terminala (np. do strojenia słów kluczowych): `.venv\Scripts\python program2.py <plik lub folder> [--bez-llm]`
(PDF w tym trybie wymaga `pip install pymupdf`; aplikacja czyta pliki sama i go nie potrzebuje).

### Kontrola jakości pisma (przeciw błędom i halucynacjom AI)

W kroku „Projekt odpowiedzi” przycisk **Sprawdź pismo** (uruchamia się też sam po wygenerowaniu pisma):
- **liczby i daty** – każda wartość w piśmie jest szukana we wniosku i odpowiedziach wydziałów: zielona ma źródło
  (podpowiedź pokazuje które), czerwona nie ma pokrycia; różne zapisy tej samej wartości są rozpoznawane
  (1 240 000 = 1.240.000, 20.11.2026 = 20 listopada 2026); odwołania do przepisów są pomijane,
- **pominięte dane** – wartości z odpowiedzi wydziałów, których nie ma w piśmie (np. zgubiona kampania),
- **forma** – pola [UZUPEŁNIĆ], brak podstawy prawnej, zwrotu grzecznościowego, „Z poważaniem”, resztki Markdown,
  nieukryte dane osobowe,
- **kompletność (Bielik)** – czy pismo odpowiada na każde żądanie z wniosku; żądanie liczy się jako spełnione tylko,
  gdy model zacytuje fragment pisma, który naprawdę w nim jest.

Wynik kontroli widać też w kroku „Eksport”, a Urzęduś robi to samo na polecenie „Sprawdź pismo”.
Kod: `asystent/kontrola.py` (bez AI) i `BielikService.sprawdz_kompletnosc`.

### Urzęduś – czat asystenta

Przycisk **Urzęduś** w nagłówku otwiera panel czatu. Urzęduś wie, która sprawa jest otwarta, i pracuje na jej
dokumentach: streszcza wniosek, odpowiada na pytania o dokumenty, proponuje wydziały, pisze prośby do wydziałów,
zawiadomienia o przedłużeniu terminu, prośby o doprecyzowanie i projekt odpowiedzi, szuka danych osobowych,
pokazuje pilne terminy i wyjaśnia przepisy UDIP. Odpowiada też na pytania o samą aplikację („do czego służy
Archiwum?”) – z wbudowanego podręcznika (`asystent/ai/podrecznik.py`, aktualizuj go przy zmianach w aplikacji) –
oraz o siebie i swój zakres obowiązków. Wyniki trafiają do sprawy dopiero po kliknięciu urzędnika
(„Wstaw do projektu”, „Zapisz w sprawie”, „Oznacz w anonimizacji”).

Regulacje – Urzęduś zajmuje się wyłącznie wnioskami UDIP, pilnowane warstwowo:
1. prośby o kod, rozrywkę i próby obejścia zasad są odrzucane od razu, bez pytania modelu;
2. polecenie trafia do jednej z zamkniętej listy czynności (słowa kluczowe, a w razie wątpliwości klasyfikator Bielika);
3. każdy prompt zawiera reguły zakresu, a dokumenty są podawane jako dane, nie polecenia;
4. odpowiedź z kodem jest przerywana; o przepisach – pokazywana tylko z podstawą prawną (art.);
   o sprawie – tylko gdy opiera się na jej dokumentach.

Gdy LM Studio jest wyłączone, aplikacja działa dalej – pola wypełnia się ręcznie, a anonimizacja korzysta z wzorców.
Ustawienia przez zmienne środowiskowe: `UDIP_LLM_URL` (domyślnie `http://localhost:1235/v1`), `UDIP_LLM_MODEL`,
`UDIP_LLM_LIMIT_ZNAKOW` (domyślnie 6000; klient sam zmniejsza limit, jeśli okno kontekstu modelu jest mniejsze).

## Obsługa plików

- Wnioski, odpowiedzi wydziałów i dokumenty bazy wiedzy wgrywa się **przeciągając plik na pole** (albo klikając je).
- Obsługiwane: PDF, DOCX, DOC (wymaga LibreOffice), TXT, zdjęcia JPG/PNG; do 25 MB.
- Każdy plik jest sprawdzany (rozszerzenie **i** zawartość), a jego tekst odczytywany lokalnie.
  PDF-y z hasłem są odrzucane z czytelnym komunikatem.
- **OCR** (`asystent/pliki/ocr.py`): skany PDF (strony bez tekstu), zdjęcia JPG/PNG i Wordy z wklejonym zdjęciem
  kartki są odczytywane silnikiem OCR wbudowanym w Windows (język polski, offline, ok. 1 s na stronę) –
  to samo podejście co w `program2.py`. Tekst z OCR dostaje ostrzeżenie „sprawdź z oryginałem”.
  Druk i skany pism czyta bardzo dobrze, **pismo odręczne – słabo**.
  Wymaga polskiego pakietu OCR w Windows (jest w polskim Windows; inaczej: Ustawienia → Czas i język → Język →
  polski → Opcje języka → Rozpoznawanie tekstu). Bez niego aplikacja działa, a skan dostaje tylko ostrzeżenie.
- Dane leżą wyłącznie na tym komputerze, w folderze `dane/` (poza gitem). Inny folder: zmienna `UDIP_KATALOG_DANYCH`.

```
dane/
  przychodzace/                   wgrane, niezatwierdzone wnioski
  sprawy/<nr>/wniosek|odpowiedzi|eksport/
  sprawy/<nr>/stan.json           projekt pisma, anonimizacja, wynik kontroli (autozapis)
  baza_wiedzy/ustawy|zarzadzenia|archiwum/
  rejestr_wnioskow.json
```

## Testy

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

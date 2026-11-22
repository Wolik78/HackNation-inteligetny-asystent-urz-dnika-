# Cyfrowy Ratusz

**Lokalny asystent urzędnika do obsługi wniosków o dostęp do informacji publicznej**
HackNation 2026 · wyzwanie Urzędu Miasta Bydgoszczy

Asystent prowadzi wniosek od wpływu do wysłania odpowiedzi:
- pilnuje terminów,
- odczytuje dokumenty, także skany,
- znajduje podobne sprawy z archiwum,
- dobiera wydziały,
- pisze projekt pisma,
- sprawdza go pod kątem błędów,
- anonimizuje dane osobowe.

Działa **w całości na komputerze urzędnika**: model językowy Bielik uruchomiony jest lokalnie w LM Studio, a żaden dokument nie opuszcza urzędu. Każdą decyzję podejmuje urzędnik, asystent tylko podpowiada.

## Testy jury – gdzie je znaleźć

| Test | Co sprawdza | Gdzie w aplikacji |
|---|---|---|
| J1 | podobne sprawy w archiwum | sprawa → krok **Podobne sprawy** (szuka sam) · ekran **Archiwum** |
| J2 | przygotowanie pisma | sprawa → **Projekt odpowiedzi** (pismo na żywo, właściwe dla rodzaju sprawy) + **kontrola jakości** |
| J3 | anonimizacja pliku z danymi osobowymi | ekran **Anonimizacja pliku** (PDF, skan, Word, TXT, zdjęcie → plik z czarnymi polami) |
| J4 | łatwość obsługi | przeciąganie plików, podpowiedzi zamiast formularzy, czat **Urzęduś**, autozapis |
| J5 | kalendarz i etapy sprawy | ekran **Wnioski** (kolory terminów, widok miesiąca, statusy, kwerenda, przebieg sprawy) |
| J6 | wgrywanie ustaw i archiwów | ekran **Baza wiedzy** (wiele plików naraz, wykrywanie duplikatów) |

Pliki do sprawdzenia: [`dane_testowe/`](dane_testowe/README.md). Wszystkie są fikcyjne, a w folderze `anonimizacja/` leży wniosek z danymi osobowymi wszystkich typów, w wersji z tekstem i jako skan.

## Szybki start

**Wymagania:**
- Windows 10/11 z polskim pakietem OCR (jest w polskim Windows),
- Python 3.11+,
- [LM Studio](https://lmstudio.ai).

**LM Studio:**
1. Pobierz model `bielik-4.5b-v3.0-instruct` (wersja **Q4_K_M** mieści się w 4 GB VRAM).
2. Ustaw Context Length na **3072**.
3. Włącz *Local Server* na porcie **1235**.
4. Wbudowany `nomic-embed` wystarczy do wyszukiwania. Wielojęzyczny **bge-m3** wyraźnie poprawia trafność archiwum (zmienna `UDIP_EMBED_MODEL`).

**Aplikacja:**
1. Kliknij dwukrotnie `uruchom.bat`. Za pierwszym razem plik tworzy środowisko `.venv` i instaluje biblioteki.
   - `uruchom.bat --web` otwiera to samo w przeglądarce na http://127.0.0.1:8080.
2. Wejdź w **Ustawienia → Wczytaj dane demonstracyjne**. To dodaje 10 wniosków w kalendarzu i 11 archiwalnych odpowiedzi.
3. Gdy w nagłówku widać zielone „Bielik lokalnie · offline”, AI jest gotowe.

Bez LM Studio aplikacja też działa. Wyszukiwanie, dobór wydziałów, klasyfikacja i anonimizacja mają wtedy tryb bez AI, a pola wypełnia się ręcznie.

**Bez Pythona:**
- `zbuduj_exe.bat` tworzy folder `dist\CyfrowyRatusz` z plikiem `CyfrowyRatusz.exe` (około 210 MB).
- Folder wystarczy skopiować na inny komputer z Windows 10/11. Dane urzędu trafiają do `dane\` obok pliku `.exe`.

## Funkcje

### Kalendarz wniosków i pulpit „Na dziś”
- Terminy liczone automatycznie:
  - 14 dni (art. 13 ust. 1 UDIP),
  - kwerenda do 2 miesięcy (art. 13 ust. 2),
  - przesunięcie z weekendu i święta na dzień roboczy (art. 57 § 4 KPA), łącznie z ruchomymi świętami.
- Kolory pilności, filtry, wyszukiwarka, wybór roku i prowadzącego, widok miesiąca.
- Statusy zmieniają się same na kolejnych etapach. Każda zmiana trafia do przebiegu sprawy.
- **Na dziś:** sprawy po terminie, na dziś i jutro, czekające na wydziały, odsetek odpowiedzi w terminie, średni czas odpowiedzi, wpływ wniosków z 12 miesięcy.
- **Eksport:** rejestr do Excela (.xlsx) i terminy do kalendarza Outlooka (.ics, z przypomnieniem, bez danych osobowych).
- **Kwerenda:** po przedłużeniu terminu asystent od razu pisze zawiadomienie wnioskodawcy (art. 13 ust. 2).

### Sprawa krok po kroku
Przy rejestracji wniosku dane wnioskodawcy (imię i nazwisko albo organizacja, e-mail lub adres) wpisują się same z treści pliku. Bielik proponuje opis, rodzaj sprawy, wydziały i kwerendę.

1. **Wniosek:**
   - dane wniosku,
   - **rodzaj sprawy** ze ścieżką postępowania: zwykła, przetworzona, w BIP, nie jest informacją publiczną, inny tryb, do doprecyzowania.
2. **Podobne sprawy:** archiwalne odpowiedzi i wnioski z ostatniego roku, z procentem trafności. Najlepsza odpowiedź trafia jako wzór pisma.
3. **Wydziały:** dobór z wykazu 19 wydziałów z BIP, czyli ranking słów kluczowych plus wybór Bielika z uzasadnieniem. Do tego gotowa prośba do wydziału.
4. **Odpowiedzi wydziałów:** wgrywanie plików od wydziałów.
5. **Projekt odpowiedzi:**
   - Bielik pisze pismo na żywo, a jego rodzaj zależy od rodzaju sprawy (np. wezwanie przy informacji przetworzonej),
   - **kontrola jakości**: każda liczba i data musi mieć źródło w dokumentach, sprawdzana jest forma pisma i odpowiedź na każde żądanie wniosku.
6. **Anonimizacja:** propozycje danych osobowych. Urzędnik je zatwierdza, eksport je maskuje.
7. **Eksport:** zapis do `.docx` lub `.txt` i „Oznacz jako wysłane”. Aplikacja niczego sama nie wysyła.

**Autopilot:** po wgraniu odpowiedzi wydziału, gdy projektu jeszcze nie ma, Bielik od razu pisze projekt pisma, a aplikacja robi kontrolę jakości i zaznacza dane osobowe do sprawdzenia. Urzędnik tylko przegląda i zatwierdza (wyłączenie: `UDIP_AUTOPILOT=0`).

### Anonimizacja pliku (J3)
- Dane osobowe wykrywane są **bez AI**:
  - imiona i nazwiska w odmianie,
  - adresy i kody pocztowe,
  - PESEL, dowód osobisty, numer konta, NIP, REGON,
  - telefony, e-maile, daty urodzenia.
- Bielik dokłada to, czego wzorce nie złapały.
- Wynik to **plik w tym samym formacie**:
  - PDF: tekst pod czarnym polem jest usuwany z pliku, a metadane czyszczone,
  - skan i zdjęcie: zamalowane piksele w miejscach wskazanych przez OCR,
  - Word: maska w treści, tabelach, nagłówkach i stopkach.
- Na koniec aplikacja odczytuje plik wynikowy ponownie, także OCR-em, i potwierdza, że ukrytych danych w nim nie ma.
- **Wiele plików naraz** (np. archiwum przed publikacją): wszystkie dane wykryte wzorcami są ukrywane od razu, każdy plik przechodzi kontrolę, całość można zapisać jako ZIP.

### Dokumenty i OCR
- Obsługiwane formaty: PDF, DOCX, DOC (przez LibreOffice), TXT, JPG, PNG, do 25 MB.
- Każdy plik jest sprawdzany po rozszerzeniu i po zawartości.
- Skany, zdjęcia i Wordy z wklejonym zdjęciem odczytuje OCR wbudowany w Windows: po polsku, offline, około 1 s na stronę. Tekst z OCR jest oznaczony do sprawdzenia, bo pismo odręczne OCR czyta słabo.

### Urzęduś – czat asystenta
- Pracuje na otwartej sprawie:
  - streszcza wniosek i odpowiada na pytania o dokumenty,
  - proponuje wydziały,
  - pisze prośby, zawiadomienia i wezwania,
  - sprawdza pismo,
  - szuka podobnych spraw w archiwum („znajdź podobne sprawy o wycince drzew”).
- Zna przepisy UDIP i odpowiada na pytania o samą aplikację.
- Zakres jest pilnowany warstwowo:
  - prośby spoza tematu są odrzucane bez pytania modelu,
  - polecenia trafiają do zamkniętej listy czynności,
  - odpowiedzi o przepisach muszą mieć podstawę prawną,
  - odpowiedzi o sprawie muszą opierać się na jej dokumentach.

## Bezpieczeństwo i RODO
- **Offline:** model działa lokalnie (LM Studio), a aplikacja łączy się tylko z `localhost`.
- **Dane** leżą wyłącznie w folderze `dane/`, który jest poza gitem. Można go przenieść, np. na zaszyfrowany dysk: zmienna `UDIP_KATALOG_DANYCH`.
- **Człowiek decyduje:** propozycje AI są oznaczone i trafiają do sprawy dopiero po zatwierdzeniu.
- **Dziennik działań AI** (rozliczalność): co zaproponował asystent, co zatwierdził urzędnik i kiedy. Zapisywane są tylko metadane, bez treści dokumentów i danych osobowych.
- **Pliki** są sprawdzane po sygnaturze, ze zwalidowaną nazwą i z ochroną przed „zip bombą” w DOCX.
- **Anonimizacja** usuwa dane z pliku, a nie tylko je zakrywa. Czyści też metadane: autora PDF i Worda oraz EXIF zdjęć.

## Struktura

```
main.py                     punkt startowy (uruchom.bat → .venv → main.py)
asystent/
  konfiguracja.py           ścieżki, limity, model AI (zmienne UDIP_*)
  rejestr.py                kalendarz wniosków: terminy, statusy, kwerenda, rodzaj sprawy, historia
  terminy.py                dni robocze, święta, terminy wg art. 57 KPA
  archiwum.py               podobne sprawy: wspólne słowa (TF-IDF) + znaczenie (embeddingi), indeks wektorów
  klasyfikacja.py           rodzaje spraw, ścieżki postępowania, reguły
  anonimizacja.py           wykrywanie danych osobowych bez AI, maskowanie
  kontrola.py               kontrola jakości pisma bez AI (liczby, daty, forma)
  stan_sprawy.py            autozapis pracy w sprawie
  wnioskodawca.py           dane wnioskodawcy z treści wniosku (bez AI)
  statystyki.py             pulpit „Na dziś”: pilne sprawy, terminowość, średni czas odpowiedzi
  eksport_rejestru.py       rejestr do Excela, terminy do kalendarza (.ics)
  dziennik.py               dziennik działań AI (tylko metadane)
  demo.py                   dane demonstracyjne jednym kliknięciem
  uslugi.py                 wspólne instancje usług
  ai/
    bielik_service.py       asynchroniczny klient LM Studio (analiza, pisma, dane osobowe, embeddingi)
    dobor_wydzialow.py      algorytm doboru wydziałów (ranking + Bielik); działa też z terminala
    wydzialy.py             dobór wydziałów w aplikacji (wynik dla GUI i czatu, praca w tle)
    urzedus.py              czat Urzęduś: rozpoznawanie poleceń, regulacje zakresu, czynności
    podrecznik.py           podręcznik aplikacji, z którego odpowiada Urzęduś
    prompty.py, prompty_czatu.py
  pliki/                    obsługa plików – bez zależności od GUI
    walidacja.py            typ, rozmiar, sygnatura, bezpieczna nazwa
    ekstrakcja.py           tekst z PDF / DOCX / DOC / TXT / zdjęć
    ocr.py                  OCR Windows z położeniem słów
    anonimizacja_pliku.py   plik z czarnymi polami w tym samym formacie + kontrola wyniku
    magazyn.py, eksport.py  lokalny magazyn dokumentów, zapis pism
  gui/                      interfejs (NiceGUI): aplikacja, czat, komponenty, strony/ – jeden moduł na ekran
  zasoby/wydzialy.md        wykaz wydziałów UM Bydgoszczy z BIP (zadania, rejestry)
dane_testowe/               fikcyjne dokumenty do pokazu i testów
narzedzia/zbuduj_exe.py     budowanie wersji .exe (uruchamiane przez zbuduj_exe.bat)
docs/TODO.md                plan prac
tests/                      testy automatyczne (pytest)
```

Dobór wydziałów z terminala, np. do strojenia słów kluczowych:

```powershell
.venv\Scripts\python -m asystent.ai.dobor_wydzialow dane_testowe\wnioski --bez-llm
```

## Konfiguracja (zmienne środowiskowe)

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `UDIP_KATALOG_DANYCH` | `dane/` | folder z dokumentami, rejestrem i indeksem |
| `UDIP_LLM_URL` | `http://localhost:1235/v1` | adres serwera LM Studio |
| `UDIP_LLM_MODEL` | `bielik-4.5b-v3.0-instruct` | model językowy |
| `UDIP_LLM_LIMIT_ZNAKOW` | `6000` | najwięcej tekstu w jednym zapytaniu (zmniejszany do okna kontekstu) |
| `UDIP_EMBED_MODEL` | `text-embedding-nomic-embed-text-v1.5` | model wyszukiwania podobnych spraw |
| `UDIP_AUTOPILOT` | `1` | `0` wyłącza autopilota (projekt pisma po wgraniu odpowiedzi wydziału) |

## Testy i jakość kodu

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check .
```

Testy działają bez LM Studio, bo serwer modelu jest podstawiany. Testy OCR są pomijane, gdy w systemie nie ma polskiego pakietu OCR.

## Technologie

Python 3.11, NiceGUI (okno aplikacji przez pywebview), LM Studio + **Bielik 4.5B v3.0 Instruct** (SpeakLeash), PyMuPDF, python-docx, openpyxl, Pillow, winocr (Windows.Media.Ocr), httpx, NumPy, pytest, ruff, PyInstaller.

PyMuPDF jest na licencji AGPL. Przy wdrożeniu w urzędzie trzeba to uwzględnić: albo licencja komercyjna, albo wymiana tej części na inną bibliotekę.

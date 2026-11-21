# TO-DO do MVP – Asystent UDIP (HackNation 2026, UM Bydgoszcz)

Priorytety: **P0** – bez tego nie przejdziemy testów jury · **P1** – mocno podnosi ocenę · **P2** – jeśli zostanie czas.
W nawiasach odwołania do treści zadania: „Z” = założenia (pkt 2), „I” = instrukcja działania, „J” = testy jury (pkt 6).

Kryteria oceny: zgodność z założeniami 30% · bezpieczeństwo i anonimizacja 20% · łatwość obsługi 20% · kompletność prototypu 30%.

---

## ✅ Zrobione

- [x] Aplikacja desktopowa (NiceGUI, okno natywne), uruchamianie jednym `uruchom.bat`
- [x] Wgrywanie PDF/DOCX/DOC/TXT przeciąganiem, walidacja plików, odczyt tekstu, lokalny magazyn (Z2)
- [x] Kalendarz: 10 wniosków testowych od najstarszych, kolory terminów, Lp., nr, opis, inicjały, daty (Z3, J5)
- [x] Lokalny Bielik w LM Studio – analiza wniosku, projekt pisma na żywo, dane osobowe (Z1, Z7)
- [x] Anonimizacja: szare propozycje → czarne po akceptacji, maskowanie w eksporcie (Z4)
- [x] Eksport pisma do .docx/.txt, brak automatycznej wysyłki (I9, Z9)
- [x] Kontrola jakości pisma: liczby ze źródłami, pominięte dane, kompletność (Z7 – „wykluczyć halucynacje”)
- [x] Czat Urzęduś z regulacjami zakresu
- [x] Baza wiedzy: ustawy, zarządzenia, archiwalne odpowiedzi (I1, J6)
- [x] 154 testy automatyczne, dane testowe w `dane_testowe/`

---

## 1. Krytyczne pod testy jury (P0)

- [ ] **Archiwum semantyczne – prawdziwe „podobne sprawy”** (Z5, I3, **J1** – pierwsza rzecz, którą sprawdzi jury)
  - [ ] indeksowanie dokumentów z Bazy wiedzy modelem `nomic-embed-text` (jest już w LM Studio)
  - [ ] wyszukiwanie po wgraniu wniosku: top 5 z % podobieństwa w kroku „Podobne sprawy” i na ekranie Archiwum
  - [ ] także podobne wnioski z bieżącego rejestru z ostatniego roku (I3)
  - [ ] najlepsze dopasowanie automatycznie jako wzór do projektu odpowiedzi
  - [ ] usunąć dane przykładowe z `archiwum.py` i `sprawa.py`
- [ ] **Zapisywanie stanu sprawy** – dziś projekt pisma i anonimizacja giną po wyjściu ze sprawy
  - [ ] projekt, zatwierdzone fragmenty do ukrycia i wynik kontroli zapisywane w katalogu sprawy
- [ ] **Statusy spraw zmieniane na każdym kroku** (I11, J5) – dziś status ustawia się tylko przy dodaniu wniosku
  - [ ] brak działań → zapytania do wydziałów (po skopiowaniu prośby / wgraniu odpowiedzi) → odpowiedź przygotowana (po eksporcie) → wysłana
  - [ ] kwerenda + liczba dni (I11c), przycisk „Oznacz jako wysłane” z datą udzielenia odpowiedzi (dziś TODO)
- [ ] **Anonimizacja dowolnego pliku** (**J3**: jury wgra plik z danymi osobowymi i sprawdzi, czy je ukrywamy)
  - [ ] osobne narzędzie: wgraj PDF/DOCX → zaznacz dane → zatwierdź → pobierz zanonimizowany DOCX
  - [ ] wykrywanie imion i nazwisk bez AI (słownik polskich imion + wzorce), adresów, kodów pocztowych, dat urodzenia, NIP/REGON osób fizycznych
  - [ ] przetestować na kilku plikach z danymi (także gdy LM Studio jest wyłączone)
- [ ] **Materiały od mentorów (kod QR w dniu startu)** – wgrać wzory wniosków i odpowiedzi, zastąpić nimi dane testowe, sprawdzić całą ścieżkę na nich
- [ ] **Lista wydziałów i biur z BIP + dobór wydziału** (Z6, I4) – 👤 **robi kolega**; uzgodnić miejsca styku (`analizuj_wniosek(znane_wydzialy=…)`, krok „Wydziały”, czat)

## 2. Kalendarz wniosków

- [ ] P1 Wybór roku faktycznie filtruje listę (dziś pole nic nie robi) (Z3)
- [ ] P1 Widok miesiąca – siatka z wnioskami na dniach terminu (dziś placeholder) (Z3)
- [ ] P1 Edycja danych wniosku i usuwanie wniosku (z potwierdzeniem)
- [ ] P1 Przesuwanie terminu z soboty/niedzieli/święta na następny dzień roboczy (art. 57 § 4 KPA)
- [ ] P2 Wyszukiwarka i filtry: pilne / w toku / wysłane / moje (inicjały)
- [ ] P2 Rejestr w SQLite zamiast JSON (skalowanie na setki spraw)

## 3. AI i automatyzacja

- [ ] P1 **Szybkość**: model `Bielik-4.5B-v3.0-Instruct` w wersji **Q4_K_M** (Q8_0 nie mieści się w 4 GB VRAM GTX 1650), pełny GPU offload; zmierzyć czasy przed i po
- [ ] P1 Autopilot w tle (Z4 – automatyzacja): po wgraniu wniosku analiza + podobne sprawy + prośba do wydziałów; po wgraniu odpowiedzi projekt + dane osobowe + kontrola; kolejka zadań i znacznik „AI pracuje…” na liście
- [ ] P1 Klasyfikacja wniosku i ścieżka postępowania: zwykła / przetworzona / nie jest informacją publiczną / dostępna w BIP / do doprecyzowania → odpowiedź, decyzja odmowna albo prośba o doprecyzowanie
- [ ] P2 Rozgrzanie modelu przy starcie aplikacji (pierwsze zapytanie jest najwolniejsze)
- [ ] P2 Odczyt danych z wniosku: wnioskodawca, e-mail/adres do odpowiedzi
- [ ] P2 OCR skanów offline (Tesseract) – dziś skan dostaje tylko ostrzeżenie
- [ ] P2 Zawiadomienie o kwerendzie z jednego kliknięcia przy zaznaczeniu kwerendy

## 4. Bezpieczeństwo i RODO (20% oceny)

- [ ] P1 Test „bez internetu”: odłączyć sieć i przejść całą ścieżkę (pokazać na filmie)
- [ ] P1 Dziennik działań AI: co zaproponował model, co zatwierdził urzędnik, kiedy (bez danych osobowych w logach)
- [ ] P1 Opis zabezpieczeń do prezentacji: lokalny model, dane w `dane/`, walidacja plików, regulacje czatu, maskowanie, brak wysyłki
- [ ] P2 Usuwanie danych zakończonej sprawy po okresie przechowywania (retencja)
- [ ] P2 Szyfrowanie folderu danych (np. BitLocker / zaszyfrowany katalog – `UDIP_KATALOG_DANYCH`)
- [ ] P2 Ekran logowania / blokada aplikacji (inicjały urzędnika z konta)

## 5. Dane i baza wiedzy

- [ ] P1 Wgrać ustawę UDIP i KPA (linki z treści zadania, ISAP) do Bazy wiedzy
- [ ] P1 Aktualizacja ustaw: nowa wersja zastępuje starą (wersjonowanie, data obowiązywania) (J6)
- [ ] P1 Archiwum testowe: kilkadziesiąt archiwalnych odpowiedzi do pokazu wyszukiwania (od mentorów albo przygotowane)
- [ ] P2 Import całego folderu naraz (np. archiwum z roku)
- [ ] P2 Test wydajności: 300+ dokumentów w bazie – czas indeksowania i wyszukiwania

## 6. Wygląd i łatwość obsługi (20% oceny)

- [ ] P1 Wdrożyć nowy wygląd wg zatwierdzonego szkicu (lżejszy nagłówek, menu z aktywną pozycją, odznaki statusów, pionowe kroki sprawy)
- [ ] P1 Przejrzeć wszystkie ekrany pod kątem stanów: pusto / ładowanie / błąd / brak LM Studio
- [ ] P1 Usunąć wszystkie przyciski „TODO” z interfejsu albo je zrealizować (Archiwum „Szukaj”, „Otwórz” w podobnych sprawach, „Oznacz jako wysłane”, „Zapisz” w ustawieniach)
- [ ] P2 Skróty klawiszowe, podpowiedzi przy pierwszym uruchomieniu
- [ ] P2 Test z osobą spoza zespołu (najlepiej mentor z UMB) – 10 minut, notujemy, gdzie się gubi

## 7. Stabilność i wdrożenie („łatwo zainstalować i uruchomić”)

- [ ] P1 Paczka `.exe` (`nicegui-pack` / PyInstaller) + instrukcja instalacji LM Studio i modelu Bielik
- [ ] P1 Test na czystym komputerze (bez Pythona) – od rozpakowania do pierwszego wniosku
- [ ] P1 Obsługa błędów: brak LM Studio, uszkodzony plik, brak miejsca na dysku – czytelne komunikaty, bez wysypania aplikacji
- [ ] P2 GitHub Actions: testy przy każdym pushu
- [ ] P2 Diagram architektury do README i prezentacji

## 8. Wymagania formalne (pkt 4 zadania)

- [ ] P0 **Film do 3 minut**: wgranie wniosku → podobne sprawy → wydziały → odpowiedź wydziału → projekt pisma na żywo → kontrola jakości → anonimizacja → eksport; kalendarz z kolorami; czat
- [ ] P0 **Prezentacja do 10 slajdów**:
  - [ ] 1. nazwa projektu i skład zespołu
  - [ ] 2. problem: jak przyspieszamy pracę urzędnika i chronimy dane osobowe, dlaczego to ważne
  - [ ] 3. rozwiązanie: wyszukiwanie w archiwum, anonimizacja, kalendarz, technologia
  - [ ] 4. jak to działa (zrzuty / fragment filmu)
  - [ ] 5. dla kogo – urzędnicy JST
  - [ ] 6. przyszłość: wdrożenie w UM Bydgoszcz
  - [ ] 7. narzędzia: Python, NiceGUI, LM Studio, Bielik, pypdf, python-docx, httpx, pytest
  - [ ] 8. **praca offline**: tak – model Bielik (SpeakLeash, PL) lokalnie; propozycja docelowa: Bielik 11B v2.x na serwerze urzędu z GPU, 4.5B na stanowiskach
- [ ] P0 Scenariusz pokazu krok po kroku + plan B (nagranie), gdyby na żywo coś nie zadziałało

## 9. Dzień przed oddaniem – checklista

- [ ] Wszystko zacommitowane i wypchnięte na `main`, kolega na aktualnej wersji
- [ ] Świeże dane demo (10 wniosków testowych, archiwum, ustawy), wyczyszczone testowe śmieci
- [ ] LM Studio: model załadowany, port 1235, sprawdzone „Sprawdź połączenie”
- [ ] Laptop: zasilanie, wyłączone powiadomienia i aktualizacje, rozdzielczość do nagrania
- [ ] Przejście całego scenariusza jury (J1–J6) na czysto, z zegarkiem

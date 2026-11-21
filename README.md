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
asystent/
  konfiguracja.py         ścieżki, limity, terminy
  rejestr.py              lista wniosków (10 testowych + dodane przez urzędnika)
  uslugi.py               wspólne instancje (magazyn plików)
  pliki/                  obsługa plików – bez zależności od GUI
    walidacja.py          typ, rozmiar, sygnatura pliku, bezpieczna nazwa
    ekstrakcja.py         tekst z PDF / DOCX / DOC / TXT
    magazyn.py            lokalne przechowywanie dokumentów + metadane
    eksport.py            zapis pisma do .docx / .txt
  gui/
    aplikacja.py          układ okna, menu, routing
    komponenty.py         pole „przeciągnij i upuść”, karta pliku, …
    strony/               jeden moduł na ekran
tests/                    testy (pytest)
```

## Obsługa plików

- Wnioski, odpowiedzi wydziałów i dokumenty bazy wiedzy wgrywa się **przeciągając plik na pole** (albo klikając je).
- Obsługiwane: PDF, DOCX, DOC (wymaga LibreOffice), TXT; do 25 MB.
- Każdy plik jest sprawdzany (rozszerzenie **i** zawartość), a jego tekst odczytywany lokalnie.
  Skany bez warstwy tekstowej i PDF-y z hasłem są wyraźnie oznaczane.
- Dane leżą wyłącznie na tym komputerze, w folderze `dane/` (poza gitem). Inny folder: zmienna `UDIP_KATALOG_DANYCH`.

```
dane/
  przychodzace/                   wgrane, niezatwierdzone wnioski
  sprawy/<nr>/wniosek|odpowiedzi|eksport/
  baza_wiedzy/ustawy|zarzadzenia|archiwum/
  rejestr_wnioskow.json
```

## Testy

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

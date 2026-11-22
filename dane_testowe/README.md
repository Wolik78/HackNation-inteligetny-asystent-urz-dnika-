# Dane testowe

Wszystkie dokumenty są **fikcyjne** – imiona, nazwiska, adresy, numery i kwoty zostały wymyślone na potrzeby testów.
Służą do pokazu i do testów automatycznych (`tests/`).

| Folder / plik | Do czego | Test jury |
|---|---|---|
| `wnioski/wniosek_wydatki_na_promocje.pdf` | wniosek o wydatki na promocję miasta – rejestracja wniosku, wydziały, podobne sprawy | J1, J2 |
| `odpowiedzi_wydzialow/odpowiedz_wydzialu_promocja.docx` | odpowiedź wydziału z kwotami – podstawa projektu pisma | J2 |
| `kontrola_jakosci/projekt_pisma_z_bledami.txt` | projekt pisma z celowymi błędami (zmyślone kwoty, brak podstawy prawnej) – kontrola jakości | J2 |
| `anonimizacja/wniosek_z_danymi_osobowymi.pdf` | wniosek z danymi osobowymi wszystkich typów (PESEL, dowód, konto, NIP, adresy, telefony…) | J3 |
| `anonimizacja/wniosek_z_danymi_osobowymi_skan.pdf` | ten sam wniosek jako skan bez warstwy tekstowej (OCR) | J3 |
| `archiwum/` | 11 archiwalnych odpowiedzi UDIP na różne tematy – wyszukiwanie podobnych spraw | J1, J6 |

Archiwum wgrywa się do aplikacji jednym kliknięciem: **Ustawienia → Wczytaj dane demonstracyjne**
(albo ręcznie: Baza wiedzy → rodzaj „Archiwalna odpowiedź” → przeciągnij pliki z folderu `archiwum/`).

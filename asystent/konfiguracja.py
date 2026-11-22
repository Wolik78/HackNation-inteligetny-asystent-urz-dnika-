"""Ustawienia aplikacji: ścieżki, limity i terminy."""

import os
import sys
from pathlib import Path

# Wersja zbudowana do .exe (PyInstaller): zasoby (wykaz wydziałów, dane demonstracyjne) są w paczce,
# a dane urzędu – w folderze „dane” obok pliku .exe (nie w folderze tymczasowym paczki).
ZBUDOWANA = getattr(sys, 'frozen', False)
KATALOG_PROJEKTU = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
KATALOG_PROGRAMU = Path(sys.executable).resolve().parent if ZBUDOWANA else KATALOG_PROJEKTU

# Wszystkie dane (wgrane pliki, eksporty) trzymamy lokalnie – katalog jest w .gitignore.
# Można go przenieść zmienną środowiskową, np. na zaszyfrowany dysk urzędu.
KATALOG_DANYCH = Path(os.environ.get('UDIP_KATALOG_DANYCH', KATALOG_PROGRAMU / 'dane'))

DOZWOLONE_ROZSZERZENIA = ('.pdf', '.docx', '.doc', '.txt', '.jpg', '.jpeg', '.png')  # zdjęcia – przez OCR
MAKS_ROZMIAR_PLIKU = 25 * 1024 * 1024  # 25 MB

TERMIN_DNI = 14         # art. 13 ust. 1 UDIP (kwerenda: do 2 miesięcy – patrz rejestr.MIESIACE_KWERENDY)

# Lokalny model językowy (LM Studio, API zgodne z OpenAI). Działa tylko na tym komputerze.
LLM_URL = os.environ.get('UDIP_LLM_URL', 'http://localhost:1235/v1')
LLM_MODEL = os.environ.get('UDIP_LLM_MODEL', 'bielik-4.5b-v3.0-instruct')
LLM_LIMIT_ZNAKOW = int(os.environ.get('UDIP_LLM_LIMIT_ZNAKOW', 6000))  # tekstu w jednym zapytaniu
LLM_TEMPERATURA = 0.1
# Model embeddingów do wyszukiwania podobnych spraw (Archiwum). Wbudowany w LM Studio nomic-embed słabo zna polski,
# dlatego wyszukiwanie opiera się głównie na słowach; lepszy wielojęzyczny model, np. bge-m3, podnosi wagę znaczenia.
EMBED_MODEL = os.environ.get('UDIP_EMBED_MODEL', 'text-embedding-nomic-embed-text-v1.5')

# Autopilot: po wgraniu odpowiedzi wydziału Bielik sam pisze projekt pisma, a aplikacja robi kontrolę jakości
# i zaznacza dane osobowe do sprawdzenia. Wyłączenie: UDIP_AUTOPILOT=0.
AUTOPILOT = os.environ.get('UDIP_AUTOPILOT', '1') != '0'

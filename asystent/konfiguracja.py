"""Ustawienia aplikacji: ścieżki, limity i terminy."""

import os
from pathlib import Path

KATALOG_PROJEKTU = Path(__file__).resolve().parent.parent

# Wszystkie dane (wgrane pliki, eksporty) trzymamy lokalnie – katalog jest w .gitignore.
# Można go przenieść zmienną środowiskową, np. na zaszyfrowany dysk urzędu.
KATALOG_DANYCH = Path(os.environ.get('UDIP_KATALOG_DANYCH', KATALOG_PROJEKTU / 'dane'))

DOZWOLONE_ROZSZERZENIA = ('.pdf', '.docx', '.doc', '.txt', '.jpg', '.jpeg', '.png')  # zdjęcia – przez OCR
MAKS_ROZMIAR_PLIKU = 25 * 1024 * 1024  # 25 MB

TERMIN_DNI = 14         # art. 13 ust. 1 UDIP (kwerenda: do 2 miesięcy – patrz rejestr.MIESIACE_KWERENDY)

# Lokalny model językowy (LM Studio, API zgodne z OpenAI). Działa tylko na tym komputerze.
LLM_URL = os.environ.get('UDIP_LLM_URL', 'http://localhost:1235/v1')
LLM_MODEL = os.environ.get('UDIP_LLM_MODEL', 'bielik-4.5b-v3.0-instruct')
LLM_LIMIT_ZNAKOW = int(os.environ.get('UDIP_LLM_LIMIT_ZNAKOW', 6000))  # tekstu w jednym zapytaniu
LLM_TEMPERATURA = 0.1

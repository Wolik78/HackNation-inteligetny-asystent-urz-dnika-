"""Ustawienia aplikacji: ścieżki, limity i terminy."""

import os
from pathlib import Path

KATALOG_PROJEKTU = Path(__file__).resolve().parent.parent

# Wszystkie dane (wgrane pliki, eksporty) trzymamy lokalnie – katalog jest w .gitignore.
# Można go przenieść zmienną środowiskową, np. na zaszyfrowany dysk urzędu.
KATALOG_DANYCH = Path(os.environ.get('UDIP_KATALOG_DANYCH', KATALOG_PROJEKTU / 'dane'))

DOZWOLONE_ROZSZERZENIA = ('.pdf', '.docx', '.doc', '.txt')
MAKS_ROZMIAR_PLIKU = 25 * 1024 * 1024  # 25 MB

TERMIN_DNI = 14         # art. 13 ust. 1 UDIP
TERMIN_KWERENDA = 60    # art. 13 ust. 2 UDIP – do 2 miesięcy

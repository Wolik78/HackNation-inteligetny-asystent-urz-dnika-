"""Asystent UDIP – punkt startowy aplikacji.

Uruchomienie:
    uruchom.bat            -> okno aplikacji (domyślnie)
    uruchom.bat --web      -> w przeglądarce na http://127.0.0.1:8080 (do debugowania)

Kod aplikacji jest w pakiecie `asystent/` (opis struktury: README.md).
"""

import sys

try:
    import nicegui  # noqa: F401
except ModuleNotFoundError:
    sys.exit(f'Brak biblioteki NiceGUI w tym Pythonie ({sys.executable}).\n'
             'Uruchom aplikację przez uruchom.bat albo wybierz w VS Code interpreter z folderu .venv.')

from asystent.gui import uruchom

if __name__ in {'__main__', '__mp_main__'}:
    uruchom(tryb_web='--web' in sys.argv)

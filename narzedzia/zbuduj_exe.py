"""Buduje wersję do uruchomienia bez Pythona: dist/CyfrowyRatusz/CyfrowyRatusz.exe (PyInstaller, folder).

Uruchamiane przez zbuduj_exe.bat. Do paczki trafiają: NiceGUI (pliki interfejsu), wykaz wydziałów z BIP,
dane demonstracyjne, szablon dokumentu Word i moduły OCR Windows (winrt).
"""

import os
import sys
from pathlib import Path

import nicegui
import PyInstaller.__main__

KATALOG = Path(__file__).resolve().parent.parent
SEP = os.pathsep  # PyInstaller: ŹRÓDŁO;CEL na Windows


def main() -> None:
    os.chdir(KATALOG)
    PyInstaller.__main__.run([
        '--noconfirm', '--clean', '--windowed', '--onedir', '--name', 'CyfrowyRatusz',
        '--add-data', f'{Path(nicegui.__file__).parent}{SEP}nicegui',
        '--add-data', f'{KATALOG / "asystent" / "zasoby"}{SEP}asystent/zasoby',
        '--add-data', f'{KATALOG / "dane_testowe"}{SEP}dane_testowe',
        '--collect-data', 'docx',
        '--collect-submodules', 'winrt',
        '--hidden-import', 'winocr',
        str(KATALOG / 'main.py'),
    ])
    print(f'\nGotowe: {KATALOG / "dist" / "CyfrowyRatusz" / "CyfrowyRatusz.exe"}')


if __name__ == '__main__':
    sys.exit(main())

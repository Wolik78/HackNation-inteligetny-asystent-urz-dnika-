@echo off
rem Uruchamia Asystenta UDIP. Tworzy srodowisko .venv i doinstalowuje biblioteki, gdy zmieni sie requirements.txt.
rem Uzycie: dwuklik albo "uruchom.bat --web" (wersja w przegladarce).
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Pierwsze uruchomienie: tworze srodowisko .venv...
    python -m venv .venv || goto :blad
    ".venv\Scripts\python" -m pip install --upgrade pip || goto :blad
)

fc /b requirements.txt ".venv\requirements.zainstalowane" >nul 2>&1 || (
    echo Instaluje biblioteki z requirements.txt...
    ".venv\Scripts\python" -m pip install -r requirements.txt || goto :blad
    copy /y requirements.txt ".venv\requirements.zainstalowane" >nul
)

".venv\Scripts\python" GUI.py %*
exit /b %errorlevel%

:blad
echo.
echo Nie udalo sie przygotowac srodowiska. Sprawdz, czy Python 3.11+ jest zainstalowany i dostepny jako "python".
pause
exit /b 1

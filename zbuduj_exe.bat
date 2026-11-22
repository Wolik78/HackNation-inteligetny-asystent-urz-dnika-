@echo off
rem Buduje wersje do uruchomienia bez Pythona: folder dist\CyfrowyRatusz z plikiem CyfrowyRatusz.exe.
rem Folder mozna skopiowac na inny komputer z Windows 10/11 (LM Studio z Bielikiem instaluje sie osobno).
rem Dane urzedu trafiaja do dist\CyfrowyRatusz\dane (obok pliku .exe).
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Najpierw uruchom uruchom.bat - przygotuje srodowisko .venv.
    exit /b 1
)
".venv\Scripts\python" -m pip install -q -r requirements-dev.txt || goto :blad
".venv\Scripts\python" narzedzia\zbuduj_exe.py || goto :blad
exit /b 0

:blad
echo.
echo Budowanie nie powiodlo sie - szczegoly powyzej.
exit /b 1

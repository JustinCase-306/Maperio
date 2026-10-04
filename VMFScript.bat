@echo off
REM ============================================================
REM  VMFScript 5.0 - Starter fuer Portal 2
REM  Doppelklick startet die grafische Oberflaeche.
REM ============================================================
setlocal
cd /d "%~dp0"

REM GUI liegt im scripts-Ordner, nicht im Wurzelordner.
set "GUI=%~dp0scripts\vmfs_gui.py"

if not exist "%GUI%" (
    echo FEHLER: vmfs_gui.py nicht gefunden.
    echo Erwartet: "%GUI%"
    echo.
    pause
    exit /b 1
)

echo VMFScript 5.0 wird gestartet ...
echo.

REM Python suchen: erst mit tkinter pruefen, sonst ist das Fenster tot.
set "PY="
for %%P in (
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python313\python.exe"
    "%LocalAppData%\Programs\Python\Python311\python.exe"
    "%LocalAppData%\Programs\Python\Python310\python.exe"
) do (
    if exist %%P (
        %%P -c "import tkinter" >nul 2>&1 && (
            set "PY=%%~P"
            goto :startgui
        )
    )
)

REM Kein fest verdrahtetes Python: im PATH suchen (mit tkinter-Test).
for %%C in (python python3 py) do (
    for /f "delims=" %%R in ('where %%C 2^>nul') do (
        if not defined PY (
            %%R -c "import tkinter" >nul 2>&1 && set "PY=%%R"
        )
    )
)

:startgui
if not defined PY (
    echo FEHLER: Kein Python mit tkinter gefunden.
    echo.
    echo tkinter wird bei der Python-Installation mitgebracht.
    echo Bitte Python von https://www.python.org/downloads/ installieren
    echo und im Installationsdialog den Haken bei "tcl/tk" setzen.
    echo.
    pause
    exit /b 1
)

echo Gestartet mit: %PY%
echo Das Fenster schliesst sich beim Beenden. Zum Nachlesen:
echo   "%GUI%"
echo.
start "" "%PY%" "%GUI%"
exit /b 0
@echo off
rem Klassenbildung & Stundenplan starten (Windows). Doppelklick genuegt.
chcp 65001 >nul
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py -3
if not exist ".venv\Scripts\python.exe" (
  echo Erste Einrichtung - einmalig, dauert 2 bis 5 Minuten ...
  %PY% -m venv .venv
  if errorlevel 1 goto keinpython
)
echo Programm wird vorbereitet ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -e .
if errorlevel 1 goto fehler
echo Die Bedienoberflaeche oeffnet sich im Browser. Dieses Fenster offen lassen; zum Beenden schliessen.
".venv\Scripts\python.exe" -m skf app
goto ende

:keinpython
echo.
echo Python wurde nicht gefunden.
echo Bitte Python 3.11 oder neuer von https://www.python.org/downloads/ installieren
echo und dabei "Add python.exe to PATH" anhaken. Danach erneut starten.
pause
goto ende

:fehler
echo.
echo Die Installation ist fehlgeschlagen. Bitte Internetverbindung pruefen und erneut starten.
pause

:ende

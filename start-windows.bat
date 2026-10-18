@echo off
rem SPDX-License-Identifier: LicenseRef-Proprietary
rem Copyright (c) 2026 Luca De Simoni. Alle Rechte vorbehalten.
rem ============================================================
rem  Klassenbildung & Stundenplan – Start fuer Windows
rem  Einfach doppelklicken. Beim ersten Mal wird alles Noetige
rem  automatisch eingerichtet (Internet noetig, 2-5 Minuten).
rem ============================================================
chcp 65001 >nul
title Klassenbildung und Stundenplan
cd /d "%~dp0"
if "%SKF_PYTHON%"=="" set "SKF_PYTHON=3.12"

set "UV="
where uv >nul 2>nul && set "UV=uv"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV (
  echo Erste Einrichtung: Hilfsprogramm wird geladen ...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex" >nul
  if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
)
if not defined UV goto mitpython

call :verknuepfung
echo Programm wird vorbereitet - beim ersten Mal dauert das einige Minuten ...
"%UV%" run --python %SKF_PYTHON% --quiet skf app
if errorlevel 1 goto fehler
goto ende

:mitpython
rem Rueckfallebene: vorhandenes Python verwenden
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 goto keinpython
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -e .
if errorlevel 1 goto fehler
call :verknuepfung
".venv\Scripts\python.exe" -m skf app
goto ende

:verknuepfung
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $l=Join-Path $d 'Klassenbildung.lnk'; if (-not (Test-Path $l)) { $s=(New-Object -ComObject WScript.Shell).CreateShortcut($l); $s.TargetPath='%~f0'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='shell32.dll,21'; $s.Description='Klassenbildung und Stundenplan'; $s.Save(); Write-Host 'Verknuepfung Klassenbildung auf dem Desktop angelegt.' }"
exit /b 0

:keinpython
echo.
echo Die automatische Einrichtung hat nicht geklappt und Python wurde nicht gefunden.
echo Bitte Internetverbindung pruefen und erneut doppelklicken.
echo Alternativ Python von https://www.python.org/downloads/ installieren
echo (dabei "Add python.exe to PATH" anhaken).
pause
goto ende

:fehler
echo.
echo Es ist ein Fehler aufgetreten. Bitte Internetverbindung pruefen und erneut doppelklicken.
echo Falls es weiterhin nicht klappt: Ordner ".venv" loeschen und nochmals starten.
pause

:ende

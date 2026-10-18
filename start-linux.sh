#!/bin/bash
# Klassenbildung & Stundenplan starten (Linux/macOS): ./start-linux.sh
set -e
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python || true)
if [ -z "$PY" ]; then
  echo "Python wurde nicht gefunden. Bitte Python 3.11 oder neuer installieren: https://www.python.org/downloads/"
  read -r -p "Enter zum Schliessen …"
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "Erste Einrichtung – einmalig, dauert 2 bis 5 Minuten …"
  "$PY" -m venv .venv
fi
if [ ! -f .venv/.installiert ] || [ pyproject.toml -nt .venv/.installiert ]; then
  echo "Programm wird vorbereitet …"
  .venv/bin/python -m pip install --disable-pip-version-check -q -e .
  touch .venv/.installiert
fi
echo "Die Bedienoberfläche öffnet sich im Browser. Zum Beenden: Ctrl+C oder Fenster schliessen."
exec .venv/bin/python -m skf app

#!/bin/bash
# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
# ============================================================
#  Klassenbildung & Stundenplan – Start für Linux und macOS
#  ./start-linux.sh  (macOS: Doppelklick auf start-mac.command)
#  Beim ersten Mal wird alles Nötige automatisch eingerichtet.
# ============================================================
cd "$(dirname "$0")" || exit 1
SKF_PYTHON="${SKF_PYTHON:-3.12}"
pause_und_ende() { read -r -p "Enter zum Schliessen …" _; exit 1; }

UV=$(command -v uv || true)
[ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"
if [ -z "$UV" ]; then
  echo "Erste Einrichtung: Hilfsprogramm wird geladen …"
  if command -v curl >/dev/null; then curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
  elif command -v wget >/dev/null; then wget -qO- https://astral.sh/uv/install.sh | sh >/dev/null 2>&1; fi
  [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"
fi

if [ -n "$UV" ]; then
  echo "Programm wird vorbereitet – beim ersten Mal dauert das einige Minuten …"
  exec "$UV" run --python "$SKF_PYTHON" --quiet skf app
fi

# Rückfallebene: vorhandenes Python verwenden
PY=$(command -v python3 || command -v python || true)
if [ -z "$PY" ]; then
  echo "Die automatische Einrichtung hat nicht geklappt und Python wurde nicht gefunden."
  echo "Bitte Internetverbindung prüfen oder Python installieren: https://www.python.org/downloads/"
  pause_und_ende
fi
if [ ! -x .venv/bin/python ]; then "$PY" -m venv .venv || pause_und_ende; fi
if [ ! -f .venv/.installiert ] || [ pyproject.toml -nt .venv/.installiert ]; then
  echo "Programm wird vorbereitet …"
  .venv/bin/python -m pip install --disable-pip-version-check -q -e . || pause_und_ende
  touch .venv/.installiert
fi
exec .venv/bin/python -m skf app

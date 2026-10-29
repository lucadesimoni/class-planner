# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Wo das Programm läuft: normales Python (Desktop, CLI, Server) oder im Browser (stlite / Pyodide).

Im Browser gibt es kein OR-Tools: gerechnet wird über ``skf.fernrechnen`` auf dem Rechenserver
(Vercel-Funktion ``api/rechnen.py``) – mit genau derselben Funktion ``skf.ablauf.rechne``.
"""
from __future__ import annotations

import os
import sys

# SKF_BROWSER=1 führt die Browser-Pfade in normalem Python aus (Tests)
IN_BROWSER = sys.platform == "emscripten" or os.environ.get("SKF_BROWSER") == "1"
RECHEN_URL = os.environ.get("SKF_RECHNEN_URL", "/api/rechnen")   # relativ = gleiche Adresse wie die Seite
# Sekunden Rechenzeit pro Szenario auf dem Server: rechne() hält höchstens 1,5 × dieser Zeit plus die
# Konfliktanalyse ein – das bleibt unter Vercels maxDuration von 300 s
MAX_RECHENZEIT = 160

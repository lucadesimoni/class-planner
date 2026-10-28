# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
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
MAX_RECHENZEIT = 240   # Sekunden pro Szenario auf dem Server (Vercel: maxDuration 300)

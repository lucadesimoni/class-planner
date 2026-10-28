# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Vercel-Funktion: rechnet für die Browser-Version (POST /api/rechnen).

Nur eine Hülle um ``skf.fernrechnen.bearbeite`` – die Rechnung selbst ist ``skf.ablauf.rechne``.
Region und Laufzeit: vercel.json. Abhängigkeiten der Funktion: requirements.txt (nur OR-Tools und PyYAML).
"""
from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skf.fernrechnen import MAX_ANFRAGE, bearbeite  # noqa: E402


class handler(BaseHTTPRequestHandler):  # Name von Vercel vorgegeben
    def do_POST(self):  # noqa: N802
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge > MAX_ANFRAGE * 4:
            status, text = 413, '{"fehler": "Anfrage zu gross"}'
        else:
            status, text = bearbeite(self.rfile.read(laenge).decode("utf-8", "replace"))
        daten = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(daten)))
        self.end_headers()
        self.wfile.write(daten)

    def do_GET(self):  # noqa: N802 – Erreichbarkeit prüfen, ohne zu rechnen
        from skf.version import __version__
        daten = f'{{"dienst": "skf-rechnen", "version": "{__version__}"}}'.encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(daten)))
        self.end_headers()
        self.wfile.write(daten)

    def log_message(self, *args):  # keine Anfragedaten ins Log
        pass

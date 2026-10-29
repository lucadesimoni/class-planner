# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Browser-Version bauen (Vercel): Wheel, Startseite, Icon und Kartenkomponente in einem Ordner.

    python scripts/build_web.py            # → _site/ (lokal ansehen: python -m http.server -d _site 8000)

Die Seite startet die App mit stlite (Streamlit in WebAssembly/Pyodide) – nichts zu installieren. Gerechnet
wird über die Vercel-Funktion api/rechnen.py (skf.fernrechnen), weil OR-Tools nicht im Browser läuft.
Vercel (vercel.json) führt dieses Skript aus und veröffentlicht _site/ samt Funktion. Wie site-development.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
from skf.icons import PFADE  # noqa: E402
from skf.version import __version__  # noqa: E402


def build_id() -> str:
    """Commit und Datum, z.B. "a1b2c3d · 2026-10-28" (Vercel und GitHub liefern den Commit)."""
    sha = os.environ.get("VERCEL_GIT_COMMIT_SHA") or os.environ.get("GITHUB_SHA") or ""
    if not sha:
        try:
            sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=WURZEL, capture_output=True, text=True).stdout
        except OSError:
            sha = ""
    datum = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    return f"{sha.strip()[:7]} · {datum}" if sha.strip() else datum


def icon_svg() -> str:
    return ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'><rect width='40' height='40' rx='10' "
            f"fill='#2f5d50'/><g transform='translate(8 8)' fill='white'><path d='{PFADE['school']}'/></g></svg>")


def build(ziel: Path = WURZEL / "_site") -> Path:
    if ziel.exists():
        shutil.rmtree(ziel)
    ziel.mkdir(parents=True)
    uv = (shutil.which("uv") or next((str(c) for c in (Path(sys.executable).with_name("uv"),
                                                        Path.home() / ".local/bin/uv") if c.exists()), "uv"))
    subprocess.run([uv, "build", "--wheel", "--out-dir", str(ziel)], cwd=WURZEL, check=True)
    wheels = sorted(ziel.glob(f"class_planner-{__version__}-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"genau ein Wheel für {__version__} erwartet, gefunden: {[w.name for w in wheels]}")
    seite = (WURZEL / "web" / "index.html").read_text(encoding="utf-8")
    seite = seite.replace("__WHEEL__", wheels[0].name).replace("__VERSION__", __version__).replace("__BUILD__", build_id())
    (ziel / "index.html").write_text(seite, encoding="utf-8")
    (ziel / "icon.svg").write_text(icon_svg(), encoding="utf-8")
    # Kartenkomponente (Gebiet zeichnen): im Browser von hier geladen statt vom Streamlit-Server
    shutil.copytree(WURZEL / "skf" / "static", ziel / "komponenten" / "gebietskarte",
                    ignore=shutil.ignore_patterns("material-symbols"))
    (ziel / ".gitignore").unlink(missing_ok=True)       # von uv build geschrieben – nicht Teil der Seite
    return ziel


if __name__ == "__main__":
    print(f"Gebaut: {build()}")

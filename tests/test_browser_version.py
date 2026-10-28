# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Browser-Version (stlite auf Vercel) und Rechnen über den Server (skf.fernrechnen, api/rechnen.py).

Die echte WebAssembly-Umgebung braucht das stlite/Pyodide-CDN; hier laufen die Browser-Pfade in normalem
Python (SKF_BROWSER=1, OR-Tools ausgeblendet) und der Rechenserver als lokaler HTTP-Server.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import pickle
import re
import subprocess
import sys
import threading
import zipfile
import zlib
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from skf.ablauf import rechne
from skf.daten import lade_kinder, lade_schule
from skf.fernrechnen import NUR_IM_BROWSER, anfrage, bearbeite, rechne_fern
from skf.version import __version__

WURZEL = Path(__file__).resolve().parent.parent
VORLAGE = WURZEL / "beispiele" / "vorlage"
OHNE_ORTOOLS = "import sys\nfor m in ('ortools', 'ortools.sat', 'ortools.sat.python'): sys.modules[m] = None\n"


def _cfg() -> dict:
    return yaml.safe_load((VORLAGE / "schule.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def server():
    """api/rechnen.py als lokaler HTTP-Server (so wie Vercel die Funktion aufruft)."""
    spec = importlib.util.spec_from_file_location("api_rechnen", WURZEL / "api" / "rechnen.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), modul.handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/api/rechnen"
    httpd.shutdown()


def test_build_web(tmp_path):
    sys.path.insert(0, str(WURZEL))
    from scripts.build_web import build
    ziel = build(tmp_path / "site")
    seite = (ziel / "index.html").read_text(encoding="utf-8")
    wheel = next(ziel.glob("*.whl"))
    assert f'new URL("{wheel.name}"' in seite and __version__ in seite and "__WHEEL__" not in seite
    assert "@stlite/browser@1.10.0" in seite and "idbfsMountpoints" in seite and "SKF_RECHNEN_URL" in seite
    namen = zipfile.ZipFile(wheel).namelist()
    assert {"skf/app.py", "skf/fernrechnen.py", "skf/static/index.html", "skf/beispiele/malters/schule.yaml"} <= set(namen)
    metadaten = zipfile.ZipFile(wheel).read(next(n for n in namen if n.endswith("METADATA"))).decode()
    assert re.search(r"Requires-Dist: ortools.*sys_platform != .emscripten.", metadaten)  # im Browser nicht installiert
    assert (ziel / "komponenten" / "gebietskarte" / "index.html").exists()
    assert (ziel / "komponenten" / "gebietskarte" / "leaflet" / "leaflet.js").exists()
    assert {p.name for p in ziel.iterdir()} == {"index.html", "icon.svg", "komponenten", wheel.name}


def test_runtime_flag():
    code = "from skf import runtime; print(runtime.IN_BROWSER, runtime.RECHEN_URL)"
    out = subprocess.run([sys.executable, "-c", code], env=dict(os.environ, SKF_BROWSER="1"),
                         capture_output=True, text=True, cwd=WURZEL)
    assert out.stdout.split() == ["True", "/api/rechnen"]


def test_web_entry_fuehrt_app_einmal_aus():
    seite = (WURZEL / "web" / "index.html").read_text(encoding="utf-8")
    block = re.search(r'"streamlit_app\.py": \[(.*?)\]\.join', seite, re.S).group(1)
    code = "\n".join(json.loads("[" + block.strip().rstrip(",") + "]")) + "\n"
    assert "import skf.app" not in code and "find_spec('skf.app')" in code
    compile(code, "streamlit_app.py", "exec")


def test_ohne_ortools_importierbar_und_ergebnis_lesbar(tmp_path):
    """Im Browser fehlt OR-Tools: die Module müssen trotzdem laden und das Ergebnis vom Server entpacken."""
    status, text = bearbeite(anfrage(_cfg(), "Basis", lade_kinder(VORLAGE / "kinder.csv"), 20))
    assert status == 200
    (tmp_path / "antwort.json").write_text(text, encoding="utf-8")
    code = OHNE_ORTOOLS + f"""
import base64, json, pickle, zlib
import skf, skf.ablauf, skf.bericht, skf.datenablage, skf.fernrechnen, skf.uebertritt, skf.verlauf
assert skf.solver.cp_model is None
a = json.load(open({str(tmp_path / 'antwort.json')!r}, encoding="utf-8"))
r = pickle.loads(zlib.decompress(base64.b64decode(a["ergebnis"])))
print(len(r.einteilung.klassen), r.kennzahlen()["Klassen"], bool(r.lektionen))
"""
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=WURZEL)
    assert out.returncode == 0, out.stderr
    n, kz, plan = out.stdout.split()
    assert n == kz and plan == "True"


def test_rechnen_ueber_server_wie_lokal(server):
    schule, kinder = lade_schule(VORLAGE / "schule.yaml"), lade_kinder(VORLAGE / "kinder.csv")
    zeilen = []
    fern = rechne_fern(_cfg(), "Basis", kinder, zeitlimit=30, protokoll=zeilen.append, url=server)
    lokal = rechne(schule, kinder, zeitlimit=30, protokoll=lambda t: None)
    assert fern.vollstaendig and not fern.anzahl("Fehler") and zeilen
    assert fern.einteilung.klasse_von == lokal.einteilung.klasse_von          # dieselbe Rechnung
    assert [i.zielwert for i in fern.infos] == [i.zielwert for i in lokal.infos]
    assert [k.name for k in fern.kinder] == [k.name for k in kinder]          # Namen wieder eingesetzt
    assert any(k.name for k in fern.kinder)


def test_datensparsam():
    kinder = lade_kinder(VORLAGE / "kinder.csv")
    gesendet = json.loads(anfrage(_cfg(), "Basis", kinder, 30))["kinder"]
    assert all(not set(NUR_IM_BROWSER) & set(d) for d in gesendet)
    text = json.dumps(gesendet, ensure_ascii=False)
    assert not any(k.name and k.name in text for k in kinder)
    assert not any(k.adresse and k.adresse in text for k in kinder)


@pytest.mark.parametrize("aendern, status, meldung", [
    (lambda a: a.update(version="0.0.0"), 409, "neu laden"),
    (lambda a: a["kinder"][0].update(passwort="x"), 400, "unbekannte Angaben"),
    (lambda a: a["kinder"][0].update(name="Max Muster"), 400, "unbekannte Angaben"),
    (lambda a: a["konfiguration"].update(basis_profil="../../etc/passwd"), 400, "Kantonsprofil"),
    (lambda a: a.update(kinder="alle"), 400, "Liste"),
])
def test_server_lehnt_fehlerhafte_anfragen_ab(aendern, status, meldung):
    a = json.loads(anfrage(_cfg(), "Basis", lade_kinder(VORLAGE / "kinder.csv"), 5))
    aendern(a)
    s, text = bearbeite(json.dumps(a))
    assert s == status and meldung in json.loads(text)["fehler"]


def test_server_grenzen():
    assert bearbeite("x" * 9_000_000)[0] == 413
    assert bearbeite("kein json")[0] == 400


def test_server_rechenzeit_begrenzt(monkeypatch):
    from skf import ablauf, fernrechnen
    gesehen = {}

    def falsch_rechnen(schule, kinder, zeitlimit, nur_klassen, protokoll):
        gesehen["zeit"] = zeitlimit
        return ablauf.Ergebnis(schule, kinder)
    monkeypatch.setattr(ablauf, "rechne", falsch_rechnen)
    s, _ = fernrechnen.bearbeite(anfrage(_cfg(), "Basis", lade_kinder(VORLAGE / "kinder.csv"), 10_000))
    assert s == 200 and gesehen["zeit"] == fernrechnen.MAX_RECHENZEIT


def test_server_abhaengigkeiten_wie_uv_lock():
    lock = (WURZEL / "uv.lock").read_text(encoding="utf-8")
    for zeile in (WURZEL / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if zeile and not zeile.startswith("#"):
            name, version = zeile.split("==")
            assert f'name = "{name}"\nversion = "{version}"' in lock, f"{name}=={version} nicht in uv.lock"


def test_ergebnis_antwort_kompakt():
    """Vercel begrenzt Antworten auf 4.5 MB – das Ergebnis kommt komprimiert."""
    status, text = bearbeite(anfrage(_cfg(), "Basis", lade_kinder(VORLAGE / "kinder.csv"), 20))
    r = pickle.loads(zlib.decompress(base64.b64decode(json.loads(text)["ergebnis"])))
    assert status == 200 and len(text) < 200_000 and r.einteilung

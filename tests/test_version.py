# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Eine Version überall: Programm, Paket, Lockdatei, Changelog, Ausgaben."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import skf
from skf.austausch import exportiere_stammdaten, importiere_stammdaten, lese_rohkonfiguration
from skf.cli import main

WURZEL = Path(__file__).parent.parent
VORLAGE = WURZEL / "beispiele" / "vorlage"


def test_alle_versionsangaben_stimmen_ueberein():
    aus = subprocess.run([sys.executable, str(WURZEL / "scripts" / "version.py")], capture_output=True, text=True)
    assert aus.returncode == 0, aus.stdout + aus.stderr
    assert re.fullmatch(r"\d+\.\d+\.\d+", skf.__version__)
    assert f"## [{skf.__version__}]" in (WURZEL / "CHANGELOG.md").read_text(encoding="utf-8")


def test_cli_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert skf.__version__ in capsys.readouterr().out


def test_export_traegt_programmversion_und_neueres_format_wird_abgelehnt(tmp_path):
    from skf.austausch import lese_kinder
    cfg = lese_rohkonfiguration(VORLAGE / "schule.yaml")
    pfad = tmp_path / "daten.json"
    exportiere_stammdaten(cfg, lese_kinder(VORLAGE / "kinder.csv"), pfad)
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    assert daten["programm"] == skf.__version__ and daten["version"] == 1
    daten["version"] = 99
    pfad.write_text(json.dumps(daten), encoding="utf-8")
    with pytest.raises(ValueError, match="neueren Programmversion"):
        importiere_stammdaten(pfad)


def test_ausgaben_nennen_die_version(tmp_path):
    from skf.ablauf import rechne
    from skf.bericht import schreibe_html
    from skf.daten import lade_kinder, lade_schule
    from skf.export import exportiere_listen
    r = rechne(lade_schule(VORLAGE / "schule.yaml"), lade_kinder(VORLAGE / "kinder.csv"), zeitlimit=20,
               protokoll=lambda *_: None)
    schreibe_html(tmp_path / "bericht.html", r)
    exportiere_listen(r, tmp_path)
    assert f"Stundenplan {skf.__version__}" in (tmp_path / "bericht.html").read_text(encoding="utf-8")
    assert f"Klassenbildung {skf.__version__}" in (tmp_path / "druck.html").read_text(encoding="utf-8")
    assert "Profilversion 2026.10.1" in (tmp_path / "bericht.html").read_text(encoding="utf-8")

# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Daten bleiben ausserhalb der App erhalten: offen, dokumentiert, maschinen- und menschenlesbar."""
import csv
import json
from pathlib import Path

import pytest

from skf import verlauf
from skf.ablauf import rechne
from skf.austausch import importiere_stammdaten, lese_kinder, lese_rohkonfiguration
from skf.daten import lade_schule
from skf.datenablage import arbeitsstand_info, lade_arbeitsstand, speichere_arbeitsstand

jsonschema = pytest.importorskip("jsonschema")
WURZEL = Path(__file__).parent.parent
VORLAGE = WURZEL / "beispiele" / "vorlage"


@pytest.fixture(scope="module")
def stand(tmp_path_factory):
    ordner = tmp_path_factory.mktemp("verlauf")
    r = rechne(lade_schule(VORLAGE / "schule.yaml"), lese_kinder(VORLAGE / "kinder.csv"), zeitlimit=20,
               protokoll=lambda *_: None)
    return verlauf.speichere(r, lese_rohkonfiguration(VORLAGE / "schule.yaml"), "Test", ordner), r


def _schema(name):
    return json.loads((WURZEL / "schema" / name).read_text(encoding="utf-8"))


def test_stand_enthaelt_menschen_und_maschinenlesbares(stand):
    ordner, _ = stand
    for datei in ("LIESMICH.txt", "meta.json", "zuteilung.json", "ergebnis.json", "stammdaten.json",
                  "stammdaten.xlsx", "einteilung.csv", "klassen.csv", "lehrauftraege.csv", "stundenplan.csv",
                  "meldungen.csv", "bericht.html", "klassenlisten.xlsx", "stundenplaene.xlsx", "druck.html"):
        assert (ordner / datei).exists(), datei
    liesmich = (ordner / "LIESMICH.txt").read_text(encoding="utf-8")
    assert "ergebnis.json" in liesmich and "docs/datenformate.md" in liesmich


def test_ergebnis_json_entspricht_schema_und_ergebnis(stand):
    ordner, r = stand
    daten = json.loads((ordner / "ergebnis.json").read_text(encoding="utf-8"))
    jsonschema.validate(daten, _schema("skf-ergebnis.schema.json"))
    assert daten["vollstaendig"] and len(daten["klassen"]) == len(r.einteilung.klassen)
    assert set(daten["zuteilung"]) == {k.id for k in r.kinder}
    assert len(daten["stundenplan"]) == len(r.lektionen)
    with open(ordner / "einteilung.csv", encoding="utf-8") as f:  # CSV und JSON sagen dasselbe
        assert {z["id"]: z["klasse"] for z in csv.DictReader(f)} == \
            {k: v["klasse"] for k, v in daten["zuteilung"].items()}


def test_stammdaten_json_entspricht_schema_und_ist_wieder_lesbar(stand):
    ordner, r = stand
    daten = json.loads((ordner / "stammdaten.json").read_text(encoding="utf-8"))
    jsonschema.validate(daten, _schema("skf-stammdaten.schema.json"))
    cfg, kinder = importiere_stammdaten(ordner / "stammdaten.json")
    assert [k.id for k in kinder] == [k.id for k in r.kinder]


def test_arbeitsstand_sichern_und_fortsetzen(tmp_path, monkeypatch):
    monkeypatch.setenv("SKF_DATEN", str(tmp_path))
    assert arbeitsstand_info() is None
    cfg = lese_rohkonfiguration(VORLAGE / "schule.yaml")
    kinder = lese_kinder(VORLAGE / "kinder.csv")
    ordner = speichere_arbeitsstand(cfg, kinder)
    assert {p.name for p in ordner.iterdir()} == {"stammdaten.json", "schule.yaml", "kinder.csv", "LIESMICH.txt"}
    info = arbeitsstand_info()
    assert info["lernende"] == len(kinder) and info["schule"] == cfg["name"]
    cfg2, kinder2 = lade_arbeitsstand()
    assert cfg2["name"] == cfg["name"] and len(kinder2) == len(kinder)
    assert lese_kinder(ordner / "kinder.csv")[0].id == kinder[0].id  # auch ohne App lesbar

# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Schuljahreswechsel: jede Stufe hat eine nächste Stufe (KG → Primar → Sek A/B/C, Kanti = Austritt)."""
import csv
from pathlib import Path

import pytest
import yaml

from skf.austausch import normalisiere_jahrgang
from skf.cli import main
from skf.daten import Kind, baue_schule
from skf.klassen import geschwistergruppen
from skf.uebertritt import naechste, naechstes_schuljahr, schuljahreswechsel, zusammenfassung

VORLAGE = Path(__file__).parent.parent / "beispiele" / "vorlage"
SEK = ["S1A", "S1B", "S1C", "S2A", "S2B", "S2C", "S3A", "S3B", "S3C"]


@pytest.fixture
def schule():
    cfg = yaml.safe_load((VORLAGE / "schule.yaml").read_text(encoding="utf-8"))
    cfg["jahrgaenge"] = cfg["jahrgaenge"] + ["3", "4", "5", "6"] + SEK
    return baue_schule(cfg)


def kind(i, jg, entscheid="", **kw):
    return Kind(i, i, jg, "w", "", 47.03, 8.18, uebertritt=entscheid, **kw)


def test_naechste_stufe(schule):
    f = naechste(schule)
    assert f["KG1"] == ["KG2"] and f["KG2"] == ["1"] and f["5"] == ["6"]
    assert f["6"] == ["S1A", "S1B", "S1C"]
    assert f["S1B"][0] == "S2B" and f["S3C"] == ["Abschluss"]


@pytest.mark.parametrize("jg, entscheid, nach, art", [
    ("KG2", "", "1", "Übertritt Kindergarten → Primar"),
    ("3", "", "4", "Aufstieg"),
    ("6", "Sek A", "S1A", "Übertritt Primar → Sek A"),
    ("6", "B", "S1B", "Übertritt Primar → Sek B"),
    ("6", "Niveau C", "S1C", "Übertritt Primar → Sek C"),
    ("6", "Kanti", "Kanti", "Austritt: Kanti"),
    ("6", "Langzeitgymnasium", "Langzeitgymnasium", "Austritt: Langzeitgymnasium"),
    ("4", "Wegzug", "Wegzug", "Austritt: Wegzug"),
    ("3", "repetiert", "3", "Repetition"),
    ("2", "überspringt", "4", "Überspringt eine Stufe"),
    ("S1A", "", "S2A", "Aufstieg"),
    ("S1A", "B", "S2B", "Umstufung A → B"),
    ("S2C", "Kurzzeitgymnasium", "Kurzzeitgymnasium", "Austritt: Kurzzeitgymnasium"),
    ("S3B", "", "Abschluss", "Abschluss"),
    ("6", "", "6", "Entscheid fehlt"),
    ("6", "Niveau Z", "6", "Entscheid fehlt"),
])
def test_schritte(schule, jg, entscheid, nach, art):
    _, prot = schuljahreswechsel(schule, [kind("x", jg, entscheid)])
    assert (prot[0].nach, prot[0].art) == (nach, art)


def test_bisherige_klasse_und_wuensche(schule):
    alt = [kind("a", "KG2", zusammen_mit=["b"]), kind("b", "KG2"), kind("c", "6", "Kanti")]
    neu, prot = schuljahreswechsel(schule, alt, {"a": "A KGa", "b": "A KGa"}, {"a": "Schulhaus A"},
                                   neueintritte=[kind("n1", "KG1")])
    nach_id = {k.id: k for k in neu}
    assert set(nach_id) == {"a", "b", "n1"}                     # Kanti = Austritt
    assert nach_id["a"].bisherige_klasse == "A KGa"              # Gspänli-Regel im neuen Jahr
    assert nach_id["a"].bisheriges_schulhaus == "Schulhaus A"
    assert nach_id["a"].zusammen_mit == []                       # Wünsche gelten ein Jahr
    assert dict(zusammenfassung(prot))["Neueintritt"] == 1


def test_schule_ohne_oberstufe(schule):
    cfg = yaml.safe_load((VORLAGE / "schule.yaml").read_text(encoding="utf-8"))
    cfg["jahrgaenge"] = cfg["jahrgaenge"] + ["3", "4", "5", "6"]
    primar = baue_schule(cfg)
    _, prot = schuljahreswechsel(primar, [kind("x", "6", "A"), kind("y", "6", "Kanti")])
    assert [p.art for p in prot] == ["Austritt: Oberstufe (andere Schule)", "Austritt: Kanti"]


def test_jahrgang_schreibweisen():
    assert [normalisiere_jahrgang(x) for x in ("1. Sek A", "Sek 2 B", "S3C", "2. Sek")] == ["S1A", "S2B", "S3C", "S2"]
    assert naechstes_schuljahr("2027/28") == "2028/29"


def test_geschwister_primar_und_oberstufe_getrennt():
    cfg = yaml.safe_load((VORLAGE / "schule.yaml").read_text(encoding="utf-8"))
    cfg["jahrgaenge"] = cfg["jahrgaenge"] + ["S1A"]
    cfg["schulhaeuser"].append({"name": "OS", "lat": 47.03, "lon": 8.18,
                                "raeume": [{"typ": "Klassenzimmer", "anzahl": 2}]})
    for v in cfg["klassenbildung"]["vorlagen"]:  # Primar nur in den Primarschulhäusern
        v["schulhaeuser"] = ["Schulhaus A", "Schulhaus B"]
    cfg["klassenbildung"]["vorlagen"].append({"jahrgaenge": ["S1A"], "min": 1, "max": 24, "schulhaeuser": ["OS"]})
    s = baue_schule(cfg)
    gruppen = geschwistergruppen(s, [kind("p", "1", familie="F"), kind("q", "2", familie="F"),
                                     kind("o", "S1A", familie="F")])
    assert sorted(map(sorted, gruppen["F"])) == [["o"], ["p", "q"]]


def test_cli(tmp_path, capsys):
    pfad = tmp_path / "jetzt.csv"
    with open(pfad, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["id", "jahrgang", "lat", "lon", "Klasse", "Übertritt"])
        wr.writerows([["K1", "KG2", 47.03, 8.18, "A KGa", ""], ["K2", "1", 47.03, 8.18, "A 1a", "repetiert"],
                      ["K3", "2", 47.03, 8.18, "A 2a", "Wegzug"]])
    main(["uebertritt", str(VORLAGE / "schule.yaml"), str(pfad), "-o", str(tmp_path / "neu.csv")])
    aus = capsys.readouterr().out
    assert "3 → 2 Lernende" in aus and "Austritt: Wegzug" in aus
    with open(tmp_path / "neu.csv", encoding="utf-8") as f:
        neu = {z["id"]: z for z in csv.DictReader(f)}
    assert neu["K1"]["jahrgang"] == "1" and neu["K1"]["bisherige_klasse"] == "A KGa"
    assert neu["K2"]["jahrgang"] == "1"
    assert (tmp_path / "neu_uebertritte.csv").exists()

# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Alltagsfälle, die eine Berechnung nicht blockieren dürfen – oder klar gemeldet werden müssen."""
import copy
from pathlib import Path

from skf.ablauf import rechne
from skf.bericht import schreibe_html
from skf.daten import lade_kinder, lade_schule

VORLAGE = Path(__file__).parent.parent / "beispiele" / "vorlage"


def _rechne(kinder, t=20):
    return rechne(lade_schule(VORLAGE / "schule.yaml"), kinder, zeitlimit=t, protokoll=lambda *_: None)


def test_ohne_lernende_klare_meldung():
    r = _rechne([])
    assert any(m.schwere == "Fehler" and "Keine Lernenden" in m.text for m in r.meldungen)


def test_wunsch_auf_weggezogenes_kind_blockiert_nicht():
    kinder = lade_kinder(VORLAGE / "kinder.csv")
    kinder[0].zusammen_mit = ["WEGGEZOGEN"]
    kinder[1].nicht_mit = ["AUCH-WEG"]
    r = _rechne(kinder)
    assert r.vollstaendig and r.anzahl("Fehler") == 0
    assert any(m.schwere == "Warnung" and "WEGGEZOGEN" in m.text for m in r.meldungen)


def test_lernende_ohne_koordinaten_werden_eingeteilt(tmp_path):
    kinder = copy.deepcopy(lade_kinder(VORLAGE / "kinder.csv"))
    for k in kinder[:10]:
        k.lat = k.lon = None
    r = _rechne(kinder)
    assert r.vollstaendig and r.anzahl("Fehler") == 0
    assert {k.id for k in kinder[:10]} <= set(r.einteilung.klasse_von)
    assert any("ohne Koordinaten" in m.text and m.schwere == "Warnung" for m in r.meldungen)
    schreibe_html(tmp_path / "bericht.html", r)  # Karte ohne diese Punkte, kein Absturz
    assert "km" in r.kennzahlen()["Ø Schulweg"]

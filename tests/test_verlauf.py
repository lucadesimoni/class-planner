# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Verlauf, Vergleich zweier Stände, manuelles Verschieben, Kartendaten (Klassen/Geschwister)."""
from pathlib import Path

import yaml

from skf import lade_kinder, lade_schule, verlauf
from skf.ablauf import rechne, verschiebe
from skf.bericht import karten_daten

VORLAGE = Path(__file__).parent.parent / "beispiele" / "vorlage"


def _ergebnis():
    return rechne(lade_schule(VORLAGE / "schule.yaml"), lade_kinder(VORLAGE / "kinder.csv"), zeitlimit=20,
                  nur_klassen=True, protokoll=lambda *_: None)


def test_verlauf_speichern_vergleichen_kindverlauf(tmp_path):
    cfg = yaml.safe_load((VORLAGE / "schule.yaml").read_text(encoding="utf-8"))
    r = _ergebnis()
    verlauf.speichere(r, cfg, "erster Stand", ordner=tmp_path)
    kind = next(k for k in r.kinder if k.jahrgang == "1")
    ziel = next(c.name for c in r.einteilung.klassen
                if "1" in c.vorlage.jahrgaenge and c.name != r.einteilung.klasse_von[kind.id])
    alt = r.einteilung.klasse_von[kind.id]
    verschiebe(r, kind.id, ziel)
    assert r.einteilung.klasse_von[kind.id] == ziel and r.manuell
    assert any(m.bereich == "Manuell" for m in r.meldungen)
    import time
    time.sleep(1.1)  # eindeutiger Zeitstempel im Ordnernamen
    verlauf.speichere(r, cfg, "manuell", ordner=tmp_path)

    staende = verlauf.staende(tmp_path)
    assert [s["notiz"] for s in staende] == ["manuell", "erster Stand"]
    v = verlauf.vergleiche(staende[1], staende[0])
    assert v["gewechselt"] == [{"id": kind.id, "vorher": alt, "nachher": ziel,
                                "schulhaus_gewechselt": alt.split()[0] != ziel.split()[0]}]
    historie = verlauf.kind_verlauf(kind.id, tmp_path)
    assert [h["klasse"] for h in historie] == [ziel, alt]
    for datei in ("meta.json", "zuteilung.json", "stammdaten.xlsx", "bericht.html", "klassenlisten.xlsx"):
        assert (Path(staende[0]["ordner"]) / datei).exists()


def test_karten_daten_klassen_und_geschwister():
    r = _ergebnis()
    d = karten_daten(r)
    assert set(d["klassen"]) == {c.name for c in r.einteilung.klassen}
    assert len(d["kinder"]) == len(r.kinder)
    familien = {}
    for k in r.kinder:
        if k.familie:
            familien.setdefault(k.familie, []).append(k)
    mehrfach = [f for f in familien.values() if len(f) > 1]
    assert len(d["familien"]) == len(mehrfach)
    getrennt = sum(len({r.einteilung.schulhaus_von[k.id] for k in f}) > 1 for f in mehrfach)
    assert d["getrennt"] == getrennt
    assert all("Geschwister" in d["kinder"][i]["t"] for f in d["familien"] for i in f["kinder"])

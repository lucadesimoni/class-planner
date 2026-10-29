# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""End-to-end-Tests an einer kleinen Schule mit zwei Schulhäusern."""
import csv
import random

import pytest

from skf import erstelle_stundenplan, lade_kinder, lade_schule, teile_ein, verteile_lehrauftraege
from skf.cli import main
from skf.pruefung import pruefe
from skf.solver import KeineLoesung

SCHULE = """
name: Testschule
jahrgaenge: ["1", "2"]
schulhaeuser:
  - {name: Nord, kuerzel: N, lat: 47.05, lon: 8.18,
     raeume: [{typ: Klassenzimmer, anzahl: 2, plaetze: 24}, {typ: Turnhalle, plaetze: 30}]}
  - {name: Sued, kuerzel: S, lat: 47.02, lon: 8.18,
     raeume: [{typ: Klassenzimmer, anzahl: 2, plaetze: 20}], nutzt: {Turnhalle: Nord}}
klassenbildung:
  max_schulweg_m: {default: 4000}
  vorlagen:
    - {jahrgaenge: ["1"], min: 10, max: 24}
    - {jahrgaenge: ["2"], min: 10, max: 24}
    - {jahrgaenge: ["1", "2"], min: 10, max: 20, strafe: 100}
zeitraster:
  halbtage: {VM: ["08:00", "08:50", "09:55"], NM: ["13:30", "14:20"]}
  frei: [Mi-NM]
faecher:
  Deutsch: {max_pro_tag: 2}
  Mathematik: {max_pro_tag: 2}
  Werken: {dauer: 2}
  Sport: {raumtyp: Turnhalle, max_pro_tag: 1}
stundentafel:
  "1": {Deutsch: 6, Mathematik: 5, Werken: 2, Sport: 2}
  "2": {Deutsch: 6, Mathematik: 6, Werken: 2, Sport: 3}
lehrpersonen:
  - {name: A, faecher: [Deutsch, Mathematik, Werken], schulhaeuser: Nord, pensum: [10, 25]}
  - {name: B, faecher: [Deutsch, Mathematik, Werken], schulhaeuser: Nord, pensum: [10, 25], nicht_verfuegbar: [Fr-NM]}
  - {name: C, faecher: [Deutsch, Mathematik, Werken], schulhaeuser: Sued, pensum: [10, 25]}
  - {name: D, faecher: [Deutsch, Mathematik, Werken], schulhaeuser: Sued, pensum: [10, 25], nicht_verfuegbar: [Mo-VM-1]}
  - {name: Sport, faecher: [Sport]}
"""


def kinder_csv(pfad, n=70, seed=1):
    rnd = random.Random(seed)
    with open(pfad, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["id", "jahrgang", "geschlecht", "lat", "lon", "familie", "foerderbedarf", "nicht_mit"])
        for i in range(n):
            nord = i % 3 != 0
            wr.writerow([f"K{i:03d}", "12"[i % 2], "wm"[rnd.random() < 0.5],
                         47.05 - 0.004 * rnd.random() if nord else 47.02 + 0.004 * rnd.random(),
                         8.18 + 0.004 * rnd.random(), f"F{i // 3}" if i < 9 else "",
                         "ja" if i % 7 == 0 else "", "K011" if i == 13 else ""])


@pytest.fixture
def daten(tmp_path):
    (tmp_path / "schule.yaml").write_text(SCHULE)
    kinder_csv(tmp_path / "kinder.csv")
    return lade_schule(tmp_path / "schule.yaml"), lade_kinder(tmp_path / "kinder.csv"), tmp_path


def test_slots_und_verfuegbarkeit(daten):
    schule, _, _ = daten
    assert len(schule.slots) == 5 * 3 + 4 * 2
    b = next(lp for lp in schule.lehrpersonen if lp.name == "B")
    assert len(b.nicht_verfuegbar) == 2
    d = next(lp for lp in schule.lehrpersonen if lp.name == "D")
    assert [schule.slots[i].label for i in d.nicht_verfuegbar] == ["Mo 08:00"]


def test_gesamter_ablauf_erfuellt_alle_regeln(daten):
    schule, kinder, _ = daten
    e = teile_ein(schule, kinder, zeitlimit=20)
    assert sorted(len(c.kinder) for c in e.klassen) == sorted(c.groesse for c in e.klassen)
    bloecke, _ = verteile_lehrauftraege(schule, e.klassen, zeitlimit=10)
    lektionen, infos, _ = erstelle_stundenplan(schule, e.klassen, bloecke, zeitlimit=30)
    assert pruefe(schule, kinder, e, bloecke, lektionen) == []
    # Sued nutzt die Turnhalle von Nord -> ein gemeinsames Modell
    assert len(infos) == 1


def test_kurze_schulwege(daten):
    schule, kinder, _ = daten
    e = teile_ein(schule, kinder, zeitlimit=20)
    # Kinder sitzen nahe an "ihrem" Schulhaus; Kapazität Sued (2x20) reicht für ~23 Kinder
    sued = [k for k in kinder if k.lat < 47.03]
    assert sum(e.schulhaus_von[k.id] == "Sued" for k in sued) == len(sued)


def test_nicht_mit_wird_eingehalten(daten):
    schule, kinder, _ = daten
    e = teile_ein(schule, kinder, zeitlimit=20)
    k11, k13 = (next(k for k in kinder if k.id == i) for i in ("K011", "K013"))
    sh = e.schulhaus_von["K011"]
    parallel = [c for c in e.klassen if c.schulhaus == sh and k11.jahrgang in c.jahrgaenge]
    if e.schulhaus_von["K013"] == sh and len(parallel) > 1:
        assert e.klasse_von["K013"] != e.klasse_von["K011"]
    assert "K011" in k13.nicht_mit


def test_schulhaus_fix(daten):
    schule, kinder, _ = daten
    kinder[0].schulhaus_fix = "Sued"
    e = teile_ein(schule, kinder, zeitlimit=20)
    assert e.schulhaus_von[kinder[0].id] == "Sued"


def test_zu_wenig_platz_meldet_fehler(daten):
    schule, kinder, tmp = daten
    kinder_csv(tmp / "viele.csv", n=200)
    with pytest.raises(KeineLoesung):
        teile_ein(schule, lade_kinder(tmp / "viele.csv"), zeitlimit=10)


def test_cli(daten, capsys):
    _, _, tmp = daten
    main([str(tmp / "schule.yaml"), str(tmp / "kinder.csv"), "-o", str(tmp / "out"), "-t", "40"])
    assert "0 Fehler" in capsys.readouterr().out
    for datei in ("einteilung.csv", "klassen.csv", "lehrauftraege.csv", "stundenplan.csv", "meldungen.csv",
                  "bericht.html"):
        assert (tmp / "out" / datei).stat().st_size > 0


def test_blockzeiten_unerfuellbar_wird_frueh_erkannt(daten):
    """Fehlt B am Freitag, können A und Sport die Freitagmorgen von Nord nicht abdecken."""
    schule, kinder, _ = daten
    b = next(lp for lp in schule.lehrpersonen if lp.name == "B")
    b.nicht_verfuegbar = {s.index for s in schule.slots if s.tag == "Fr"}
    e = teile_ein(schule, kinder, zeitlimit=20)
    with pytest.raises(KeineLoesung, match="Lehraufträge"):
        verteile_lehrauftraege(schule, e.klassen, zeitlimit=10)

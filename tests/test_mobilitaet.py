# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Schulbus und Wegzeiten der Lehrpersonen (optionale Regeln für Dörfer mit Weilern)."""
import csv

import pytest

from skf.ablauf import rechne
from skf.daten import lade_kinder, lade_schule
from skf.mobilitaet import bus_halbtag, halbtage_der_klasse, wegzeit, zu_knapp
from skf.pruefung import pruefe, vorpruefung
from skf.stundenplan import Lektion
from skf.transparenz import regeln
from tests.test_klein import SCHULE, kinder_csv

MUSIK = """
  - {name: M, faecher: [Musik], schulhaeuser: [Nord, Sued], pensum: [0, 20]}
"""
BUS = """
schulbus:
  wartezeit_max: 15
  linien:
    - name: Linie Berg
      schulhaeuser: [Sued]
      ankunft: {VM: "07:50", NM: "13:20"}
      abfahrt: {VM: "10:45", NM: ["15:10"]}
"""
WEG = """
wegzeiten:
  minuten: {Nord-Sued: 30}
"""


def _schule(tmp_path, zusatz="", kinder_bus=(), weit_weg=()):
    text = SCHULE.replace('  Sport: {raumtyp: Turnhalle, max_pro_tag: 1}\n',
                          '  Sport: {raumtyp: Turnhalle, max_pro_tag: 1}\n  Musik: {max_pro_tag: 1}\n')
    text = text.replace('"1": {Deutsch: 6, Mathematik: 5, Werken: 2, Sport: 2}',
                        '"1": {Deutsch: 6, Mathematik: 5, Werken: 2, Sport: 2, Musik: 2}')
    text = text.replace('"2": {Deutsch: 6, Mathematik: 6, Werken: 2, Sport: 3}',
                        '"2": {Deutsch: 6, Mathematik: 6, Werken: 2, Sport: 3, Musik: 2}')
    text = text.rstrip() + MUSIK + zusatz
    (tmp_path / "schule.yaml").write_text(text, encoding="utf-8")
    kinder_csv(tmp_path / "roh.csv")
    with open(tmp_path / "roh.csv") as f:
        zeilen = list(csv.DictReader(f))
    for z in zeilen:
        z["bus"] = "Linie Berg" if z["id"] in kinder_bus else ""
        if z["id"] in weit_weg:
            z["lat"] = "47.10"  # über 4 km von jedem Schulhaus
    with open(tmp_path / "kinder.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(zeilen[0]))
        wr.writeheader()
        wr.writerows(zeilen)
    return lade_schule(tmp_path / "schule.yaml"), lade_kinder(tmp_path / "kinder.csv")


def test_bus_halbtag_logik(tmp_path):
    schule, _ = _schule(tmp_path, BUS)
    hs = halbtage_der_klasse(schule, "Sued")
    vm = hs["Mo", "VM"]
    moeglich, ende_ok, _ = bus_halbtag(schule, {"Linie Berg"}, vm)
    assert moeglich and ende_ok == {vm[-1].index}          # 09:55 + 45 = 10:40, Abfahrt 10:45
    nm = hs["Mo", "NM"]
    moeglich, ende_ok, _ = bus_halbtag(schule, {"Linie Berg"}, nm)
    assert moeglich and ende_ok == {nm[-1].index}          # nur 15:05 passt zu 15:10


def test_schulbus_bindet_schulhaus_und_unterrichtsschluss(tmp_path):
    bus = {"K001", "K002", "K004", "K005", "K007", "K008"}  # wohnen bei Nord
    schule, kinder = _schule(tmp_path, BUS, kinder_bus=bus, weit_weg={"K001"})
    r = rechne(schule, kinder, zeitlimit=40, protokoll=lambda *_: None)
    assert r.vollstaendig and r.anzahl("Fehler") == 0, [m.text for m in r.meldungen if m.schwere == "Fehler"]
    e = r.einteilung
    assert {e.schulhaus_von[k] for k in bus} == {"Sued"}
    # kein Schulweg-Hinweis für Buskinder, obwohl K001 weit weg wohnt
    assert not any("K001" in m.text and "Schulweg" in m.text for m in r.meldungen)
    # Klassen mit Buskindern: Nachmittag ganz oder gar nicht (Bus fährt erst 15:10)
    for c in e.klassen:
        if set(c.kinder) & bus:
            nm = {}
            for l in r.lektionen:
                s = schule.slots[l.slot]
                if l.klasse == c.name and l.art == "unterricht" and s.halbtag == "NM":
                    nm.setdefault(s.tag, set()).add(s.nr)
            assert all(nrs == {0, 1} for nrs in nm.values()), nm
    assert any(x["regel"].startswith("Schulbus") for x in regeln(r))


def test_unpassender_bus_wird_erklaert(tmp_path):
    zu_frueh = BUS.replace('NM: "13:20"', 'NM: "12:00"')
    schule, kinder = _schule(tmp_path, zu_frueh, kinder_bus={f"K{i:03d}" for i in range(1, 70, 2)})
    assert any("Ankunft passt nicht" in m.text for m in vorpruefung(schule, kinder))
    r = rechne(schule, kinder, zeitlimit=20, protokoll=lambda *_: None)
    fehler = " ".join(m.text for m in r.meldungen if m.schwere == "Fehler")
    assert "Schulbus" in fehler


def test_unbekannte_buslinie_ist_fehler(tmp_path):
    schule, kinder = _schule(tmp_path, BUS, kinder_bus={"K003"})
    kinder[3].bus = "Linie X"
    assert any("unbekannte Buslinie 'Linie X'" in m.text for m in vorpruefung(schule, kinder))


def test_wegzeiten(tmp_path):
    schule, kinder = _schule(tmp_path, WEG)
    assert wegzeit(schule, "Nord", "Sued") == 30
    knapp = zu_knapp(schule)
    mo = [s for s in schule.slots if s.tag == "Mo"]
    assert (mo[0].index, mo[1].index) in knapp["Nord", "Sued"]        # 5 min Pause
    assert (mo[2].index, mo[3].index) not in knapp["Nord", "Sued"]    # Mittag
    r = rechne(schule, kinder, zeitlimit=40, protokoll=lambda *_: None)
    assert r.vollstaendig and r.anzahl("Fehler") == 0, [m.text for m in r.meldungen if m.schwere == "Fehler"]
    wo = {(l.lehrperson, l.slot): l.raum_ort for l in r.lektionen}
    for (a, b), paare in knapp.items():
        for s1, s2 in paare:
            assert not (wo.get(("M", s1)) == a and wo.get(("M", s2)) == b)
    assert any(x["regel"].startswith("Wegzeiten") and x["verstoesse"] == 0 for x in regeln(r))


def test_wegzeit_aus_koordinaten_und_pruefung(tmp_path):
    schule, kinder = _schule(tmp_path, "\nwegzeiten: true\n")
    # 3.3 km Luftlinie × 1.3 Umweg bei 20 km/h ≈ 13 min
    assert 12 <= wegzeit(schule, "Nord", "Sued") <= 14
    mo = [s for s in schule.slots if s.tag == "Mo"]
    r = rechne(schule, kinder, zeitlimit=20, nur_klassen=True, protokoll=lambda *_: None)
    nord = next(c.name for c in r.einteilung.klassen if c.schulhaus == "Nord")
    sued = next(c.name for c in r.einteilung.klassen if c.schulhaus == "Sued")
    falsch = [Lektion(nord, "Musik", "M", mo[0].index, "Zi", "Nord", "Nord"),
              Lektion(sued, "Musik", "M", mo[1].index, "Zi", "Sued", "Sued")]
    texte = [m.text for m in pruefe(schule, kinder, r.einteilung, [], falsch)]
    assert any("Wegzeit Nord → Sued" in t for t in texte), texte

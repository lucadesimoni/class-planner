# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Szenarien, Gewichte, Verfügbarkeit von Schulhäusern/Räumen und Meldungen."""
import pytest

from skf import lade_kinder, lade_schule
from skf.ablauf import rechne
from skf.cli import main
from skf.daten import _mische, szenarien
from tests.test_klein import SCHULE, kinder_csv

SZENARIEN = """
szenarien:
  Schulweg wichtig:
    gewichte: {schulweg_pro_km: 900}
  Sued kleiner:
    schulhaeuser:
      - {name: Sued, raeume: [{typ: Klassenzimmer, anzahl: 1, plaetze: 20}]}
  Ohne D:
    lehrpersonen:
      - {name: D, entfernen: true}
"""


@pytest.fixture
def pfade(tmp_path):
    (tmp_path / "schule.yaml").write_text(SCHULE + SZENARIEN)
    kinder_csv(tmp_path / "kinder.csv")
    return tmp_path / "schule.yaml", tmp_path / "kinder.csv", tmp_path


def test_mische_listen_nach_name():
    basis = {"a": [{"name": "x", "v": 1}, {"name": "y", "v": 2}], "b": {"c": 1, "d": 2}}
    patch = {"a": [{"name": "x", "v": 9}, {"name": "y", "entfernen": True}, {"name": "z"}], "b": {"c": 5}}
    assert _mische(basis, patch) == {"a": [{"name": "x", "v": 9}, {"name": "z"}], "b": {"c": 5, "d": 2}}


def test_szenarien_laden(pfade):
    yaml_pfad, _, _ = pfade
    assert szenarien(yaml_pfad) == ["Basis", "Schulweg wichtig", "Sued kleiner", "Ohne D"]
    assert lade_schule(yaml_pfad, "Schulweg wichtig").gewichte["schulweg_pro_km"] == 900
    assert len(lade_schule(yaml_pfad, "Sued kleiner").schulhaus("Sued").raeume) == 1
    assert "D" not in [lp.name for lp in lade_schule(yaml_pfad, "Ohne D").lehrpersonen]
    with pytest.raises(ValueError):
        lade_schule(yaml_pfad, "Gibt es nicht")


def test_gewichte_ueberschreiben_und_pruefen(pfade):
    yaml_pfad, _, _ = pfade
    assert lade_schule(yaml_pfad, gewichte={"klasse": 7}).gewichte["klasse"] == 7
    with pytest.raises(ValueError, match="Unbekannte Gewichte"):
        lade_schule(yaml_pfad, gewichte={"tippfehler": 1})


def test_schulhaus_und_raum_verfuegbarkeit(pfade):
    yaml_pfad, kinder_pfad, tmp = pfade
    text = yaml_pfad.read_text().replace(
        "raeume: [{typ: Klassenzimmer, anzahl: 2, plaetze: 24}, {typ: Turnhalle, plaetze: 30}]}",
        "raeume: [{typ: Klassenzimmer, anzahl: 2, plaetze: 24},"
        " {typ: Turnhalle, plaetze: 30, nicht_verfuegbar: [Di, Mi]}], nicht_verfuegbar: [Fr-NM]}")
    yaml_pfad.write_text(text)
    schule = lade_schule(yaml_pfad)
    r = rechne(schule, lade_kinder(kinder_pfad), zeitlimit=40, protokoll=lambda *_: None)
    assert r.anzahl("Fehler") == 0, [str(m) for m in r.meldungen if m.schwere == "Fehler"]
    zu_nord = schule.schulhaus("Nord").nicht_verfuegbar
    halle = schule.schulhaus("Nord").raeume[-1]
    assert zu_nord and halle.nicht_verfuegbar
    for l in r.lektionen:
        if l.schulhaus == "Nord":
            assert l.slot not in zu_nord
        if l.fach == "Sport":
            assert l.slot not in halle.nicht_verfuegbar


def test_vorpruefung_meldet_fehler_mit_schweregrad(pfade):
    yaml_pfad, _, tmp = pfade
    kinder_csv(tmp / "viele.csv", n=200)
    r = rechne(lade_schule(yaml_pfad), lade_kinder(tmp / "viele.csv"), zeitlimit=10, protokoll=lambda *_: None)
    assert r.einteilung is None
    fehler = [m for m in r.meldungen if m.schwere == "Fehler"]
    assert any("Plätze" in m.text for m in fehler)


def test_qualitaetshinweise(pfade):
    yaml_pfad, kinder_pfad, _ = pfade
    r = rechne(lade_schule(yaml_pfad), lade_kinder(kinder_pfad), zeitlimit=40, protokoll=lambda *_: None)
    assert r.vollstaendig
    assert {m.schwere for m in r.meldungen} <= {"Warnung", "Hinweis"}
    assert r.kennzahlen()["Fehler"] == "0"


def test_cli_szenarienvergleich(pfade, capsys):
    yaml_pfad, kinder_pfad, tmp = pfade
    main([str(yaml_pfad), str(kinder_pfad), "-o", str(tmp / "out"), "-t", "20",
          "-s", "Basis", "-s", "Schulweg wichtig", "-g", "klasse=500"])
    vergleich = (tmp / "out" / "vergleich.html").read_text()
    assert "Schulweg_wichtig/bericht.html" in vergleich
    assert (tmp / "out" / "Basis" / "bericht.html").exists()
    assert (tmp / "out" / "Schulweg_wichtig" / "meldungen.csv").exists()


def test_raumsperre_macht_blockzeit_unmoeglich(pfade):
    """D fehlt Mo 08:00, die Turnhalle ist Mo zu: niemand kann S 1a am Montagmorgen
    unterrichten. Das muss schon bei den Lehraufträgen erkannt werden."""
    yaml_pfad, kinder_pfad, _ = pfade
    yaml_pfad.write_text(yaml_pfad.read_text().replace(
        "{typ: Turnhalle, plaetze: 30}]}", "{typ: Turnhalle, plaetze: 30, nicht_verfuegbar: [Mo]}]}"))
    r = rechne(lade_schule(yaml_pfad), lade_kinder(kinder_pfad), zeitlimit=20, protokoll=lambda *_: None)
    assert any(m.schwere == "Fehler" and "Lehraufträge" in m.text for m in r.meldungen)

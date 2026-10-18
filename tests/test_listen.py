# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Luca De Simoni. Alle Rechte vorbehalten.
"""Raum- und Lehrpersonenlisten aus CSV/Excel übernehmen (tolerante Spaltennamen)."""
from pathlib import Path

import pytest
from openpyxl import Workbook

from skf.austausch import (lese_liste, lese_rohkonfiguration, raumtypen, uebernehme_liste, zeitangabe)
from skf.cli import main
from skf.daten import baue_schule

VORLAGE = Path(__file__).parent.parent / "beispiele" / "vorlage"


@pytest.fixture
def cfg():
    return lese_rohkonfiguration(VORLAGE / "schule.yaml")


@pytest.mark.parametrize("text, erwartet", [("Mi", "Mi"), ("Fr-NM", "Fr-NM"), ("Freitag Nachmittag", "Fr-NM"),
                                            ("mo vm 1", "Mo-VM-1"), ("Donnerstag", "Do")])
def test_zeitangaben(text, erwartet):
    assert zeitangabe(text) == erwartet


def test_zeitangabe_unverstaendlich():
    with pytest.raises(ValueError, match="nicht verstanden"):
        zeitangabe("Samstag")


def test_raumliste_csv_wird_erkannt(cfg):
    zeilen = lese_liste(VORLAGE / "raumliste.csv", "Raeume", raumtypen=raumtypen(cfg))
    assert zeilen[0] == {"schulhaus": "Schulhaus A", "typ": "Klassenzimmer", "name": "A-Zi", "anzahl": 3,
                         "plaetze": 24}
    assert zeilen[1]["typ"] == "Kindergarten"            # "Kiga"
    assert zeilen[2]["typ"] == "Turnhalle"               # "Sporthalle"
    assert zeilen[2]["nicht_verfuegbar"] == ["Fr-NM"]    # "Freitag Nachmittag"


def test_raumliste_excel_und_uebernahme(cfg, tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Räume"
    ws.append(["Gebäude", "Raumnummer", "Nutzung", "Kapazität", "Sperrzeiten"])
    ws.append(["Schulhaus B", "B-Zi", "Schulzimmer", 26, None])
    ws.append(["Schulhaus B", "B-Zi 2", "Klassenzimmer", 24, "Mi"])
    ws.append(["Schulhaus B", "B-KG", "Kindergarten", 22, None])
    ws.append(["Schulhaus B", "Werkraum", "Werken", 16, "Mo-VM; Di-VM"])
    pfad = tmp_path / "raeume.xlsx"
    wb.save(pfad)
    zeilen = lese_liste(pfad, "Raeume", raumtypen=raumtypen(cfg))
    neu, hinweise = uebernehme_liste(cfg, "Raeume", zeilen)
    assert hinweise[0] == "4 Räume in 1 Schulhaus übernommen."
    assert any("TTG-Zimmer" in h and "nicht verplant" in h for h in hinweise)
    schule = baue_schule(neu)
    b = schule.schulhaus("Schulhaus B")
    assert [r.name for r in b.raeume] == ["B-Zi", "B-Zi 2", "B-KG", "Werkraum"]
    assert b.raeume[0].plaetze == 26 and len(b.raeume[1].nicht_verfuegbar) > 0
    # Schulhaus A unverändert
    assert len(schule.schulhaus("Schulhaus A").raeume) == 5


def test_raumliste_unbekanntes_schulhaus(cfg):
    with pytest.raises(ValueError, match="Unbekannte Schulhäuser: Schulhaus Z"):
        uebernehme_liste(cfg, "Raeume", [{"schulhaus": "Schulhaus Z", "typ": "Klassenzimmer"}])


def test_raumliste_fehlende_spalte(tmp_path):
    pfad = tmp_path / "r.csv"
    pfad.write_text("Raum;Plätze\nA1;24\n", encoding="utf-8")
    with pytest.raises(ValueError, match="schulhaus, typ"):
        lese_liste(pfad, "Raeume")


def test_lehrpersonenliste(cfg, tmp_path):
    pfad = tmp_path / "personal.csv"
    pfad.write_text("Vorname;Nachname;Kürzel;Fächer;Schulhaus;Pensum;Freie Tage\n"
                    "Anna;Muster;AM;Deutsch, Mathematik, NMG;Schulhaus A;12-16;Mittwoch\n"
                    "Beat;Beispiel;BB;Bewegung und Sport/Schach;;8;\n", encoding="utf-8")
    zeilen = lese_liste(pfad, "Lehrpersonen")
    assert zeilen[0] == {"name": "Anna Muster", "kuerzel": "AM", "faecher": ["Deutsch", "Mathematik", "NMG"],
                         "schulhaeuser": ["Schulhaus A"], "pensum_min": 12, "pensum_max": 16,
                         "nicht_verfuegbar": ["Mi"]}
    neu, hinweise = uebernehme_liste(cfg, "Lehrpersonen", zeilen, ersetzen=False)
    assert any("Unbekannte Fächer: Schach" in h for h in hinweise)
    schule = baue_schule(neu)
    anna = next(lp for lp in schule.lehrpersonen if lp.name == "Anna Muster")
    assert (anna.pensum_min, anna.pensum_max) == (12, 16) and anna.nicht_verfuegbar
    assert len(schule.lehrpersonen) == len(cfg["lehrpersonen"]) + 2


def test_cli_raeume(tmp_path, capsys):
    ziel = tmp_path / "schule.yaml"
    ziel.write_text((VORLAGE / "schule.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    main(["raeume", str(ziel), str(VORLAGE / "raumliste.csv")])
    aus = capsys.readouterr().out
    assert "8 Räume in 2 Schulhäusern übernommen." in aus
    assert (tmp_path / "schule.yaml.bak").exists()
    schule = baue_schule(lese_rohkonfiguration(ziel))
    assert sum(len(sh.raeume) for sh in schule.schulhaeuser) == 8

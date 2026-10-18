# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""IF/DaZ/IS, Kontinuität, Geschwister, Kantonsprofil, Konfliktanalyse, Import/Export."""
import csv
import json
from pathlib import Path

import pytest

from skf import lade_kinder, lade_schule
from skf.ablauf import rechne
from skf.austausch import (exportiere_stammdaten, importiere_stammdaten, lese_rohkonfiguration, lv95_zu_wgs84,
                           normalisiere_jahrgang, schreibe_kinder)
from skf.cli import main
from skf.daten import Foerderangebot
from skf.klassen import teile_ein

VORLAGE = Path(__file__).parent.parent / "beispiele" / "vorlage"
STILL = {"protokoll": lambda *_: None}


@pytest.fixture(scope="module")
def ergebnis():
    schule = lade_schule(VORLAGE / "schule.yaml")
    kinder = lade_kinder(VORLAGE / "kinder.csv")
    return rechne(schule, kinder, zeitlimit=30, **STILL)


def test_vorlage_vollstaendig_und_fehlerfrei(ergebnis):
    assert ergebnis.vollstaendig
    assert ergebnis.anzahl("Fehler") == 0, [str(m) for m in ergebnis.meldungen if m.schwere == "Fehler"]


def test_foerderlektionen_parallel_und_gruppiert(ergebnis):
    foerder = [b for b in ergebnis.bloecke if b.art == "foerder"]
    assert {b.fach for b in foerder} >= {"IF", "DaZ Anfang", "DaZ Aufbau"}
    # IF pro Klasse: 0.2 L pro Kind (1 Vollpensum / 140 Lernende), aufgerundet
    for b in foerder:
        if b.fach == "IF":
            klasse = next(c for c in ergebnis.einteilung.klassen if c.name == b.klasse)
            assert b.lektionen == -(-len(klasse.kinder) // 5)
    # Förderlektionen liegen immer parallel zu einem passenden Fach jeder beteiligten Klasse
    fach_in = {(l.klasse, l.slot): l.fach for l in ergebnis.lektionen if l.art == "unterricht"}
    for l in ergebnis.lektionen:
        if l.art == "foerder":
            b = next(b for b in foerder if b.klassen == l.klassen and b.fach == l.fach)
            assert all(fach_in.get((kl, l.slot)) in b.parallel_zu for kl in l.klassen)


def test_daz_formel_luzern():
    a = Foerderangebot("DaZ Anfang", merkmal="daz=anfang", basis={"default": 4, "1": 3, "2": 3},
                       frei_bis=3, pro_kind=0.5)
    assert a.lektionen(["1"], 0) == 0
    assert a.lektionen(["1"], 2) == 3       # 1–3 Lernende KG–2. Kl.: 3 L
    assert a.lektionen(["3"], 3) == 4       # ab 3. Kl.: 4 L
    assert a.lektionen(["3"], 5) == 5       # +0.5 L je weitere Lernende ab 4


def test_is_regeln(ergebnis):
    nach_id = {k.id: k for k in ergebnis.kinder}
    for c in ergebnis.einteilung.klassen:
        anz_is = sum(nach_id[i].is_ for i in c.kinder)
        assert anz_is <= ergebnis.schule.max_is_pro_klasse
        assert len(c.kinder) + anz_is <= min(c.vorlage.max, c.raum.plaetze)  # IS zählt doppelt


def test_kontinuitaet_lehrperson(ergebnis):
    # "Lehrperson 2" führte "A 1a"; deren Kinder sind jetzt in der 2. Klasse in Schulhaus A
    nach_id = {k.id: k for k in ergebnis.kinder}
    klasse = max(ergebnis.einteilung.klassen,
                 key=lambda c: sum(nach_id[i].bisherige_klasse == "A 1a" for i in c.kinder))
    lps = {b.lehrperson for b in ergebnis.bloecke if b.klasse == klasse.name and b.art == "unterricht"}
    assert "Lehrperson 2" in lps


def test_geschwister_hart():
    schule = lade_schule(VORLAGE / "schule.yaml", "Geschwister zwingend")
    kinder = lade_kinder(VORLAGE / "kinder.csv")
    e = teile_ein(schule, kinder, zeitlimit=20)
    familien = {}
    for k in kinder:
        if k.familie:
            familien.setdefault(k.familie, set()).add(e.schulhaus_von[k.id])
    assert all(len(s) == 1 for s in familien.values())


def test_rechtsquellen_in_meldungen(ergebnis):
    quellen = ergebnis.schule.profil["quellen"]
    assert {"VBV-3", "VBV-7", "FV", "IF-RL", "DaZ-UH"} <= set(quellen)
    for m in ergebnis.meldungen:
        if m.quelle:
            assert m.quelle in quellen and quellen[m.quelle]["url"].startswith("https://")


def test_verbindliches_profil_begrenzt_klassengroesse(tmp_path):
    text = (VORLAGE / "schule.yaml").read_text().replace(
        '{jahrgaenge: ["1"], min: 16, max: 22, ideal: 20}', '{jahrgaenge: ["1"], min: 10, max: 30, ideal: 20}')
    (tmp_path / "s.yaml").write_text(text + "\nprofil: {verbindlich: true}\n")
    v = next(v for v in lade_schule(tmp_path / "s.yaml").vorlagen if v.jahrgaenge == ["1"])
    assert (v.min, v.max) == (16, 22)
    (tmp_path / "s2.yaml").write_text(text)
    v = next(v for v in lade_schule(tmp_path / "s2.yaml").vorlagen if v.jahrgaenge == ["1"])
    assert (v.min, v.max) == (10, 30)


def test_konfliktanalyse_nennt_regeln(tmp_path):
    text = (VORLAGE / "schule.yaml").read_text().replace(
        "pensum: [10, 28], nicht_verfuegbar: [Fr-NM]}", "pensum: [10, 28], nicht_verfuegbar: [Mo]}")
    assert "nicht_verfuegbar: [Mo]}" in text  # Lehrperson 4 (Schulhaus B) fehlt am Montag
    (tmp_path / "s.yaml").write_text(text)
    r = rechne(lade_schule(tmp_path / "s.yaml"), lade_kinder(VORLAGE / "kinder.csv"), zeitlimit=20, **STILL)
    fehler = [m.text for m in r.meldungen if m.schwere == "Fehler"]
    assert any("widersprechen sich" in t and "Blockzeiten" in t for t in fehler), fehler


def test_referenzen_werden_geprueft(tmp_path):
    text = (VORLAGE / "schule.yaml").read_text().replace("schulhaeuser: Schulhaus B, pensum: [20, 28]}",
                                                        "schulhaeuser: Schulhaus Z, pensum: [20, 28]}")
    (tmp_path / "s.yaml").write_text(text)
    r = rechne(lade_schule(tmp_path / "s.yaml"), lade_kinder(VORLAGE / "kinder.csv"), zeitlimit=5, **STILL)
    assert any("unbekanntes Schulhaus 'Schulhaus Z'" in m.text for m in r.meldungen if m.schwere == "Fehler")
    assert r.einteilung is None


# ------------------------------------------------------------ Import / Export

def test_kinderimport_schulverwaltung(tmp_path):
    """Semikolon-CSV in Windows-1252 mit deutschen Spaltennamen und LV95-Koordinaten."""
    zeilen = ["Schüler-Nr;Vorname;Nachname;Stufe;Geschlecht;Strasse;PLZ;Ort;E;N;DaZ;IS;Klasse Vorjahr",
              "77;Zoé;Müller;2. Klasse;weiblich;Hauptstrasse 3;6102;Malters;2656000;1211000;ja;nein;BM 1a",
              "78;Jan;Meier;KG 1;männlich;Dorf 1;6102;Malters;2656100;1211100;;x;"]
    (tmp_path / "export.csv").write_bytes("\n".join(zeilen).encode("cp1252"))
    k = lade_kinder(tmp_path / "export.csv", {"id": "Schüler-Nr"})
    assert [x.jahrgang for x in k] == ["2", "KG1"]
    assert k[0].name == "Zoé Müller" and k[0].adresse == "Hauptstrasse 3, 6102 Malters"
    assert k[0].geschlecht == "w" and k[1].geschlecht == "m"
    assert k[0].daz == "aufbau" and not k[0].is_ and k[1].is_
    assert k[0].bisherige_klasse == "BM 1a"
    assert 47.0 < k[0].lat < 47.1 and 8.1 < k[0].lon < 8.25


def test_lv95_und_jahrgang():
    lat, lon = lv95_zu_wgs84(2_600_000, 1_200_000)  # Bern, alte Sternwarte
    assert abs(lat - 46.951) < 0.001 and abs(lon - 7.4386) < 0.001
    assert normalisiere_jahrgang("3. Klasse") == "3"
    assert normalisiere_jahrgang("2. Kindergarten") == "KG2"
    assert normalisiere_jahrgang("KG1") == "KG1"


def _normal(cfg):
    """Einzelwert und einelementige Liste sind gleichwertig (z.B. schulhaeuser: A == [A])."""
    def n(x, schluessel=""):
        if isinstance(x, dict):
            return {k: n(v, k) for k, v in sorted(x.items())}
        if isinstance(x, list):
            return [n(v) for v in x]
        if schluessel in ("schulhaeuser", "jahrgaenge", "faecher", "nicht_verfuegbar", "parallel_zu") \
                and isinstance(x, str):
            return [x]
        return x
    return n(json.loads(json.dumps(cfg)))


@pytest.mark.parametrize("endung", [".xlsx", ".json"])
def test_stammdaten_roundtrip(tmp_path, endung):
    cfg = lese_rohkonfiguration(VORLAGE / "schule.yaml")
    kinder = lade_kinder(VORLAGE / "kinder.csv")
    exportiere_stammdaten(cfg, kinder, tmp_path / f"daten{endung}")
    cfg2, kinder2 = importiere_stammdaten(tmp_path / f"daten{endung}")
    assert _normal(cfg2) == _normal(cfg)
    assert [(k.id, k.jahrgang, k.if_, k.daz, k.is_, k.familie, k.bisherige_klasse) for k in kinder2] == \
           [(k.id, k.jahrgang, k.if_, k.daz, k.is_, k.familie, k.bisherige_klasse) for k in kinder]


def test_cli_import_export_und_listen(tmp_path, capsys):
    main(["export", str(VORLAGE / "schule.yaml"), str(VORLAGE / "kinder.csv"), "-o", str(tmp_path / "s.xlsx")])
    main(["import", str(tmp_path / "s.xlsx"), "-o", str(tmp_path / "neu")])
    main(["pruefen", str(tmp_path / "neu" / "schule.yaml"), str(tmp_path / "neu" / "kinder.csv")])
    main(["rechnen", str(tmp_path / "neu" / "schule.yaml"), str(tmp_path / "neu" / "kinder.csv"),
          "-o", str(tmp_path / "out"), "-t", "20"])
    for datei in ("klassenlisten.xlsx", "stundenplaene.xlsx", "druck.html", "bericht.html", "meldungen.csv"):
        assert (tmp_path / "out" / datei).stat().st_size > 0
    from openpyxl import load_workbook
    wb = load_workbook(tmp_path / "out" / "klassenlisten.xlsx")
    assert wb.sheetnames[0] == "Übersicht" and len(wb.sheetnames) > 3
    assert "Förderung" not in [c.value for c in wb[wb.sheetnames[1]][5]]  # ohne --mit-foerderdaten
    with open(tmp_path / "out" / "meldungen.csv", encoding="utf-8") as f:
        assert "quelle_url" in next(csv.reader(f))


def test_kinder_umwandeln(tmp_path):
    kinder = lade_kinder(VORLAGE / "kinder.csv")
    schreibe_kinder(kinder, tmp_path / "k.xlsx")
    assert [k.id for k in lade_kinder(tmp_path / "k.xlsx")] == [k.id for k in kinder]


def test_json_export_entspricht_schema(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((Path(__file__).parent.parent / "schema" / "skf-stammdaten.schema.json").read_text())
    for beispiel in (VORLAGE, VORLAGE.parent / "malters"):
        exportiere_stammdaten(lese_rohkonfiguration(beispiel / "schule.yaml"), lade_kinder(beispiel / "kinder.csv"),
                              tmp_path / "d.json")
        jsonschema.validate(json.loads((tmp_path / "d.json").read_text()), schema)

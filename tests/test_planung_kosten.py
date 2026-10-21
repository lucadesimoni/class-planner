# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Kosten, Qualität, Hypothesen-Szenarien und Langfristplanung (Kohortenmodell)."""
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from skf.ablauf import rechne
from skf.daten import (
    GEWICHT_HEBEL,
    Kind,
    baue_schule,
    lade_kinder,
    lese_konfiguration,
    szenario_aus_hebeln,
    szenario_infos,
)
from skf.kosten import kosten
from skf.planung import Planung, _prognose
from skf.pruefung import vorpruefung

BEISPIELE = Path(__file__).parent.parent / "beispiele"
VORLAGE = BEISPIELE / "vorlage"
SEK = ["S1A", "S1B", "S1C", "S2A", "S2B", "S2C", "S3A", "S3B", "S3C"]


def _cfg(**extra) -> dict:
    cfg = yaml.safe_load((VORLAGE / "schule.yaml").read_text(encoding="utf-8"))
    cfg.update(extra)
    return cfg


def _schreibe(tmp_path, cfg) -> Path:
    pfad = tmp_path / "schule.yaml"
    pfad.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return pfad


# ------------------------------------------------------------------ Eingaben prüfen (Härtung)

@pytest.mark.parametrize("kosten_cfg, meldung", [
    ({"lektion_chf": -1}, "negativ"),
    ({"lektion_chf": "viel"}, "Zahl erwartet"),
    ({"raum_chf": {"Klassenzimmer": -5}}, "negativ"),
    ({"lohn": 5}, "unbekannte Angabe"),
    ([1, 2], "Posten"),
])
def test_kostenmodell_wird_geprueft(kosten_cfg, meldung):
    with pytest.raises(ValueError, match=meldung):
        baue_schule(_cfg(kosten=kosten_cfg))


@pytest.mark.parametrize("planung, meldung", [
    ({"wachstum_prozent": 80}, "ausserhalb"),
    ({"wachstum_prozent": "rasch"}, "Zahl erwartet"),
    ({"austritt_prozent": {"2": 120}}, "höchstens 100"),
    ({"vollpensum_lektionen": 0}, "grösser als 0"),
    ({"quartiere": [{"name": "Nord", "schulhaus": "Schulhaus A"}]}, "wohnungen"),
    ({"quartiere": [{"name": "Nord", "wohnungen": -3}]}, "negativ"),
])
def test_planung_wird_geprueft(planung, meldung):
    with pytest.raises(ValueError, match=meldung):
        baue_schule(_cfg(planung=planung))


def test_bezuege_in_planung_und_kosten_werden_gemeldet():
    s = baue_schule(_cfg(planung={"quartiere": [{"name": "Nord", "schulhaus": "Gibtsnicht", "kinder": 10}],
                                  "austritt_prozent": {"9": 5}},
                         kosten={"raum_chf": {"Aula": 1000}}))
    texte = " ".join(m.text for m in vorpruefung(s, []))
    assert "Gibtsnicht" in texte and "Aula" in texte and "'9'" in texte


def test_unbekanntes_ziel_wird_abgelehnt(tmp_path):
    pfad = _schreibe(tmp_path, _cfg(szenarien={"X": {"ziel": "Spass", "hypothese": "?"}}))
    with pytest.raises(ValueError, match="Spass"):
        baue_schule(lese_konfiguration(pfad, "X"))


# ------------------------------------------------------------------ Hypothesen

def test_hypothese_ist_beschreibung_keine_aenderung(tmp_path):
    pfad = _schreibe(tmp_path, _cfg(szenarien={"Wachstum": {
        "ziel": "planung", "hypothese": "Was wäre, wenn …", "planung": {"wachstum_prozent": 5}}}))
    basis, sz = lese_konfiguration(pfad), lese_konfiguration(pfad, "Wachstum")
    assert "hypothese" not in sz and "ziel" not in sz
    s = baue_schule(sz)
    assert (s.hypothese, s.ziel, s.planung["wachstum_prozent"]) == ("Was wäre, wenn …", "Planung", 5.0)
    assert baue_schule(basis).hypothese == ""
    infos = szenario_infos(yaml.safe_load(pfad.read_text(encoding="utf-8")))
    assert infos["Wachstum"] == {"hypothese": "Was wäre, wenn …", "ziel": "planung"}


def test_szenario_aus_hebeln_ist_gueltig(tmp_path):
    patch = szenario_aus_hebeln("Was wäre, wenn grössere Klassen und ein Quartier?",
                                ["Weniger, grössere Klassen"], 4,
                                {"name": "Nord", "schulhaus": "Schulhaus A", "ab": "2029/30", "wohnungen": 50},
                                ["Lehrperson 4"])
    assert patch["gewichte"] == GEWICHT_HEBEL["Weniger, grössere Klassen"][1]
    pfad = _schreibe(tmp_path, _cfg(szenarien={"Neu": patch}))
    s = baue_schule(lese_konfiguration(pfad, "Neu"))
    assert s.ziel == "Planung" and s.planung["quartiere"][0]["wohnungen"] == 50
    assert "Lehrperson 4" not in {lp.name for lp in s.lehrpersonen}
    assert s.gewichte["klasse"] == 1500


def test_malters_szenarien_haben_hypothesen():
    cfg = yaml.safe_load((BEISPIELE / "malters" / "schule.yaml").read_text(encoding="utf-8"))
    infos = szenario_infos(cfg)
    assert all(i["hypothese"] and i["ziel"] for n, i in infos.items() if n != "Basis")
    assert {i["ziel"] for i in infos.values()} >= {"Kosten", "Qualität", "Planung"}
    for n in infos:  # jedes Szenario lässt sich einlesen
        baue_schule(lese_konfiguration(BEISPIELE / "malters" / "schule.yaml", n))


def test_planung_und_kosten_aendern_die_berechnung_nicht(tmp_path):
    """Kern bleibt unberührt: Annahmen für Prognose/Kosten und Hypothesentexte fliessen nicht in die Optimierung."""
    kinder = lade_kinder(VORLAGE / "kinder.csv")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    ohne = baue_schule(lese_konfiguration(_schreibe(tmp_path / "a", _cfg())))
    mit = baue_schule(lese_konfiguration(_schreibe(tmp_path / "b", _cfg(
        planung={"wachstum_prozent": 9, "quartiere": [{"name": "N", "kinder": 40}]},
        kosten={"lektion_chf": 4000, "schulhaus_chf": 1, "raum_chf": {"Klassenzimmer": 2}}))))
    a = rechne(ohne, kinder, zeitlimit=60, protokoll=lambda t: None)
    b = rechne(mit, kinder, zeitlimit=60, protokoll=lambda t: None)
    assert a.vollstaendig and not a.anzahl("Fehler")
    assert [i.zielwert for i in a.infos] == [i.zielwert for i in b.infos]
    assert a.einteilung.klasse_von == b.einteilung.klasse_von
    assert "Kosten/Jahr" in b.kennzahlen() and "Kosten/Jahr" not in a.kennzahlen()
    total = kosten(b)[-1]["CHF"]
    assert total == sum(z["CHF"] for z in kosten(b)[:-1]) and total >= 4000 * sum(x.lektionen for x in b.bloecke)


# ------------------------------------------------------------------ Kohortenmodell

def _prognose_von(cfg: dict, verteilung: dict[str, int]) -> Planung:
    """Prognose ohne Rechnen: alle Lernenden im ersten Schulhaus, das ihre Stufe führt."""
    s = baue_schule(cfg)
    kinder, haus = [], {}
    for jg, n in verteilung.items():
        for i in range(n):
            kinder.append(Kind(f"{jg}-{i}", "", jg, "w", "", None, None))
            haus[f"{jg}-{i}"] = s.schulhaeuser[0].name
    r = SimpleNamespace(einteilung=SimpleNamespace(schulhaus_von=haus, klassen=[]), bloecke=[], lektionen=[],
                        kinder=kinder, schule=s)
    p = Planung()
    _prognose(s, kinder, r, p)
    return p


def _sek_cfg(**planung):
    sek = [{"jahrgaenge": [j], "min": 8, "max": 24} for j in ["3", "4", "5", "6"] + SEK]
    cfg = _cfg(jahrgaenge=["KG1", "KG2", "1", "2", "3", "4", "5", "6"] + SEK, planung=planung)
    cfg["klassenbildung"]["vorlagen"] = cfg["klassenbildung"]["vorlagen"] + sek
    for sh in cfg["schulhaeuser"]:
        sh.pop("stufen", None)
    return cfg


def test_kohorten_folgen_der_stufenfolge():
    """6. Klasse verteilt sich auf S1A/B/C im heutigen Verhältnis, Sek-Niveaus bleiben, S3 schliesst ab."""
    p = _prognose_von(_sek_cfg(austritt_prozent={"6": 10}), {"6": 40, "S1A": 20, "S1B": 10, "S1C": 10,
                                                             "S3A": 15})
    j1 = p.jahre[1]
    assert p.jahre[0]["Lernende"] == 95
    # 40 × 90 % gehen in die Sek, S1 rückt nach S2, S3A schliesst ab, KG1 neu = heute 0
    assert j1["Lernende"] == 36 + 40
    assert p.jahre[0]["Klassen (mind.)"] == 2 + 1 + 1 + 1 + 1  # 6. Klasse: 40 Lernende, max. 24


def test_wachstum_und_quartier_im_richtigen_jahr():
    cfg = _cfg(planung={"wachstum_prozent": 10, "neue_kg1_pro_jahr": 20,
                        "quartiere": [{"name": "Nord", "ab": "2029/30", "kinder": 40}]})
    p = _prognose_von(cfg, {"KG1": 20, "KG2": 20, "1": 20, "2": 20})
    zuzug = {j["Schuljahr"]: j["davon Zuzug Quartiere"] for j in p.jahre}
    assert zuzug["2029/30"] == 40 and sum(zuzug.values()) == 40
    # Jahr 1: KG1 neu 22 (+10 %), alle anderen rücken nach, Jahrgang 2 tritt aus der Schule aus
    assert p.jahre[1]["Lernende"] == 22 + 20 + 20 + 20


def test_negatives_wachstum_und_null_lernende_sind_robust():
    p = _prognose_von(_cfg(planung={"wachstum_prozent": -20}), {"KG1": 5})
    assert [j["Lernende"] for j in p.jahre][:2] == [5, 9]
    p = _prognose_von(_cfg(), {"1": 3})
    assert p.jahre[-1]["Lernende"] == 0 and all(j["fehlende Räume"] == 0 for j in p.jahre)

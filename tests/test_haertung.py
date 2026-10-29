# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Härtung des Rechenkerns: je ein Test pro Fehler, den die Prüfung vom Oktober 2026 nachgestellt hat.

Klassenbildung/Solver/Ablauf, Lehraufträge/Stundenplan, Nachprüfung, Planung, Gebiete, Einlesen, Rechenserver.
"""
from __future__ import annotations

import json
import tempfile
import textwrap

import pytest
import yaml

from skf.ablauf import Ergebnis, rechne
from skf.daten import (
    Kind,
    Raum,
    Schulhaus,
    _mische,
    baue_schule,
    lade_kinder,
    lade_schule,
    lese_konfiguration,
    stufen_liste,
)
from skf.klassen import Klasse, geschwistergruppen, teile_ein
from skf.lehrauftrag import verteile_lehrauftraege
from skf.pruefung import pruefe
from skf.solver import KeineLoesung
from skf.stundenplan import erstelle_stundenplan
from tests.test_planung_kosten import VORLAGE, _cfg

KLEIN = """
name: T
jahrgaenge: ["1"]
schulhaeuser:
  - name: A
    lat: 47.05
    lon: 8.30
    raeume:
      - {name: A-Zi, typ: Klassenzimmer, anzahl: 3, plaetze: 24}
      - {name: A-Halle, typ: Turnhalle, plaetze: 30}
klassenbildung:
  vorlagen:
    - {jahrgaenge: ["1"], min: 1, max: 30, ideal: 20}
zeitraster:
  blockzeiten: false
  halbtage:
    VM: ["08:00", "08:50", "09:55", "10:45"]
    NM: ["13:30", "14:20"]
faecher:
  Deutsch: {max_pro_tag: 2}
stundentafel:
  "1": {Deutsch: 4}
lehrpersonen:
  - {name: L1, faecher: [Deutsch], pensum: [0, 28]}
"""


def schule_aus(text: str):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(textwrap.dedent(text))
    return baue_schule(lese_konfiguration(f.name))


def klasse(s, name, sh="A", n=20, jg="1"):
    v = next(v for v in s.vorlagen if jg in v.jahrgaenge)
    return Klasse(name, sh, next(r for r in s.schulhaus(sh).raeume if r.typ == v.raumtyp), v, {jg: n})


def vorlage():
    return lade_schule(VORLAGE / "schule.yaml"), lade_kinder(VORLAGE / "kinder.csv")


# ------------------------------------------------------------------ Klassenbildung, Solver, Ablauf

def test_konflikt_nennt_keine_unbeteiligte_regel():
    from ortools.sat.python import cp_model

    from skf.solver import Regeln, loese_mit_regeln
    m = cp_model.CpModel()
    regeln = Regeln(m)
    a, b = m.new_int_var(0, 10, "a"), m.new_int_var(0, 10, "b")
    m.add(a >= 20)                                   # unlösbar ohne benannte Regel
    regeln.nur_wenn(m.add(b >= 1), "Regel Y (harmlos)")
    with pytest.raises(KeineLoesung) as fehler:
        loese_mit_regeln(m, regeln, "Test", 5)
    assert fehler.value.konflikt == [] and "Regel Y" not in str(fehler.value)


def test_geschwister_ohne_gemeinsames_schulhaus_keine_kette():
    s, k = vorlage()
    a, b = s.schulhaeuser
    a.stufen, b.stufen = ["KG1", "KG2"], ["KG1", "KG2", "2"]
    s.schulhaeuser.append(Schulhaus("C", "C", 47.045, 8.305, [Raum(f"C-Zi {i}", "Klassenzimmer", 24) for i in (1, 2, 3)],
                                    nutzt={"Turnhalle": a.name}, stufen=["1", "2"]))
    for x in k:
        x.familie = ""
    familie = [next(x for x in k if x.jahrgang == j) for j in ("KG1", "1", "2")]
    for x in familie:
        x.familie = "FX"
    gruppen = geschwistergruppen(s, k)["FX"]
    assert sorted(map(len, gruppen)) == [1, 2]               # KG-Kind allein, 1./2. Klasse zusammen (Schulhaus C)
    s.geschwister = "hart"
    e = teile_ein(s, k, zeitlimit=15)                        # vorher: "nachweislich keine Lösung"
    assert e.schulhaus_von[familie[1].id] == e.schulhaus_von[familie[2].id]


def test_gesperrter_raum_wird_nicht_als_schulzimmer_gewaehlt():
    s, k = vorlage()
    s.schulhaeuser[0].raeume[0].nicht_verfuegbar = {sl.index for sl in s.slots}   # A-Zi 1: Umbau
    r = rechne(s, k, zeitlimit=40, protokoll=lambda t: None)
    assert r.vollstaendig and not r.anzahl("Fehler")
    assert all(c.raum.name != s.schulhaeuser[0].raeume[0].name for c in r.einteilung.klassen)


def test_zeitlimit_ist_keine_unloesbarkeit(monkeypatch):
    from skf import ablauf
    aufrufe = []

    def zu_langsam(*args, **kwargs):
        aufrufe.append(1)
        raise KeineLoesung("Stundenplan: innerhalb von 1s keine Lösung gefunden (UNKNOWN)", nachweislich=False)
    monkeypatch.setattr(ablauf, "erstelle_stundenplan", zu_langsam)
    s, k = vorlage()
    r = rechne(s, k, zeitlimit=20, protokoll=lambda t: None)
    assert len(aufrufe) == 1                                  # keine Wiederholungsschleife
    assert not any("unlösbar" in m.text for m in r.meldungen if m.bereich == "Solver" and m.schwere == "Hinweis")
    assert any("Zeitlimit erhöhen" not in m.text or "keine Lösung gefunden" in m.text
               for m in r.meldungen if m.schwere == "Fehler")


def test_gemeinsame_frist_fuer_alle_versuche(monkeypatch):
    import time as zeitmodul

    from skf import ablauf
    zeiten = []

    def unloesbar(schule, klassen, bloecke, zeitlimit, **kwargs):
        zeiten.append(zeitlimit)
        zeitmodul.sleep(min(zeitlimit, 0.4))
        raise KeineLoesung("Stundenplan: nachweislich keine Lösung möglich", ["Verfügbarkeit Lehrperson 1"])
    monkeypatch.setattr(ablauf, "erstelle_stundenplan", unloesbar)
    s, k = vorlage()
    start = zeitmodul.time()
    rechne(s, k, zeitlimit=2, protokoll=lambda t: None)
    assert zeitmodul.time() - start < 2 * 1.5 + 25            # Frist + Klassenbildung/Konfliktanalyse
    assert all(z <= 2 * 0.6 + 1e-9 for z in zeiten)


# ------------------------------------------------------------------ Lehraufträge, Stundenplan, Zeiten

def test_uhrzeiten_ohne_anfuehrungszeichen():
    s = schule_aus(KLEIN.replace('NM: ["13:30", "14:20"]', "NM: [13:30, 14:20]").replace(
        'VM: ["08:00", "08:50", "09:55", "10:45"]', 'VM: [8:00, "08:50", "09:55", "10:45"]'))
    assert [sl.zeit for sl in s.slots[:6]] == ["08:00", "08:50", "09:55", "10:45", "13:30", "14:20"]
    assert s.vormittag() == "VM"
    with pytest.raises(ValueError, match="Uhrzeit"):
        schule_aus(KLEIN.replace('NM: ["13:30", "14:20"]', 'NM: ["25:00"]'))
    with pytest.raises(ValueError, match="Liste"):
        schule_aus(KLEIN.replace('NM: ["13:30", "14:20"]', 'NM: "13:30"'))


def test_lektionen_gegen_offene_zeitfenster():
    s = schule_aus(KLEIN.replace('"1": {Deutsch: 4}', '"1": {Deutsch: 26}').replace(
        "Deutsch: {max_pro_tag: 2}", "Deutsch: {max_pro_tag: 6}").replace(
        "    lon: 8.30\n", "    lon: 8.30\n    nicht_verfuegbar: [Mi]\n"))
    with pytest.raises(KeineLoesung, match="26 Lektionen, aber nur 24 Zeitfenster"):
        verteile_lehrauftraege(s, [klasse(s, "1a")], zeitlimit=10)


def test_rueckmeldung_aus_dem_stundenplan_zeigt_den_eigentlichen_grund():
    s = schule_aus(KLEIN.replace("Deutsch: {max_pro_tag: 2}", "Deutsch: {max_pro_tag: 2, dauer: 2}\n  Mathe: {max_pro_tag: 6}")
                   .replace('"1": {Deutsch: 4}', '"1": {Deutsch: 4, Mathe: 10}')
                   .replace("  - {name: L1, faecher: [Deutsch], pensum: [0, 28]}",
                            "  - {name: L1, faecher: [Deutsch], pensum: [0, 28], nicht_verfuegbar: [Mo-VM-2, Mo-VM-4, "
                            "Mo-NM, Di-VM-2, Di-VM-4, Di-NM, Mi, Do, Fr]}\n  - {name: L2, faecher: [Mathe], pensum: [0, 28]}"))
    kinder = [k for k in lade_kinder(VORLAGE / "kinder.csv") if k.jahrgang == "1"][:20]
    for k in kinder:
        k.if_, k.daz, k.is_ = False, "", False
    r = rechne(s, kinder, zeitlimit=20, protokoll=lambda t: None)
    fehler = [m.text for m in r.meldungen if m.schwere == "Fehler"]
    assert fehler and "Stundenplan" in fehler[0] and "Verfügbarkeit L1" in fehler[0]


def test_geschlossene_halle_beschuldigt_keine_lehrperson():
    y = KLEIN.replace("{name: A-Halle, typ: Turnhalle, plaetze: 30}",
                      "{name: A-Halle, typ: Turnhalle, plaetze: 30, nicht_verfuegbar: [Mo, Di, Mi, Do]}").replace(
        "Deutsch: {max_pro_tag: 2}", "Deutsch: {max_pro_tag: 2}\n  Sport: {raumtyp: Turnhalle, max_pro_tag: 1}").replace(
        '"1": {Deutsch: 4}', '"1": {Deutsch: 4, Sport: 3}').replace(
        "  - {name: L1, faecher: [Deutsch], pensum: [0, 28]}",
        "  - {name: L1, faecher: [Deutsch], pensum: [0, 28]}\n"
        "  - {name: L2, faecher: [Sport], pensum: [0, 28], nicht_verfuegbar: [Mo, Di]}")
    s = schule_aus(y)
    kl = [klasse(s, "1a")]
    b, _ = verteile_lehrauftraege(s, kl, zeitlimit=10)
    with pytest.raises(KeineLoesung) as fehler:
        erstelle_stundenplan(s, kl, b, zeitlimit=10)
    assert "L2" not in str(fehler.value) and "Sport pro Tag" in str(fehler.value)


def test_foerdergruppe_ueber_klassen_braucht_qualifikation_fuer_alle():
    y = KLEIN.replace('jahrgaenge: ["1"]\n', 'jahrgaenge: ["1", "2"]\n', 1).replace(
        '    - {jahrgaenge: ["1"], min: 1, max: 30, ideal: 20}',
        '    - {jahrgaenge: ["1"], min: 1, max: 30, ideal: 20}\n    - {jahrgaenge: ["2"], min: 1, max: 30, ideal: 20}').replace(
        '"1": {Deutsch: 4}', '"1": {Deutsch: 4}\n  "2": {Deutsch: 4}').replace(
        "  - {name: L1, faecher: [Deutsch], pensum: [0, 28]}",
        '  - {name: L1, faecher: [Deutsch], pensum: [0, 28]}\n  - {name: D1, faecher: [DaZ], jahrgaenge: ["1"], '
        "pensum: [0, 28]}") + """
sonderpaedagogik:
  foerderangebote:
    - {name: DaZ, merkmal: daz, basis: 2, gruppierung: schulhaus, parallel_zu: [Deutsch]}
"""
    s = schule_aus(y)
    alle = lade_kinder(VORLAGE / "kinder.csv")
    k1, k2 = [k for k in alle if k.jahrgang == "1"][:10], [k for k in alle if k.jahrgang == "2"][:10]
    for k in k1 + k2:
        k.daz = "anfang"
    c1, c2 = klasse(s, "1a", n=10, jg="1"), klasse(s, "2a", n=10, jg="2")
    c1.kinder, c2.kinder, c2.raum = [k.id for k in k1], [k.id for k in k2], s.schulhaus("A").raeume[1]
    with pytest.raises(KeineLoesung, match="Keine Lehrperson für DaZ in 1a\\+2a"):
        verteile_lehrauftraege(s, [c1, c2], zeitlimit=10, kinder=k1 + k2)


# ------------------------------------------------------------------ Nachprüfung, Transparenz

def test_nachpruefung_findet_alle_harten_regeln():
    s, k = vorlage()
    r = rechne(s, k, zeitlimit=30, protokoll=lambda t: None)
    e = r.einteilung
    assert not pruefe(s, k, e, r.bloecke, r.lektionen)
    kg = next(c for c in e.klassen if c.vorlage.raumtyp == "Kindergarten")
    zimmer = next(x for x in s.schulhaus(kg.schulhaus).raeume if x.typ == "Klassenzimmer")
    orig = kg.raum
    kg.raum = zimmer
    assert any("verlangt Raumtyp" in m.text for m in pruefe(s, k, e))
    kg.raum = orig
    s.max_klassen = 1
    assert any("Klassen, höchstens 1" in m.text for m in pruefe(s, k, e))
    s.max_klassen = None
    kid = e.klassen[0].kinder[0]
    e.schulhaus_von[kid] = next(x.name for x in s.schulhaeuser if x.name != e.klassen[0].schulhaus)
    assert any("Schulhaus der Klasse" in m.text for m in pruefe(s, k, e))


def test_transparenz_zaehlt_geschwister_wie_der_optimierer():
    from skf.transparenz import kriterien
    s, k = vorlage()
    r = rechne(s, k, zeitlimit=30, nur_klassen=True, protokoll=lambda t: None)
    zeile = next(z for z in kriterien(r) if z["kriterium"].startswith("Geschwister"))
    erwartet = sum(len({r.einteilung.schulhaus_von[i] for i in ids}) - 1
                   for gs in geschwistergruppen(s, k).values() for ids in gs if len(ids) > 1)
    assert zeile["anzahl"] == erwartet


# ------------------------------------------------------------------ Einlesen, Planung, Gebiete

@pytest.mark.parametrize("aendern, meldung", [
    (lambda c: c["planung"].update(quartiere=[{"name": "N", "kinder": float("inf")}]), "endliche Zahl"),
    (lambda c: c["planung"].update(jahre=200), "jahre"),
    (lambda c: c["gewichte"].update(klasse="viel"), "Zahl erwartet"),
    (lambda c: c["gewichte"].update(schulweg_pro_km=-1000), "negativ"),
    (lambda c: c["schulhaeuser"][0]["raeume"][0].update(anzahl=1_000_000), "Raum-Anzahl"),
    (lambda c: c["schulhaeuser"][0].update(stufen="2-1"), "umgekehrter Bereich"),
    (lambda c: c["klassenbildung"]["vorlagen"][1].update(min=25, max=20), "min ≤ max"),
    (lambda c: c.update(schulhaeuser=["x"]), "Liste von Einträgen"),
    (lambda c: c.update(basis_profil="../../etc/passwd"), "Kantonsprofil"),
    (lambda c: c.update(wegzeiten={"geschwindigkeit_kmh": 0}), "grösser als 0"),
])
def test_einlesen_lehnt_unsinn_ab(tmp_path, aendern, meldung):
    c = _cfg()
    c.setdefault("planung", {})
    c.setdefault("gewichte", {})
    aendern(c)
    pfad = tmp_path / "s.yaml"
    pfad.write_text(yaml.safe_dump(c, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match=meldung):
        baue_schule(lese_konfiguration(pfad))


def test_gewichte_als_ganze_zahlen():
    c = _cfg()
    c["gewichte"] = {"klasse": 250.6}
    assert baue_schule(c).gewichte["klasse"] == 251


def test_szenario_mischen_ohne_ueberraschungen():
    basis = {"raeume": [{"name": "A-Zi", "typ": "Klassenzimmer"}, {"name": "A-Halle", "typ": "Turnhalle"}],
             "schulbus": {"wartezeit_max": 15}}
    neu = _mische(basis, {"raeume": [{"typ": "Klassenzimmer", "plaetze": 20}],
                          "schulbus": {"linien": [{"name": "L1", "entfernen": True}]}})
    assert [r.get("name") for r in neu["raeume"]] == ["A-Zi", "A-Halle", None]   # angehängt, nicht ersetzt
    assert neu["schulbus"]["linien"] == []                                        # nichts zum Entfernen


def test_stufen_umgekehrt_oder_leer():
    with pytest.raises(ValueError):
        stufen_liste("KG2-KG1", ["KG1", "KG2", "1"])


def test_keine_neuen_kg1_wird_beachtet():
    from tests.test_planung_kosten import _prognose_von
    p0 = _prognose_von(_cfg(planung={"neue_kg1_pro_jahr": 0}), {"KG1": 20, "KG2": 20})
    standard = _prognose_von(_cfg(), {"KG1": 20, "KG2": 20})
    assert p0.jahre[1]["Lernende"] == 40 and standard.jahre[1]["Lernende"] == 60   # 0 neue KG1 statt 20


def test_gebiete_eingaben_geprueft():
    from skf.gebiete import lese_gebiete
    with pytest.raises(ValueError, match="Punkten"):
        lese_gebiete([{"name": "G", "flaeche": ["47", "8", "47"], "neue_lernende": 3}])
    with pytest.raises(ValueError, match="schulbus"):
        lese_gebiete([{"name": "G", "flaeche": [[47, 8], [47, 8.1], [47.1, 8]], "schulbus": True}])
    with pytest.raises(ValueError, match="höchstens"):
        lese_gebiete([{"name": "G", "flaeche": [[47, 8 + i / 1e4] for i in range(300)], "neue_lernende": 1}])


def test_angenommene_lernende_eindeutige_ids():
    from skf.gebiete import wende_an
    quadrat = [[47.0, 8.0], [47.0, 8.1], [47.1, 8.1], [47.1, 8.0]]
    s = baue_schule(_cfg(gebiete=[{"name": f"G{i}", "flaeche": quadrat, "neue_lernende": 5} for i in range(30)]))
    neu, _ = wende_an(s, [Kind("a", "", "1", "w", "", 47.05, 8.05)])
    assert len({k.id for k in neu}) == len(neu) == 151


def test_ueberspringen_in_stufe_mit_niveaus_braucht_entscheid():
    from skf.uebertritt import schritt
    from tests.test_uebertritt import SEK
    c = _cfg()
    c["jahrgaenge"] = c["jahrgaenge"] + ["3", "4", "5", "6"] + SEK
    s = baue_schule(c)
    st = schritt(s, Kind("x", "", "5", "w", "", 47.0, 8.0, uebertritt="überspringt"))
    assert st.art == "Entscheid fehlt" and "S1A" in st.hinweis


# ------------------------------------------------------------------ Rechenserver

@pytest.mark.parametrize("aendern, status", [
    (lambda a: a["konfiguration"].update(schulhaeuser=["x"]), 400),
    (lambda a: a["konfiguration"]["zeitraster"]["halbtage"].update(VM="08:00"), 400),
    (lambda a: a["konfiguration"].setdefault("gewichte", {}).update(klasse="viel"), 400),
    (lambda a: a.update(kinder=[{"id": f"x{i}", "jahrgang": "1"} for i in range(20_001)]), 413),
])
def test_server_antwortet_immer_mit_json(aendern, status):
    from skf.fernrechnen import anfrage, bearbeite
    a = json.loads(anfrage(_cfg(), "Basis", lade_kinder(VORLAGE / "kinder.csv"), 5))
    aendern(a)
    s, text = bearbeite(json.dumps(a))
    assert s == status and "fehler" in json.loads(text)


def test_server_versteckt_interne_fehler(monkeypatch):
    from skf import ablauf, fernrechnen
    monkeypatch.setattr(ablauf, "rechne", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("geheim /pfad")))
    s, text = fernrechnen.bearbeite(fernrechnen.anfrage(_cfg(), "Basis", lade_kinder(VORLAGE / "kinder.csv"), 5))
    assert s == 500 and "geheim" not in text


def test_ergebnis_ohne_fehler_bleibt_gleich():
    """Kontrolle: die Härtung ändert gültige Ergebnisse nicht (Beispiel Vorlage, ein Lauf)."""
    s, k = vorlage()
    r = rechne(s, k, zeitlimit=30, protokoll=lambda t: None)
    assert isinstance(r, Ergebnis) and r.vollstaendig and not r.anzahl("Fehler")

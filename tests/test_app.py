# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""End-to-End-Test der Bedienoberfläche: Daten laden → prüfen → berechnen → Ergebnis."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).parent.parent / "skf" / "app.py")


def _seite(at, name):
    at.sidebar.radio(key="seite").set_value(name).run(timeout=180)


@pytest.fixture(autouse=True)
def verlauf_ordner(tmp_path, monkeypatch):
    monkeypatch.setenv("SKF_DATEN", str(tmp_path))
    return tmp_path


def _vorlage(at):
    next(b for b in at.button if "Kleine Vorlage" in b.label).click().run()
    assert not at.exception


def test_app_ablauf_mit_vorlage(verlauf_ordner):
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    assert not at.exception
    assert at.session_state["seite"] == "start"

    _vorlage(at)
    assert at.session_state["seite"] == "daten"
    assert {"Raumliste aus Excel/CSV übernehmen", "Lehrpersonenliste aus Excel/CSV übernehmen"} <= \
        {e.label for e in at.expander}
    assert any("110 Lernende" in c.value for c in at.caption)

    _seite(at, "pruefen")
    assert not at.exception
    assert any("Keine Probleme gefunden" in s.value for s in at.success)

    _seite(at, "berechnen")
    at.select_slider[0].set_value(30)
    next(b for b in at.button if "berechnen" in b.label).click().run(timeout=300)
    assert not at.exception
    r = at.session_state["ergebnis"]
    assert r.vollstaendig and r.anzahl("Fehler") == 0

    _seite(at, "ergebnis")
    assert not at.exception
    assert any("Alle harten Regeln erfüllt" in s.value for s in at.success)
    assert [m.label for m in at.metric][:2] == ["Klassen", "Ø Klassengrösse"]
    # Raumplanung im Reiter Stundenpläne: Auslastung und Wochenplan je Raum
    next(x for x in at.radio if x.label == "Stundenplan für").set_value("Raum").run()
    assert "Räume" in [m.label for m in at.metric]
    assert at.selectbox(key="raum_wahl").value.startswith("Schulhaus A · ")
    assert {b.label for b in at.get("download_button")} >= {
        "Klassenlisten (Excel, druckfertig)", "Alles als ZIP (inkl. CSV-Rohdaten)"}

    # Verlauf: Berechnung wurde gespeichert
    assert len(list((verlauf_ordner / "verlauf").iterdir())) == 1
    _seite(at, "verlauf")
    assert not at.exception


def test_manuell_verschieben(verlauf_ordner):
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    _vorlage(at)
    _seite(at, "berechnen")
    at.select_slider[0].set_value(30)
    next(b for b in at.button if "berechnen" in b.label).click().run(timeout=300)
    _seite(at, "ergebnis")
    r = at.session_state["ergebnis"]
    kind = next(k for k in r.kinder if k.jahrgang == "1")
    ziel = next(c.name for c in r.einteilung.klassen
                if "1" in c.vorlage.jahrgaenge and c.name != r.einteilung.klasse_von[kind.id])
    bisher = r.einteilung.klasse_von[kind.id]
    at.selectbox(key="kl_wahl").set_value(bisher).run()
    at.selectbox(key=f"anp_kind_{bisher}").set_value(kind.id).run()
    at.selectbox(key=f"anp_ziel_{kind.id}").set_value(ziel).run()
    next(b for b in at.button if b.label == "Verschieben und prüfen").click().run()
    assert not at.exception
    r = at.session_state["ergebnis"]
    assert r.einteilung.klasse_von[kind.id] == ziel and r.manuell


def test_app_bearbeitung_wirkt_sich_aus():
    """Eine in der Tabelle geänderte Lehrperson (Fach gestrichen) führt zu einer Meldung in der Prüfung."""
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    _vorlage(at)
    df = at.session_state["bearbeitet"]["Lehrpersonen"].copy()
    df.loc[df["name"] == "SHP (IF)", "faecher"] = "Werken"
    at.session_state["bearbeitet"]["Lehrpersonen"] = df
    _seite(at, "pruefen")
    texte = [e.value for e in at.error]
    assert any("unbekanntes Fach 'Werken'" in t for t in texte), texte


def test_schulbus_und_wegzeiten_bleiben_beim_bearbeiten_erhalten():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    next(b for b in at.button if "Beispiel Malters" in b.label).click().run()
    assert not at.exception
    rest = at.session_state["extra"]["rest"]
    linie = rest["schulbus"]["linien"][0]
    assert linie["name"] == "Schulbus Blatten" and linie["abfahrt"]["NM"] == ["14:25", "15:15"]
    assert linie["ankunft"] == {"VM": "07:50", "NM": "13:20"}
    assert rest["wegzeiten"]["minuten"] == [["Bündtmättli", "Eischachen", 10]]
    assert at.toggle(key="wegzeiten_an").value
    _seite(at, "pruefen")
    assert not at.exception


def test_schuljahreswechsel_in_der_app(verlauf_ordner):
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    _vorlage(at)
    vorher = len(at.session_state["bearbeitet"]["Kinder"])
    _seite(at, "uebertritt")
    assert not at.exception
    assert [m.label for m in at.metric] == ["Lernende neu", "Übertritte", "Austritte", "Entscheid fehlt"]
    next(b for b in at.button if b.label == "Als neues Schuljahr übernehmen").click().run()
    assert not at.exception
    assert at.session_state["seite"] == "daten"
    assert at.session_state["extra"]["rest"]["schuljahr"] == "2028/29"
    kinder = at.session_state["bearbeitet"]["Kinder"]
    assert len(kinder) < vorher and "KG1" not in set(kinder["jahrgang"])  # KG1 → KG2, oberste Stufe tritt aus


def test_arbeitsstand_wird_gesichert_und_fortgesetzt(verlauf_ordner):
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    _vorlage(at)
    assert (verlauf_ordner / "arbeitsstand" / "stammdaten.json").exists()
    neu = AppTest.from_file(APP, default_timeout=180)  # App neu gestartet
    neu.run()
    neu.button(key="weiter").click().run()
    assert not neu.exception and neu.session_state["seite"] == "daten"
    assert len(neu.session_state["bearbeitet"]["Kinder"]) == 110

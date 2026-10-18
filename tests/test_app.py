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
    at.selectbox(key="anp_kind").set_value(kind.id).run()
    at.selectbox(key="anp_ziel").set_value(ziel).run()
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

"""End-to-End-Test der Bedienoberfläche: Daten laden → prüfen → berechnen → Ergebnis."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).parent.parent / "skf" / "app.py")


def _seite(at, name):
    at.sidebar.radio(key="seite").set_value(name).run(timeout=180)


def test_app_ablauf_mit_vorlage():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    assert not at.exception
    assert "Noch keine Daten geladen." in [i.value for i in at.info]

    next(b for b in at.button if b.label == "Kleine Vorlage laden").click().run()
    assert not at.exception
    assert any("110 Lernende" in c.value for c in at.caption)

    _seite(at, "2 · Prüfen")
    assert not at.exception
    assert any("Keine Probleme gefunden" in s.value for s in at.success)

    _seite(at, "3 · Berechnen")
    at.slider[0].set_value(30)
    next(b for b in at.button if "berechnen" in b.label).click().run(timeout=300)
    assert not at.exception
    r = at.session_state["ergebnis"]
    assert r.vollstaendig and r.anzahl("Fehler") == 0

    _seite(at, "4 · Ergebnis")
    assert not at.exception
    assert any("Alle harten Regeln erfüllt" in s.value for s in at.success)
    assert [m.label for m in at.metric][:2] == ["Klassen", "Ø Klassengrösse"]
    assert {b.label for b in at.get("download_button")} >= {
        "⬇ Klassenlisten (Excel, druckfertig)", "⬇ Alles als ZIP (inkl. CSV-Rohdaten)"}


def test_app_bearbeitung_wirkt_sich_aus():
    """Eine in der Tabelle geänderte Lehrperson (Fach gestrichen) führt zu einer Meldung in der Prüfung."""
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    next(b for b in at.button if b.label == "Kleine Vorlage laden").click().run()
    df = at.session_state["bearbeitet"]["Lehrpersonen"].copy()
    df.loc[df["name"] == "SHP (IF)", "faecher"] = "Werken"
    at.session_state["bearbeitet"]["Lehrpersonen"] = df
    _seite(at, "2 · Prüfen")
    texte = [e.value for e in at.error]
    assert any("unbekanntes Fach 'Werken'" in t for t in texte), texte

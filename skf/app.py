# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Bedienoberfläche für Schulleitung und Lehrpersonen (Streamlit).

Start:  skf app   (oder Doppelklick auf start-windows.bat / start-mac.command / start-linux.sh)

Ablauf in vier Schritten: 1 Daten → 2 Prüfen → 3 Berechnen → 4 Ergebnis, dazu Verlauf und Hilfe.
Alle Daten bleiben auf dem eigenen Computer.
"""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import yaml

from skf import verlauf
from skf.ablauf import Ergebnis, rechne, verschiebe
from skf.austausch import (BLAETTER, KINDER_SPALTEN, LISTENFELDER, ZAHLFELDER, _cfg_aus_tabellen, _tabellen_aus_cfg,
                           exportiere_stammdaten, importiere_stammdaten, kind_als_dict, lese_kinder, lese_liste,
                           raumtypen, uebernehme_liste)
from skf.bericht import (CSS, _empfehlungen_html, _osm_karte, _plan, _raumbelegung, _wuensche_html, schreibe_csv,
                         schreibe_html, transparenz_html)
from skf.daten import (GEWICHT_HEBEL, STANDARD_GEWICHTE, beispiel_ordner, lade_schule, szenario_aus_hebeln,
                       szenario_infos)
from skf.export import exportiere_listen
from skf.pruefung import SCHWEREGRADE, vorpruefung
from skf.transparenz import begruendung, regeln
from skf.datenablage import arbeitsstand_info, arbeitsstand_ordner, lade_arbeitsstand, speichere_arbeitsstand
from skf.version import __version__

BEISPIELE = beispiel_ordner()
ICON = {"Fehler": ":material/cancel:", "Warnung": ":material/warning:", "Hinweis": ":material/info:"}
FARBE = {"Fehler": "red", "Warnung": "orange", "Hinweis": "gray"}

# Design-System wie genealogy-store: helle Fläche, weisse Karten, feine Rahmen, Akzent Wandtafelgrün
STIL = """
<style>
.stApp { background:#f6f7fb; }
.block-container { max-width:1240px; padding-top:2.2rem; }
[data-testid="stSidebar"] { background:#ffffff; border-right:1px solid #e4e7ee; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { font-size:13px; }
h1, h2, h3 { letter-spacing:-.01em; color:#14171f; }
h2 { font-size:21px !important; font-weight:700 !important; }
h3 { font-size:16px !important; font-weight:600 !important; }
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) { border-radius:12px; }
div[data-testid="stVerticalBlockBorderWrapper"][class*="border"], [data-testid="stExpander"] details {
  background:#ffffff; border-color:#e4e7ee !important; border-radius:12px !important;
  box-shadow:0 1px 2px rgba(20,23,31,.05); }
[data-testid="stMetric"] { background:#ffffff; border:1px solid #e4e7ee; border-radius:12px; padding:12px 14px;
  box-shadow:0 1px 2px rgba(20,23,31,.05); }
[data-testid="stMetricLabel"] p { font-size:12px; color:#676e7d; }
[data-testid="stMetricValue"] { font-size:24px; font-weight:600; }
.stButton > button, .stDownloadButton > button { border-radius:8px; font-weight:500; font-size:13px;
  border-color:#cdd2dd; }
.stButton > button[kind="primary"] { background:#2f5d50; border-color:#2f5d50; }
.stButton > button[kind="primary"]:hover { background:#244a40; border-color:#244a40; }
[data-baseweb="tab-list"] { gap:4px; border-bottom:1px solid #e4e7ee; }
[data-baseweb="tab"] p { font-size:13px; font-weight:500; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"] { border:1px solid #e4e7ee; border-radius:8px; overflow:hidden; }
.skf-kopf { display:flex; align-items:center; gap:12px; margin:0 0 14px; }
.skf-logo { width:40px; height:40px; border-radius:10px; background:#2f5d50; color:#fff; display:grid;
  place-items:center; box-shadow:0 2px 6px rgba(20,23,31,.07); flex:none; }
.skf-kopf h1 { font-size:21px; font-weight:700; margin:0; padding:0; line-height:1.2; }
.skf-kopf p { margin:2px 0 0; color:#676e7d; font-size:13px; }
.skf-schritt { color:#2f5d50; font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
</style>
"""


def _logo() -> str:
    """Logo als Bild (Streamlit filtert eingebettetes SVG aus st.html)."""
    import base64
    from skf.icons import PFADE
    svg = f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='white'><path d='{PFADE['school']}'/></svg>"
    return (f"<div class='skf-logo'><img alt='' width='24' height='24' "
            f"src='data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}'></div>")


def _kopf(titel: str, untertitel: str, schritt: str = "") -> None:
    st.html(f"<div class='skf-kopf'>{_logo()}<div>"
            f"{f'<div class=skf-schritt>{schritt}</div>' if schritt else ''}<h1>{titel}</h1><p>{untertitel}</p>"
            "</div></div>")
SPALTEN_LERNENDE = {
    "id": "ID", "vorname": "Vorname", "nachname": "Nachname", "name": "Name", "jahrgang": "Jahrgang (KG1, KG2, 1–6)",
    "geschlecht": "Geschlecht (w/m)", "adresse": "Adresse", "lat": "Breite", "lon": "Länge", "familie": "Familie (Geschwister)",
    "if": "IF", "daz": "DaZ (anfang/aufbau)", "is": "IS", "foerderbedarf": "weiterer Förderbedarf",
    "schulhaus_fix": "Schulhaus fix", "bisheriges_schulhaus": "Schulhaus Vorjahr",
    "bisherige_klasse": "Klasse/KG-Gruppe Vorjahr", "zusammen_mit": "Wunsch: zusammen mit (IDs)",
    "nicht_mit": "Wunsch: nicht zusammen mit (IDs)", "wunsch_schulhaus": "Wunsch-Schulhaus", "bus": "Schulbus (Linie)",
    "bemerkung": "Bemerkung",
}

GEWICHT_TEXT = {
    "schulweg_pro_km": "Kurzer Schulweg (pro km)",
    "klasse": "Wenige Klassen (pro Klasse)",
    "groessen_abweichung": "Klassengrösse nahe am Ideal",
    "geschwister_getrennt": "Geschwister im selben Schulhaus",
    "geschlecht_ungleich": "Ausgeglichen Mädchen/Knaben",
    "foerderbedarf_ungleich": "IF/DaZ/IS ausgeglichen verteilen",
    "nicht_zusammen": "Wunsch „nicht zusammen mit“",
    "schulhaus_gewechselt": "Im bisherigen Schulhaus bleiben",
    "klasse_getrennt": "Bisherige Klasse zusammenhalten",
    "allein_aus_klasse": "Gspänli-Regel (niemand allein aus KG-Gruppe/Klasse)",
    "wunsch_zusammen": "Wunsch „zusammen mit“",
    "wunsch_schulhaus": "Wunsch-Schulhaus",
    "lehrperson_pro_klasse": "Wenige Lehrpersonen pro Klasse",
    "pensum_unterschritten": "Mindestpensum erreichen",
    "lehrperson_mehrere_schulhaeuser": "Lehrperson an einem Schulhaus",
    "lehrperson_kontinuitaet": "Lehrperson führt ihre Klasse weiter",
    "praesenz_halbtag": "Wenige Präsenz-Halbtage für Lehrpersonen",
    "schulhauswechsel": "Kein Schulhauswechsel im Halbtag",
    "springstunde": "Keine Springstunden",
}


# ------------------------------------------------------------------ Hilfen

# Lesbare Spaltentitel der Stammdaten-Tabellen (die Daten behalten ihre Feldnamen)
SPALTEN_TABELLEN = {
    "schulhaus": "Schulhaus", "name": "Name", "typ": "Raumtyp", "anzahl": "Anzahl", "plaetze": "Plätze",
    "nicht_verfuegbar": "Nicht verfügbar", "kuerzel": "Kürzel", "lat": "Breite (lat)", "lon": "Länge (lon)",
    "nutzt": "Nutzt (Raumtyp=Schulhaus)", "stufen": "Stufen (z.B. KG1-6, S1-S3)", "faecher": "Fächer", "jahrgaenge": "Jahrgänge", "schulhaeuser": "Schulhäuser",
    "pensum_min": "Pensum min.", "pensum_max": "Pensum max.", "bisherige_klasse": "Bisherige Klasse",
    "bezeichnung": "Bezeichnung", "raumtyp": "Raumtyp", "min": "Min.", "max": "Max.", "ideal": "Ideal",
    "strafe": "Strafe", "min_pro_jahrgang": "Min. pro Jahrgang", "dauer": "Dauer (Lektionen)",
    "max_pro_tag": "Max. pro Tag", "merkmal": "Merkmal", "basis": "Basis", "pro_kind": "Pro Kind",
    "frei_bis": "Frei bis", "parallel_zu": "Parallel zu", "quelle": "Quelle",
}


def _html(inhalt: str, hoehe: int = 500) -> None:
    components.html(f"<style>{CSS} body{{max-width:none;padding:4px}}</style>{inhalt}", height=hoehe, scrolling=True)


def _schule_aus_cfg(cfg: dict, szenario: str = "Basis"):
    with tempfile.TemporaryDirectory() as tmp:
        pfad = Path(tmp) / "schule.yaml"
        pfad.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return lade_schule(pfad, szenario)


def _kinder_aus_df(df: pd.DataFrame):
    with tempfile.TemporaryDirectory() as tmp:
        pfad = Path(tmp) / "kinder.csv"
        df.fillna("").astype(str).to_csv(pfad, index=False)
        return lese_kinder(pfad)


def _df_aus_tabelle(zeilen: list[dict], spalten: list[str]) -> pd.DataFrame:
    def wert(z, s):
        v = z.get(s)
        if isinstance(v, list):
            return "; ".join(map(str, v))
        if s in ZAHLFELDER:
            return v  # Zahlen bleiben Zahlen (leer = None)
        return "" if v is None else str(v)
    alle = spalten + sorted({k for z in zeilen for k in z} - set(spalten))
    return pd.DataFrame([{s: wert(z, s) for s in alle} for z in zeilen], columns=alle)


def _tabelle_aus_df(df: pd.DataFrame) -> list[dict]:
    zeilen = []
    for z in df.to_dict("records"):
        e = {}
        for k, v in z.items():
            if v is None or v == "" or (isinstance(v, float) and v != v):  # leer oder NaN
                continue
            if k in LISTENFELDER:
                v = [x.strip() for x in str(v).replace(",", ";").split(";") if x.strip()]
            elif k in ZAHLFELDER:
                v = float(str(v).replace(",", "."))
                v = int(v) if v.is_integer() else v
            elif isinstance(v, float) and v.is_integer():
                v = int(v)
            e[k] = v
        if e:
            zeilen.append(e)
    return zeilen


def _laden(cfg: dict, kinder) -> None:
    """Neue Daten übernehmen. Original und bearbeiteter Stand werden getrennt gehalten
    (die Tabellen-Editoren erhalten immer das Original und liefern den bearbeiteten Stand)."""
    st.session_state.version = st.session_state.get("version", 0) + 1
    st.session_state.kinder_df = pd.DataFrame([kind_als_dict(k) for k in kinder], columns=KINDER_SPALTEN)
    tabellen, extra = _tabellen_aus_cfg(cfg)
    st.session_state.tabellen = {n: _df_aus_tabelle(t, BLAETTER[n]) for n, t in tabellen.items()}
    st.session_state.bearbeitet = {"Kinder": st.session_state.kinder_df, **st.session_state.tabellen}
    st.session_state.extra = extra
    st.session_state.pop("ergebnis", None)
    st.toast("Daten geladen", icon=":material/check_circle:")


def _aktuelle_daten():
    """Konfiguration und Lernende aus den (evtl. bearbeiteten) Tabellen."""
    b = st.session_state.bearbeitet
    t = {n: _tabelle_aus_df(b[n]) for n in st.session_state.tabellen}
    cfg = _cfg_aus_tabellen(t, st.session_state.extra["rest"], st.session_state.extra["stundentafel"])
    return cfg, _kinder_aus_df(b["Kinder"])


# ------------------------------------------------------------------ Navigation

SEITEN = {"start": ":material/home: Start", "daten": ":material/table_view: 1 · Daten",
          "pruefen": ":material/fact_check: 2 · Prüfen", "berechnen": ":material/calculate: 3 · Berechnen",
          "ergebnis": ":material/insights: 4 · Ergebnis", "uebertritt": ":material/upgrade: Schuljahreswechsel",
          "verlauf": ":material/history: Verlauf",
          "hilfe": ":material/help: Hilfe"}
TITEL = {k: v.split(": ", 1)[1].split(" · ")[-1] for k, v in SEITEN.items()}


def _gehe(seite: str) -> None:
    st.session_state.seite = seite


def _weiter(seite: str, text: str | None = None) -> None:
    st.button(text or f"Weiter: {TITEL[seite]}", type="primary", on_click=_gehe, args=(seite,), key=f"weiter_{seite}",
              icon=":material/arrow_forward:")


def _ja_nein(ok: bool) -> str:
    return ":green[:material/check_circle:]" if ok else ":red[:material/cancel:]"


def _beispiel(name: str) -> None:
    ordner = BEISPIELE / name
    _laden(yaml.safe_load((ordner / "schule.yaml").read_text(encoding="utf-8")), lese_kinder(ordner / "kinder.csv"))
    st.session_state.seite = "daten"


# ------------------------------------------------------------------ Seiten

def _arbeitsstand_laden() -> None:
    _laden(*lade_arbeitsstand())
    st.session_state.seite = "daten"


def _arbeitsstand_sichern() -> None:
    """Eingaben bei jeder Änderung dauerhaft ablegen (JSON + YAML + CSV) – nichts geht verloren."""
    if "tabellen" not in st.session_state:
        return
    try:
        cfg, kinder = _aktuelle_daten()
        zeichen = hashlib.sha256((json.dumps(cfg, sort_keys=True, default=str)
                                  + st.session_state.bearbeitet["Kinder"].to_csv()).encode()).hexdigest()
        if st.session_state.get("gesichert") != zeichen:
            speichere_arbeitsstand(cfg, kinder)
            st.session_state.gesichert = zeichen
            st.session_state.gesichert_um = datetime.now().strftime("%H:%M")
        st.sidebar.caption(f":material/save: Arbeitsstand gesichert {st.session_state.get('gesichert_um', '')}",
                           help=f"{arbeitsstand_ordner()} – stammdaten.json, schule.yaml, kinder.csv")
    except Exception as fehler:  # noqa: BLE001 – Sichern darf die Bedienung nie unterbrechen
        st.sidebar.caption(f":material/warning: Arbeitsstand nicht gesichert: {fehler}")


def seite_start() -> None:
    _kopf("Klassenbildung & Stundenplan", "Volksschule · Kindergarten, Primar und Oberstufe · alle Daten bleiben "
          "auf diesem Computer")
    st.write("Bildet Klassen, verteilt Lehraufträge und erstellt den Stundenplan – unter Berücksichtigung von "
             "Schulwegen, Geschwistern, Kindergartengruppen, Wünschen der Erziehungsberechtigten, IF/DaZ/IS, "
             "Verfügbarkeiten und kantonalen Vorgaben. **Alle Daten bleiben auf diesem Computer.**")
    hat_daten, hat_ergebnis = "tabellen" in st.session_state, bool(st.session_state.get("ergebnis"))
    c = st.columns(4)
    for spalte, (titel, text, fertig) in zip(c, [
            ("1 Daten", "Lernende, Lehrpersonen, Schulhäuser erfassen oder Excel hochladen", hat_daten),
            ("2 Prüfen", "Fehlende oder widersprüchliche Angaben finden", hat_daten),
            ("3 Berechnen", "Klassen und Stundenplan berechnen lassen", hat_ergebnis),
            ("4 Ergebnis", "Karte, Klassenlisten, Stundenpläne, Planung & Kosten", hat_ergebnis)]):
        with spalte.container(border=True):
            st.markdown(f"{':green[:material/check_circle:]' if fertig else ':gray[:material/radio_button_unchecked:]'} "
                        f"**{titel}**")
            st.caption(text)
    info = arbeitsstand_info()
    if info and not hat_daten:
        with st.container(border=True):
            st.markdown(f":material/restore: **Weiterarbeiten** – Arbeitsstand vom {info['zeit']}: "
                        f"{info['schule']}, {info['lernende']} Lernende")
            st.button("Letzten Arbeitsstand fortsetzen", type="primary", icon=":material/restore:",
                      on_click=_arbeitsstand_laden, key="weiter")
    st.subheader("Loslegen")
    a, b, d = st.columns(3)
    a.button("Beispiel Malters ansehen", icon=":material/folder_open:", on_click=_beispiel, args=("malters",), width="stretch",
             help="884 fiktive Lernende, KG bis Oberstufe, 4 Schulhäuser – zeigt alle Funktionen")
    b.button("Kleine Vorlage öffnen", icon=":material/extension:", on_click=_beispiel, args=("vorlage",), width="stretch",
             help="110 Lernende, 2 Schulhäuser – ideal zum Ausprobieren und als Ausgangspunkt")
    d.button("Eigene Daten hochladen", icon=":material/upload:", on_click=_gehe, args=("daten",), width="stretch")
    if hat_ergebnis:
        st.success("Es liegt ein berechnetes Ergebnis vor.")
        _weiter("ergebnis", "Zum Ergebnis")
    staende = verlauf.staende()
    if staende:
        st.caption(f":material/history: {len(staende)} gespeicherte Stände im Verlauf (zuletzt {staende[0]['zeit'].replace('T', ' ')}).")


def seite_daten() -> None:
    _kopf("Daten", "Lernende, Lehrpersonen, Schulhäuser und Regeln erfassen oder hochladen", "Schritt 1 von 4")
    c1, c2, c3 = st.columns(3)
    c1.button("Beispiel Malters laden", on_click=_beispiel, args=("malters",), width="stretch")
    c2.button("Kleine Vorlage laden", on_click=_beispiel, args=("vorlage",), width="stretch")
    with c3.popover("Eigene Dateien hochladen", icon=":material/upload:", width="stretch"):
        st.caption("Am einfachsten: zuerst die *Kleine Vorlage* laden, als Excel speichern, dort ausfüllen und "
                   "hier wieder hochladen.")
        stamm = st.file_uploader("Stammdaten (Excel .xlsx) oder Konfiguration (.yaml/.json)",
                                 type=["xlsx", "json", "yaml", "yml"])
        lernende = st.file_uploader("Lernende (CSV oder Excel) – nur bei .yaml nötig", type=["csv", "xlsx"])
        if stamm and st.button("Übernehmen", type="primary"):
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    pfad = Path(tmp) / stamm.name
                    pfad.write_bytes(stamm.getvalue())
                    if pfad.suffix in (".yaml", ".yml"):
                        if not lernende:
                            st.error("Bitte zusätzlich die Liste der Lernenden hochladen.")
                            return
                        lpfad = Path(tmp) / lernende.name
                        lpfad.write_bytes(lernende.getvalue())
                        _laden(yaml.safe_load(pfad.read_text(encoding="utf-8")), lese_kinder(lpfad))
                    else:
                        _laden(*importiere_stammdaten(pfad))
                st.toast("Daten übernommen", icon=":material/check_circle:")
            except Exception as fehler:  # noqa: BLE001 – verständlich melden statt abstürzen
                st.error(f"Die Datei konnte nicht gelesen werden: {fehler}")

    if "tabellen" not in st.session_state:
        st.info("Noch keine Daten geladen.")
        return

    cfg = st.session_state.extra["rest"]
    st.caption(f"**{cfg.get('name', 'Schule')}** · Schuljahr {cfg.get('schuljahr', '–')} · "
               f"Kantonsprofil: {cfg.get('basis_profil', 'keines')} · "
               f"{len(st.session_state.bearbeitet['Kinder'])} Lernende")
    tabs = st.tabs([":material/child_care: Lernende", ":material/co_present: Lehrpersonen", ":material/school: Schulhäuser",
                    ":material/meeting_room: Räume", ":material/category: Klassentypen", ":material/menu_book: Fächer",
                    ":material/volunteer_activism: Förderangebote", ":material/tune: Gewichtung",
                    ":material/directions_bus: Schulbus & Wege"])
    with tabs[0]:
        alle = st.toggle("Alle Spalten zeigen (Koordinaten, Förderdetails)", key="alle_spalten")
        st.caption("Wünsche: IDs mit `;` trennen. *Klasse/KG-Gruppe Vorjahr* hält Gruppen zusammen (Gspänli-Regel). "
                   "IF/IS: `ja`; DaZ: `anfang` oder `aufbau`. Neue Zeile: unten in der Tabelle.")
        sichtbar = None if alle else ["id", "vorname", "nachname", "jahrgang", "geschlecht", "adresse", "familie",
                                      "if", "daz", "is", "bisherige_klasse", "zusammen_mit", "nicht_mit",
                                      "wunsch_schulhaus", "bus", "bemerkung"]
        st.session_state.bearbeitet["Kinder"] = st.data_editor(
            st.session_state.kinder_df, num_rows="dynamic", width="stretch", height=430,
            key=f"ed_kinder_{st.session_state.version}", column_order=sichtbar,
            column_config={k: st.column_config.Column(v) for k, v in SPALTEN_LERNENDE.items()})
    namen = {1: "Lehrpersonen", 2: "Schulhaeuser", 3: "Raeume", 4: "Klassentypen", 5: "Faecher", 6: "Foerderangebote"}
    hinweise = {
        1: "Nicht verfügbar z.B. `Mi; Fr-NM; Mo-VM-1`. Förderangebote unterrichten Lehrpersonen mit dem Fach "
           "`IF`, `DaZ Anfang`, `DaZ Aufbau`. *bisherige_klasse*: Klasse, die die Lehrperson weiterführt.",
        2: "*stufen*: welche Stufen hier zur Schule gehen, z.B. `KG1-6` (Kindergarten und Primar), `S1-S3` (Oberstufe) "
           "oder `5-S3`; leer = alle, für die es Räume gibt. Koordinaten (lat/lon) z.B. aus map.geo.admin.ch.",
        3: "Gleichartige Räume mit `anzahl` zusammenfassen. Nicht verfügbar z.B. `Fr-NM` (Vereinsnutzung).",
        4: "Erlaubte Klassen: Jahrgänge (`1; 2` = Mehrjahrgangsklasse), Mindest-/Höchstgrösse, Raumtyp.",
        6: "Ergänzt oder überschreibt die Förderangebote des Kantonsprofils (gleicher Name).",
    }
    for i, name in namen.items():
        with tabs[i]:
            if i in hinweise:
                st.caption(hinweise[i])
            if name in ("Raeume", "Lehrpersonen"):
                _liste_hochladen(name)
            st.session_state.bearbeitet[name] = st.data_editor(
                st.session_state.tabellen[name], num_rows="dynamic", width="stretch",
                key=f"ed_{name}_{st.session_state.version}",
                column_config={k: st.column_config.Column(v) for k, v in SPALTEN_TABELLEN.items()})
    with tabs[7]:
        rest = st.session_state.extra["rest"]
        kb = rest.setdefault("klassenbildung", {})
        c1, c2 = st.columns(2)
        kb["geschwister"] = c1.radio("Geschwister", ["weich", "hart", "aus"],
                                     index=["weich", "hart", "aus"].index(kb.get("geschwister", "weich")),
                                     horizontal=True, help="hart = immer im selben Schulhaus; weich = möglichst")
        profil = rest.get("profil") or {}
        profil["verbindlich"] = c2.toggle("Klassengrössen des Kantons verbindlich einhalten",
                                          value=bool(profil.get("verbindlich")))
        rest["profil"] = profil
        st.caption("Was ist wichtiger? Höherer Wert = stärker berücksichtigt, 0 = egal.")
        gew = rest.get("gewichte") or {}
        gruppen = {"Klassenbildung": list(STANDARD_GEWICHTE)[:12], "Lehrpersonen": list(STANDARD_GEWICHTE)[12:16],
                   "Stundenplan": list(STANDARD_GEWICHTE)[16:]}
        for titel, schluessel in gruppen.items():
            with st.expander(titel, expanded=titel == "Klassenbildung"):
                spalten = st.columns(3)
                for i, k in enumerate(schluessel):
                    standard = STANDARD_GEWICHTE[k]
                    gew[k] = spalten[i % 3].slider(GEWICHT_TEXT.get(k, k), 0, max(1000, standard * 3),
                                                   int(gew.get(k, standard)), step=10, key=f"g_{k}")
        rest["gewichte"] = {k: v for k, v in gew.items() if v != STANDARD_GEWICHTE[k]}

    with tabs[8]:
        _schulbus_und_wege(st.session_state.extra["rest"])

    cfg_neu, kinder = _aktuelle_daten()
    with tempfile.TemporaryDirectory() as tmp:
        exportiere_stammdaten(cfg_neu, kinder, Path(tmp) / "stammdaten.xlsx")
        inhalt = (Path(tmp) / "stammdaten.xlsx").read_bytes()
    a, b = st.columns(2)
    a.download_button("Stammdaten als Excel speichern", inhalt, "stammdaten.xlsx", icon=":material/save:", width="stretch")
    with b:
        _weiter("pruefen")


def _zeiten(text) -> list[str]:
    return [t.strip() for t in str(text or "").replace(",", ";").split(";") if t.strip()]


def _schulbus_und_wege(rest: dict) -> None:
    """Optionale Regeln für Dörfer: Schulbus und Wegzeiten der Lehrpersonen."""
    st.markdown("**Schulbus** – Kinder mit einer Buslinie (Spalte *Schulbus* bei den Lernenden) kommen nur in "
                "Schulhäuser, die die Linie anfährt. Ihr Unterricht beginnt nach der Ankunft und endet passend zu "
                "einer Abfahrt. Zeiten wie `07:50`, mehrere mit `;` trennen.")
    bus = rest.get("schulbus") or {}
    def text(v) -> str:
        return v if isinstance(v, str) else "; ".join(str(x) for x in v or [])

    zeilen = [{"name": l.get("name", ""), "schulhaeuser": text(l.get("schulhaeuser")),
               **{f"{art}_{ht.lower()}": text((l.get(art) or {}).get(ht)) for art in ("ankunft", "abfahrt")
                  for ht in ("VM", "NM")}}
              for l in bus.get("linien") or []]
    df = st.data_editor(
        pd.DataFrame(zeilen, columns=["name", "schulhaeuser", "ankunft_vm", "ankunft_nm", "abfahrt_vm", "abfahrt_nm"]),
        num_rows="dynamic", width="stretch", key=f"ed_bus_{st.session_state.version}",
        column_config={"name": "Linie", "schulhaeuser": "Angefahrene Schulhäuser", "ankunft_vm": "Ankunft Vormittag",
                       "ankunft_nm": "Ankunft Nachmittag", "abfahrt_vm": "Abfahrten Mittag",
                       "abfahrt_nm": "Abfahrten Nachmittag"})
    warte = st.number_input("Höchste Wartezeit der Kinder (Minuten)", 0, 60, int(bus.get("wartezeit_max", 15)), 5)
    linien = []
    for z in df.to_dict("records"):
        if not str(z.get("name") or "").strip():
            continue
        l = {"name": str(z["name"]).strip(), "schulhaeuser": _zeiten(z.get("schulhaeuser"))}
        ank = {k: str(z[f"ankunft_{k.lower()}"]).strip() for k in ("VM", "NM") if str(z.get(f"ankunft_{k.lower()}") or "").strip()}
        ab = {k: _zeiten(z.get(f"abfahrt_{k.lower()}")) for k in ("VM", "NM") if _zeiten(z.get(f"abfahrt_{k.lower()}"))}
        if ank:
            l["ankunft"] = ank
        if ab:
            l["abfahrt"] = ab
        linien.append(l)
    if linien:
        rest["schulbus"] = {"wartezeit_max": int(warte), "linien": linien}
    else:
        rest.pop("schulbus", None)

    st.divider()
    st.markdown("**Wegzeiten der Lehrpersonen** – zwei Lektionen direkt nacheinander in verschiedenen Schulhäusern "
                "nur, wenn die Pause für den Weg reicht.")
    weg = rest.get("wegzeiten")
    an = st.toggle("Wegzeiten berücksichtigen", value=bool(weg), key="wegzeiten_an")
    if not an:
        rest.pop("wegzeiten", None)
        return
    weg = weg if isinstance(weg, dict) else {}
    kmh = st.number_input("Geschwindigkeit für Wege ohne eigene Angabe (km/h, aus Koordinaten)", 3, 60,
                          int(weg.get("geschwindigkeit_kmh", 20)))
    minuten = weg.get("minuten") or {}
    paare = [{"von": a, "nach": b, "minuten": v} for a, b, v in (
        [[*str(k).partition(" - " if " - " in str(k) else "-")[::2], v] for k, v in minuten.items()]
        if isinstance(minuten, dict) else minuten)]
    df = st.data_editor(pd.DataFrame(paare, columns=["von", "nach", "minuten"]), num_rows="dynamic", width="stretch",
                        key=f"ed_weg_{st.session_state.version}",
                        column_config={"von": "Schulhaus", "nach": "Schulhaus",
                                       "minuten": st.column_config.NumberColumn("Minuten", min_value=0, step=1)})
    eintraege = [[str(z["von"]).strip(), str(z["nach"]).strip(), int(z["minuten"])] for z in df.to_dict("records")
                 if str(z.get("von") or "").strip() and str(z.get("nach") or "").strip() and pd.notna(z.get("minuten"))]
    rest["wegzeiten"] = {"geschwindigkeit_kmh": int(kmh), **({"minuten": eintraege} if eintraege else {})}


def _liste_hochladen(art: str) -> None:
    """Raum- oder Lehrpersonenliste aus der Hauswartung/Personaladministration übernehmen."""
    text = "Raumliste" if art == "Raeume" else "Lehrpersonenliste"
    beispiel = ("Erkannte Spalten z.B. *Schulhaus/Standort, Raum/Zimmer, Typ/Raumart, Plätze/Kapazität, Anzahl, "
                "gesperrt* – Raumarten wie *Schulzimmer*, *Sporthalle*, *Werkraum* werden zugeordnet, Zeiten wie "
                "*Freitag Nachmittag* übersetzt." if art == "Raeume" else
                "Erkannte Spalten z.B. *Name (oder Vorname + Nachname), Kürzel, Fächer, Stufen, Schulhaus, Pensum "
                "(12-16), nicht verfügbar, bisherige Klasse*.")
    with st.expander(f"{text} aus Excel/CSV übernehmen", icon=":material/upload_file:"):
        st.caption(beispiel)
        datei = st.file_uploader(text, type=["csv", "xlsx"], key=f"up_{art}_{st.session_state.version}",
                                 label_visibility="collapsed")
        ergaenzen = st.toggle("Bestehende Einträge behalten (nur ergänzen)", key=f"erg_{art}",
                              help="Aus: Räume der Schulhäuser in der Liste bzw. alle Lehrpersonen werden ersetzt.")
        if datei and st.button("Übernehmen", type="primary", key=f"ueb_{art}", icon=":material/check:"):
            cfg, kinder = _aktuelle_daten()
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    pfad = Path(tmp) / datei.name
                    pfad.write_bytes(datei.getvalue())
                    zeilen = lese_liste(pfad, art, raumtypen=raumtypen(cfg))
                neu, hinweise = uebernehme_liste(cfg, art, zeilen, ersetzen=not ergaenzen)
            except Exception as fehler:  # noqa: BLE001 – verständlich melden statt abstürzen
                st.error(f"Die Liste konnte nicht übernommen werden: {fehler}")
                return
            _laden(neu, kinder)
            st.session_state[f"hinweise_{art}"] = hinweise
            st.rerun()
    for h in st.session_state.pop(f"hinweise_{art}", []):
        (st.success if h.endswith("übernommen.") else st.warning)(h)


def _raeume_tab(r: Ergebnis) -> None:
    """Raumplanung: Auslastung aller Räume, Wochenplan je Raum, Belegungsübersicht."""
    schule = r.schule
    if not r.lektionen:
        st.info("Kein Stundenplan berechnet – Räume werden mit dem Stundenplan verplant.")
        return
    st.caption("Jede Klasse erhält ihr Schulzimmer; Turnhallen, TTG-Zimmer, Gruppenräume usw. werden pro Lektion "
               "verplant – mit Plätzen, Sperrzeiten (z.B. Vereinsnutzung) und Schulhaus-Öffnungszeiten.")
    belegt: dict[tuple[str, str], list] = {}
    for l in r.lektionen:
        belegt.setdefault((l.raum_ort or l.schulhaus, l.raum), []).append(l)
    zeilen = []
    for sh in schule.schulhaeuser:
        offen = len(schule.slots) - len(sh.nicht_verfuegbar)
        for raum in sh.raeume:
            ls = belegt.get((sh.name, raum.name), [])
            slots = {l.slot for l in ls}
            verfuegbar = offen - len(raum.nicht_verfuegbar - sh.nicht_verfuegbar)
            zeilen.append({"Schulhaus": sh.name, "Raum": raum.name, "Typ": raum.typ, "Plätze": raum.plaetze,
                           "Lektionen": len(slots), "verfügbar": verfuegbar,
                           "Auslastung": round(100 * len(slots) / verfuegbar) if verfuegbar else 0,
                           "genutzt von": ", ".join(sorted({k for l in ls for k in l.klassen}))[:80]})
    df = pd.DataFrame(zeilen)
    c = st.columns(4)
    c[0].metric("Räume", len(df))
    c[1].metric("Ungenutzt", int((df["Lektionen"] == 0).sum()))
    c[2].metric("Über 85 % belegt", int((df["Auslastung"] > 85).sum()))
    c[3].metric("Ø Auslastung (genutzte)", f"{df.loc[df['Lektionen'] > 0, 'Auslastung'].mean():.0f} %"
                if (df["Lektionen"] > 0).any() else "–")
    typen = st.multiselect("Raumtyp", sorted(df["Typ"].unique()), placeholder="alle Raumtypen")
    sicht = df[df["Typ"].isin(typen)] if typen else df
    st.dataframe(sicht, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(sicht)),
                 column_config={"Auslastung": st.column_config.ProgressColumn("Auslastung", format="%d %%",
                                                                              min_value=0, max_value=100)})
    wahl = st.selectbox("Wochenplan für Raum", [f"{z['Schulhaus']} · {z['Raum']}" for z in sicht.to_dict("records")],
                        key="raum_wahl")
    if wahl:
        sh_name, raum_name = wahl.split(" · ", 1)
        sh = schule.schulhaus(sh_name)
        raum = next(x for x in sh.raeume if x.name == raum_name)
        eintr = {l.slot: f"<b>{'/'.join(l.klassen)}</b><br>{l.fach}<br><span class='muted'>{l.lehrperson}</span>"
                 for l in belegt.get((sh_name, raum_name), [])}
        _html(_plan(r, eintr, raum.nicht_verfuegbar | sh.nicht_verfuegbar, {}), 440)
    with st.expander("Belegungsübersicht aller Räume", icon=":material/grid_view:"):
        _html(_raumbelegung(r), 520)


def seite_pruefen() -> None:
    _kopf("Prüfen", "Fehlende oder widersprüchliche Angaben vor dem Rechnen finden", "Schritt 2 von 4")
    if "tabellen" not in st.session_state:
        st.info("Zuerst Daten laden (Schritt 1).")
        return
    cfg, kinder = _aktuelle_daten()
    try:
        schule = _schule_aus_cfg(cfg)
    except Exception as fehler:  # noqa: BLE001
        st.error(f"Die Angaben sind unvollständig oder fehlerhaft: {fehler}")
        return
    meldungen = vorpruefung(schule, kinder)
    zaehler = {s: sum(m.schwere == s for m in meldungen) for s in SCHWEREGRADE}
    c = st.columns(3)
    for i, s in enumerate(SCHWEREGRADE):
        c[i].metric(f"{ICON[s]} {s}", zaehler[s])
    if not zaehler["Fehler"]:
        st.success("Keine Probleme gefunden – bereit zum Berechnen." if not meldungen
                   else "Keine Fehler – Warnungen/Hinweise bitte kurz ansehen.")
    for m in sorted(meldungen, key=lambda m: SCHWEREGRADE.index(m.schwere)):
        {"Fehler": st.error, "Warnung": st.warning, "Hinweis": st.info}[m.schwere](f"**{m.bereich}:** {m.text}")
    if not zaehler["Fehler"]:
        _weiter("berechnen")


def seite_berechnen() -> None:
    _kopf("Berechnen", "Klassen, Lehraufträge und Stundenplan optimieren", "Schritt 3 von 4")
    if "tabellen" not in st.session_state:
        st.info("Zuerst Daten laden (Schritt 1).")
        return
    cfg, kinder = _aktuelle_daten()
    infos = szenario_infos(cfg)
    gewaehlt = st.multiselect(
        "Szenarien", list(infos), default=["Basis"],
        format_func=lambda n: f"{n} · {infos[n]['ziel']}" if infos[n]["ziel"] else n,
        help="Jedes Szenario ist eine Hypothese (\"Was wäre, wenn …\"). Mehrere wählen = nacheinander rechnen "
             "und nebeneinander vergleichen.")
    for n in gewaehlt:
        if infos[n]["hypothese"]:
            st.caption(f":material/lightbulb: **{n}:** {infos[n]['hypothese']}")
    _hypothese_anlegen(cfg)
    zeit = st.select_slider("Rechenzeit pro Szenario", options=[30, 60, 120, 300, 600], value=120,
                            format_func=lambda s: f"{s // 60} min" if s >= 60 else f"{s} s",
                            help="Mehr Zeit = näher am Optimum. Kleine Schulen sind in Sekunden fertig.")
    notiz = st.text_input("Notiz für den Verlauf (optional)", placeholder="z.B. Variante mit 2 Mehrjahrgangsklassen")
    if st.button("Klassen und Stundenplan berechnen", type="primary", width="stretch", icon=":material/play_arrow:",
                 disabled=not gewaehlt):
        ergebnisse = {}
        for szenario in gewaehlt:
            try:
                schule = _schule_aus_cfg(cfg, szenario)
            except Exception as fehler:  # noqa: BLE001
                st.error(f"{szenario}: Die Angaben sind fehlerhaft: {fehler}")
                continue
            with st.status(f"{szenario}: Berechnung läuft – bitte warten …", expanded=len(gewaehlt) == 1) as status:
                r = rechne(schule, kinder, zeitlimit=zeit, protokoll=lambda t: st.write(t.strip()))
                ergebnisse[szenario] = r
                try:
                    st.session_state.stand = str(verlauf.speichere(r, cfg, notiz))
                    st.write(":material/history: Im Verlauf gespeichert.")
                except OSError as fehler:
                    st.warning(f"Verlauf konnte nicht gespeichert werden: {fehler}")
                ok = r.anzahl("Fehler") == 0 and r.vollstaendig
                status.update(label=f"{szenario}: fertig" if ok else f"{szenario}: fertig – mit Fehlern",
                              state="complete" if ok else "error")
        if ergebnisse:
            st.session_state.ergebnis = next(iter(ergebnisse.values()))
            st.session_state.vergleich = ergebnisse if len(ergebnisse) > 1 else None
    if st.session_state.get("vergleich"):
        _szenarien_vergleich(st.session_state.vergleich)
    if st.session_state.get("ergebnis"):
        _weiter("ergebnis", "Zum Ergebnis")


def _planung_tab(r: Ergebnis, kz: dict) -> None:
    """Kosten, Qualität und Langfristplanung – Zahlen oben, Details und Empfehlungen darunter."""
    jahre = r.planung.jahre
    werte = [(k, kz[k]) for k in ("Kosten/Jahr", "Kosten pro Lernende", "Klassen nahe Idealgrösse",
                                  "Lehrpersonen pro Klasse", "Auslastung Schulzimmer") if k in kz]
    if jahre and len(jahre) > 1:
        z = jahre[-1]
        werte.append((f"Lernende {z['Schuljahr']}", f"{z['Lernende']}",))
        werte.append((f"Fehlende Räume {z['Schuljahr']}", str(z["fehlende Räume"])))
    if werte:
        for spalte, (k, v) in zip(st.columns(len(werte)), werte):
            spalte.metric(k, v)
    if jahre and len(jahre) > 1:
        df = pd.DataFrame(jahre).set_index("Schuljahr")[["Lernende", "Klassen (mind.)"]]
        st.line_chart(df, height=220)
    if not (r.schule.kosten or {}).get("lektion_chf"):
        st.caption("Ohne Kostenmodell werden nur Mengen gezählt – Ansätze in den Einstellungen unter "
                   "`kosten` ergänzen (siehe Hilfe).")
    _html(_empfehlungen_html(r) or "<p>Keine Empfehlungen.</p>", 720)


def _szenarien_vergleich(ergebnisse: dict[str, Ergebnis]) -> None:
    st.subheader("Szenarien im Vergleich")
    kz = {n: r.kennzahlen() for n, r in ergebnisse.items()}
    for n, r in ergebnisse.items():
        if r.planung.jahre:
            letzt = r.planung.jahre[-1]
            kz[n][f"Klassen {letzt['Schuljahr']}"] = str(letzt["Klassen (mind.)"])
            kz[n][f"Fehlende Räume {letzt['Schuljahr']}"] = str(letzt["fehlende Räume"])
    zeilen = list(dict.fromkeys(k for v in kz.values() for k in v))
    df = pd.DataFrame({n: [ergebnisse[n].schule.hypothese or "Heutige Angaben"] + [kz[n].get(k, "–") for k in zeilen]
                       for n in ergebnisse}, index=["Hypothese"] + zeilen)
    st.dataframe(df, width="stretch")
    wahl = st.radio("Im Ergebnis anzeigen", list(ergebnisse), horizontal=True, key="vergleich_wahl")
    st.session_state.ergebnis = ergebnisse[wahl]


_GEBIETSKARTE = components.declare_component("gebietskarte", path=str(Path(__file__).parent / "static"))


def _gebietskarte(cfg: dict):
    """Karte zum Zeichnen eines Gebiets (skf/static/index.html) → [[lat, lon], …] oder None."""
    from skf.bericht import _kacheln
    url, quelle = _kacheln()
    kinder = _aktuelle_daten()[1]
    punkte = [[k.lat, k.lon] for k in kinder if k.lat is not None and k.lon is not None][:3000]
    return _GEBIETSKARTE(kacheln=url, quelle=quelle, lernende=punkte, key="hyp_gebiet", default=None,
                         schulhaeuser=[{"name": s["name"], "lat": s["lat"], "lon": s["lon"]}
                                       for s in cfg.get("schulhaeuser") or [] if "lat" in s])


def _gebiet_eingeben(cfg: dict) -> dict | None:
    """Gezeichnetes Gebiet mit Annahmen: Aufteilung nach Schulhaus, Schulbus (z.B. Dorfzone), Zuzug.
    Wahlweise dauerhaft für alle Berechnungen speichern (Konfiguration 'gebiete')."""
    flaeche = _gebietskarte(cfg)
    if not flaeche:
        return None
    from skf.gebiete import Gebiet, lernende_im_gebiet
    im_gebiet = lernende_im_gebiet(Gebiet("x", [tuple(x) for x in flaeche]), _aktuelle_daten()[1])
    st.caption(f"{len(im_gebiet)} heutige Lernende wohnen im gezeichneten Gebiet.")
    c, d, e = st.columns(3)
    name = c.text_input("Name des Gebiets", "Gebiet", key="hyp_g_name")
    linien = [l.get("name") for l in (cfg.get("schulbus") or {}).get("linien") or [] if l.get("name")]
    bus = d.selectbox("Schulbus im Gebiet", ["wie bisher", "kein Schulbus (z.B. Dorfzone)", *linien], key="hyp_g_bus")
    neu = e.number_input("Zusätzliche Lernende (Annahme)", 0, 2000, 0, 5, key="hyp_g_neu")
    st.markdown("**Gewünschte Aufteilung nach Schulhaus** (%, leer = wie bisher)")
    haeuser = [s["name"] for s in cfg.get("schulhaeuser") or []]
    spalten = st.columns(max(1, len(haeuser)))
    aufteilung = {sh: spalten[i].number_input(sh, 0, 100, 0, 5, key=f"hyp_g_auf_{i}") for i, sh in enumerate(haeuser)}
    aufteilung = {sh: v for sh, v in aufteilung.items() if v}
    verbindlich = st.toggle("Aufteilung verbindlich (sonst als Wunsch, gewichtet wie das Wunsch-Schulhaus)",
                            key="hyp_g_fest")
    gebiet = {"name": name, "flaeche": flaeche}
    if bus != "wie bisher":
        gebiet["schulbus"] = False if bus.startswith("kein") else bus
    if aufteilung:
        gebiet.update(aufteilung=aufteilung, verbindlich=verbindlich)
    if neu:
        gebiet["neue_lernende"] = neu
    if len(gebiet) == 2:
        return None
    if st.button("Als dauerhaften Bereich speichern (alle Berechnungen)", icon=":material/push_pin:",
                 key="hyp_g_dauerhaft"):
        rest = st.session_state.extra["rest"]
        alt = list(rest.get("gebiete") or [])
        rest["gebiete"] = [x for x in alt if x.get("name") != name] + [gebiet]
        try:
            _schule_aus_cfg(_aktuelle_daten()[0])
        except Exception as fehler:  # noqa: BLE001
            rest["gebiete"] = alt
            st.error(f"Bereich nicht gespeichert: {fehler}")
            return gebiet
        st.toast(f"Bereich „{name}“ gilt jetzt für alle Berechnungen (Einstellungen: gebiete).",
                 icon=":material/check_circle:")
    return gebiet


def _hypothese_anlegen(cfg: dict) -> None:
    """Neues Szenario aus einfachen Hebeln – landet in den Einstellungen unter 'szenarien'."""
    with st.expander("Neue Hypothese als Szenario anlegen", icon=":material/add_circle:"):
        name = st.text_input("Name", placeholder="z.B. Neubaugebiet Nord doppelt", key="hyp_name")
        hypothese = st.text_input("Was wäre, wenn …", key="hyp_text",
                                  placeholder="z.B. Was wäre, wenn 2030 ein Quartier mit 200 Wohnungen dazukommt?")
        hebel = st.multiselect("Schwerpunkt (Kosten oder Qualität)", list(GEWICHT_HEBEL), key="hyp_hebel",
                               format_func=lambda h: f"{h} · {GEWICHT_HEBEL[h][0]}")
        a, b = st.columns(2)
        planung = cfg.get("planung") or {}
        wachstum = a.number_input("Wachstum Lernende % pro Jahr", -20.0, 20.0,
                                  float(planung.get("wachstum_prozent", 0)), 0.5, key="hyp_wachstum")
        lehrpersonen = b.multiselect("Stellen unbesetzt", [lp["name"] for lp in cfg.get("lehrpersonen") or []],
                                     key="hyp_lp")
        quartier = None
        if st.toggle("Quartierentwicklung (Zuzug ab einem Schuljahr)", key="hyp_q"):
            c, d, e, f = st.columns(4)
            q_name = c.text_input("Quartier", "Neubaugebiet", key="hyp_q_name")
            q_sh = d.selectbox("Schulhaus", [s["name"] for s in cfg.get("schulhaeuser") or []], key="hyp_q_sh")
            q_ab = e.text_input("ab Schuljahr", key="hyp_q_ab", placeholder="2029/30")
            q_wo = f.number_input("Wohnungen", 0, 5000, 100, 10, key="hyp_q_wo")
            quartier = {"name": q_name, "schulhaus": q_sh, "ab": q_ab or "1", "wohnungen": q_wo,
                        "kinder_pro_wohnung": 0.3}
            st.caption("Annahme: 0.3 schulpflichtige Kinder pro Wohnung, verteilt über alle Stufen "
                       "(in den Einstellungen unter planung.quartiere anpassbar).")
        gebiet = _gebiet_eingeben(cfg) if st.toggle("Gebiet auf der Karte zeichnen (geografische Hypothese)",
                                                     key="hyp_g") else None
        if st.button("Szenario anlegen", icon=":material/save:", key="hyp_speichern",
                     disabled=not (name and hypothese)):
            aendert_wachstum = wachstum != float(planung.get("wachstum_prozent", 0))
            patch = szenario_aus_hebeln(hypothese, hebel, wachstum if aendert_wachstum else None, quartier,
                                        lehrpersonen)
            if gebiet:
                patch["gebiete"] = [gebiet]
                patch.setdefault("ziel", "Planung")
            rest = st.session_state.extra["rest"]
            rest.setdefault("szenarien", {})[name] = patch
            try:
                _schule_aus_cfg(_aktuelle_daten()[0], name)
            except Exception as fehler:  # noqa: BLE001
                rest["szenarien"].pop(name)
                st.error(f"Szenario nicht angelegt: {fehler}")
                return
            st.toast(f"Szenario „{name}“ angelegt – jetzt oben auswählen. Es steht auch in den Einstellungen "
                     "und wird mit den Daten gespeichert.", icon=":material/check_circle:")
            st.rerun()


def _kind_karte(r: Ergebnis, kid: str) -> None:
    e = r.einteilung
    nach_id = {k.id: k for k in r.kinder}
    k = nach_id[kid]
    st.subheader(f"{k.name or k.id} ({k.id})")
    a, b, c = st.columns(3)
    a.metric("Klasse", e.klasse_von[kid], help=f"Schulhaus {e.schulhaus_von[kid]}")
    b.metric("Schulweg", f"{e.schulweg_m[kid] / 1000:.2f} km")
    c.metric("Vorjahr", k.bisherige_klasse or "–")
    info = [f"**Jahrgang** {k.jahrgang}", f"**Adresse** {k.adresse or '–'}"]
    merkmale = ", ".join(x for x, an in (("IF", k.if_), (f"DaZ {k.daz}", bool(k.daz)), ("IS", k.is_)) if an)
    if merkmale:
        info.append(f"**Förderung** {merkmale}")
    st.markdown(" · ".join(info))
    geschwister = [g for g in r.kinder if k.familie and g.familie == k.familie and g.id != kid]
    if geschwister:
        st.markdown("**Geschwister:** " + ", ".join(
            f"{g.name} ({g.id}, {e.klasse_von[g.id]}{'' if e.schulhaus_von[g.id] == e.schulhaus_von[kid] else ' :orange[anderes Schulhaus]'})"
            for g in geschwister))
    wuensche_k = []
    for anderer in k.zusammen_mit:
        if anderer in nach_id:
            wuensche_k.append(f"{_ja_nein(e.klasse_von[anderer] == e.klasse_von[kid])} zusammen mit "
                              f"{nach_id[anderer].name} ({anderer}, {e.klasse_von[anderer]})")
    for anderer in k.nicht_mit:
        if anderer in nach_id:
            wuensche_k.append(f"{_ja_nein(e.klasse_von[anderer] != e.klasse_von[kid])} nicht zusammen mit "
                              f"{nach_id[anderer].name} ({anderer})")
    if k.wunsch_schulhaus:
        wuensche_k.append(f"{_ja_nein(e.schulhaus_von[kid] == k.wunsch_schulhaus)} Wunsch-Schulhaus "
                          f"{k.wunsch_schulhaus}")
    if k.bus:
        st.markdown(f"**Schulbus:** {k.bus}")
    if wuensche_k:
        st.markdown("**Wünsche der Erziehungsberechtigten:**  \n" + "  \n".join(wuensche_k))
    if k.bisherige_klasse:
        gspaenli = [g for g in r.kinder if g.bisherige_klasse == k.bisherige_klasse and g.id != kid
                    and e.klasse_von[g.id] == e.klasse_von[kid]]
        st.markdown(f"**Aus {k.bisherige_klasse} ebenfalls in {e.klasse_von[kid]}:** "
                    + (", ".join(g.name for g in gspaenli) if gspaenli else ":orange[niemand]"))
    if k.bemerkung:
        st.markdown(f"**Bemerkung:** {k.bemerkung}")
    with st.container(border=True):
        st.markdown(":material/visibility: **Warum hier?**")
        b = begruendung(r, kid)
        st.markdown(f"**Schulhaus:** {b['schulhaus_text']}  \n**Klasse:** {b['klasse_text']}")
        st.dataframe(pd.DataFrame([{"": "✓" if z["gewaehlt"] else "", "Schulhaus": z["schulhaus"],
                                    "Weg km": z["weg_km"], "Klassen dieses Jahrgangs (Grösse)": z["klassen"],
                                    "freie Plätze": z["freie_plaetze"], "spricht dafür / dagegen": z["gruende"]}
                                   for z in b["schulhaeuser"]]), hide_index=True, width="stretch")
    historie = verlauf.kind_verlauf(kid)
    if historie:
        st.markdown("**Verlauf (gespeicherte Stände):**")
        st.dataframe(pd.DataFrame([{"Zeitpunkt": h["zeit"].replace("T", " "), "Szenario": h["szenario"],
                                    "Klasse": h["klasse"], "Schulhaus": h["schulhaus"]} for h in historie]),
                     hide_index=True, width="stretch")


def _anpassen(r: Ergebnis, nach_id: dict, klasse) -> None:
    e = r.einteilung
    st.caption(f"Ein Kind aus {klasse.name} in eine andere Klasse verschieben – danach wird alles neu geprüft "
               "(Klassengrössen, Wünsche, Geschwister, Gspänli-Regel, Recht).")
    a, b = st.columns(2)
    kid = a.selectbox("Kind", sorted(klasse.kinder, key=lambda i: nach_id[i].name), key=f"anp_kind_{klasse.name}",
                      format_func=lambda i: f"{nach_id[i].name} · {i}")
    moeglich = [c.name for c in e.klassen if nach_id[kid].jahrgang in c.vorlage.jahrgaenge]
    ziel = b.selectbox("Neue Klasse", moeglich, index=moeglich.index(e.klasse_von[kid]), key=f"anp_ziel_{kid}")
    if st.button("Verschieben und prüfen", type="primary", disabled=ziel == e.klasse_von[kid]):
        vorher = r.anzahl("Fehler"), r.anzahl("Warnung")
        text = verschiebe(r, kid, ziel)
        st.toast(text)
        nachher = r.anzahl("Fehler"), r.anzahl("Warnung")
        (st.error if nachher[0] > vorher[0] else st.success)(
            f"{text}. Fehler {vorher[0]} → {nachher[0]}, Warnungen {vorher[1]} → {nachher[1]}.")
    if r.manuell:
        st.markdown("**Manuelle Anpassungen:**  \n" + "  \n".join(f"• {t}" for t in r.manuell))
        if st.button("Angepassten Stand im Verlauf speichern"):
            cfg, _ = _aktuelle_daten()
            verlauf.speichere(r, cfg, "manuell angepasst")
            st.toast("Im Verlauf gespeichert", icon=":material/history:")


def seite_ergebnis() -> None:
    _kopf("Ergebnis", "Karte, Klassen, Begründungen, Stundenpläne, Planung & Kosten und Downloads", "Schritt 4 von 4")
    r: Ergebnis | None = st.session_state.get("ergebnis")
    if not r:
        st.info("Noch nichts berechnet (Schritt 3).")
        return
    if r.anzahl("Fehler"):
        st.error(f"{r.anzahl('Fehler')} Fehler – das Ergebnis ist so nicht verwendbar. Details unter *Prüfung*.")
    else:
        st.success("Alle harten Regeln erfüllt." + (f" {r.anzahl('Warnung')} Warnungen bitte prüfen."
                                                       if r.anzahl("Warnung") else ""))
    if r.schule.hypothese:
        st.caption(f":material/lightbulb: Szenario **{r.schule.szenario}**"
                   f"{' · ' + r.schule.ziel if r.schule.ziel else ''}: {r.schule.hypothese}")
    kz = r.kennzahlen()
    spalten = st.columns(6)
    for i, k in enumerate(["Klassen", "Ø Klassengrösse", "Ø Schulweg", "Wünsche erfüllt", "Förderlektionen",
                           "Springstunden"]):
        spalten[i].metric(k, kz[k])
    tabs = st.tabs([":material/map: Karte", ":material/groups: Klassen", ":material/person_search: Lernende",
                    ":material/calendar_month: Stundenpläne", ":material/favorite: Wünsche",
                    ":material/trending_up: Planung & Kosten", ":material/verified: Prüfung", ":material/download: Herunterladen"])
    e = r.einteilung
    with tabs[6]:
        if e:
            rg = [x for x in regeln(r) if x["geprueft"]]
            ok = sum(not x["verstoesse"] for x in rg)
            (st.success if ok == len(rg) else st.error)(f"{ok} von {len(rg)} harten Regeln erfüllt – unabhängig "
                                                        "nachgezählt.", icon=":material/verified:")
        with st.expander(f"Meldungen ({len(r.meldungen)})", icon=":material/list:", expanded=not e or bool(
                r.anzahl("Fehler"))):
            filt = st.multiselect("Anzeigen", SCHWEREGRADE, default=["Fehler", "Warnung"])
            df = pd.DataFrame([{"Schweregrad": m.schwere, "Bereich": m.bereich, "Meldung": m.text, "Quelle": m.quelle}
                               for m in sorted(r.meldungen, key=lambda m: SCHWEREGRADE.index(m.schwere))
                               if m.schwere in filt])
            st.dataframe(df, width="stretch", hide_index=True, height=360)
        if e:
            _html(transparenz_html(r), 1100)
    if not e:
        return
    nach_id = {k.id: k for k in r.kinder}
    with tabs[0]:
        st.caption("Rechts oben: Klasse wählen (zeigt Einzugsgebiet), Farbe nach Schulhaus oder Jahrgang, "
                   "Geschwister verbinden, Schulwege. Punkt anklicken hebt die Familie hervor.")
        _html(_osm_karte(r), 640)
    with tabs[1]:
        zeilen = []
        for c in e.klassen:
            ks = [nach_id[i] for i in c.kinder]
            zeilen.append({"Klasse": c.name, "Schulhaus": c.schulhaus, "Schulzimmer": c.raum.name,
                           "Jahrgänge": "/".join(c.jahrgaenge), "Lernende": len(ks),
                           "♀": sum(k.geschlecht == "w" for k in ks), "♂": sum(k.geschlecht == "m" for k in ks),
                           "IF": sum(k.if_ for k in ks), "DaZ": sum(bool(k.daz) for k in ks), "IS": sum(k.is_ for k in ks),
                           "Ø Weg km": round(sum(e.schulweg_m[k.id] for k in ks) / max(1, len(ks)) / 1000, 2)})
        st.dataframe(pd.DataFrame(zeilen), width="stretch", hide_index=True)
        wahl = st.selectbox("Klassenliste", [c.name for c in e.klassen], key="kl_wahl")
        c = next(c for c in e.klassen if c.name == wahl)
        familien = {}
        for k in r.kinder:
            if k.familie:
                familien.setdefault(k.familie, []).append(k)
        st.dataframe(pd.DataFrame([{
            "ID": k.id, "Name": k.name, "Jg.": k.jahrgang, "G.": k.geschlecht, "Vorjahr": k.bisherige_klasse,
            "Geschwister": ", ".join(f"{g.vorname or g.name} ({e.klasse_von[g.id]})" for g in familien.get(k.familie, [])
                                     if g.id != k.id),
            "Wünsche": "; ".join(filter(None, [f"mit {', '.join(k.zusammen_mit)}" if k.zusammen_mit else "",
                                               f"nicht mit {', '.join(k.nicht_mit)}" if k.nicht_mit else ""])),
            "Weg km": round(e.schulweg_m[k.id] / 1000, 2)}
            for k in sorted((nach_id[i] for i in c.kinder), key=lambda k: k.name)]), width="stretch", hide_index=True)
        with st.expander("Kind in eine andere Klasse verschieben", icon=":material/swap_horiz:",
                         expanded=bool(r.manuell)):
            _anpassen(r, nach_id, c)
    with tabs[2]:
        optionen = sorted(r.kinder, key=lambda k: k.name)
        kid = st.selectbox("Lernende suchen (Name oder ID tippen)", [k.id for k in optionen],
                           format_func=lambda i: f"{nach_id[i].name} · {i} · {nach_id[i].jahrgang}", key="kind_wahl")
        _kind_karte(r, kid)
    with tabs[3]:
        if not r.lektionen:
            st.info("Kein Stundenplan berechnet.")
        else:
            art = st.radio("Stundenplan für", ["Klasse", "Lehrperson", "Raum"], horizontal=True)
            if art == "Klasse":
                wahl = st.selectbox("Klasse", [c.name for c in e.klassen], key="sp_klasse")
                c = next(c for c in e.klassen if c.name == wahl)
                eintr: dict[int, str] = {}
                for l in sorted(r.lektionen, key=lambda l: l.art != "unterricht"):
                    if c.name in l.klassen:
                        eintr[l.slot] = eintr.get(l.slot, "") + (
                            f"<b>{l.fach}</b><br>{l.lehrperson}<br><span class='muted'>{l.raum_label}</span>"
                            if l.art == "unterricht" else f"<br><i>+ {l.fach}: {l.lehrperson}</i>")
                _html(_plan(r, eintr, r.schule.schulhaus(c.schulhaus).nicht_verfuegbar, {}), 440)
            elif art == "Lehrperson":
                namen = sorted({b.lehrperson for b in r.bloecke})
                wahl = st.selectbox("Lehrperson", namen, key="sp_lp")
                lp = next(x for x in r.schule.lehrpersonen if x.name == wahl)
                eintr = {l.slot: f"<b>{'/'.join(l.klassen)}</b><br>{l.fach}<br><span class='muted'>{l.raum_label}</span>"
                         for l in r.lektionen if l.lehrperson == wahl}
                st.caption(f"{len(eintr)} Lektionen · Pensum {lp.pensum_min}–{lp.pensum_max}")
                _html(_plan(r, eintr, lp.nicht_verfuegbar, {}), 440)
            if art == "Raum":
                _raeume_tab(r)
    with tabs[4]:
        _html(_wuensche_html(r), 560)
    with tabs[5]:
        _planung_tab(r, kz)
    with tabs[7]:
        mit_foerder = st.toggle("IF/DaZ/IS in Klassenlisten aufnehmen (besonders schützenswerte Daten)")
        with tempfile.TemporaryDirectory() as tmp:
            ordner = Path(tmp)
            schreibe_csv(ordner, r)
            schreibe_html(ordner / "bericht.html", r)
            exportiere_listen(r, ordner, mit_foerder)
            for name, text in {"klassenlisten.xlsx": "Klassenlisten (Excel, druckfertig)",
                               "stundenplaene.xlsx": "Stundenpläne (Excel, pro Klasse/Lehrperson/Raum)",
                               "druck.html": "Druckversion (im Browser drucken oder als PDF speichern)",
                               "bericht.html": "Bericht (alles auf einen Blick)"}.items():
                if (ordner / name).exists():
                    st.download_button(text, (ordner / name).read_bytes(), name, icon=":material/download:", key=f"dl_{name}",
                                       width="stretch")
            zip_puffer = io.BytesIO()
            with zipfile.ZipFile(zip_puffer, "w", zipfile.ZIP_DEFLATED) as z:
                for f in ordner.iterdir():
                    z.write(f, f.name)
            st.download_button("Alles als ZIP (inkl. CSV-Rohdaten)", zip_puffer.getvalue(), "ergebnis.zip",
                               icon=":material/folder_zip:",
                               width="stretch")


def _stand_laden(ordner: Path) -> None:
    _laden(*importiere_stammdaten(ordner / "stammdaten.xlsx"))
    st.session_state.seite = "daten"


def seite_uebertritt() -> None:
    """Nächstes Schuljahr vorbereiten: jede Stufe → nächste Stufe, Entscheide, Neueintritte."""
    from skf.uebertritt import extern, naechste, naechstes_schuljahr, schuljahreswechsel, zusammenfassung
    _kopf("Schuljahreswechsel", "Lernende ins nächste Schuljahr übernehmen – Übertritte, Repetitionen, Austritte")
    if "tabellen" not in st.session_state:
        st.info("Zuerst die Daten des laufenden Schuljahres laden (Schritt 1).")
        return
    cfg, kinder = _aktuelle_daten()
    schule = _schule_aus_cfg(cfg)
    folge = naechste(schule)
    r = st.session_state.get("ergebnis")
    klasse_von = dict(r.einteilung.klasse_von) if r and r.einteilung else {}
    schulhaus_von = dict(r.einteilung.schulhaus_von) if r and r.einteilung else {}
    with st.expander("Stufenfolge – welche Stufe folgt worauf", icon=":material/account_tree:"):
        st.dataframe(pd.DataFrame([{"Stufe": j, "nächste Stufe": " oder ".join(n)} for j, n in folge.items()]),
                     hide_index=True, width="stretch")
        st.caption("Ausserhalb der Schule (zählt wie ein Wegzug): " + ", ".join(extern(schule))
                   + ". Anpassbar in der Konfiguration unter `uebertritte`.")
    if not klasse_von:
        st.warning("Tipp: zuerst das laufende Schuljahr berechnen (Schritt 3) – dann werden die aktuellen Klassen "
                   "als „bisherige Klasse“ übernommen (Gspänli-Regel, Kontinuität).", icon=":material/info:")
    st.markdown("**Entscheide** – *normal* = in die nächste Stufe. Wo es mehrere nächste Stufen gibt "
                "(z.B. 6. Klasse → Sek A/B/C), ist ein Entscheid nötig.")
    optionen = ["normal", "A", "B", "C", "repetiert", "überspringt"] + extern(schule)
    wahl_noetig = {j for j, n in folge.items() if len(n) > 1}
    nur = st.toggle("Nur Übertrittsstufen zeigen", value=True, key="ue_nur",
                    help="Kindergarten 2, letzte Primarklasse und Oberstufe")
    df = st.session_state.bearbeitet["Kinder"].copy()
    if "uebertritt" not in df:
        df["uebertritt"] = ""
    df["uebertritt"] = df["uebertritt"].fillna("").astype(str).replace("", "normal")
    df["klasse"] = df["id"].map(klasse_von).fillna(df.get("bisherige_klasse", ""))
    sicht = df[df["jahrgang"].isin(wahl_noetig | {"KG2"} | {j for j in folge if j.startswith("S")})] if nur else df
    ed = st.data_editor(
        sicht[["id", "vorname", "nachname", "jahrgang", "klasse", "uebertritt"]], hide_index=True, width="stretch",
        height=380, key=f"ed_ue_{st.session_state.version}", disabled=["id", "vorname", "nachname", "jahrgang", "klasse"],
        column_config={"uebertritt": st.column_config.SelectboxColumn("Entscheid", options=optionen),
                       "id": "ID", "vorname": "Vorname", "nachname": "Nachname",
                       "klasse": "Klasse jetzt", "jahrgang": "Jahrgang jetzt"})
    geaendert = {i: ("" if u in (None, "normal") else u) for i, u in zip(ed["id"], ed["uebertritt"])}
    basis = st.session_state.bearbeitet["Kinder"]
    if "uebertritt" not in basis:
        basis["uebertritt"] = ""
    basis["uebertritt"] = [geaendert.get(i, u) for i, u in zip(basis["id"], basis["uebertritt"].fillna(""))]
    neu_datei = st.file_uploader("Neueintritte (z.B. Kindergarten 1 von der Einwohnerkontrolle), CSV oder Excel",
                                 type=["csv", "xlsx"], key="ue_neu")
    neueintritte = []
    if neu_datei:
        with tempfile.TemporaryDirectory() as tmp:
            pfad = Path(tmp) / neu_datei.name
            pfad.write_bytes(neu_datei.getvalue())
            neueintritte = lese_kinder(pfad)
    kinder = _kinder_aus_df(basis)
    kinder_neu, protokoll = schuljahreswechsel(schule, kinder, klasse_von, schulhaus_von, neueintritte)
    st.subheader("Vorschau " + naechstes_schuljahr(cfg.get("schuljahr", "")))
    z = dict(zusammenfassung(protokoll))
    c = st.columns(4)
    c[0].metric("Lernende neu", len(kinder_neu), len(kinder_neu) - len(kinder))
    c[1].metric("Übertritte", sum(n for a, n in z.items() if a.startswith("Übertritt")))
    c[2].metric("Austritte", sum(n for a, n in z.items() if a.startswith("Austritt") or a == "Abschluss"))
    c[3].metric("Entscheid fehlt", z.get("Entscheid fehlt", 0))
    st.dataframe(pd.DataFrame([{"Art": a, "Anzahl": n} for a, n in z.items()]), hide_index=True)
    offen = [s for s in protokoll if s.art == "Entscheid fehlt"]
    if offen:
        st.error(f"{len(offen)} Entscheide fehlen – diese Lernenden blieben im bisherigen Jahrgang: "
                 + ", ".join(f"{s.name or s.kind} ({s.von})" for s in offen[:8]) + (" …" if len(offen) > 8 else ""),
                 icon=":material/error:")
    with st.expander("Alle Schritte"):
        st.dataframe(pd.DataFrame([{"ID": s.kind, "Name": s.name, "von": s.von, "nach": s.nach, "Art": s.art,
                                    "Klasse jetzt": s.klasse_bisher, "Hinweis": s.hinweis} for s in protokoll]),
                     hide_index=True, width="stretch", height=360)
    st.button("Als neues Schuljahr übernehmen", type="primary", icon=":material/upgrade:", disabled=bool(offen),
              on_click=_neues_schuljahr, args=(cfg, kinder_neu, r))


def _neues_schuljahr(cfg: dict, kinder_neu, r) -> None:
    from skf.uebertritt import naechstes_schuljahr
    if r:  # laufendes Jahr bleibt im Verlauf erhalten
        verlauf.speichere(r, cfg, "Stand vor dem Schuljahreswechsel")
    cfg_neu = dict(cfg)
    cfg_neu["schuljahr"] = naechstes_schuljahr(cfg.get("schuljahr", ""))
    _laden(cfg_neu, kinder_neu)
    st.session_state.seite = "daten"


def seite_verlauf() -> None:
    _kopf("Verlauf", "Gespeicherte Berechnungen vergleichen und wiederherstellen")
    st.caption(f"Jede Berechnung wird mit Eingabedaten und Ergebnis gespeichert in `{verlauf.basis()}`.")
    staende = verlauf.staende()
    if not staende:
        st.info("Noch keine gespeicherten Stände – nach jeder Berechnung erscheint hier ein Eintrag.")
        return
    tabelle = pd.DataFrame([{"Zeitpunkt": s["zeit"].replace("T", " "), "Szenario": s["szenario"],
                             "Notiz": s.get("notiz", ""), "Klassen": s["kennzahlen"].get("Klassen"),
                             "Wünsche": s["kennzahlen"].get("Wünsche erfüllt"),
                             "Ø Schulweg": s["kennzahlen"].get("Ø Schulweg"), "Fehler": s["kennzahlen"].get("Fehler"),
                             "manuell": len(s.get("manuell", [])),
                             "Version": s.get("programmversion", "–")} for s in staende])
    st.dataframe(tabelle, width="stretch", hide_index=True)
    label = {s["name"]: f"{s['zeit'].replace('T', ' ')} · {s['szenario']}{' · ' + s['notiz'] if s.get('notiz') else ''}"
             for s in staende}
    st.subheader("Zwei Stände vergleichen")
    if len(staende) < 2:
        st.info("Für einen Vergleich braucht es mindestens zwei gespeicherte Stände (z.B. zwei Varianten berechnen).")
    a, b = st.columns(2)
    alt = a.selectbox("Älterer Stand", list(label), index=min(1, len(staende) - 1), format_func=label.get)
    neu = b.selectbox("Neuerer Stand", list(label), index=0, format_func=label.get)
    s_alt, s_neu = (next(s for s in staende if s["name"] == n) for n in (alt, neu))
    if alt != neu:
        v = verlauf.vergleiche(s_alt, s_neu)
        st.markdown(f"**{len(v['gewechselt'])} Lernende in anderer Klasse**"
                    + (f", davon {sum(x['schulhaus_gewechselt'] for x in v['gewechselt'])} mit Schulhauswechsel"
                       if v["gewechselt"] else ""))
        if v["kennzahlen"]:
            st.dataframe(pd.DataFrame([{"Kennzahl": k, "vorher": x[0], "nachher": x[1]}
                                       for k, x in v["kennzahlen"].items()]), hide_index=True)
        if v["gewechselt"]:
            st.dataframe(pd.DataFrame(v["gewechselt"]).rename(columns={"id": "ID", "vorher": "vorher", "nachher": "nachher",
                                                                       "schulhaus_gewechselt": "Schulhaus gewechselt"}),
                         hide_index=True, width="stretch")
        if v["klassen_neu"] or v["klassen_weg"]:
            st.caption(f"Neue Klassen: {', '.join(v['klassen_neu']) or '–'} · weggefallen: "
                       f"{', '.join(v['klassen_weg']) or '–'}")
    st.subheader("Stand öffnen")
    wahl = st.selectbox("Stand", list(label), format_func=label.get, key="vl_wahl")
    s = next(s for s in staende if s["name"] == wahl)
    ordner = Path(s["ordner"])
    c1, c2, c3 = st.columns(3)
    if (ordner / "bericht.html").exists():
        c1.download_button("Bericht", (ordner / "bericht.html").read_bytes(), "bericht.html", icon=":material/description:", width="stretch")
    if (ordner / "klassenlisten.xlsx").exists():
        c2.download_button("Klassenlisten", (ordner / "klassenlisten.xlsx").read_bytes(), "klassenlisten.xlsx",
                           icon=":material/table_view:", width="stretch")
    c3.button("Eingabedaten dieses Standes laden", icon=":material/settings_backup_restore:", width="stretch", on_click=_stand_laden, args=(ordner,))
    if s.get("manuell"):
        st.caption("Manuelle Anpassungen: " + "; ".join(s["manuell"]))
    with st.popover("Stand löschen", icon=":material/delete:"):
        st.write("Diesen Stand endgültig löschen?")
        if st.button("Ja, löschen", type="primary"):
            verlauf.loesche(s)
            st.rerun()


def seite_hilfe() -> None:
    _kopf("Hilfe", "Bedienung, Begriffe und Datenschutz")
    st.markdown("""
**So gehts**

1. **Daten** – Beispiel oder Vorlage laden, oder eigene Stammdaten (Excel) hochladen. Tipp: Vorlage laden →
   *Stammdaten als Excel speichern* → in Excel ausfüllen → wieder hochladen.
2. **Prüfen** – zeigt fehlende oder widersprüchliche Angaben (:red[:material/cancel:] Fehler,
   :orange[:material/warning:] Warnung, :gray[:material/info:] Hinweis).
3. **Berechnen** – Szenario und Rechenzeit wählen, starten. Jede Berechnung landet im Verlauf.
4. **Ergebnis** – Karte, Klassen, Lernende (Personenkarte mit Geschwistern, Wünschen, Verlauf), manuell anpassen,
   Stundenpläne, Wünsche, Planung & Kosten (Empfehlungen, Langfristplanung), Downloads.

**Begriffe**
- *Lernende*: Kinder und Jugendliche in Kindergarten, Primar und Oberstufe · *Erziehungsberechtigte*: Eltern bzw. Sorgeberechtigte.
- *Mehrjahrgangsklasse*: altersdurchmischtes Lernen (AdL) · *KG-Gruppe*: Kindergartenklasse im Vorjahr.
- *IF* Integrative Förderung · *DaZ* Deutsch als Zweitsprache · *IS* Integrative Sonderschulung ·
  *SHP* Schulische Heilpädagogin/Schulischer Heilpädagoge.
- *Gspänli-Regel*: Niemand kommt als einziges Kind aus seiner KG-Gruppe/Klasse in eine neue Klasse.
- *Blockzeiten*: Unterricht an allen Vormittagen (Kanton Luzern: VBV § 3).
- *Schulbus*: Kinder einer Buslinie kommen nur in angefahrene Schulhäuser; Unterricht beginnt nach der Ankunft und endet passend zu einer Abfahrt (Daten → Schulbus & Wege).
- *Wegzeiten*: Lehrpersonen wechseln direkt nacheinander nur dann das Schulhaus, wenn die Pause für den Weg reicht.
- *Schuljahreswechsel*: Jede Stufe hat eine nächste Stufe (KG1 → KG2 → 1 … 6 → Sek A/B/C). Kanti, Gymnasium oder
  Wegzug zählen als Austritt. Die aktuelle Klasse wird zur „bisherigen Klasse“ (Gspänli-Regel).
- *Oberstufe*: Jahrgang mit Niveau, z.B. `S1A` = 1. Sek Niveau A.

**Datenschutz** – Alle Daten bleiben auf diesem Computer (Verlauf im Ordner *Klassenbildung* im Benutzerordner).
Nur Kartenkacheln werden von OpenStreetMap geladen. Förderdaten erscheinen in Listen nur auf Wunsch.

**Hilfe bei Problemen** – Fenster schliessen und das Startprogramm erneut doppelklicken. Unklare Meldungen bei
*Prüfen* zuerst beheben.
""")
    with st.expander("Über diese Software und Lizenzen", icon=":material/info:"):
        st.markdown(f"**Klassenbildung & Stundenplan {__version__}** · © 2026 Outthinkx for Communities · "
                    "alle Rechte vorbehalten.  \n"
                    "Nutzung nur mit gültiger Lizenz. Verwendete Komponenten (Google OR-Tools, Streamlit, pandas, "
                    "openpyxl, PyYAML, Leaflet, Material Symbols u.a.) stehen unter freizügigen Lizenzen "
                    "(Apache-2.0, MIT, BSD); Kartendaten © OpenStreetMap-Mitwirkende. Details: "
                    "`LICENSE` und `THIRD_PARTY_NOTICES.md` im Programmordner.")


def main() -> None:
    st.set_page_config(page_title="Klassenbildung & Stundenplan", page_icon=":material/school:", layout="wide")
    st.html(STIL)
    st.session_state.setdefault("seite", "start")
    st.sidebar.html(f"<div class='skf-kopf'>{_logo()}<div><h1>Klassenbildung"
                    "</h1><p>& Stundenplan</p></div></div>")
    st.sidebar.radio("Navigation", list(SEITEN), key="seite", label_visibility="collapsed", format_func=SEITEN.get)
    if "tabellen" in st.session_state:
        st.sidebar.caption(f":material/description: {st.session_state.extra['rest'].get('name', '')} · "
                           f"{len(st.session_state.bearbeitet['Kinder'])} Lernende")
    if st.session_state.get("ergebnis"):
        r = st.session_state.ergebnis
        st.sidebar.caption(f":material/calculate: Berechnet: {r.schule.szenario} · "
                           f"{':green[:material/check_circle:]' if not r.anzahl('Fehler') else ':red[:material/cancel:]'} "
                           f"{r.anzahl('Fehler')} Fehler")
    st.sidebar.caption(f"Version {__version__}")
    {"start": seite_start, "daten": seite_daten, "pruefen": seite_pruefen, "berechnen": seite_berechnen,
     "ergebnis": seite_ergebnis, "uebertritt": seite_uebertritt, "verlauf": seite_verlauf,
     "hilfe": seite_hilfe}[st.session_state.seite]()
    _arbeitsstand_sichern()  # nach der Seite: enthält die eben gemachten Änderungen


main()

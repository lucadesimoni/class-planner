"""Bedienoberfläche für Schulleitung und Lehrpersonen (Streamlit).

Start:  skf app   (oder Doppelklick auf start-windows.bat / start-mac.command / start-linux.sh)

Ablauf in vier Schritten: 1 Daten → 2 Prüfen → 3 Berechnen → 4 Ergebnis.
Alle Daten bleiben auf dem eigenen Computer.
"""
from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import yaml

from skf.ablauf import Ergebnis, rechne
from skf.austausch import (BLAETTER, KINDER_SPALTEN, LISTENFELDER, ZAHLFELDER, _cfg_aus_tabellen, _tabellen_aus_cfg,
                           exportiere_stammdaten, importiere_stammdaten, kind_als_dict, lese_kinder)
from skf.bericht import CSS, _empfehlungen_html, _osm_karte, _plan, _wuensche_html, schreibe_csv, schreibe_html
from skf.daten import STANDARD_GEWICHTE, beispiel_ordner, lade_schule
from skf.export import exportiere_listen
from skf.pruefung import SCHWEREGRADE, vorpruefung

BEISPIELE = beispiel_ordner()
ICON = {"Fehler": "⛔", "Warnung": "⚠️", "Hinweis": "ℹ️"}
SPALTEN_LERNENDE = {
    "id": "ID", "vorname": "Vorname", "nachname": "Nachname", "name": "Name", "jahrgang": "Jahrgang (KG1, KG2, 1–6)",
    "geschlecht": "Geschlecht (w/m)", "adresse": "Adresse", "lat": "Breite", "lon": "Länge", "familie": "Familie (Geschwister)",
    "if": "IF", "daz": "DaZ (anfang/aufbau)", "is": "IS", "foerderbedarf": "weiterer Förderbedarf",
    "schulhaus_fix": "Schulhaus fix", "bisheriges_schulhaus": "Schulhaus Vorjahr",
    "bisherige_klasse": "Klasse/KG-Gruppe Vorjahr", "zusammen_mit": "Wunsch: zusammen mit (IDs)",
    "nicht_mit": "Wunsch: nicht zusammen mit (IDs)", "wunsch_schulhaus": "Wunsch-Schulhaus", "bemerkung": "Bemerkung",
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


def _aktuelle_daten():
    """Konfiguration und Lernende aus den (evtl. bearbeiteten) Tabellen."""
    b = st.session_state.bearbeitet
    t = {n: _tabelle_aus_df(b[n]) for n in st.session_state.tabellen}
    cfg = _cfg_aus_tabellen(t, st.session_state.extra["rest"], st.session_state.extra["stundentafel"])
    return cfg, _kinder_aus_df(b["Kinder"])


# ------------------------------------------------------------------ Seiten

def seite_daten() -> None:
    st.header("1 · Daten")
    st.write("Beispiel laden oder eigene Dateien hochladen. Tabellen lassen sich direkt bearbeiten "
             "(Zeilen hinzufügen: unten in der Tabelle; Listen mit `;` trennen).")
    c1, c2, c3 = st.columns(3)
    if c1.button("Beispiel Malters laden", width="stretch"):
        _laden(yaml.safe_load((BEISPIELE / "malters" / "schule.yaml").read_text(encoding="utf-8")),
               lese_kinder(BEISPIELE / "malters" / "kinder.csv"))
    if c2.button("Kleine Vorlage laden", width="stretch"):
        _laden(yaml.safe_load((BEISPIELE / "vorlage" / "schule.yaml").read_text(encoding="utf-8")),
               lese_kinder(BEISPIELE / "vorlage" / "kinder.csv"))
    with c3.popover("Eigene Dateien hochladen", width="stretch"):
        stamm = st.file_uploader("Stammdaten (Excel .xlsx oder .json) oder Schul-Konfiguration (.yaml)",
                                 type=["xlsx", "json", "yaml", "yml"])
        lernende = st.file_uploader("Lernende (CSV oder Excel) – nur nötig bei .yaml", type=["csv", "xlsx"])
        if stamm and st.button("Übernehmen"):
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
            st.success("Daten übernommen.")

    if "tabellen" not in st.session_state:
        st.info("Noch keine Daten geladen.")
        return

    cfg = st.session_state.extra["rest"]
    st.caption(f"**{cfg.get('name', 'Schule')}** · Schuljahr {cfg.get('schuljahr', '–')} · "
               f"Kantonsprofil: {cfg.get('basis_profil', 'keines')} · {len(st.session_state.bearbeitet['Kinder'])} Lernende")
    tabs = st.tabs(["Lernende", "Lehrpersonen", "Schulhäuser", "Räume", "Klassentypen", "Fächer",
                    "Förderangebote", "Gewichtung & Einstellungen"])
    with tabs[0]:
        st.caption("Wünsche der Erziehungsberechtigten: `zusammen_mit`/`nicht_mit` (IDs), `wunsch_schulhaus`. "
                   "`bisherige_klasse` = Klasse bzw. KG-Gruppe im Vorjahr (für Kontinuität und Gspänli-Regel). "
                   "IF/IS: ja; DaZ: anfang/aufbau.")
        st.session_state.bearbeitet["Kinder"] = st.data_editor(
            st.session_state.kinder_df, num_rows="dynamic", width="stretch", height=420,
            key=f"ed_kinder_{st.session_state.version}",
            column_config={k: st.column_config.Column(v) for k, v in SPALTEN_LERNENDE.items()})
    namen = {1: "Lehrpersonen", 2: "Schulhaeuser", 3: "Raeume", 4: "Klassentypen", 5: "Faecher", 6: "Foerderangebote"}
    hinweise = {
        1: "Verfügbarkeit `nicht_verfuegbar`: z.B. `Mi; Fr-NM; Mo-VM-1`. Förderangebote: Fach = Name des Angebots "
           "(z.B. IF, DaZ Anfang). `bisherige_klasse`: Klasse, die die Lehrperson weiterführt.",
        3: "Gleichartige Räume mit `anzahl` zusammenfassen. `nicht_verfuegbar` z.B. `Fr-NM` (Vereinsnutzung).",
        4: "Erlaubte Klassen: Jahrgänge (`1; 2` = Mehrjahrgangsklasse), Mindest-/Höchstgrösse, Raumtyp.",
        6: "Förderangebote ergänzen oder überschreiben jene des Kantonsprofils (gleicher Name).",
    }
    for i, name in namen.items():
        with tabs[i]:
            if i in hinweise:
                st.caption(hinweise[i])
            st.session_state.bearbeitet[name] = st.data_editor(
                st.session_state.tabellen[name], num_rows="dynamic", width="stretch",
                key=f"ed_{name}_{st.session_state.version}")
    with tabs[7]:
        rest = st.session_state.extra["rest"]
        kb = rest.setdefault("klassenbildung", {})
        c1, c2 = st.columns(2)
        kb["geschwister"] = c1.radio("Geschwister", ["weich", "hart", "aus"],
                                     index=["weich", "hart", "aus"].index(kb.get("geschwister", "weich")),
                                     help="hart = immer im selben Schulhaus; weich = möglichst")
        profil = rest.setdefault("profil", {}) or {}
        profil["verbindlich"] = c2.toggle("Klassengrössen des Kantons verbindlich", value=bool(profil.get("verbindlich")))
        rest["profil"] = profil
        st.subheader("Gewichtung")
        st.caption("Was ist wichtiger? Höherer Wert = stärker berücksichtigt. 0 = egal.")
        gew = rest.setdefault("gewichte", {}) or {}
        spalten = st.columns(3)
        for i, (k, standard) in enumerate(STANDARD_GEWICHTE.items()):
            gew[k] = spalten[i % 3].slider(GEWICHT_TEXT.get(k, k), 0, max(1000, standard * 3),
                                           int(gew.get(k, standard)), step=10, key=f"g_{k}")
        rest["gewichte"] = {k: v for k, v in gew.items() if v != STANDARD_GEWICHTE[k]}

    cfg_neu, kinder = _aktuelle_daten()
    puffer = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp:
        exportiere_stammdaten(cfg_neu, kinder, Path(tmp) / "stammdaten.xlsx")
        puffer.write((Path(tmp) / "stammdaten.xlsx").read_bytes())
    st.download_button("Stammdaten speichern (Excel)", puffer.getvalue(), "stammdaten.xlsx", width="stretch")


def seite_pruefen() -> None:
    st.header("2 · Prüfen")
    if "tabellen" not in st.session_state:
        st.info("Zuerst Daten laden (Schritt 1).")
        return
    cfg, kinder = _aktuelle_daten()
    try:
        schule = _schule_aus_cfg(cfg)
    except Exception as fehler:  # noqa: BLE001 – Eingabefehler verständlich zeigen
        st.error(f"Konfiguration fehlerhaft: {fehler}")
        return
    meldungen = vorpruefung(schule, kinder)
    zaehler = {s: sum(m.schwere == s for m in meldungen) for s in SCHWEREGRADE}
    c = st.columns(3)
    for i, s in enumerate(SCHWEREGRADE):
        c[i].metric(f"{ICON[s]} {s}", zaehler[s])
    if not meldungen:
        st.success("Keine Probleme gefunden – weiter mit Schritt 3.")
    for m in sorted(meldungen, key=lambda m: SCHWEREGRADE.index(m.schwere)):
        {"Fehler": st.error, "Warnung": st.warning, "Hinweis": st.info}[m.schwere](f"**{m.bereich}:** {m.text}")


def seite_berechnen() -> None:
    st.header("3 · Berechnen")
    if "tabellen" not in st.session_state:
        st.info("Zuerst Daten laden (Schritt 1).")
        return
    cfg, kinder = _aktuelle_daten()
    szenarien = ["Basis"] + list((cfg.get("szenarien") or {}).keys())
    c1, c2 = st.columns(2)
    szenario = c1.selectbox("Szenario", szenarien, help="Varianten sind in der Konfiguration unter 'szenarien' "
                                                      "definiert (z.B. Umbau, Lehrpersonenmangel).")
    zeit = c2.slider("Rechenzeit (Sekunden)", 20, 600, 120, step=10,
                     help="Mehr Zeit = näher am Optimum. Kleine Schulen sind in Sekunden fertig.")
    if st.button("▶ Klassen und Stundenplan berechnen", type="primary", width="stretch"):
        schule = _schule_aus_cfg(cfg, szenario)
        with st.status("Berechnung läuft …", expanded=True) as status:
            r = rechne(schule, kinder, zeitlimit=zeit, protokoll=lambda t: st.write(t.strip()))
            st.session_state.ergebnis = r
            ok = r.anzahl("Fehler") == 0 and r.vollstaendig
            status.update(label="Fertig – weiter mit Schritt 4" if ok else "Fertig mit Fehlern – siehe Schritt 4",
                          state="complete" if ok else "error")


def seite_ergebnis() -> None:
    st.header("4 · Ergebnis")
    r: Ergebnis | None = st.session_state.get("ergebnis")
    if not r:
        st.info("Noch nichts berechnet (Schritt 3).")
        return
    if r.anzahl("Fehler"):
        st.error(f"{r.anzahl('Fehler')} Fehler – das Ergebnis ist so nicht verwendbar.")
    else:
        st.success("Alle harten Regeln erfüllt." + (f" {r.anzahl('Warnung')} Warnungen prüfen." if r.anzahl("Warnung")
                                                       else ""))
    kz = r.kennzahlen()
    spalten = st.columns(6)
    for i, k in enumerate(["Klassen", "Ø Klassengrösse", "Ø Schulweg", "Wünsche erfüllt", "Förderlektionen",
                           "Springstunden"]):
        spalten[i].metric(k, kz[k])
    tabs = st.tabs(["Meldungen", "Karte", "Klassen", "Stundenpläne", "Wünsche & KG-Gruppen", "Empfehlungen",
                    "Herunterladen"])
    with tabs[0]:
        df = pd.DataFrame([{"": ICON[m.schwere], "Schweregrad": m.schwere, "Bereich": m.bereich, "Meldung": m.text,
                            "Quelle": m.quelle} for m in sorted(r.meldungen, key=lambda m: SCHWEREGRADE.index(m.schwere))])
        st.dataframe(df, width="stretch", hide_index=True, height=420)
    if not r.einteilung:
        return
    e = r.einteilung
    nach_id = {k.id: k for k in r.kinder}
    with tabs[1]:
        _html(_osm_karte(r), 560)
    with tabs[2]:
        zeilen = []
        for c in e.klassen:
            ks = [nach_id[i] for i in c.kinder]
            zeilen.append({"Klasse": c.name, "Schulhaus": c.schulhaus, "Schulzimmer": c.raum.name,
                           "Jahrgänge": "/".join(c.jahrgaenge), "Lernende": len(ks),
                           "Mädchen": sum(k.geschlecht == "w" for k in ks), "Knaben": sum(k.geschlecht == "m" for k in ks),
                           "IF": sum(k.if_ for k in ks), "DaZ": sum(bool(k.daz) for k in ks), "IS": sum(k.is_ for k in ks)})
        st.dataframe(pd.DataFrame(zeilen), width="stretch", hide_index=True)
        wahl = st.selectbox("Klassenliste anzeigen", [c.name for c in e.klassen])
        c = next(c for c in e.klassen if c.name == wahl)
        st.dataframe(pd.DataFrame([{"ID": k.id, "Name": k.name, "Jahrgang": k.jahrgang, "Geschlecht": k.geschlecht,
                                    "bisher": k.bisherige_klasse, "Schulweg km": round(e.schulweg_m[k.id] / 1000, 2),
                                    "Wünsche": "; ".join(filter(None, [
                                        f"mit {', '.join(k.zusammen_mit)}" if k.zusammen_mit else "",
                                        f"nicht mit {', '.join(k.nicht_mit)}" if k.nicht_mit else ""]))}
                                   for k in sorted((nach_id[i] for i in c.kinder), key=lambda k: k.name)]),
                     width="stretch", hide_index=True)
    with tabs[3]:
        if not r.lektionen:
            st.info("Kein Stundenplan berechnet.")
        else:
            art = st.radio("Stundenplan für", ["Klasse", "Lehrperson"], horizontal=True)
            if art == "Klasse":
                wahl = st.selectbox("Klasse", [c.name for c in e.klassen], key="sp_klasse")
                c = next(c for c in e.klassen if c.name == wahl)
                eintr: dict[int, str] = {}
                for l in sorted(r.lektionen, key=lambda l: l.art != "unterricht"):
                    if c.name in l.klassen:
                        eintr[l.slot] = eintr.get(l.slot, "") + (
                            f"<b>{l.fach}</b><br>{l.lehrperson}<br><span class='muted'>{l.raum_label}</span>"
                            if l.art == "unterricht" else f"<br><i>+ {l.fach}: {l.lehrperson}</i>")
                _html(_plan(r, eintr, r.schule.schulhaus(c.schulhaus).nicht_verfuegbar, {}), 420)
            else:
                namen = sorted({b.lehrperson for b in r.bloecke})
                wahl = st.selectbox("Lehrperson", namen, key="sp_lp")
                lp = next(x for x in r.schule.lehrpersonen if x.name == wahl)
                eintr = {l.slot: f"<b>{'/'.join(l.klassen)}</b><br>{l.fach}<br><span class='muted'>{l.raum_label}</span>"
                         for l in r.lektionen if l.lehrperson == wahl}
                st.caption(f"{len(eintr)} Lektionen · Pensum {lp.pensum_min}–{lp.pensum_max}")
                _html(_plan(r, eintr, lp.nicht_verfuegbar, {}), 420)
    with tabs[4]:
        _html(_wuensche_html(r), 520)
    with tabs[5]:
        _html(_empfehlungen_html(r) or "<p>Keine Empfehlungen.</p>", 700)
    with tabs[6]:
        with tempfile.TemporaryDirectory() as tmp:
            ordner = Path(tmp)
            mit_foerder = st.toggle("IF/DaZ/IS in Klassenlisten aufnehmen (besonders schützenswerte Daten)")
            schreibe_csv(ordner, r)
            schreibe_html(ordner / "bericht.html", r)
            exportiere_listen(r, ordner, mit_foerder)
            dateien = {
                "bericht.html": "Bericht (alles auf einen Blick, im Browser öffnen)",
                "klassenlisten.xlsx": "Klassenlisten (Excel, druckfertig)",
                "stundenplaene.xlsx": "Stundenpläne (Excel, pro Klasse/Lehrperson/Raum)",
                "druck.html": "Druckversion (im Browser drucken oder als PDF speichern)",
            }
            for name, text in dateien.items():
                if (ordner / name).exists():
                    st.download_button(f"⬇ {text}", (ordner / name).read_bytes(), name, key=f"dl_{name}",
                                       width="stretch")
            zip_puffer = io.BytesIO()
            with zipfile.ZipFile(zip_puffer, "w", zipfile.ZIP_DEFLATED) as z:
                for f in ordner.iterdir():
                    z.write(f, f.name)
            st.download_button("⬇ Alles als ZIP (inkl. CSV-Rohdaten)", zip_puffer.getvalue(), "ergebnis.zip",
                               width="stretch")


def seite_hilfe() -> None:
    st.header("Hilfe")
    st.markdown("""
**So gehts**

1. **Daten**: Beispiel laden oder eigene Stammdaten (Excel) hochladen. Lernende, Lehrpersonen, Schulhäuser,
   Räume usw. direkt in den Tabellen anpassen. Mit *Stammdaten speichern* sichern.
2. **Prüfen**: zeigt fehlende oder widersprüchliche Angaben (⛔ Fehler, ⚠️ Warnung, ℹ️ Hinweis).
3. **Berechnen**: Szenario und Rechenzeit wählen, starten.
4. **Ergebnis**: Klassen, Stundenpläne, Karte, Wünsche, Empfehlungen ansehen und herunterladen.

**Begriffe**
- *Lernende*: Kinder in Kindergarten und Primarschule. *Erziehungsberechtigte*: Eltern bzw. Sorgeberechtigte.
- *Mehrjahrgangsklasse*: Klasse mit mehreren Jahrgängen (altersdurchmischtes Lernen, AdL).
- *IF* Integrative Förderung · *DaZ* Deutsch als Zweitsprache · *IS* Integrative Sonderschulung ·
  *SHP* Schulische Heilpädagogin/Schulischer Heilpädagoge.
- *Gspänli-Regel*: Niemand kommt als einziges Kind aus seiner bisherigen KG-Gruppe/Klasse in eine neue Klasse.
- *Blockzeiten*: Unterricht an allen Vormittagen (Kanton Luzern: VBV § 3).

**Datenschutz**: Alle Daten bleiben auf diesem Computer. Nur die Kartenkacheln werden von OpenStreetMap geladen.
""")


def main() -> None:
    st.set_page_config(page_title="Klassenbildung & Stundenplan", page_icon="🏫", layout="wide")
    st.sidebar.title("🏫 Klassenbildung & Stundenplan")
    seiten = {"1 · Daten": seite_daten, "2 · Prüfen": seite_pruefen, "3 · Berechnen": seite_berechnen,
              "4 · Ergebnis": seite_ergebnis, "Hilfe": seite_hilfe}
    wahl = st.sidebar.radio("Schritt", list(seiten), key="seite")
    if "tabellen" in st.session_state:
        st.sidebar.caption(f"{st.session_state.extra['rest'].get('name', '')} · "
                           f"{len(st.session_state.bearbeitet['Kinder'])} Lernende")
    if st.session_state.get("ergebnis"):
        r = st.session_state.ergebnis
        st.sidebar.caption(f"Letzte Berechnung: {r.schule.szenario}, {r.anzahl('Fehler')} Fehler")
    seiten[wahl]()


main()

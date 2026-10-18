"""Bedienoberfläche für Schulleitung und Lehrpersonen (Streamlit).

Start:  skf app   (oder Doppelklick auf start-windows.bat / start-mac.command / start-linux.sh)

Ablauf in vier Schritten: 1 Daten → 2 Prüfen → 3 Berechnen → 4 Ergebnis, dazu Verlauf und Hilfe.
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

from skf import verlauf
from skf.ablauf import Ergebnis, rechne, verschiebe
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
    st.toast("Daten geladen ✅")


def _aktuelle_daten():
    """Konfiguration und Lernende aus den (evtl. bearbeiteten) Tabellen."""
    b = st.session_state.bearbeitet
    t = {n: _tabelle_aus_df(b[n]) for n in st.session_state.tabellen}
    cfg = _cfg_aus_tabellen(t, st.session_state.extra["rest"], st.session_state.extra["stundentafel"])
    return cfg, _kinder_aus_df(b["Kinder"])


# ------------------------------------------------------------------ Navigation

SEITEN = ["🏠 Start", "1 · Daten", "2 · Prüfen", "3 · Berechnen", "4 · Ergebnis", "🕘 Verlauf", "❓ Hilfe"]


def _gehe(seite: str) -> None:
    st.session_state.seite = seite


def _weiter(seite: str, text: str | None = None) -> None:
    st.button(text or f"Weiter: {seite} →", type="primary", on_click=_gehe, args=(seite,), key=f"weiter_{seite}")


def _beispiel(name: str) -> None:
    ordner = BEISPIELE / name
    _laden(yaml.safe_load((ordner / "schule.yaml").read_text(encoding="utf-8")), lese_kinder(ordner / "kinder.csv"))
    st.session_state.seite = "1 · Daten"


# ------------------------------------------------------------------ Seiten

def seite_start() -> None:
    st.title("Klassenbildung & Stundenplan")
    st.write("Bildet Klassen, verteilt Lehraufträge und erstellt den Stundenplan – unter Berücksichtigung von "
             "Schulwegen, Geschwistern, Kindergartengruppen, Wünschen der Erziehungsberechtigten, IF/DaZ/IS, "
             "Verfügbarkeiten und kantonalen Vorgaben. **Alle Daten bleiben auf diesem Computer.**")
    hat_daten, hat_ergebnis = "tabellen" in st.session_state, bool(st.session_state.get("ergebnis"))
    c = st.columns(4)
    for spalte, (titel, text, fertig) in zip(c, [
            ("1 Daten", "Lernende, Lehrpersonen, Schulhäuser erfassen oder Excel hochladen", hat_daten),
            ("2 Prüfen", "Fehlende oder widersprüchliche Angaben finden", hat_daten),
            ("3 Berechnen", "Klassen und Stundenplan berechnen lassen", hat_ergebnis),
            ("4 Ergebnis", "Karte, Klassenlisten, Stundenpläne, Empfehlungen", hat_ergebnis)]):
        with spalte.container(border=True):
            st.markdown(f"**{'✅' if fertig else '⬜'} {titel}**")
            st.caption(text)
    st.subheader("Loslegen")
    a, b, d = st.columns(3)
    a.button("📂 Beispiel Malters ansehen", on_click=_beispiel, args=("malters",), width="stretch",
             help="644 fiktive Lernende, 3 Schulhäuser – zeigt alle Funktionen")
    b.button("🧩 Kleine Vorlage öffnen", on_click=_beispiel, args=("vorlage",), width="stretch",
             help="110 Lernende, 2 Schulhäuser – ideal zum Ausprobieren und als Ausgangspunkt")
    d.button("⬆️ Eigene Daten hochladen", on_click=_gehe, args=("1 · Daten",), width="stretch")
    if hat_ergebnis:
        st.success("Es liegt ein berechnetes Ergebnis vor.")
        _weiter("4 · Ergebnis", "Zum Ergebnis →")
    staende = verlauf.staende()
    if staende:
        st.caption(f"🕘 {len(staende)} gespeicherte Stände im Verlauf (zuletzt {staende[0]['zeit'].replace('T', ' ')}).")


def seite_daten() -> None:
    st.header("1 · Daten")
    c1, c2, c3 = st.columns(3)
    c1.button("Beispiel Malters laden", on_click=_beispiel, args=("malters",), width="stretch")
    c2.button("Kleine Vorlage laden", on_click=_beispiel, args=("vorlage",), width="stretch")
    with c3.popover("⬆️ Eigene Dateien hochladen", width="stretch"):
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
                st.toast("Daten übernommen ✅")
            except Exception as fehler:  # noqa: BLE001 – verständlich melden statt abstürzen
                st.error(f"Die Datei konnte nicht gelesen werden: {fehler}")

    if "tabellen" not in st.session_state:
        st.info("Noch keine Daten geladen.")
        return

    cfg = st.session_state.extra["rest"]
    st.caption(f"**{cfg.get('name', 'Schule')}** · Schuljahr {cfg.get('schuljahr', '–')} · "
               f"Kantonsprofil: {cfg.get('basis_profil', 'keines')} · "
               f"{len(st.session_state.bearbeitet['Kinder'])} Lernende")
    tabs = st.tabs(["👧 Lernende", "🧑‍🏫 Lehrpersonen", "🏫 Schulhäuser", "🚪 Räume", "🧮 Klassentypen", "📚 Fächer",
                    "🤝 Förderangebote", "⚖️ Gewichtung"])
    with tabs[0]:
        alle = st.toggle("Alle Spalten zeigen (Koordinaten, Förderdetails)", key="alle_spalten")
        st.caption("Wünsche: IDs mit `;` trennen. *Klasse/KG-Gruppe Vorjahr* hält Gruppen zusammen (Gspänli-Regel). "
                   "IF/IS: `ja`; DaZ: `anfang` oder `aufbau`. Neue Zeile: unten in der Tabelle.")
        sichtbar = None if alle else ["id", "vorname", "nachname", "jahrgang", "geschlecht", "adresse", "familie",
                                      "if", "daz", "is", "bisherige_klasse", "zusammen_mit", "nicht_mit",
                                      "wunsch_schulhaus", "bemerkung"]
        st.session_state.bearbeitet["Kinder"] = st.data_editor(
            st.session_state.kinder_df, num_rows="dynamic", width="stretch", height=430,
            key=f"ed_kinder_{st.session_state.version}", column_order=sichtbar,
            column_config={k: st.column_config.Column(v) for k, v in SPALTEN_LERNENDE.items()})
    namen = {1: "Lehrpersonen", 2: "Schulhaeuser", 3: "Raeume", 4: "Klassentypen", 5: "Faecher", 6: "Foerderangebote"}
    hinweise = {
        1: "Nicht verfügbar z.B. `Mi; Fr-NM; Mo-VM-1`. Förderangebote unterrichten Lehrpersonen mit dem Fach "
           "`IF`, `DaZ Anfang`, `DaZ Aufbau`. *bisherige_klasse*: Klasse, die die Lehrperson weiterführt.",
        2: "Koordinaten (lat/lon) z.B. aus map.geo.admin.ch oder OpenStreetMap (Rechtsklick → Koordinaten).",
        3: "Gleichartige Räume mit `anzahl` zusammenfassen. Nicht verfügbar z.B. `Fr-NM` (Vereinsnutzung).",
        4: "Erlaubte Klassen: Jahrgänge (`1; 2` = Mehrjahrgangsklasse), Mindest-/Höchstgrösse, Raumtyp.",
        6: "Ergänzt oder überschreibt die Förderangebote des Kantonsprofils (gleicher Name).",
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

    cfg_neu, kinder = _aktuelle_daten()
    with tempfile.TemporaryDirectory() as tmp:
        exportiere_stammdaten(cfg_neu, kinder, Path(tmp) / "stammdaten.xlsx")
        inhalt = (Path(tmp) / "stammdaten.xlsx").read_bytes()
    a, b = st.columns(2)
    a.download_button("💾 Stammdaten als Excel speichern", inhalt, "stammdaten.xlsx", width="stretch")
    with b:
        _weiter("2 · Prüfen")


def seite_pruefen() -> None:
    st.header("2 · Prüfen")
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
        _weiter("3 · Berechnen")


def seite_berechnen() -> None:
    st.header("3 · Berechnen")
    if "tabellen" not in st.session_state:
        st.info("Zuerst Daten laden (Schritt 1).")
        return
    cfg, kinder = _aktuelle_daten()
    szenarien = ["Basis"] + list((cfg.get("szenarien") or {}).keys())
    c1, c2 = st.columns(2)
    szenario = c1.selectbox("Szenario", szenarien, help="Varianten (z.B. Umbau, Lehrpersonenmangel) sind in der "
                                                      "Konfiguration unter 'szenarien' definiert.")
    zeit = c2.select_slider("Rechenzeit", options=[30, 60, 120, 300, 600], value=120,
                            format_func=lambda s: f"{s // 60} min" if s >= 60 else f"{s} s",
                            help="Mehr Zeit = näher am Optimum. Kleine Schulen sind in Sekunden fertig.")
    notiz = st.text_input("Notiz für den Verlauf (optional)", placeholder="z.B. Variante mit 2 Mehrjahrgangsklassen")
    if st.button("▶ Klassen und Stundenplan berechnen", type="primary", width="stretch"):
        try:
            schule = _schule_aus_cfg(cfg, szenario)
        except Exception as fehler:  # noqa: BLE001
            st.error(f"Die Angaben sind fehlerhaft: {fehler}")
            return
        with st.status("Berechnung läuft – bitte warten …", expanded=True) as status:
            r = rechne(schule, kinder, zeitlimit=zeit, protokoll=lambda t: st.write(t.strip()))
            st.session_state.ergebnis = r
            try:
                st.session_state.stand = str(verlauf.speichere(r, cfg, notiz))
                st.write("🕘 Im Verlauf gespeichert.")
            except OSError as fehler:
                st.warning(f"Verlauf konnte nicht gespeichert werden: {fehler}")
            ok = r.anzahl("Fehler") == 0 and r.vollstaendig
            status.update(label="Fertig ✅" if ok else "Fertig – mit Fehlern (siehe Ergebnis)",
                          state="complete" if ok else "error")
    if st.session_state.get("ergebnis"):
        _weiter("4 · Ergebnis", "Zum Ergebnis →")


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
            f"{g.name} ({g.id}, {e.klasse_von[g.id]}{'' if e.schulhaus_von[g.id] == e.schulhaus_von[kid] else ' ⚠️ anderes Schulhaus'})"
            for g in geschwister))
    wuensche_k = []
    for anderer in k.zusammen_mit:
        if anderer in nach_id:
            wuensche_k.append(f"{'✅' if e.klasse_von[anderer] == e.klasse_von[kid] else '❌'} zusammen mit "
                              f"{nach_id[anderer].name} ({anderer}, {e.klasse_von[anderer]})")
    for anderer in k.nicht_mit:
        if anderer in nach_id:
            wuensche_k.append(f"{'✅' if e.klasse_von[anderer] != e.klasse_von[kid] else '❌'} nicht zusammen mit "
                              f"{nach_id[anderer].name} ({anderer})")
    if k.wunsch_schulhaus:
        wuensche_k.append(f"{'✅' if e.schulhaus_von[kid] == k.wunsch_schulhaus else '❌'} Wunsch-Schulhaus "
                          f"{k.wunsch_schulhaus}")
    if wuensche_k:
        st.markdown("**Wünsche der Erziehungsberechtigten:**  \n" + "  \n".join(wuensche_k))
    if k.bisherige_klasse:
        gspaenli = [g for g in r.kinder if g.bisherige_klasse == k.bisherige_klasse and g.id != kid
                    and e.klasse_von[g.id] == e.klasse_von[kid]]
        st.markdown(f"**Aus {k.bisherige_klasse} ebenfalls in {e.klasse_von[kid]}:** "
                    + (", ".join(g.name for g in gspaenli) if gspaenli else "niemand ⚠️"))
    if k.bemerkung:
        st.markdown(f"**Bemerkung:** {k.bemerkung}")
    historie = verlauf.kind_verlauf(kid)
    if historie:
        st.markdown("**Verlauf (gespeicherte Stände):**")
        st.dataframe(pd.DataFrame([{"Zeitpunkt": h["zeit"].replace("T", " "), "Szenario": h["szenario"],
                                    "Klasse": h["klasse"], "Schulhaus": h["schulhaus"]} for h in historie]),
                     hide_index=True, width="stretch")


def seite_ergebnis() -> None:
    st.header("4 · Ergebnis")
    r: Ergebnis | None = st.session_state.get("ergebnis")
    if not r:
        st.info("Noch nichts berechnet (Schritt 3).")
        return
    if r.anzahl("Fehler"):
        st.error(f"⛔ {r.anzahl('Fehler')} Fehler – das Ergebnis ist so nicht verwendbar. Details unter *Meldungen*.")
    else:
        st.success("✅ Alle harten Regeln erfüllt." + (f" {r.anzahl('Warnung')} Warnungen bitte prüfen."
                                                       if r.anzahl("Warnung") else ""))
    kz = r.kennzahlen()
    spalten = st.columns(6)
    for i, k in enumerate(["Klassen", "Ø Klassengrösse", "Ø Schulweg", "Wünsche erfüllt", "Förderlektionen",
                           "Springstunden"]):
        spalten[i].metric(k, kz[k])
    tabs = st.tabs(["🗺️ Karte", "🏫 Klassen", "👧 Lernende", "✋ Anpassen", "🗓️ Stundenpläne",
                    "🤝 Wünsche & KG-Gruppen", "💡 Empfehlungen", "⚠️ Meldungen", "⬇️ Herunterladen"])
    e = r.einteilung
    with tabs[7]:
        filt = st.multiselect("Anzeigen", SCHWEREGRADE, default=["Fehler", "Warnung"])
        df = pd.DataFrame([{"": ICON[m.schwere], "Schweregrad": m.schwere, "Bereich": m.bereich, "Meldung": m.text,
                            "Quelle": m.quelle} for m in sorted(r.meldungen, key=lambda m: SCHWEREGRADE.index(m.schwere))
                           if m.schwere in filt])
        st.dataframe(df, width="stretch", hide_index=True, height=420)
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
    with tabs[2]:
        optionen = sorted(r.kinder, key=lambda k: k.name)
        kid = st.selectbox("Lernende suchen (Name oder ID tippen)", [k.id for k in optionen],
                           format_func=lambda i: f"{nach_id[i].name} · {i} · {nach_id[i].jahrgang}", key="kind_wahl")
        _kind_karte(r, kid)
    with tabs[3]:
        st.write("Ein Kind in eine andere Klasse verschieben. Danach wird alles neu geprüft "
                 "(Klassengrössen, Wünsche, Geschwister, Gspänli-Regel, Recht).")
        a, b = st.columns(2)
        kid = a.selectbox("Kind", [k.id for k in sorted(r.kinder, key=lambda k: k.name)], key="anp_kind",
                          format_func=lambda i: f"{nach_id[i].name} · {i} · {e.klasse_von[i]}")
        moeglich = [c.name for c in e.klassen if nach_id[kid].jahrgang in c.vorlage.jahrgaenge]
        ziel = b.selectbox("Neue Klasse", moeglich, index=moeglich.index(e.klasse_von[kid]), key="anp_ziel")
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
                st.toast("Gespeichert 🕘")
    with tabs[4]:
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
                _html(_plan(r, eintr, r.schule.schulhaus(c.schulhaus).nicht_verfuegbar, {}), 440)
            else:
                namen = sorted({b.lehrperson for b in r.bloecke})
                wahl = st.selectbox("Lehrperson", namen, key="sp_lp")
                lp = next(x for x in r.schule.lehrpersonen if x.name == wahl)
                eintr = {l.slot: f"<b>{'/'.join(l.klassen)}</b><br>{l.fach}<br><span class='muted'>{l.raum_label}</span>"
                         for l in r.lektionen if l.lehrperson == wahl}
                st.caption(f"{len(eintr)} Lektionen · Pensum {lp.pensum_min}–{lp.pensum_max}")
                _html(_plan(r, eintr, lp.nicht_verfuegbar, {}), 440)
    with tabs[5]:
        _html(_wuensche_html(r), 560)
    with tabs[6]:
        _html(_empfehlungen_html(r) or "<p>Keine Empfehlungen.</p>", 720)
    with tabs[8]:
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
                    st.download_button(f"⬇ {text}", (ordner / name).read_bytes(), name, key=f"dl_{name}",
                                       width="stretch")
            zip_puffer = io.BytesIO()
            with zipfile.ZipFile(zip_puffer, "w", zipfile.ZIP_DEFLATED) as z:
                for f in ordner.iterdir():
                    z.write(f, f.name)
            st.download_button("⬇ Alles als ZIP (inkl. CSV-Rohdaten)", zip_puffer.getvalue(), "ergebnis.zip",
                               width="stretch")


def _stand_laden(ordner: Path) -> None:
    _laden(*importiere_stammdaten(ordner / "stammdaten.xlsx"))
    st.session_state.seite = "1 · Daten"


def seite_verlauf() -> None:
    st.header("🕘 Verlauf")
    st.caption(f"Jede Berechnung wird mit Eingabedaten und Ergebnis gespeichert in `{verlauf.basis()}`.")
    staende = verlauf.staende()
    if not staende:
        st.info("Noch keine gespeicherten Stände – nach jeder Berechnung erscheint hier ein Eintrag.")
        return
    tabelle = pd.DataFrame([{"Zeitpunkt": s["zeit"].replace("T", " "), "Szenario": s["szenario"],
                             "Notiz": s.get("notiz", ""), "Klassen": s["kennzahlen"].get("Klassen"),
                             "Wünsche": s["kennzahlen"].get("Wünsche erfüllt"),
                             "Ø Schulweg": s["kennzahlen"].get("Ø Schulweg"), "Fehler": s["kennzahlen"].get("Fehler"),
                             "manuell": len(s.get("manuell", []))} for s in staende])
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
        c1.download_button("⬇ Bericht", (ordner / "bericht.html").read_bytes(), "bericht.html", width="stretch")
    if (ordner / "klassenlisten.xlsx").exists():
        c2.download_button("⬇ Klassenlisten", (ordner / "klassenlisten.xlsx").read_bytes(), "klassenlisten.xlsx",
                           width="stretch")
    c3.button("↩ Eingabedaten dieses Standes laden", width="stretch", on_click=_stand_laden, args=(ordner,))
    if s.get("manuell"):
        st.caption("Manuelle Anpassungen: " + "; ".join(s["manuell"]))
    with st.popover("🗑 Stand löschen"):
        st.write("Diesen Stand endgültig löschen?")
        if st.button("Ja, löschen", type="primary"):
            verlauf.loesche(s)
            st.rerun()


def seite_hilfe() -> None:
    st.header("❓ Hilfe")
    st.markdown("""
**So gehts**

1. **Daten** – Beispiel oder Vorlage laden, oder eigene Stammdaten (Excel) hochladen. Tipp: Vorlage laden →
   *Stammdaten als Excel speichern* → in Excel ausfüllen → wieder hochladen.
2. **Prüfen** – zeigt fehlende oder widersprüchliche Angaben (⛔ Fehler, ⚠️ Warnung, ℹ️ Hinweis).
3. **Berechnen** – Szenario und Rechenzeit wählen, starten. Jede Berechnung landet im 🕘 Verlauf.
4. **Ergebnis** – Karte, Klassen, Lernende (Personenkarte mit Geschwistern, Wünschen, Verlauf), manuell anpassen,
   Stundenpläne, Wünsche, Empfehlungen, Downloads.

**Begriffe**
- *Lernende*: Kinder in Kindergarten und Primarschule · *Erziehungsberechtigte*: Eltern bzw. Sorgeberechtigte.
- *Mehrjahrgangsklasse*: altersdurchmischtes Lernen (AdL) · *KG-Gruppe*: Kindergartenklasse im Vorjahr.
- *IF* Integrative Förderung · *DaZ* Deutsch als Zweitsprache · *IS* Integrative Sonderschulung ·
  *SHP* Schulische Heilpädagogin/Schulischer Heilpädagoge.
- *Gspänli-Regel*: Niemand kommt als einziges Kind aus seiner KG-Gruppe/Klasse in eine neue Klasse.
- *Blockzeiten*: Unterricht an allen Vormittagen (Kanton Luzern: VBV § 3).

**Datenschutz** – Alle Daten bleiben auf diesem Computer (Verlauf im Ordner *Klassenbildung* im Benutzerordner).
Nur Kartenkacheln werden von OpenStreetMap geladen. Förderdaten erscheinen in Listen nur auf Wunsch.

**Hilfe bei Problemen** – Fenster schliessen und das Startprogramm erneut doppelklicken. Unklare Meldungen bei
*Prüfen* zuerst beheben.
""")


def main() -> None:
    st.set_page_config(page_title="Klassenbildung & Stundenplan", page_icon="🏫", layout="wide")
    st.session_state.setdefault("seite", SEITEN[0])
    st.sidebar.title("🏫 Klassenbildung")
    st.sidebar.radio("Navigation", SEITEN, key="seite", label_visibility="collapsed")
    if "tabellen" in st.session_state:
        st.sidebar.caption(f"📄 {st.session_state.extra['rest'].get('name', '')} · "
                           f"{len(st.session_state.bearbeitet['Kinder'])} Lernende")
    if st.session_state.get("ergebnis"):
        r = st.session_state.ergebnis
        st.sidebar.caption(f"🧮 Berechnet: {r.schule.szenario} · {'✅' if not r.anzahl('Fehler') else '⛔'} "
                           f"{r.anzahl('Fehler')} Fehler")
    {"🏠 Start": seite_start, "1 · Daten": seite_daten, "2 · Prüfen": seite_pruefen, "3 · Berechnen": seite_berechnen,
     "4 · Ergebnis": seite_ergebnis, "🕘 Verlauf": seite_verlauf, "❓ Hilfe": seite_hilfe}[st.session_state.seite]()


main()

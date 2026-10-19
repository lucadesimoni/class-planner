# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Kommandozeile.

    skf rechnen  schule.yaml kinder.csv -o ausgabe/      Klassen + Stundenplan + Berichte + Listen
    skf pruefen  schule.yaml kinder.csv                  nur Vorprüfung (Daten, Referenzen, Kapazität)
    skf export   schule.yaml kinder.csv -o daten.xlsx    Stammdaten exportieren (.xlsx oder .json)
    skf import   daten.xlsx -o ordner/                   Stammdaten importieren → schule.yaml + kinder.csv
    skf kinder   export_schulverwaltung.csv -o kinder.csv  Kinderliste normalisieren/umwandeln
    skf uebertritt schule.yaml kinder.csv -o kinder_neu.csv  Schuljahreswechsel: nächste Stufe, Übertritte, Austritte
    skf raeume   schule.yaml raumliste.xlsx              Raumliste übernehmen (CSV/Excel, Spalten frei benannt)
    skf lehrpersonen schule.yaml personal.csv            Lehrpersonenliste übernehmen
    skf vorlage  -o ordner/                              Vorlagen zum Erfassen eigener Daten
    skf profile                                          verfügbare Kantonsprofile
    skf app                                              Bedienoberfläche im Browser starten

Kurzform: ``skf schule.yaml kinder.csv`` entspricht ``skf rechnen …``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .ablauf import rechne
from .austausch import (exportiere_stammdaten, importiere_stammdaten, lese_liste, lese_rohkonfiguration, raumtypen,
                        schreibe_kinder, schreibe_rohkonfiguration, schreibe_vorlage, uebernehme_liste)
from .bericht import ordnername, schreibe_csv, schreibe_html, schreibe_vergleich
from .daten import STANDARD_GEWICHTE, baue_schule, lade_kinder, lade_profil, lade_schule, profile, szenarien
from .export import exportiere_listen
from .geo import geocodiere
from .pruefung import referenzen, vorpruefung
from .version import __version__

BEFEHLE = ("rechnen", "pruefen", "export", "import", "kinder", "uebertritt", "raeume", "lehrpersonen", "vorlage",
           "profile", "app")


def _gewicht(text: str) -> tuple[str, int]:
    name, _, wert = text.partition("=")
    if name not in STANDARD_GEWICHTE or not wert.lstrip("-").isdigit():
        raise argparse.ArgumentTypeError(f"erwartet NAME=ZAHL mit NAME aus: {', '.join(STANDARD_GEWICHTE)}")
    return name, int(wert)


def _spalte(text: str) -> tuple[str, str]:
    feld, _, spalte = text.partition("=")
    if not feld or not spalte:
        raise argparse.ArgumentTypeError("erwartet FELD=Spaltenname, z.B. id=Schüler-Nr")
    return feld, spalte


def _melde(meldungen, max_zeilen: int = 15) -> int:
    fehler = [m for m in meldungen if m.schwere == "Fehler"]
    for m in (fehler + [m for m in meldungen if m.schwere == "Warnung"])[:max_zeilen]:
        print(f"  [{m.schwere.upper()}] {m.bereich}: {m.text}")
    return len(fehler)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skf", description="Klassenbildung und Stundenplan für die Volksschule")
    p.add_argument("--version", action="version", version=f"Klassenbildung & Stundenplan {__version__}")
    p.add_argument("--gewichte-anzeigen", action="store_true", help="alle Gewichte mit Standardwert auflisten")
    sub = p.add_subparsers(dest="befehl")

    r = sub.add_parser("rechnen", help="Klassen, Lehraufträge und Stundenplan berechnen")
    r.add_argument("schule", help="Schul-Konfiguration (YAML)")
    r.add_argument("kinder", help="Kinderliste (CSV oder XLSX)")
    r.add_argument("-o", "--ausgabe", default="ausgabe", help="Ausgabeordner (Standard: ausgabe)")
    r.add_argument("-t", "--zeit", type=float, default=120, help="Zeitlimit pro Szenario in Sekunden (Standard: 120)")
    r.add_argument("-s", "--szenario", action="append", default=[],
                   help="Szenario aus der YAML rechnen (mehrfach möglich; 'alle' = alle Szenarien)")
    r.add_argument("-g", "--gewicht", action="append", type=_gewicht, default=[], metavar="NAME=ZAHL",
                   help="Gewicht überschreiben, z.B. -g schulweg_pro_km=300 (mehrfach möglich)")
    r.add_argument("--spalte", action="append", type=_spalte, default=[], metavar="FELD=SPALTE",
                   help="Spalte der Kinderliste zuordnen, z.B. --spalte id=Schüler-Nr")
    r.add_argument("--nur-klassen", action="store_true", help="nur Klassenbildung, kein Stundenplan")
    r.add_argument("--mit-foerderdaten", action="store_true",
                   help="IF/DaZ/IS in Klassenlisten aufnehmen (besonders schützenswerte Daten!)")
    r.add_argument("--geocodieren", action="store_true",
                   help="fehlende Koordinaten über geo.admin.ch aus der Adresse ermitteln")

    pr = sub.add_parser("pruefen", help="Daten prüfen, ohne zu rechnen")
    pr.add_argument("schule")
    pr.add_argument("kinder")
    pr.add_argument("-s", "--szenario", default="Basis")
    pr.add_argument("--spalte", action="append", type=_spalte, default=[], metavar="FELD=SPALTE")

    ex = sub.add_parser("export", help="Stammdaten (Schule + Kinder) als .xlsx oder .json exportieren")
    ex.add_argument("schule")
    ex.add_argument("kinder")
    ex.add_argument("-o", "--ziel", required=True, help="Zieldatei .xlsx oder .json")
    ex.add_argument("--spalte", action="append", type=_spalte, default=[], metavar="FELD=SPALTE")

    im = sub.add_parser("import", help="Stammdaten aus .xlsx oder .json importieren")
    im.add_argument("quelle")
    im.add_argument("-o", "--ordner", required=True, help="Zielordner für schule.yaml und kinder.csv")

    ki = sub.add_parser("kinder", help="Kinderliste (z.B. Export der Schulverwaltung) normalisieren")
    ki.add_argument("quelle", help="CSV oder XLSX")
    ki.add_argument("-o", "--ziel", required=True, help="Ziel .csv oder .xlsx")
    ki.add_argument("--spalte", action="append", type=_spalte, default=[], metavar="FELD=SPALTE")

    ue = sub.add_parser("uebertritt", help="Schuljahreswechsel: jede Stufe → nächste Stufe (Übertritte, Austritte)")
    ue.add_argument("schule", help="schule.yaml (Stufenfolge aus den Jahrgängen, anpassbar unter 'uebertritte')")
    ue.add_argument("kinder", help="Lernende des laufenden Jahres; Spalte 'uebertritt' = Entscheid (A/B/C, Kanti, "
                                   "repetiert, Wegzug …)")
    ue.add_argument("-o", "--ziel", required=True, help="Lernende des nächsten Jahres (.csv/.xlsx)")
    ue.add_argument("--zuteilung", help="aktuelle Klassen: einteilung.csv einer Berechnung oder zuteilung.json "
                                        "aus dem Verlauf (sonst Spalte 'klasse')")
    ue.add_argument("--neu", help="Neueintritte (z.B. KG1 von der Einwohnerkontrolle), CSV/Excel")
    ue.add_argument("--entscheide", help="Entscheide als eigene Liste (Spalten ID und Entscheid/Übertritt), "
                                         "z.B. aus dem Übertrittsverfahren")
    ue.add_argument("--spalte", action="append", type=_spalte, default=[], metavar="FELD=SPALTE")

    for befehl, text in (("raeume", "Raumliste (CSV/Excel) in die Konfiguration übernehmen"),
                         ("lehrpersonen", "Lehrpersonenliste (CSV/Excel) in die Konfiguration übernehmen")):
        li = sub.add_parser(befehl, help=text)
        li.add_argument("schule", help="schule.yaml")
        li.add_argument("liste", help="CSV oder XLSX; Spaltennamen werden erkannt (z.B. Schulhaus, Raum, Typ, Plätze)")
        li.add_argument("-o", "--ziel", help="Ziel-YAML (Standard: schule.yaml überschreiben, Sicherung .bak)")
        li.add_argument("--ergaenzen", action="store_true",
                        help="bestehende Einträge behalten (Standard: Räume der genannten Schulhäuser bzw. alle "
                             "Lehrpersonen ersetzen)")
        li.add_argument("--spalte", action="append", type=_spalte, default=[], metavar="FELD=SPALTE")

    vo = sub.add_parser("vorlage", help="Vorlagen zum Erfassen eigener Daten erzeugen")
    vo.add_argument("-o", "--ordner", required=True)

    sub.add_parser("profile", help="verfügbare Kantonsprofile anzeigen")
    ap = sub.add_parser("app", help="Bedienoberfläche im Browser starten")
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--ohne-browser", action="store_true", help="Browser nicht automatisch öffnen")
    return p


def _utf8_ausgabe() -> None:
    """Windows schreibt in Umleitungen/Logs sonst cp1252 und bricht bei Zeichen wie „→“ ab."""
    for strom in (sys.stdout, sys.stderr):
        if hasattr(strom, "reconfigure") and (strom.encoding or "").lower().replace("-", "") != "utf8":
            strom.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> None:
    _utf8_ausgabe()
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in BEFEHLE and not argv[0].startswith("-"):
        argv.insert(0, "rechnen")  # Kurzform: skf schule.yaml kinder.csv
    p = _parser()
    args = p.parse_args(argv)

    if args.gewichte_anzeigen:
        for k, v in STANDARD_GEWICHTE.items():
            print(f"{k:34} {v}")
        return
    if args.befehl is None:
        p.print_help()
        return
    try:
        {"rechnen": _rechnen, "pruefen": _pruefen, "export": _export, "import": _import, "kinder": _kinder,
         "uebertritt": _uebertritt, "raeume": _liste, "lehrpersonen": _liste, "vorlage": _vorlage, "profile": _profile, "app": _app}[args.befehl](args)
    except (ValueError, KeyError, FileNotFoundError) as fehler:
        sys.exit(f"Fehler: {fehler}")


def _rechnen(args) -> None:
    vorhanden = szenarien(args.schule)
    gewuenscht = vorhanden if "alle" in args.szenario else (args.szenario or ["Basis"])
    for s in gewuenscht:
        if s not in vorhanden:
            raise ValueError(f"unbekanntes Szenario '{s}'. Vorhanden: {', '.join(vorhanden)}")

    kinder = lade_kinder(args.kinder, dict(args.spalte))
    ausgabe = Path(args.ausgabe)
    ausgabe.mkdir(parents=True, exist_ok=True)
    if args.geocodieren:
        for f in geocodiere(kinder, ausgabe / "geocache.json"):
            print(f"  Adresse nicht gefunden: {f}")

    mehrere = len(gewuenscht) > 1
    ergebnisse = {}
    for name in gewuenscht:
        schule = lade_schule(args.schule, name, dict(args.gewicht))
        print(f"== Szenario {name}: {len(kinder)} Lernende, {len(schule.schulhaeuser)} Schulhäuser, "
              f"{len(schule.lehrpersonen)} Lehrpersonen, {len(schule.slots)} Zeitfenster/Woche")
        r = rechne(schule, kinder, zeitlimit=args.zeit, nur_klassen=args.nur_klassen)
        ordner = ausgabe / ordnername(name) if mehrere else ausgabe
        schreibe_csv(ordner, r)
        schreibe_html(ordner / "bericht.html", r, "../vergleich.html" if mehrere else "")
        listen = exportiere_listen(r, ordner, args.mit_foerderdaten)
        if args.mit_foerderdaten:
            q = ((schule.profil.get("regeln") or {}).get("datenschutz") or {}).get("quelle", "")
            print(f"  Achtung: Listen enthalten Förderdaten (besonders schützenswert{', ' + q if q else ''}) – "
                  "nur an Berechtigte weitergeben")
        _melde(r.meldungen, 10)
        print(f"  {r.anzahl('Fehler')} Fehler, {r.anzahl('Warnung')} Warnungen, {r.anzahl('Hinweis')} Hinweise"
              f" → {ordner / 'bericht.html'}"
              + (f" + {', '.join(d.name for d in listen)}" if listen else "") + f" ({r.sekunden:.0f}s)")
        ergebnisse[name] = r
    if mehrere:
        schreibe_vergleich(ausgabe / "vergleich.html", ergebnisse)
        print(f"Vergleich: {ausgabe / 'vergleich.html'}")
    if any(r.anzahl("Fehler") for r in ergebnisse.values()):
        sys.exit(1)


def _pruefen(args) -> None:
    schule = lade_schule(args.schule, args.szenario)
    kinder = lade_kinder(args.kinder, dict(args.spalte))
    meldungen = vorpruefung(schule, kinder)
    n = _melde(meldungen, 50)
    print(f"{len(kinder)} Lernende geprüft: {n} Fehler, {sum(m.schwere == 'Warnung' for m in meldungen)} Warnungen, "
          f"{sum(m.schwere == 'Hinweis' for m in meldungen)} Hinweise")
    if n:
        sys.exit(1)


def _export(args) -> None:
    cfg = lese_rohkonfiguration(args.schule)
    kinder = lade_kinder(args.kinder, dict(args.spalte))
    exportiere_stammdaten(cfg, kinder, args.ziel)
    print(f"Stammdaten exportiert: {args.ziel} ({len(kinder)} Lernende)")


def _import(args) -> None:
    cfg, kinder = importiere_stammdaten(args.quelle)
    ordner = Path(args.ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    schreibe_rohkonfiguration(cfg, ordner / "schule.yaml")
    schreibe_kinder(kinder, ordner / "kinder.csv")
    if cfg.get("basis_profil"):
        from .daten import _mische
        cfg = _mische(lade_profil(cfg["basis_profil"]), cfg)
    cfg.pop("szenarien", None)
    n = _melde(referenzen(baue_schule(cfg), kinder), 50)
    print(f"Importiert nach {ordner}/: schule.yaml, kinder.csv ({len(kinder)} Lernende), {n} Fehler in den Referenzen")
    if n:
        sys.exit(1)


def _kinder(args) -> None:
    kinder = lade_kinder(args.quelle, dict(args.spalte))
    schreibe_kinder(kinder, args.ziel)
    ohne = sum(k.lat is None for k in kinder)
    print(f"{len(kinder)} Lernende → {args.ziel}" + (f" ({ohne} ohne Koordinaten: --geocodieren verwenden)" if ohne
                                                     else ""))


def lese_zuteilung(pfad: str | Path) -> tuple[dict[str, str], dict[str, str]]:
    """Aktuelle Klasse/Schulhaus je Kind aus einteilung.csv (Ausgabe) oder zuteilung.json (Verlauf)."""
    import csv
    import json
    pfad = Path(pfad)
    if pfad.suffix.lower() == ".json":
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        return {k: v["klasse"] for k, v in daten.items()}, {k: v["schulhaus"] for k, v in daten.items()}
    with open(pfad, encoding="utf-8-sig", newline="") as f:
        zeilen = list(csv.DictReader(f))
    return {z["id"]: z["klasse"] for z in zeilen}, {z["id"]: z["schulhaus"] for z in zeilen}


def lese_entscheide(pfad: str | Path) -> dict[str, str]:
    """ID → Entscheid aus einer Liste mit tolerant erkannten Spalten (ID, Entscheid/Übertritt/Niveau …)."""
    from .austausch import ALIASE, _norm, _zeilen
    zeilen = _zeilen(pfad)
    if not zeilen:
        return {}
    kopf = {_norm(k): k for k in zeilen[0]}
    sid = next((kopf[a] for a in ALIASE["id"] if a in kopf), None)
    sent = next((kopf[a] for a in ALIASE["uebertritt"] if a in kopf), None)
    if not sid or not sent:
        raise ValueError(f"{pfad}: Spalten für ID und Entscheid nicht gefunden (vorhanden: {', '.join(zeilen[0])})")
    return {str(z[sid]).strip(): str(z[sent] or "").strip() for z in zeilen if str(z.get(sid) or "").strip()}


def _uebertritt(args) -> None:
    import csv

    from .uebertritt import schuljahreswechsel, zusammenfassung
    schule = lade_schule(args.schule)
    kinder = lade_kinder(args.kinder, dict(args.spalte))
    if args.entscheide:
        entscheide = lese_entscheide(args.entscheide)
        unbekannt = sorted(set(entscheide) - {k.id for k in kinder})
        if unbekannt:
            print(f"  Achtung: Entscheide für unbekannte IDs übergangen: {', '.join(unbekannt[:5])}")
        for k in kinder:
            k.uebertritt = entscheide.get(k.id, k.uebertritt)
    klasse_von, schulhaus_von = lese_zuteilung(args.zuteilung) if args.zuteilung else ({}, {})
    neu = lade_kinder(args.neu) if args.neu else []
    kinder_neu, protokoll = schuljahreswechsel(schule, kinder, klasse_von, schulhaus_von, neu)
    schreibe_kinder(kinder_neu, args.ziel)
    ziel = Path(args.ziel)
    prot = ziel.with_name(ziel.stem + "_uebertritte.csv")
    with open(prot, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["id", "name", "von", "nach", "art", "klasse_bisher", "hinweis"])
        wr.writerows([s.kind, s.name, s.von, s.nach, s.art, s.klasse_bisher, s.hinweis] for s in protokoll)
    for art, n in zusammenfassung(protokoll):
        print(f"  {n:4}  {art}")
    offen = [s for s in protokoll if s.art == "Entscheid fehlt"]
    print(f"{len(kinder)} → {len(kinder_neu)} Lernende → {ziel}  (Protokoll: {prot.name})")
    if offen:
        print(f"Achtung: {len(offen)} Entscheide fehlen (bleiben im bisherigen Jahrgang): "
              + ", ".join(f"{s.kind} ({s.hinweis})" for s in offen[:5]))
        sys.exit(1)


def _liste(args) -> None:
    art = {"raeume": "Raeume", "lehrpersonen": "Lehrpersonen"}[args.befehl]
    quelle = Path(args.schule)
    cfg = lese_rohkonfiguration(quelle)
    zeilen = lese_liste(args.liste, art, dict(args.spalte), raumtypen(cfg))
    neu, hinweise = uebernehme_liste(cfg, art, zeilen, ersetzen=not args.ergaenzen)
    ziel = Path(args.ziel) if args.ziel else quelle
    if ziel == quelle:
        quelle.with_suffix(quelle.suffix + ".bak").write_bytes(quelle.read_bytes())
    schreibe_rohkonfiguration(neu, ziel)
    for h in hinweise:
        print(f"  {h}")
    print(f"→ {ziel}" + (f" (Sicherung: {quelle.name}.bak)" if ziel == quelle else ""))


def _vorlage(args) -> None:
    for d in schreibe_vorlage(args.ordner):
        print(f"  {d}")


def _profile(args) -> None:
    for name in profile():
        p = lade_profil(name)["profil"]
        print(f"{name:12} {p['name']} (Profilversion {p.get('version', '–')})")


def _app(args) -> None:
    import threading
    import webbrowser

    from streamlit.web import cli as streamlit_cli
    app = Path(__file__).parent / "app.py"
    url = f"http://localhost:{args.port}"
    print(f"Bedienoberfläche startet: {url}  (beenden mit Ctrl+C bzw. Fenster schliessen)")
    if not args.ohne_browser:  # Browser selbst öffnen (headless vermeidet Rückfragen beim ersten Start)
        threading.Timer(3.0, webbrowser.open, args=(url,)).start()
    sys.argv = ["streamlit", "run", str(app), "--server.port", str(args.port), "--server.address", "localhost",
                "--server.headless", "true", "--browser.gatherUsageStats", "false", "--client.toolbarMode", "minimal",
                # Design-System wie genealogy-store: helle Fläche, weisse Karten, Akzent Wandtafelgrün
                "--theme.base", "light", "--theme.primaryColor", "#2f5d50", "--theme.backgroundColor", "#f6f7fb",
                "--theme.secondaryBackgroundColor", "#eef0f5", "--theme.textColor", "#14171f"]
    sys.exit(streamlit_cli.main())

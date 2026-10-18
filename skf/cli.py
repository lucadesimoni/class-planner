"""Kommandozeile.

    skf rechnen  schule.yaml kinder.csv -o ausgabe/      Klassen + Stundenplan + Berichte + Listen
    skf pruefen  schule.yaml kinder.csv                  nur Vorprüfung (Daten, Referenzen, Kapazität)
    skf export   schule.yaml kinder.csv -o daten.xlsx    Stammdaten exportieren (.xlsx oder .json)
    skf import   daten.xlsx -o ordner/                   Stammdaten importieren → schule.yaml + kinder.csv
    skf kinder   export_schulverwaltung.csv -o kinder.csv  Kinderliste normalisieren/umwandeln
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
from .austausch import (exportiere_stammdaten, importiere_stammdaten, lese_rohkonfiguration, schreibe_kinder,
                        schreibe_rohkonfiguration, schreibe_vorlage)
from .bericht import ordnername, schreibe_csv, schreibe_html, schreibe_vergleich
from .daten import STANDARD_GEWICHTE, baue_schule, lade_kinder, lade_profil, lade_schule, profile, szenarien
from .export import exportiere_listen
from .geo import geocodiere
from .pruefung import referenzen, vorpruefung

BEFEHLE = ("rechnen", "pruefen", "export", "import", "kinder", "vorlage", "profile", "app")


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
        print(f"  {'⛔' if m.schwere == 'Fehler' else '⚠'} {m.bereich}: {m.text}")
    return len(fehler)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skf", description="Klassenbildung und Stundenplan für die Volksschule")
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

    vo = sub.add_parser("vorlage", help="Vorlagen zum Erfassen eigener Daten erzeugen")
    vo.add_argument("-o", "--ordner", required=True)

    sub.add_parser("profile", help="verfügbare Kantonsprofile anzeigen")
    ap = sub.add_parser("app", help="Bedienoberfläche im Browser starten")
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--ohne-browser", action="store_true", help="Browser nicht automatisch öffnen")
    return p


def main(argv: list[str] | None = None) -> None:
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
         "vorlage": _vorlage, "profile": _profile, "app": _app}[args.befehl](args)
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
            print(f"  ⚠ Listen enthalten Förderdaten (besonders schützenswert{', ' + q if q else ''}) – "
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


def _vorlage(args) -> None:
    for d in schreibe_vorlage(args.ordner):
        print(f"  {d}")


def _profile(args) -> None:
    for name in profile():
        print(f"{name:12} {lade_profil(name)['profil']['name']}")


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
                "--server.headless", "true", "--browser.gatherUsageStats", "false", "--theme.base", "light",
                "--client.toolbarMode", "minimal"]
    sys.exit(streamlit_cli.main())

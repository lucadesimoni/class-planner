"""Kommandozeile: python -m skf schule.yaml kinder.csv -o ausgabe/"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .ablauf import rechne
from .bericht import ordnername, schreibe_csv, schreibe_html, schreibe_vergleich
from .daten import STANDARD_GEWICHTE, lade_kinder, lade_schule, szenarien
from .geo import geocodiere


def _gewicht(text: str) -> tuple[str, int]:
    name, _, wert = text.partition("=")
    if name not in STANDARD_GEWICHTE or not wert.lstrip("-").isdigit():
        raise argparse.ArgumentTypeError(f"erwartet NAME=ZAHL mit NAME aus: {', '.join(STANDARD_GEWICHTE)}")
    return name, int(wert)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="skf", description="Klasseneinteilung und Stundenplan berechnen")
    p.add_argument("schule", nargs="?", help="Schul-Konfiguration (YAML)")
    p.add_argument("kinder", nargs="?", help="Kinderliste (CSV)")
    p.add_argument("-o", "--ausgabe", default="ausgabe", help="Ausgabeordner (Standard: ausgabe)")
    p.add_argument("-t", "--zeit", type=float, default=120, help="Zeitlimit pro Szenario in Sekunden (Standard: 120)")
    p.add_argument("-s", "--szenario", action="append", default=[],
                   help="Szenario aus der YAML rechnen (mehrfach möglich; 'alle' = alle Szenarien)")
    p.add_argument("-g", "--gewicht", action="append", type=_gewicht, default=[], metavar="NAME=ZAHL",
                   help="Gewicht überschreiben, z.B. -g schulweg_pro_km=300 (mehrfach möglich)")
    p.add_argument("--nur-klassen", action="store_true", help="nur Klasseneinteilung, kein Stundenplan")
    p.add_argument("--geocodieren", action="store_true",
                   help="fehlende Koordinaten über geo.admin.ch aus der Adresse ermitteln")
    p.add_argument("--gewichte-anzeigen", action="store_true", help="alle Gewichte mit Standardwert auflisten")
    args = p.parse_args(argv)

    if args.gewichte_anzeigen:
        for k, v in STANDARD_GEWICHTE.items():
            print(f"{k:34} {v}")
        return
    if not args.schule or not args.kinder:
        p.error("schule.yaml und kinder.csv angeben")

    vorhanden = szenarien(args.schule)
    gewuenscht = vorhanden if "alle" in args.szenario else (args.szenario or ["Basis"])
    for s in gewuenscht:
        if s not in vorhanden:
            sys.exit(f"Fehler: unbekanntes Szenario '{s}'. Vorhanden: {', '.join(vorhanden)}")

    kinder = lade_kinder(args.kinder)
    ausgabe = Path(args.ausgabe)
    ausgabe.mkdir(parents=True, exist_ok=True)
    if args.geocodieren:
        for f in geocodiere(kinder, ausgabe / "geocache.json"):
            print(f"  Adresse nicht gefunden: {f}")

    mehrere = len(gewuenscht) > 1
    ergebnisse = {}
    for name in gewuenscht:
        try:
            schule = lade_schule(args.schule, name, dict(args.gewicht))
        except ValueError as fehler:
            sys.exit(f"Fehler: {fehler}")
        print(f"== Szenario {name}: {len(kinder)} Kinder, {len(schule.schulhaeuser)} Schulhäuser, "
              f"{len(schule.lehrpersonen)} Lehrpersonen, {len(schule.slots)} Zeitfenster/Woche")
        r = rechne(schule, kinder, zeitlimit=args.zeit, nur_klassen=args.nur_klassen)
        ordner = ausgabe / ordnername(name) if mehrere else ausgabe
        schreibe_csv(ordner, r)
        schreibe_html(ordner / "bericht.html", r, "../vergleich.html" if mehrere else "")
        for m in [m for m in r.meldungen if m.schwere == "Fehler"][:10]:
            print(f"  ⛔ {m.text}")
        print(f"  {r.anzahl('Fehler')} Fehler, {r.anzahl('Warnung')} Warnungen, {r.anzahl('Hinweis')} Hinweise"
              f" → {ordner / 'bericht.html'} ({r.sekunden:.0f}s)")
        ergebnisse[name] = r
    if mehrere:
        schreibe_vergleich(ausgabe / "vergleich.html", ergebnisse)
        print(f"Vergleich: {ausgabe / 'vergleich.html'}")
    if any(r.anzahl("Fehler") for r in ergebnisse.values()):
        sys.exit(1)

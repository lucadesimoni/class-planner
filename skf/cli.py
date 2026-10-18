"""Kommandozeile: python -m skf schule.yaml kinder.csv -o ausgabe/"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .bericht import schreibe_csv, schreibe_html
from .daten import lade_kinder, lade_schule
from .geo import geocodiere
from .klassen import teile_ein
from .lehrauftrag import verteile_lehrauftraege
from .pruefung import pruefe
from .solver import KeineLoesung
from .stundenplan import erstelle_stundenplan


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="skf", description="Klasseneinteilung und Stundenplan berechnen")
    p.add_argument("schule", help="Schul-Konfiguration (YAML)")
    p.add_argument("kinder", help="Kinderliste (CSV)")
    p.add_argument("-o", "--ausgabe", default="ausgabe", help="Ausgabeordner (Standard: ausgabe)")
    p.add_argument("-t", "--zeit", type=float, default=120, help="Zeitlimit in Sekunden (Standard: 120)")
    p.add_argument("--nur-klassen", action="store_true", help="nur Klasseneinteilung, kein Stundenplan")
    p.add_argument("--geocodieren", action="store_true",
                   help="fehlende Koordinaten über geo.admin.ch aus der Adresse ermitteln")
    args = p.parse_args(argv)

    start = time.time()
    schule = lade_schule(args.schule)
    kinder = lade_kinder(args.kinder)
    ausgabe = Path(args.ausgabe)
    ausgabe.mkdir(parents=True, exist_ok=True)
    if args.geocodieren:
        for f in geocodiere(kinder, ausgabe / "geocache.json"):
            print(f"  Adresse nicht gefunden: {f}")

    try:
        print(f"{len(kinder)} Kinder, {len(schule.schulhaeuser)} Schulhäuser, "
              f"{len(schule.lehrpersonen)} Lehrpersonen, {len(schule.slots)} Zeitfenster/Woche")
        e = teile_ein(schule, kinder, zeitlimit=args.zeit * 0.25)
        for i in e.infos:
            print(f"  {i}")
        bloecke, lektionen, infos, warnungen = [], [], list(e.infos), list(e.warnungen)
        if not args.nur_klassen:
            bloecke, info_l = verteile_lehrauftraege(schule, e.klassen, zeitlimit=args.zeit * 0.15)
            print(f"  {info_l}")
            lektionen, infos_s, warn_s = erstelle_stundenplan(schule, e.klassen, bloecke, zeitlimit=args.zeit * 0.6)
            for i in infos_s:
                print(f"  {i}")
            infos += [info_l] + infos_s
            warnungen += warn_s
    except KeineLoesung as fehler:
        sys.exit(f"Fehler: {fehler}")

    verstoesse = pruefe(schule, kinder, e, *((bloecke, lektionen) if not args.nur_klassen else ()))
    print(f"Prüfung: {'alle harten Regeln erfüllt' if not verstoesse else f'{len(verstoesse)} Verstösse'}")
    for v in verstoesse:
        print(f"  ✗ {v}")
    warnungen += verstoesse
    for w in warnungen[:8]:
        print(f"  Warnung: {w}")
    if len(warnungen) > 8:
        print(f"  … und {len(warnungen) - 8} weitere Warnungen (siehe bericht.html)")
    schreibe_csv(ausgabe, schule, kinder, e, bloecke, lektionen)
    schreibe_html(ausgabe / "bericht.html", schule, kinder, e, bloecke, lektionen, infos, warnungen)
    print(f"{len(e.klassen)} Klassen gebildet, Ergebnisse in {ausgabe}/ ({time.time() - start:.0f}s)")

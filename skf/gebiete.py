# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Geografische Hypothesen: Gebiete auf der Karte (Polygon, WGS84) mit einer Annahme.

    szenarien:
      "Blatten nach Eischachen":
        ziel: Planung
        hypothese: Was wäre, wenn das Gebiet Blatten zum Schulhaus Eischachen gehört?
        gebiete:
          - name: Blatten
            flaeche: [[47.05, 8.16], [47.06, 8.18], [47.04, 8.19]]   # [lat, lon], mindestens 3 Punkte
            schulhaus: Eischachen        # alle Lernenden darin gehen dorthin (sofern es ihre Stufe führt)
          - name: Neubaugebiet Nord
            flaeche: [...]
            neue_lernende: 30            # zusätzliche (angenommene) Lernende, verteilt wie die heutigen Jahrgänge

Die Gebiete verändern nur die Eingaben (Lernende), nie die Optimierung: dieselben Regeln
und Gewichte entscheiden über Klassen und Stundenpläne.
"""
from __future__ import annotations

import random
import zlib
from collections import Counter
from dataclasses import dataclass, replace

from .daten import Kind, Schule

PRAEFIX = "H-"  # IDs angenommener Lernender


@dataclass
class Gebiet:
    name: str
    flaeche: list[tuple[float, float]]
    schulhaus: str = ""
    neue_lernende: int = 0


def lese_gebiete(roh) -> list[Gebiet]:
    """Gebiete aus der Konfiguration prüfen (Punkte, Zahlen) – Fehler mit klarer Meldung."""
    gebiete = []
    for i, g in enumerate(roh or []):
        if not isinstance(g, dict):
            raise ValueError(f"gebiete[{i + 1}]: Angaben als 'name, flaeche, schulhaus/neue_lernende' erwarten")
        name = str(g.get("name") or f"Gebiet {i + 1}")
        try:
            punkte = [(float(p[0]), float(p[1])) for p in g.get("flaeche") or []]
        except (TypeError, ValueError, IndexError):
            raise ValueError(f"Gebiet '{name}': flaeche als Liste von [lat, lon] erwarten") from None
        if len(punkte) < 3:
            raise ValueError(f"Gebiet '{name}': mindestens 3 Punkte für die Fläche nötig")
        if any(not (-90 <= a <= 90 and -180 <= b <= 180) for a, b in punkte):
            raise ValueError(f"Gebiet '{name}': Punkte ausserhalb gültiger Koordinaten (lat, lon)")
        try:
            neu = int(g.get("neue_lernende") or 0)
        except (TypeError, ValueError):
            raise ValueError(f"Gebiet '{name}': neue_lernende als ganze Zahl erwarten") from None
        if not 0 <= neu <= 5000:
            raise ValueError(f"Gebiet '{name}': neue_lernende zwischen 0 und 5000")
        if not g.get("schulhaus") and not neu:
            raise ValueError(f"Gebiet '{name}': 'schulhaus' oder 'neue_lernende' angeben")
        gebiete.append(Gebiet(name, punkte, str(g.get("schulhaus") or ""), neu))
    return gebiete


def enthaelt(flaeche: list[tuple[float, float]], lat: float, lon: float) -> bool:
    """Punkt im Polygon (Strahlverfahren; für Gemeindegrössen genau genug)."""
    drin = False
    for (a1, b1), (a2, b2) in zip(flaeche, flaeche[1:] + flaeche[:1]):
        if (b1 > lon) != (b2 > lon) and lat < a1 + (lon - b1) * (a2 - a1) / (b2 - b1):
            drin = not drin
    return drin


def lernende_im_gebiet(gebiet: Gebiet, kinder: list[Kind]) -> list[Kind]:
    return [k for k in kinder if k.lat is not None and k.lon is not None and enthaelt(gebiet.flaeche, k.lat, k.lon)]


def _punkte(gebiet: Gebiet, n: int) -> list[tuple[float, float]]:
    """n Wohnorte im Gebiet – reproduzierbar (gleicher Name = gleiche Punkte)."""
    zufall = random.Random(zlib.crc32(gebiet.name.encode("utf-8")))
    lats, lons = [p[0] for p in gebiet.flaeche], [p[1] for p in gebiet.flaeche]
    punkte = []
    for _ in range(n * 200):
        if len(punkte) == n:
            break
        lat, lon = zufall.uniform(min(lats), max(lats)), zufall.uniform(min(lons), max(lons))
        if enthaelt(gebiet.flaeche, lat, lon):
            punkte.append((round(lat, 6), round(lon, 6)))
    while len(punkte) < n:  # sehr schmale Fläche: Schwerpunkt
        punkte.append((sum(lats) / len(lats), sum(lons) / len(lons)))
    return punkte


def _verteilung(schule: Schule, kinder: list[Kind], n: int) -> list[str]:
    """n Jahrgänge im Verhältnis der heutigen Lernenden (grösster Rest), sonst gleichmässig."""
    anzahl = Counter(k.jahrgang for k in kinder if k.jahrgang in schule.jahrgaenge)
    gesamt = sum(anzahl.values())
    anteile = {j: (anzahl[j] / gesamt if gesamt else 1 / len(schule.jahrgaenge)) * n for j in schule.jahrgaenge}
    ganz = {j: int(a) for j, a in anteile.items()}
    for j in sorted(anteile, key=lambda j: anteile[j] - ganz[j], reverse=True)[:n - sum(ganz.values())]:
        ganz[j] += 1
    return [j for j in schule.jahrgaenge for _ in range(ganz[j])]


def wende_an(schule: Schule, kinder: list[Kind]) -> tuple[list[Kind], list[str]]:
    """Gebiete des Szenarios auf die Lernenden anwenden → (Lernende, Hinweise für die Meldungen)."""
    from .klassen import moegliche_schulhaeuser

    gebiete = getattr(schule, "gebiete", None) or []
    if not gebiete:
        return kinder, []
    kinder = list(kinder)
    hinweise = []
    for g in gebiete:
        if g.neue_lernende:
            neu = []
            for i, (jg, (lat, lon)) in enumerate(zip(_verteilung(schule, kinder, g.neue_lernende),
                                                     _punkte(g, g.neue_lernende))):
                kid = f"{PRAEFIX}{zlib.crc32(g.name.encode('utf-8')) % 10000:04d}-{i + 1:03d}"
                neu.append(Kind(kid, f"Annahme {i + 1} ({g.name})", jg, "wm"[i % 2], g.name, lat, lon,
                                bemerkung=f"Hypothese: angenommene Lernende im Gebiet {g.name}"))
            kinder += neu
            hinweise.append(f"Gebiet {g.name}: {len(neu)} angenommene Lernende ergänzt (IDs {PRAEFIX}…)")
        if g.schulhaus:
            im_gebiet = {k.id for k in lernende_im_gebiet(g, kinder)}
            passend = nicht = 0
            for i, k in enumerate(kinder):
                if k.id in im_gebiet:
                    if g.schulhaus in moegliche_schulhaeuser(schule, k):
                        kinder[i] = replace(k, schulhaus_fix=g.schulhaus)
                        passend += 1
                    else:
                        nicht += 1
            hinweise.append(f"Gebiet {g.name}: {passend} Lernende fest dem Schulhaus {g.schulhaus} zugeteilt"
                            + (f", {nicht} ohne passende Stufe dort bleiben frei" if nicht else ""))
    return kinder, hinweise

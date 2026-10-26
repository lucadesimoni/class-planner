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

Bereiche gelten auch dauerhaft (``gebiete`` auf oberster Ebene der Konfiguration), z.B.:

    gebiete:
      - name: Dorfzone
        flaeche: [...]
        schulbus: false                  # kein Schulbus (zu Fuss); oder Name einer Linie
      - name: Feld
        flaeche: [...]
        aufteilung: {Bündtmättli: 60, Eischachen: 40}   # gewünschte Aufteilung in %
        verbindlich: false               # false = Wunsch-Schulhaus (gewichtet), true = feste Zuteilung

Die Aufteilung hält Geschwister zusammen und teilt zuerst nach Nähe zu: wer deutlich näher an
einem Schulhaus wohnt, kommt eher dorthin. Die Gebiete verändern nur die Eingaben (Lernende),
nie die Optimierung: dieselben Regeln und Gewichte entscheiden über Klassen und Stundenpläne.
"""
from __future__ import annotations

import math
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
    schulbus: str | None = None                       # None = wie bisher, "" = kein Schulbus, sonst Linie
    aufteilung: dict[str, float] | None = None        # Schulhaus → Anteil in %
    verbindlich: bool = False                         # Aufteilung als feste Zuteilung statt Wunsch


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
        bus = g.get("schulbus")
        bus = None if bus is None else ("" if bus is False or str(bus).strip().lower() in ("", "nein", "kein", "false")
                                        else str(bus).strip())
        aufteilung = None
        if g.get("aufteilung") is not None:
            if not isinstance(g["aufteilung"], dict) or not g["aufteilung"]:
                raise ValueError(f"Gebiet '{name}': aufteilung als 'Schulhaus: Prozent' erwarten")
            try:
                aufteilung = {str(k): float(v) for k, v in g["aufteilung"].items()}
            except (TypeError, ValueError):
                raise ValueError(f"Gebiet '{name}': Anteile der Aufteilung als Zahlen erwarten") from None
            if any(v < 0 for v in aufteilung.values()) or sum(aufteilung.values()) <= 0:
                raise ValueError(f"Gebiet '{name}': Anteile der Aufteilung ≥ 0 und zusammen > 0")
            aufteilung = {k: v for k, v in aufteilung.items() if v > 0}
        if g.get("schulhaus"):  # Kurzform: alle in ein Schulhaus, fest
            aufteilung, verbindlich = {str(g["schulhaus"]): 100.0}, True
        else:
            verbindlich = bool(g.get("verbindlich", False))
        if not aufteilung and not neu and bus is None:
            raise ValueError(f"Gebiet '{name}': 'aufteilung', 'schulhaus', 'schulbus' oder 'neue_lernende' angeben")
        gebiete.append(Gebiet(name, punkte, str(g.get("schulhaus") or ""), neu, bus, aufteilung, verbindlich))
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
        if g.schulbus is not None:
            im_gebiet = {k.id for k in lernende_im_gebiet(g, kinder)}
            for i, k in enumerate(kinder):
                if k.id in im_gebiet:
                    kinder[i] = replace(k, bus=g.schulbus)
            hinweise.append(f"Gebiet {g.name}: {len(im_gebiet)} Lernende "
                            + (f"mit Schulbus {g.schulbus}" if g.schulbus else "ohne Schulbus (zu Fuss)"))
        if g.aufteilung:
            kinder, text = _teile_auf(schule, g, kinder)
            hinweise.append(text)
    return kinder, hinweise


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    x = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    return 6371 * math.hypot(x, math.radians(b[0] - a[0]))


def _teile_auf(schule: Schule, g: Gebiet, kinder: list[Kind]) -> tuple[list[Kind], str]:
    """Lernende im Gebiet nach der gewünschten Aufteilung auf Schulhäuser verteilen.

    Familien bleiben zusammen. Wer den grössten Vorteil hat (Weg zum nächsten statt zweitnächsten
    möglichen Schulhaus), wählt zuerst; ein Schulhaus nimmt nur bis zu seinem Anteil auf."""
    from .klassen import moegliche_schulhaeuser

    orte = {s.name: (s.lat, s.lon) for s in schule.schulhaeuser}
    anteile = {sh: a for sh, a in g.aufteilung.items() if sh in orte}
    im_gebiet = lernende_im_gebiet(g, kinder)
    if not anteile or not im_gebiet:
        return kinder, f"Gebiet {g.name}: keine Lernenden aufzuteilen"
    familien: dict[str, list[Kind]] = {}
    for k in im_gebiet:
        familien.setdefault(k.familie or k.id, []).append(k)
    summe = sum(anteile.values())
    ziel = {sh: a / summe * len(im_gebiet) for sh, a in anteile.items()}
    belegt = dict.fromkeys(anteile, 0)

    def optionen(fam: list[Kind]) -> list[tuple[float, str]]:
        moeglich = set(anteile)
        for k in fam:
            moeglich &= set(moegliche_schulhaeuser(schule, k))
        ort = (fam[0].lat, fam[0].lon)
        return sorted((_km(ort, orte[sh]), sh) for sh in moeglich)

    def vorteil(fam):
        o = optionen(fam)
        return (o[1][0] - o[0][0]) if len(o) > 1 else (math.inf if o else -math.inf)

    zuteilung: dict[str, str] = {}
    for fam in sorted(familien.values(), key=lambda f: (-vorteil(f), f[0].id)):
        o = optionen(fam)
        frei = [sh for _, sh in o if belegt[sh] + len(fam) <= ziel[sh] + 0.5]
        wahl = frei[0] if frei else (min(o, key=lambda t: belegt[t[1]] / ziel[t[1]])[1] if o else None)
        if wahl:
            belegt[wahl] += len(fam)
            zuteilung.update({k.id: wahl for k in fam})
    feld = "schulhaus_fix" if g.verbindlich else "wunsch_schulhaus"
    kinder = [replace(k, **{feld: zuteilung[k.id]}) if k.id in zuteilung else k for k in kinder]
    ergebnis = ", ".join(f"{sh} {belegt[sh]} ({100 * belegt[sh] / len(im_gebiet):.0f} %)" for sh in anteile)
    return kinder, (f"Gebiet {g.name}: Aufteilung {'verbindlich' if g.verbindlich else 'als Wunsch'} – {ergebnis}"
                    + (f"; {len(im_gebiet) - len(zuteilung)} ohne passendes Schulhaus" if len(zuteilung) < len(im_gebiet)
                       else ""))

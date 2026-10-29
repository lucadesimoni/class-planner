# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Distanzen und (optional) Geocodierung von Adressen über geo.admin.ch."""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

from .daten import Kind

GEOADMIN_URL = "https://api3.geo.admin.ch/rest/services/api/SearchServer"


def luftlinie_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _suche(adresse: str, cache: dict[str, list[float]]) -> list[float] | None:
    """Koordinaten einer Adresse (geo.admin.ch), mit Zwischenspeicher."""
    if adresse not in cache:
        query = urllib.parse.urlencode({"searchText": adresse, "type": "locations", "limit": 1})
        with urllib.request.urlopen(f"{GEOADMIN_URL}?{query}", timeout=15) as resp:
            treffer = json.load(resp).get("results", [])
        if not treffer:
            return None
        attrs = treffer[0]["attrs"]
        cache[adresse] = [attrs["lat"], attrs["lon"]]
    return cache[adresse]


def geocodiere(kinder: list[Kind], cache_pfad: str | Path) -> list[str]:
    """Ergänzt fehlende Koordinaten über die Suche von geo.admin.ch.

    Ergebnisse werden in einer JSON-Datei zwischengespeichert, damit jede Adresse
    nur einmal abgefragt wird. Gibt die Adressen zurück, die nicht gefunden wurden.
    """
    cache_pfad = Path(cache_pfad)
    cache: dict[str, list[float]] = json.loads(cache_pfad.read_text()) if cache_pfad.exists() else {}
    fehlend = []
    for k in kinder:
        if k.lat is not None and k.lon is not None:
            continue
        if not k.adresse:
            fehlend.append(f"{k.id}: keine Adresse")
            continue
        punkt = _suche(k.adresse, cache)
        if punkt is None:
            fehlend.append(f"{k.id}: {k.adresse}")
            continue
        k.lat, k.lon = punkt
    cache_pfad.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    return fehlend


def pruefe_schulhaeuser(schule, cache_pfad: str | Path, toleranz_m: float = 150) -> list[str]:
    """Vergleicht die Koordinaten der Schulhäuser mit ihrer Adresse (geo.admin.ch).

    Ändert nichts – meldet Abweichungen über ``toleranz_m`` mit den Werten aus der Adresse,
    zum Übernehmen in die Konfiguration. Postadressen "c/o …" werden übersprungen."""
    cache_pfad = Path(cache_pfad)
    cache: dict[str, list[float]] = json.loads(cache_pfad.read_text()) if cache_pfad.exists() else {}
    meldungen = []
    for sh in schule.schulhaeuser:
        if not sh.adresse or "c/o" in sh.adresse:
            continue
        punkt = _suche(sh.adresse, cache)
        if punkt is None:
            meldungen.append(f"{sh.name}: Adresse nicht gefunden ({sh.adresse})")
        elif (d := luftlinie_m(sh.lat, sh.lon, *punkt)) > toleranz_m:
            meldungen.append(f"{sh.name}: Koordinaten {d:.0f} m neben der Adresse – lat: {punkt[0]:.5f}, "
                             f"lon: {punkt[1]:.5f} übernehmen")
    cache_pfad.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    return meldungen

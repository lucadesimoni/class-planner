# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Verlauf: jede Berechnung wird mit Eingabedaten und Ergebnis gespeichert.

Ordner pro Stand: <basis>/<JJJJ-MM-TT_HHMMSS>_<szenario>/
    meta.json        Zeitpunkt, Szenario, Kennzahlen, Notiz, manuelle Anpassungen
    zuteilung.json   Lernende → Schulhaus/Klasse
    stammdaten.xlsx  Eingabedaten (Schule + Lernende) zum Wiederherstellen, dazu stammdaten.json
    ergebnis.json    vollständiges Ergebnis, maschinenlesbar (Schema skf-ergebnis)
    LIESMICH.txt     Erklärung des Ordners für Menschen
    bericht.html, klassenlisten.xlsx, stundenplaene.xlsx, druck.html, *.csv
Basis: Umgebungsvariable SKF_DATEN oder ~/Klassenbildung/verlauf.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from .ablauf import Ergebnis
from .version import __version__


def basis() -> Path:
    from .datenablage import datenordner
    return datenordner() / "verlauf"


def schreibe_stand(ziel: Path, r: Ergebnis, cfg: dict, notiz: str = "", zeit: datetime | None = None) -> None:
    """Alle Dateien eines Standes: für Menschen (HTML, Excel, LIESMICH) und Programme (JSON, CSV)."""
    from .austausch import exportiere_stammdaten
    from .bericht import schreibe_csv
    from .datenablage import schreibe_liesmich
    zeit = zeit or datetime.now()
    ziel.mkdir(parents=True, exist_ok=True)
    e = r.einteilung
    (ziel / "meta.json").write_text(json.dumps({
        "zeit": zeit.isoformat(timespec="seconds"), "szenario": r.schule.szenario, "schule": r.schule.name,
        "schuljahr": r.schule.schuljahr, "notiz": notiz, "kennzahlen": r.kennzahlen(),
        "manuell": list(getattr(r, "manuell", [])), "programmversion": __version__,
        "profilversion": (r.schule.profil or {}).get("version", ""),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    if e:
        (ziel / "zuteilung.json").write_text(json.dumps(
            {kid: {"schulhaus": e.schulhaus_von[kid], "klasse": e.klasse_von[kid]} for kid in e.klasse_von},
            ensure_ascii=False, indent=0), encoding="utf-8")
    exportiere_stammdaten(cfg, r.kinder, ziel / "stammdaten.xlsx")
    exportiere_stammdaten(cfg, r.kinder, ziel / "stammdaten.json")
    schreibe_liesmich(ziel, r)
    schreibe_csv(ziel, r)


def speichere(r: Ergebnis, cfg: dict, notiz: str = "", ordner: Path | None = None) -> Path:
    from .bericht import schreibe_html
    from .export import exportiere_listen
    jetzt = datetime.now()
    name = f"{jetzt:%Y-%m-%d_%H%M%S}_" + re.sub(r"[^\w-]+", "_", r.schule.szenario)
    ziel = (ordner or basis()) / name
    schreibe_stand(ziel, r, cfg, notiz, jetzt)
    schreibe_html(ziel / "bericht.html", r)
    exportiere_listen(r, ziel)
    return ziel


def staende(ordner: Path | None = None) -> list[dict]:
    """Gespeicherte Stände, neueste zuerst."""
    b = ordner or basis()
    if not b.exists():
        return []
    out = []
    for d in sorted(b.iterdir(), reverse=True):
        if (d / "meta.json").exists():
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            meta["ordner"] = str(d)
            meta["name"] = d.name
            out.append(meta)
    return out


def zuteilung(stand: dict) -> dict[str, dict]:
    pfad = Path(stand["ordner"]) / "zuteilung.json"
    return json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}


def vergleiche(alt: dict, neu: dict) -> dict:
    """Was hat sich zwischen zwei Ständen geändert?"""
    a, b = zuteilung(alt), zuteilung(neu)
    gewechselt = [{"id": k, "vorher": a[k]["klasse"], "nachher": b[k]["klasse"],
                   "schulhaus_gewechselt": a[k]["schulhaus"] != b[k]["schulhaus"]}
                  for k in sorted(set(a) & set(b)) if a[k]["klasse"] != b[k]["klasse"]]
    klassen_a = {v["klasse"] for v in a.values()}
    klassen_b = {v["klasse"] for v in b.values()}
    kennzahlen = {k: (alt["kennzahlen"].get(k, "–"), neu["kennzahlen"].get(k, "–"))
                  for k in neu["kennzahlen"] if alt["kennzahlen"].get(k) != neu["kennzahlen"].get(k)}
    return {"gewechselt": gewechselt, "neu": sorted(set(b) - set(a)), "weg": sorted(set(a) - set(b)),
            "klassen_neu": sorted(klassen_b - klassen_a), "klassen_weg": sorted(klassen_a - klassen_b),
            "kennzahlen": kennzahlen}


def kind_verlauf(kid: str, ordner: Path | None = None) -> list[dict]:
    """Klasse eines Kindes in allen gespeicherten Ständen (neueste zuerst)."""
    out = []
    for s in staende(ordner):
        z = zuteilung(s).get(kid)
        if z:
            out.append({"zeit": s["zeit"], "szenario": s["szenario"], **z})
    return out


def loesche(stand: dict) -> None:
    shutil.rmtree(stand["ordner"], ignore_errors=True)

# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Offene, dokumentierte Datenablage – lesbar ohne dieses Programm.

* ergebnis.json      – vollständiges Ergebnis, maschinenlesbar (Schema schema/skf-ergebnis.schema.json)
* stammdaten.json    – Eingabedaten (Schema schema/skf-stammdaten.schema.json)
* LIESMICH.txt       – Erklärung jedes Ordners für Menschen
* Arbeitsstand       – die App speichert die aktuellen Eingaben laufend unter <SKF_DATEN>/arbeitsstand/,
                       damit nichts verloren geht (stammdaten.json + schule.yaml + kinder.csv)

Alle Textdateien: UTF-8, CSV mit Komma und Kopfzeile. Beschreibung aller Dateien: docs/datenformate.md.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .version import __version__

ERGEBNIS_FORMAT, ERGEBNIS_VERSION = "skf-ergebnis", 1


def datenordner() -> Path:
    """Wurzel aller gespeicherten Daten: SKF_DATEN oder ~/Klassenbildung."""
    return Path(os.environ.get("SKF_DATEN", Path.home() / "Klassenbildung"))


def ergebnis_als_dict(r) -> dict:
    """Ergebnis einer Berechnung als einfache, stabile Struktur (siehe skf-ergebnis.schema.json)."""
    from .kosten import kosten
    from .transparenz import guete
    s, e = r.schule, r.einteilung
    nach_id = {k.id: k for k in r.kinder}
    d = {
        "format": ERGEBNIS_FORMAT, "version": ERGEBNIS_VERSION, "programm": __version__,
        "profilversion": str((s.profil or {}).get("version", "")),
        "erstellt": datetime.now().isoformat(timespec="seconds"),
        "schule": s.name, "schuljahr": s.schuljahr, "szenario": s.szenario,
        "hypothese": s.hypothese, "ziel": s.ziel,
        "vollstaendig": bool(r.vollstaendig), "kennzahlen": r.kennzahlen(), "loesungsguete": guete(r),
        "kosten": [{"posten": z["Posten"], "menge": z["Menge"], "chf": z["CHF"]} for z in kosten(r)],
        "langfristplanung": [dict(j) for j in r.planung.jahre],
        "zeitfenster": [{"index": t.index, "tag": t.tag, "halbtag": t.halbtag, "lektion": t.nr + 1, "beginn": t.zeit}
                        for t in s.slots],
        "klassen": [], "zuteilung": {}, "lehrauftraege": [], "stundenplan": [],
        "meldungen": [{"schweregrad": m.schwere, "bereich": m.bereich, "text": m.text, "bezug": m.bezug,
                       "zeitfenster": m.slot, "quelle": m.quelle} for m in r.meldungen],
    }
    if e:
        d["klassen"] = [{"name": c.name, "schulhaus": c.schulhaus, "raum": c.raum.name,
                         "klassentyp": c.vorlage.bezeichnung or "/".join(c.vorlage.jahrgaenge),
                         "jahrgaenge": list(c.jahrgaenge), "lernende": list(c.kinder),
                         "anzahl": len(c.kinder),
                         "maedchen": sum(nach_id[i].geschlecht == "w" for i in c.kinder if i in nach_id),
                         "knaben": sum(nach_id[i].geschlecht == "m" for i in c.kinder if i in nach_id)}
                        for c in e.klassen]
        d["zuteilung"] = {kid: {"schulhaus": e.schulhaus_von[kid], "klasse": e.klasse_von[kid],
                                "schulweg_m": round(e.schulweg_m.get(kid, 0))} for kid in e.klasse_von}
    d["lehrauftraege"] = [{"lehrperson": b.lehrperson, "klasse": b.klasse, "klassen": list(b.klassen),
                           "fach": b.fach, "lektionen": b.lektionen, "art": b.art} for b in r.bloecke]
    d["stundenplan"] = [{"zeitfenster": l.slot, "tag": s.slots[l.slot].tag, "beginn": s.slots[l.slot].zeit,
                         "klasse": l.klasse, "klassen": list(l.klassen), "fach": l.fach, "lehrperson": l.lehrperson,
                         "raum": l.raum, "raum_schulhaus": l.raum_ort, "schulhaus": l.schulhaus, "art": l.art}
                        for l in sorted(r.lektionen, key=lambda l: (l.slot, l.klasse))]
    return d


def schreibe_ergebnis_json(pfad: Path, r) -> None:
    Path(pfad).write_text(json.dumps(ergebnis_als_dict(r), ensure_ascii=False, indent=1), encoding="utf-8")


LIESMICH_STAND = """Klassenbildung & Stundenplan {version} – gespeicherter Stand
=============================================================
Schule: {schule}   Schuljahr: {schuljahr}   Szenario: {szenario}   Zeitpunkt: {zeit}

Alle Dateien sind offen lesbar – auch ohne dieses Programm.

Für Menschen
  bericht.html          Übersicht mit Karte, Klassen, Stundenplänen, Meldungen (im Browser öffnen)
  klassenlisten.xlsx    Klassenlisten zum Drucken (Excel/LibreOffice)
  stundenplaene.xlsx    Stundenpläne je Klasse, Lehrperson und Spezialraum
  druck.html            Druckversion (im Browser drucken oder als PDF speichern)
  stammdaten.xlsx       alle Eingabedaten, ein Blatt pro Tabelle – bearbeiten und wieder einlesen

Für Programme (UTF-8)
  ergebnis.json         vollständiges Ergebnis (Format skf-ergebnis, Schema skf-ergebnis.schema.json)
  stammdaten.json       Eingabedaten (Format skf-stammdaten, Schema skf-stammdaten.schema.json)
  meta.json             Zeitpunkt, Kennzahlen, Programm- und Profilversion dieses Standes
  zuteilung.json        Lernende → Schulhaus und Klasse
  einteilung.csv, klassen.csv, lehrauftraege.csv, stundenplan.csv, meldungen.csv
                        dieselben Daten als Tabellen (Komma-getrennt, Kopfzeile)

Wieder einlesen: in der App „Verlauf → Eingabedaten dieses Standes laden“ oder
  skf import stammdaten.json -o ordner/
Beschreibung aller Felder: docs/datenformate.md im Programmordner.

Enthält Personendaten von Lernenden (teils besonders schützenswert: IF/DaZ/IS).
Nur auf Geräten der Schule speichern und nach der kantonalen Aufbewahrungsfrist löschen.
"""

LIESMICH_ARBEITSSTAND = """Klassenbildung & Stundenplan – laufender Arbeitsstand
====================================================
Diesen Ordner schreibt die App bei jeder Änderung neu, damit keine Eingabe verloren geht.
Zuletzt gespeichert: {zeit} (Programmversion {version}).

  stammdaten.json   alle Eingaben (Format skf-stammdaten, Schema skf-stammdaten.schema.json)
  schule.yaml       Schul-Konfiguration als lesbarer Text
  kinder.csv        Lernende (UTF-8, Komma, Kopfzeile)

Fortsetzen: App starten → „Letzten Arbeitsstand fortsetzen“. Ohne App:
  skf rechnen schule.yaml kinder.csv -o ausgabe/
Enthält Personendaten von Lernenden – nur auf Geräten der Schule speichern.
"""


def schreibe_liesmich(ordner: Path, r) -> None:
    (Path(ordner) / "LIESMICH.txt").write_text(LIESMICH_STAND.format(
        version=__version__, schule=r.schule.name, schuljahr=r.schule.schuljahr or "–", szenario=r.schule.szenario,
        zeit=datetime.now().strftime("%d.%m.%Y %H:%M")), encoding="utf-8")


def arbeitsstand_ordner() -> Path:
    return datenordner() / "arbeitsstand"


def speichere_arbeitsstand(cfg: dict, kinder) -> Path:
    """Aktuelle Eingaben dauerhaft ablegen (JSON + YAML + CSV), atomar ersetzt."""
    from .austausch import exportiere_stammdaten, schreibe_kinder, schreibe_rohkonfiguration
    ziel = arbeitsstand_ordner()
    ziel.mkdir(parents=True, exist_ok=True)
    for name, schreiben in (("stammdaten.json", lambda p: exportiere_stammdaten(cfg, kinder, p)),
                            ("schule.yaml", lambda p: schreibe_rohkonfiguration(cfg, p)),
                            ("kinder.csv", lambda p: schreibe_kinder(kinder, p))):
        tmp = ziel / f".{name}.tmp{Path(name).suffix}"
        schreiben(tmp)
        os.replace(tmp, ziel / name)
    (ziel / "LIESMICH.txt").write_text(LIESMICH_ARBEITSSTAND.format(
        zeit=datetime.now().strftime("%d.%m.%Y %H:%M"), version=__version__), encoding="utf-8")
    return ziel


def arbeitsstand_info() -> dict | None:
    pfad = arbeitsstand_ordner() / "stammdaten.json"
    if not pfad.exists():
        return None
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {"pfad": pfad, "schule": daten.get("schule", {}).get("name", ""), "lernende": len(daten.get("kinder", [])),
            "zeit": datetime.fromtimestamp(pfad.stat().st_mtime).strftime("%d.%m.%Y %H:%M")}


def lade_arbeitsstand():
    from .austausch import importiere_stammdaten
    return importiere_stammdaten(arbeitsstand_ordner() / "stammdaten.json")

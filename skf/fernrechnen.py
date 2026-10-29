# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Rechnen auf dem Rechenserver – für die Browser-Version, in der OR-Tools nicht läuft.

Browser (``rechne_fern``) und Server (``bearbeite``, aufgerufen von ``api/rechnen.py``) teilen dieses
eine Austauschformat. Der Server führt genau ``skf.ablauf.rechne`` aus – dieselbe Funktion wie Desktop
und CLI, es gibt keine zweite Rechenlogik.

Anfrage (JSON): ``version``, ``konfiguration`` (wie schule.yaml, inkl. Szenarien), ``szenario``,
``kinder`` (nur die Angaben, die die Rechnung braucht), ``zeitlimit``, ``nur_klassen``.
**Datensparsam:** Namen, Adressen, Bemerkungen und weitere Spalten verlassen den Browser nicht; der
Browser setzt sie nach der Antwort wieder ein. Der Server speichert nichts.

Antwort (JSON): ``version``, ``protokoll`` und ``ergebnis`` (das ``Ergebnis``-Objekt, gepickelt,
zlib-komprimiert, Base64). Gepickelt wird nur vom Server zum Browser (gleiche Programmversion, eigener
Server); der Server selbst liest nur JSON und YAML (safe_load).
"""
from __future__ import annotations

import base64
import dataclasses
import json
import pickle
import sys
import tempfile
import urllib.error
import urllib.request
import zlib
from pathlib import Path

import yaml

from .daten import Kind
from .runtime import MAX_RECHENZEIT, RECHEN_URL
from .version import __version__

# Felder, die nie zum Server gehen (die Rechnung braucht sie nicht)
NUR_IM_BROWSER = ("name", "adresse", "bemerkung", "vorname", "nachname", "zusatz")
MAX_ANFRAGE = 8_000_000   # Zeichen
MAX_KINDER = 20_000


def _fuer_server(k: Kind) -> dict:
    d = dataclasses.asdict(k)
    for feld in NUR_IM_BROWSER:
        d.pop(feld, None)
    return d


def anfrage(cfg: dict, szenario: str, kinder: list[Kind], zeitlimit: float, nur_klassen: bool = False) -> str:
    return json.dumps({"version": __version__, "konfiguration": cfg, "szenario": szenario,
                       "kinder": [_fuer_server(k) for k in kinder], "zeitlimit": float(zeitlimit),
                       "nur_klassen": bool(nur_klassen)}, ensure_ascii=False)


def _post(url: str, text: str) -> tuple[int, str]:
    if sys.platform == "emscripten":  # im Browser: Python läuft in einem Web Worker – synchroner Aufruf erlaubt
        from js import XMLHttpRequest  # type: ignore[import-not-found]
        xhr = XMLHttpRequest.new()
        xhr.open("POST", url, False)
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.send(text)
        return int(xhr.status), str(xhr.responseText)
    req = urllib.request.Request(url, text.encode("utf-8"), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=MAX_RECHENZEIT + 60) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as fehler:
        return fehler.code, fehler.read().decode("utf-8", "replace")


def rechne_fern(cfg: dict, szenario: str, kinder: list[Kind], zeitlimit: float = 120, nur_klassen: bool = False,
                protokoll=print, url: str | None = None):
    """Wie ``skf.ablauf.rechne`` – nur auf dem Rechenserver. Gibt dasselbe ``Ergebnis`` zurück."""
    protokoll("Daten an den Rechenserver gesendet (ohne Namen und Adressen) – Berechnung läuft …")
    status, text = _post(url or RECHEN_URL, anfrage(cfg, szenario, kinder, min(zeitlimit, MAX_RECHENZEIT), nur_klassen))
    try:
        antwort = json.loads(text)
    except ValueError:
        raise RuntimeError(f"Rechenserver nicht erreichbar oder Zeit überschritten (HTTP {status}).") from None
    if status != 200:
        raise RuntimeError(antwort.get("fehler") or f"Rechenserver: HTTP {status}")
    for zeile in antwort.get("protokoll", []):
        protokoll(zeile)
    r = pickle.loads(zlib.decompress(base64.b64decode(antwort["ergebnis"])))
    vollstaendig = {k.id: k for k in kinder}          # Namen, Adressen … wieder einsetzen
    r.kinder = [vollstaendig.get(k.id, k) for k in r.kinder]
    return r


# ------------------------------------------------------------------ Server

def _kind(d: dict) -> Kind:
    if not isinstance(d, dict):
        raise ValueError("Lernende: Liste von Objekten erwartet")
    felder = {f.name for f in dataclasses.fields(Kind)} - set(NUR_IM_BROWSER)
    fremd = set(d) - felder
    if fremd:
        raise ValueError(f"Lernende: unbekannte Angaben {', '.join(sorted(fremd))}")
    if not d.get("id") or not d.get("jahrgang"):
        raise ValueError("Lernende: 'id' und 'jahrgang' sind Pflicht")
    return Kind(name="", adresse="", **d)


def bearbeite(text: str) -> tuple[int, str]:
    """Eine Anfrage beantworten → (HTTP-Status, JSON-Text). Speichert nichts."""
    from .ablauf import rechne
    from .daten import lade_schule

    def fehler(status: int, meldung: str) -> tuple[int, str]:
        return status, json.dumps({"fehler": meldung}, ensure_ascii=False)

    if len(text) > MAX_ANFRAGE:
        return fehler(413, "Anfrage zu gross")
    try:
        a = json.loads(text)
        if not isinstance(a, dict):
            raise ValueError("JSON-Objekt erwartet")
        if a.get("version") != __version__:
            return fehler(409, f"Programmversion {a.get('version')} im Browser, {__version__} auf dem Server – "
                               "Seite neu laden.")
        if not isinstance(a.get("konfiguration"), dict) or not isinstance(a.get("kinder"), list):
            raise ValueError("'konfiguration' (Objekt) und 'kinder' (Liste) erwartet")
        if len(a["kinder"]) > MAX_KINDER:
            return fehler(413, f"höchstens {MAX_KINDER} Lernende pro Berechnung")
        kinder = [_kind(d) for d in a["kinder"]]
        zeitlimit = float(a.get("zeitlimit", 120))
        if not 5 <= zeitlimit or zeitlimit != zeitlimit:
            zeitlimit = 5.0
        zeitlimit = min(zeitlimit, MAX_RECHENZEIT)
        with tempfile.TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "schule.yaml"
            pfad.write_text(yaml.safe_dump(a["konfiguration"], allow_unicode=True, sort_keys=False), encoding="utf-8")
            schule = lade_schule(pfad, str(a.get("szenario") or "Basis"))
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError) as e:
        return fehler(400, f"Angaben fehlerhaft: {e}")
    zeilen: list[str] = []
    try:
        r = rechne(schule, kinder, zeitlimit=zeitlimit, nur_klassen=bool(a.get("nur_klassen")),
                   protokoll=lambda t: zeilen.append(str(t).strip()))
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError, ZeroDivisionError) as e:
        return fehler(400, f"Angaben fehlerhaft: {type(e).__name__}: {e}")
    except Exception:  # noqa: BLE001 – nie Programmstellen oder Daten nach aussen geben
        return fehler(500, "Interner Fehler beim Rechnen – mit der installierten Version prüfen und melden.")
    ergebnis = base64.b64encode(zlib.compress(pickle.dumps(r, protocol=4), 6)).decode("ascii")
    return 200, json.dumps({"version": __version__, "protokoll": zeilen, "ergebnis": ergebnis}, ensure_ascii=False)

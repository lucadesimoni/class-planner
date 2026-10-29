# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Schuljahreswechsel: jede Stufe hat eine nächste Stufe.

    KG1 → KG2 → 1 → 2 → … → 6 → S1A | S1B | S1C | extern (Kanti, Wegzug …)
    S1A → S2A → S3A → Abschluss          (Umstufung: Entscheid "B" führt S1A → S2B)

Die Folge wird aus den Jahrgängen der Konfiguration abgeleitet und kann pro Schule
überschrieben werden:

    uebertritte:
      naechste: {"6": [S1A, S1B, S1C], S3A: Abschluss}   # einzelne Stufen anpassen
      extern: [Kanti, Langzeitgymnasium, Kurzzeitgymnasium, Privatschule, Sonderschule, Wegzug]

Der Entscheid pro Kind (Spalte *uebertritt*) wählt unter mehreren nächsten Stufen
(Niveau A/B/C), hält ein Kind zurück ("repetiert"), lässt eine Stufe aus ("überspringt")
oder führt aus der Schule hinaus (Kanti, Wegzug …) – Letzteres zählt wie ein Wegzug.
"""
from __future__ import annotations

import copy
import re
from collections import Counter
from dataclasses import dataclass

from .daten import Kind, Schule, niveau, stamm

ABSCHLUSS = "Abschluss"
EXTERN_STANDARD = ["Kanti", "Langzeitgymnasium", "Kurzzeitgymnasium", "Gymnasium", "Privatschule",
                   "Sonderschule", "Wegzug", "Austritt", "Berufslehre", "Brückenangebot"]
_REPETIERT = {"repetiert", "repetition", "wiederholt", "wiederholung", "bleibt", "zurueckgestellt",
              "zurückgestellt", "rueckstellung", "rückstellung"}
_UEBERSPRINGT = {"ueberspringt", "überspringt", "springt", "uebersprung", "übersprung"}
_NORMAL = {"", "normal", "promoviert", "promotion", "steigt auf", "aufstieg", "regulaer", "regulär", "ok"}


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", str(t or "").strip().lower())


def naechste(schule: Schule) -> dict[str, list[str]]:
    """Jahrgang → mögliche nächste Jahrgänge (Reihenfolge = Vorschlag), Abschluss am Ende."""
    stufen = schule.stufen()
    je_stufe = {s: [j for j in schule.jahrgaenge if stamm(j) == s] for s in stufen}
    folge: dict[str, list[str]] = {}
    for i, s in enumerate(stufen):
        nach = je_stufe[stufen[i + 1]] if i + 1 < len(stufen) else []
        for j in je_stufe[s]:
            gleich = [n for n in nach if niveau(n) and niveau(n) == niveau(j)]
            folge[j] = (gleich + [n for n in nach if n not in gleich]) or [ABSCHLUSS]
    for j, ziel in (schule.uebertritte.get("naechste") or {}).items():
        folge[str(j)] = [str(z) for z in (ziel if isinstance(ziel, list) else [ziel])]
    return folge


def extern(schule: Schule) -> list[str]:
    return [str(x) for x in schule.uebertritte.get("extern", EXTERN_STANDARD)]


@dataclass
class Schritt:
    kind: str
    name: str
    von: str
    nach: str            # neuer Jahrgang, "Abschluss" oder externes Ziel
    art: str             # z.B. "Übertritt Primar → Sek", "Austritt: Kanti", "Repetition"
    klasse_bisher: str = ""
    hinweis: str = ""

    @property
    def bleibt(self) -> bool:
        return not (self.art.startswith("Austritt") or self.art == "Abschluss")


def _art(von: str, nach: str) -> str:
    if von.startswith("KG") and not nach.startswith("KG"):
        return "Übertritt Kindergarten → Primar"
    if not von.startswith(("KG", "S")) and nach.startswith("S"):
        return f"Übertritt Primar → Sek {niveau(nach)}".rstrip()
    if von.startswith("S") and niveau(von) != niveau(nach):
        return f"Umstufung {niveau(von)} → {niveau(nach)}"
    return "Aufstieg"


def schritt(schule: Schule, k: Kind, klasse: str = "") -> Schritt:
    """Nächstes Schuljahr eines Kindes nach Stufenfolge und Entscheid."""
    folge, ext = naechste(schule), extern(schule)
    e = _norm(k.uebertritt)
    neu = lambda nach, art, hinweis="": Schritt(k.id, k.name, k.jahrgang, nach, art, klasse, hinweis)  # noqa: E731
    if k.jahrgang not in folge:
        return neu(k.jahrgang, "Entscheid fehlt", f"Jahrgang '{k.jahrgang}' gehört nicht zur Stufenfolge")
    for x in ext:
        if e and (e == x.lower() or e.startswith(x.lower())):
            return neu(x, f"Austritt: {x}")
    if e in _REPETIERT:
        return neu(k.jahrgang, "Repetition")
    moeglich = folge[k.jahrgang]
    if e in _UEBERSPRINGT:
        weiter = list(dict.fromkeys(n for z in moeglich if z in folge for n in folge[z]))
        if len(weiter) > 1:  # z.B. 5. Klasse → 1. Sek: das Niveau gehört zum Entscheid
            return neu(k.jahrgang, "Entscheid fehlt", f"Überspringen nach {'/'.join(weiter)}: Zielstufe direkt "
                                                      f"angeben (z.B. {weiter[0]})")
        if weiter and weiter[0] != ABSCHLUSS:
            return neu(weiter[0], "Überspringt eine Stufe")
        return neu(moeglich[0], "Aufstieg", "Überspringen nicht möglich – normal aufgestiegen")
    if moeglich == [ABSCHLUSS]:
        if k.jahrgang.startswith(("KG", "S")):
            return neu(ABSCHLUSS, "Abschluss")
        # Schule ohne Oberstufe: Übertritt in die Oberstufe einer anderen Schule (wie ein Wegzug)
        return neu("andere Schule", "Austritt: Übertritt an andere Schule", k.uebertritt)
    if len(moeglich) == 1 and e in _NORMAL:
        return neu(moeglich[0], _art(k.jahrgang, moeglich[0]))
    # Auswahl: exakter Jahrgang ("S1B"), Niveau ("B", "Sek B", "Niveau B") oder Text
    wahl = next((z for z in moeglich if _norm(z) == e), None)
    if wahl is None:
        buchstabe = re.fullmatch(r"(?:sek(?:undar)?(?:schule)?\s*)?(?:niveau\s*)?([a-d])", e)
        if buchstabe:
            wahl = next((z for z in moeglich if niveau(z) == buchstabe.group(1).upper()), None)
            if wahl is None and k.jahrgang.startswith("S"):  # Umstufung innerhalb der Sek
                ziel = f"{stamm(moeglich[0])}{buchstabe.group(1).upper()}"
                wahl = ziel if ziel in schule.jahrgaenge else None
    if wahl:
        return neu(wahl, _art(k.jahrgang, wahl))
    if e in _NORMAL and k.jahrgang.startswith("S") and niveau(k.jahrgang):
        return neu(moeglich[0], "Aufstieg")
    if e in _NORMAL:
        return neu(k.jahrgang, "Entscheid fehlt", f"Wahl nötig: {', '.join(moeglich + ext[:2])} …")
    return neu(k.jahrgang, "Entscheid fehlt", f"'{k.uebertritt}' nicht verstanden – möglich: "
                                              f"{', '.join(moeglich)}, repetiert, {', '.join(ext[:3])} …")


def _spalte(k: Kind, *namen: str) -> str:
    """Wert einer Zusatzspalte wie "Klasse" oder "Schulhaus aktuell" (Gross-/Kleinschreibung egal)."""
    gesucht = {re.sub(r"[^a-z]", "", n) for n in namen}
    return next((v for f, v in k.zusatz.items() if re.sub(r"[^a-z]", "", f.lower()) in gesucht), "")


def schuljahreswechsel(schule: Schule, kinder: list[Kind], klasse_von: dict[str, str] | None = None,
                       schulhaus_von: dict[str, str] | None = None,
                       neueintritte: list[Kind] | None = None) -> tuple[list[Kind], list[Schritt]]:
    """Lernende des laufenden Jahres → Lernende des nächsten Jahres.

    ``klasse_von``/``schulhaus_von``: aktuelle Klasse und aktuelles Schulhaus (z.B. aus der
    letzten Berechnung) – werden zu „bisherige Klasse/Schulhaus“ (Gspänli-Regel,
    Kontinuität). Wünsche gelten nur für ein Schuljahr und werden geleert. Kinder mit
    fehlendem Entscheid bleiben im bisherigen Jahrgang und sind im Protokoll markiert."""
    klasse_von, schulhaus_von = klasse_von or {}, schulhaus_von or {}
    neu, protokoll = [], []
    for k in kinder:
        klasse = klasse_von.get(k.id) or _spalte(k, "klasse", "klasseaktuell", "aktuelleklasse") or k.bisherige_klasse
        s = schritt(schule, k, klasse)
        protokoll.append(s)
        if not s.bleibt:
            continue
        n = copy.deepcopy(k)
        n.jahrgang = s.nach
        n.bisherige_klasse = klasse
        n.bisheriges_schulhaus = (schulhaus_von.get(k.id) or _spalte(k, "schulhaus", "schulhausaktuell")
                                  or k.bisheriges_schulhaus)
        n.uebertritt = ""
        n.zusammen_mit, n.nicht_mit, n.wunsch_schulhaus = [], [], ""
        n.zusatz = {f: w for f, w in k.zusatz.items()
                    if re.sub(r"[^a-z]", "", f.lower()) not in ("klasse", "klasseaktuell", "aktuelleklasse",
                                                                "schulhaus", "schulhausaktuell")}
        if s.art.startswith("Übertritt Primar") or s.art == "Übertritt Kindergarten → Primar":
            n.schulhaus_fix = ""
        neu.append(n)
    vorhanden = {n.id for n in neu}
    for k in neueintritte or []:
        if k.id in vorhanden:
            continue
        protokoll.append(Schritt(k.id, k.name, "", k.jahrgang, "Neueintritt"))
        neu.append(copy.deepcopy(k))
    # Wünsche aus Neueintritten auf weggefallene Kinder bleiben stehen – die Vorprüfung warnt
    return neu, protokoll


def zusammenfassung(protokoll: list[Schritt]) -> list[tuple[str, int]]:
    reihenfolge = ["Neueintritt", "Aufstieg", "Übertritt Kindergarten → Primar", "Übertritt Primar → Sek",
                   "Umstufung", "Repetition", "Überspringt", "Austritt", "Abschluss", "Entscheid fehlt"]
    zaehler = Counter(s.art for s in protokoll)
    return sorted(zaehler.items(), key=lambda t: (next((i for i, r in enumerate(reihenfolge) if t[0].startswith(r)),
                                                       99), t[0]))


def naechstes_schuljahr(text: str) -> str:
    """"2027/28" → "2028/29"."""
    m = re.fullmatch(r"\s*(\d{4})\s*/\s*(\d{2,4})\s*", str(text or ""))
    if not m:
        return text
    a = int(m.group(1)) + 1
    return f"{a}/{str(a + 1)[-2:]}"

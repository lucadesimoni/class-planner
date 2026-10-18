# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Schulbus und Wegzeiten der Lehrpersonen (beides optional).

* Schulbus: Kinder einer Buslinie kommen nur in Schulhäuser, die die Linie anfährt.
  Ihr Unterricht beginnt nach der Ankunft und endet passend zu einer Abfahrt –
  jeweils mit höchstens ``wartezeit_max`` Minuten Warten.
* Wegzeiten: Eine Lehrperson unterrichtet in zwei aufeinanderfolgenden Lektionen nur
  dann in verschiedenen Schulhäusern, wenn die Pause für den Weg reicht.
"""
from __future__ import annotations

from collections import defaultdict

from .daten import Schule, Slot, minuten
from .geo import luftlinie_m


def beginn(s: Slot) -> int:
    return minuten(s.zeit)


def ende(schule: Schule, s: Slot) -> int:
    return beginn(s) + schule.lektion_minuten


def zeit(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


# ------------------------------------------------------------------ Schulbus

def bus_halbtag(schule: Schule, linien: set[str], slots: list[Slot]) -> tuple[bool, set[int], list[str]]:
    """Für einen Halbtag einer Klasse (aufsteigende, offene Slots): ob Unterricht an diesem
    Halbtag möglich ist (Ankunft passt zum Beginn), die erlaubten letzten Lektionen und die
    Gründe für Einschränkungen."""
    if not slots or not linien:
        return True, {s.index for s in slots}, []
    tag, ht = slots[0].tag, slots[0].halbtag
    moeglich, ende_ok, gruende = True, {s.index for s in slots}, []
    for name in sorted(linien):
        linie = schule.buslinie(name)
        if linie is None:
            continue
        ankunft = linie.zeiten("ankunft", tag, ht)
        if ankunft is not None:
            warten = beginn(slots[0]) - ankunft
            if not 0 <= warten <= schule.bus_wartezeit:
                moeglich = False
                gruende.append(f"{name}: Ankunft {zeit(ankunft)}, Unterricht ab {slots[0].zeit}")
        abfahrten = linie.zeiten("abfahrt", tag, ht)
        if abfahrten:
            passend = {s.index for s in slots
                       if any(0 <= a - ende(schule, s) <= schule.bus_wartezeit for a in abfahrten)}
            ende_ok &= passend
            gruende.append(f"{name}: Abfahrt {', '.join(zeit(a) for a in abfahrten)}")
    return moeglich, ende_ok, gruende


def buslinien_der_klassen(klassen, kinder) -> dict[str, set[str]]:
    nach_id = {k.id: k for k in kinder}
    return {c.name: {nach_id[i].bus for i in c.kinder if i in nach_id and nach_id[i].bus} for c in klassen}


def halbtage_der_klasse(schule: Schule, schulhaus: str) -> dict[tuple[str, str], list[Slot]]:
    out: dict[tuple[str, str], list[Slot]] = defaultdict(list)
    for s in schule.offene_slots(schulhaus):
        out[s.tag, s.halbtag].append(s)
    return out


# ------------------------------------------------------------------ Wegzeiten

def wegzeit(schule: Schule, a: str, b: str) -> int:
    """Minuten zwischen zwei Schulhäusern: Angabe aus der Konfiguration, sonst
    Luftlinie × Umwegfaktor bei der eingestellten Geschwindigkeit (aufgerundet)."""
    if a == b or not schule.wegzeiten:
        return 0
    angabe = schule.wegzeiten["minuten"].get((a, b))
    if angabe is not None:
        return angabe
    sa, sb = schule.schulhaus(a), schule.schulhaus(b)
    meter = luftlinie_m(sa.lat, sa.lon, sb.lat, sb.lon) * schule.umweg_faktor
    return -(-int(meter * 60) // int(schule.wegzeiten["kmh"] * 1000))


def zu_knapp(schule: Schule) -> dict[tuple[str, str], list[tuple[int, int]]]:
    """(Schulhaus A, Schulhaus B) -> Slot-Paare (s, t) am selben Tag, zwischen denen die
    Zeit nicht für den Weg von A nach B reicht (s endet, t beginnt)."""
    if not schule.wegzeiten:
        return {}
    namen = [s.name for s in schule.schulhaeuser]
    out = {}
    for a in namen:
        for b in namen:
            w = wegzeit(schule, a, b)
            if a == b or w <= 0:
                continue
            paare = [(s.index, t.index) for s in schule.slots for t in schule.slots
                     if s.tag == t.tag and beginn(t) > beginn(s) and beginn(t) - ende(schule, s) < w]
            if paare:
                out[a, b] = paare
    return out


def lektionsort(schule: Schule, schulhaus: str, fach: str) -> str:
    """Wo eine Lektion stattfindet (z.B. Turnhalle in einem anderen Schulhaus)."""
    typ = schule.faecher[fach].raumtyp if fach in schule.faecher else ""
    return schule.schulhaus(schulhaus).nutzt.get(typ, schulhaus)

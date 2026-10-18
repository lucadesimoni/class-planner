"""Unabhängige Prüfung eines Ergebnisses gegen alle harten Regeln.

Rechnet nichts mit dem Solver, sondern zählt nur nach. Leere Liste = alles erfüllt.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from .daten import Kind, Schule
from .klassen import Einteilung
from .lehrauftrag import Block, qualifiziert, stundentafel
from .stundenplan import Lektion


def pruefe(schule: Schule, kinder: list[Kind], e: Einteilung,
           bloecke: list[Block] | None = None, lektionen: list[Lektion] | None = None) -> list[str]:
    fehler = []
    klassen = {c.name: c for c in e.klassen}

    # Klasseneinteilung
    zugeteilt = Counter(kid for c in e.klassen for kid in c.kinder)
    for k in kinder:
        if zugeteilt[k.id] != 1:
            fehler.append(f"{k.id} ist {zugeteilt[k.id]}x eingeteilt")
        elif k.jahrgang not in klassen[e.klasse_von[k.id]].vorlage.jahrgaenge:
            fehler.append(f"{k.id} ({k.jahrgang}) in falscher Stufe {e.klasse_von[k.id]}")
        if k.schulhaus_fix and e.schulhaus_von[k.id] != k.schulhaus_fix:
            fehler.append(f"{k.id} nicht im fixen Schulhaus {k.schulhaus_fix}")
    raeume = Counter((c.schulhaus, c.raum.name) for c in e.klassen)
    fehler += [f"Raum {r} doppelt belegt" for r, n in raeume.items() if n > 1]
    for c in e.klassen:
        g = len(c.kinder)
        if not (c.vorlage.min <= g <= min(c.vorlage.max, c.raum.plaetze)):
            fehler.append(f"{c.name}: Grösse {g} ausserhalb {c.vorlage.min}–{min(c.vorlage.max, c.raum.plaetze)}")
    if bloecke is None or lektionen is None:
        return fehler

    # Lehraufträge
    lp = {l.name: l for l in schule.lehrpersonen}
    last = Counter()
    for b in bloecke:
        if not qualifiziert(lp[b.lehrperson], klassen[b.klasse], b.fach):
            fehler.append(f"{b.lehrperson} nicht qualifiziert für {b.fach} in {b.klasse}")
        last[b.lehrperson] += b.lektionen
    fehler += [f"{n}: {l} Lektionen > Pensum {lp[n].pensum_max}" for n, l in last.items() if l > lp[n].pensum_max]

    # Stundenplan
    soll = Counter()
    for c in e.klassen:
        for f, n in stundentafel(schule, c).items():
            soll[c.name, f] += n
    ist = Counter((l.klasse, l.fach) for l in lektionen)
    fehler += [f"{k} {f}: {ist[k, f]} statt {n} Lektionen" for (k, f), n in soll.items() if ist[k, f] != n]

    for art, schluessel in (("Klasse", lambda l: l.klasse), ("Lehrperson", lambda l: l.lehrperson),
                            ("Raum", lambda l: (l.raum_ort, l.raum))):
        belegung = Counter((schluessel(l), l.slot) for l in lektionen)
        fehler += [f"{art} {x} doppelt belegt: {schule.slots[s].label}" for (x, s), n in belegung.items() if n > 1]
    for l in lektionen:
        if l.slot in lp[l.lehrperson].nicht_verfuegbar:
            fehler.append(f"{l.lehrperson} nicht verfügbar: {schule.slots[l.slot].label}")

    pro_tag = Counter((l.klasse, l.fach, schule.slots[l.slot].tag) for l in lektionen)
    for (k, f, tag), n in pro_tag.items():
        fach = schule.faecher[f]
        if n > max(fach.max_pro_tag, fach.dauer):
            fehler.append(f"{k} {f}: {n} Lektionen am {tag}")

    belegt = defaultdict(set)
    for l in lektionen:
        belegt[l.klasse].add(l.slot)
    vm = schule.slots[0].halbtag
    anz_vm = sum(s.halbtag == vm for s in schule.slots)
    for name, slots in belegt.items():
        for s in schule.slots:
            if s.nr > 0 and s.index in slots and s.index - 1 not in slots:
                fehler.append(f"{name}: Lücke vor {s.label}")
            if schule.blockzeiten and s.halbtag == vm and len(slots) >= anz_vm and s.index not in slots:
                fehler.append(f"{name}: Blockzeit {s.label} nicht besetzt")
    return fehler

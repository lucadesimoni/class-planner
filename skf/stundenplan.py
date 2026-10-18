"""Stundenplan als exaktes CP-SAT-Modell.

Harte Regeln: keine Doppelbelegung von Klassen, Lehrpersonen und Spezialräumen,
Verfügbarkeiten, Doppellektionen am Stück, max. Lektionen pro Fach und Tag,
Blockzeiten (Vormittag lückenlos) und keine Lücken für Kinder innerhalb eines Halbtags.
Weiche Ziele: wenige Präsenz-Halbtage und keine Springstunden für Lehrpersonen,
keine Schulhauswechsel innerhalb eines Halbtags.

Schulhäuser, die weder Lehrpersonen noch Räume teilen, werden unabhängig (und damit
schneller) gelöst – das Ergebnis bleibt exakt.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ortools.sat.python import cp_model

from .daten import Schule
from .klassen import Klasse
from .lehrauftrag import Block, gesperrte_slots
from .solver import KeineLoesung, Loesungsinfo, loese


@dataclass
class Lektion:
    klasse: str
    fach: str
    lehrperson: str
    slot: int
    raum: str
    schulhaus: str      # Schulhaus der Klasse
    raum_ort: str = ""  # Schulhaus des Raums (bei "nutzt" ein anderes)

    @property
    def raum_label(self) -> str:
        return self.raum if self.raum_ort == self.schulhaus else f"{self.raum} ({self.raum_ort})"


def _komponenten(schule: Schule, bloecke: list[Block]) -> list[set[str]]:
    eltern = {s.name: s.name for s in schule.schulhaeuser}

    def wurzel(a):
        while eltern[a] != a:
            eltern[a] = eltern[eltern[a]]
            a = eltern[a]
        return a

    def verbinde(a, b):
        eltern[wurzel(a)] = wurzel(b)

    for s in schule.schulhaeuser:
        for anderes in s.nutzt.values():
            verbinde(s.name, anderes)
    erstes = {}
    for b in bloecke:
        verbinde(b.schulhaus, erstes.setdefault(b.lehrperson, b.schulhaus))
    gruppen = defaultdict(set)
    for s in schule.schulhaeuser:
        gruppen[wurzel(s.name)].add(s.name)
    return list(gruppen.values())


def erstelle_stundenplan(schule: Schule, klassen: list[Klasse], bloecke: list[Block],
                         zeitlimit: float = 120) -> tuple[list[Lektion], list[Loesungsinfo], list[str]]:
    lektionen, infos, warnungen = [], [], []
    komponenten = [k for k in _komponenten(schule, bloecke) if any(b.schulhaus in k for b in bloecke)]
    gesamt = sum(b.lektionen for b in bloecke)
    for komp in komponenten:
        teil = [b for b in bloecke if b.schulhaus in komp]
        anteil = sum(b.lektionen for b in teil) / gesamt
        l, info, warn = _loese_komponente(schule, [c for c in klassen if c.schulhaus in komp],
                                          teil, max(5.0, zeitlimit * anteil), "/".join(sorted(komp)))
        lektionen += l
        infos.append(info)
        warnungen += warn
    return lektionen, infos, warnungen


def _loese_komponente(schule: Schule, klassen: list[Klasse], bloecke: list[Block],
                      zeitlimit: float, titel: str):
    w = schule.gewichte
    slots = schule.slots
    lp_nach_name = {lp.name: lp for lp in schule.lehrpersonen}
    klasse_nach_name = {c.name: c for c in klassen}
    warnungen: list[str] = []
    m = cp_model.CpModel()

    # Ereignisse: (Block, Dauer) mit je einer Startvariable pro möglichem Slot
    ereignisse = []  # (block, dauer, anzahl, {start_slot: var})
    for b in bloecke:
        fach = schule.faecher[b.fach]
        gesperrt = gesperrte_slots(schule, klasse_nach_name[b.klasse], b.fach, lp_nach_name[b.lehrperson])
        teile = [(fach.dauer, b.lektionen // fach.dauer)]
        if b.lektionen % fach.dauer:
            teile.append((1, b.lektionen % fach.dauer))
        for dauer, anzahl in teile:
            if anzahl == 0:
                continue
            starts = {}
            for s in slots:
                folge = slots[s.index:s.index + dauer]
                if (len(folge) == dauer and all(f.tag == s.tag and f.halbtag == s.halbtag for f in folge)
                        and not any(f.index in gesperrt for f in folge)):
                    starts[s.index] = m.new_bool_var(f"s_{b.klasse}_{b.fach}_{dauer}_{s.index}")
            if len(starts) < anzahl:
                raise KeineLoesung(f"{b.klasse} {b.fach}: zu wenige mögliche Zeitfenster für {b.lehrperson}")
            m.add(sum(starts.values()) == anzahl)
            ereignisse.append((b, dauer, anzahl, starts))

    # Belegung je (Block-Ereignis, Slot) als lineare 0/1-Ausdrücke
    belegt = defaultdict(list)  # (art, schlüssel, slot) -> Liste von Variablen
    fach_tag = defaultdict(list)
    for b, dauer, _, starts in ereignisse:
        fach = schule.faecher[b.fach]
        for st, var in starts.items():
            for i in range(st, st + dauer):
                belegt["klasse", b.klasse, i].append(var)
                belegt["lp", b.lehrperson, i].append(var)
                fach_tag[b.klasse, b.fach, slots[i].tag].append(var)
                if fach.raumtyp != "Klassenzimmer":
                    ort = schule.schulhaus(b.schulhaus).nutzt.get(fach.raumtyp, b.schulhaus)
                    belegt["raum", (ort, fach.raumtyp, b.klasse), i].append(var)

    for (kl, fach, _), vars_ in fach_tag.items():
        m.add(sum(vars_) <= max(schule.faecher[fach].max_pro_tag, schule.faecher[fach].dauer))

    # Klassen: max. 1 Lektion pro Slot, Blockzeiten, keine Lücken im Halbtag
    for c in klassen:
        total = sum(b.lektionen for b in bloecke if b.klasse == c.name)
        co = {s.index: sum(belegt["klasse", c.name, s.index]) for s in slots}
        offen = schule.offene_slots(c.schulhaus)
        pflicht = blockzeit_slots(schule, c.schulhaus) if total >= len(blockzeit_slots(schule, c.schulhaus)) else []
        vorher = None
        for s in offen:
            m.add(co[s.index] <= 1)
            if vorher is not None and vorher.tag == s.tag and vorher.halbtag == s.halbtag:
                m.add(co[s.index] <= co[vorher.index])  # keine Lücken für Kinder
            vorher = s
        for i in pflicht:
            m.add(co[i] == 1)

    # Spezialräume: Hall-Bedingung über Klassengrössen (exakt für "Raum gross genug")
    raumbedarf = defaultdict(lambda: defaultdict(list))  # (ort, typ, slot) -> klasse -> vars
    for (art, key, i), vars_ in belegt.items():
        if art == "raum":
            ort, typ, kl = key
            raumbedarf[ort, typ, i][kl] += vars_
    for (ort, typ, i), pro_klasse in raumbedarf.items():
        plaetze = sorted(r.plaetze for r in schule.schulhaus(ort).raeume
                         if r.typ == typ and i not in r.nicht_verfuegbar)
        if not plaetze:  # durch _gesperrt bereits ausgeschlossen
            continue
        groessen = {kl: klasse_nach_name[kl].groesse for kl in pro_klasse}
        for kl, g in groessen.items():
            warnung = f"{kl} ({g} Kinder) ist grösser als jeder Raum '{typ}' in {ort}"
            if g > plaetze[-1] and warnung not in warnungen:
                warnungen.append(warnung)
        for schwelle in sorted(set(min(g, plaetze[-1]) for g in groessen.values())):
            passende = sum(1 for p in plaetze if p >= schwelle)
            m.add(sum(v for kl, vs in pro_klasse.items()
                      if min(groessen[kl], plaetze[-1]) >= schwelle for v in vs) <= passende)

    # Lehrpersonen: keine Doppelbelegung, weiche Ziele
    kosten = []
    halbtage = schule.halbtage()
    for name in {b.lehrperson for b in bloecke}:
        busy = {}
        for s in slots:
            vars_ = belegt["lp", name, s.index]
            if not vars_:
                continue
            busy[s.index] = m.new_bool_var(f"busy_{name}_{s.index}")
            m.add(sum(vars_) == busy[s.index])
        orte = {b.schulhaus for b in bloecke if b.lehrperson == name}
        for tag, ht in halbtage:
            idx = [s.index for s in slots if s.tag == tag and s.halbtag == ht and s.index in busy]
            if not idx:
                continue
            praesent = m.new_bool_var("p")
            m.add_max_equality(praesent, [busy[i] for i in idx])
            kosten.append(w["praesenz_halbtag"] * praesent)
            # Springstunden: Slot frei, aber vorher und nachher Unterricht
            for k in range(1, len(idx) - 1):
                vorher, nachher = m.new_bool_var("v"), m.new_bool_var("n")
                m.add_max_equality(vorher, [busy[i] for i in idx[:k]])
                m.add_max_equality(nachher, [busy[i] for i in idx[k + 1:]])
                luecke = m.new_bool_var("l")
                m.add(luecke >= vorher + nachher - busy[idx[k]] - 1)
                kosten.append(w["springstunde"] * luecke)
            if len(orte) > 1:
                dort = []
                for ort in orte:
                    vars_ort = [v for b, dauer, _, starts in ereignisse if b.lehrperson == name and b.schulhaus == ort
                                for st, v in starts.items() if slots[st].tag == tag and slots[st].halbtag == ht]
                    if vars_ort:
                        d = m.new_bool_var("d")
                        m.add_max_equality(d, vars_ort)
                        dort.append(d)
                if len(dort) > 1:
                    wechsel = m.new_int_var(0, len(dort), "w")
                    m.add(wechsel >= sum(dort) - 1)
                    kosten.append(w["schulhauswechsel"] * wechsel)

    m.minimize(sum(kosten))
    sol, info = loese(m, f"Stundenplan {titel}", zeitlimit)

    lektionen = []
    for b, dauer, _, starts in ereignisse:
        for st, var in starts.items():
            if sol.value(var):
                for i in range(st, st + dauer):
                    lektionen.append(Lektion(b.klasse, b.fach, b.lehrperson, i, "", b.schulhaus))
    _raeume_zuweisen(schule, klasse_nach_name, lektionen)
    return lektionen, info, warnungen


def blockzeit_slots(schule: Schule, schulhaus: str) -> list[int]:
    """Slots, die bei Blockzeiten besetzt sein müssen (offene Vormittagslektionen)."""
    if not schule.blockzeiten:
        return []
    vm = schule.slots[0].halbtag
    return [s.index for s in schule.offene_slots(schulhaus) if s.halbtag == vm]


def _raeume_zuweisen(schule: Schule, klassen: dict[str, Klasse], lektionen: list[Lektion]) -> None:
    """Konkrete Räume: grösste Klasse zuerst, jeweils der kleinste passende freie Raum."""
    gruppen = defaultdict(list)
    for l in lektionen:
        typ = schule.faecher[l.fach].raumtyp
        if typ == "Klassenzimmer":
            l.raum, l.raum_ort = klassen[l.klasse].raum.name, l.schulhaus
        else:
            ort = schule.schulhaus(l.schulhaus).nutzt.get(typ, l.schulhaus)
            gruppen[ort, typ, l.slot].append(l)
    for (ort, typ, slot), ls in gruppen.items():
        frei = sorted((r for r in schule.schulhaus(ort).raeume if r.typ == typ and slot not in r.nicht_verfuegbar),
                      key=lambda r: r.plaetze)
        for l in sorted(ls, key=lambda l: -klassen[l.klasse].groesse):
            raum = next((r for r in frei if r.plaetze >= klassen[l.klasse].groesse), frei[-1])
            frei.remove(raum)
            l.raum, l.raum_ort = raum.name, ort

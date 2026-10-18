"""Verteilung der Lektionen (Klasse x Fach) auf Lehrpersonen.

Exaktes Optimierungsmodell: jede Lektionengruppe bekommt genau eine qualifizierte
Lehrperson. Pensum (max hart, min weich), Verfügbarkeit und Schulhäuser werden
eingehalten; möglichst wenige Lehrpersonen pro Klasse (Klassenlehrprinzip) und
möglichst wenige Schulhäuser pro Lehrperson.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ortools.sat.python import cp_model

from .daten import Lehrperson, Schule
from .klassen import Klasse
from .solver import KeineLoesung, Loesungsinfo, loese


@dataclass
class Block:
    klasse: str
    schulhaus: str
    fach: str
    lektionen: int
    lehrperson: str = ""


def stundentafel(schule: Schule, klasse: Klasse) -> dict[str, int]:
    """Lektionen pro Fach. Mischklassen erhalten pro Fach das Maximum ihrer Jahrgänge."""
    if klasse.vorlage.bezeichnung in schule.stundentafel:
        return dict(schule.stundentafel[klasse.vorlage.bezeichnung])
    tafel: dict[str, int] = {}
    for j in klasse.jahrgaenge:
        if j not in schule.stundentafel:
            raise ValueError(f"Keine Stundentafel für Jahrgang {j}")
        for fach, lekt in schule.stundentafel[j].items():
            tafel[fach] = max(tafel.get(fach, 0), lekt)
    return tafel


def qualifiziert(lp: Lehrperson, klasse: Klasse, fach: str) -> bool:
    return (fach in lp.faecher
            and (lp.schulhaeuser is None or klasse.schulhaus in lp.schulhaeuser)
            and (lp.jahrgaenge is None or all(j in lp.jahrgaenge for j in klasse.jahrgaenge)))


def gesperrte_slots(schule: Schule, klasse: Klasse, fach: str, lp: Lehrperson) -> set[int]:
    """Slots, in denen diese Lehrperson dieses Fach in dieser Klasse nicht unterrichten kann
    (Lehrperson, Schulhaus oder benötigter Raum nicht verfügbar)."""
    sh = schule.schulhaus(klasse.schulhaus)
    gesperrt = set(lp.nicht_verfuegbar) | sh.nicht_verfuegbar
    typ = schule.faecher[fach].raumtyp
    if typ == "Klassenzimmer":
        return gesperrt | klasse.raum.nicht_verfuegbar
    ort = schule.schulhaus(sh.nutzt.get(typ, klasse.schulhaus))
    raeume = [r for r in ort.raeume if r.typ == typ]
    if not raeume:
        raise KeineLoesung(f"{klasse.name} {fach}: Schulhaus {ort.name} hat keinen Raum vom Typ '{typ}' "
                           f"(Raum ergänzen oder 'nutzt: {{{typ}: <Schulhaus>}}' setzen)")
    for s in schule.slots:
        if s.index in ort.nicht_verfuegbar or all(s.index in r.nicht_verfuegbar for r in raeume):
            gesperrt.add(s.index)
    return gesperrt


def verteile_lehrauftraege(schule: Schule, klassen: list[Klasse],
                           zeitlimit: float = 30) -> tuple[list[Block], Loesungsinfo]:
    w = schule.gewichte
    bloecke = []
    for c in klassen:
        tafel = stundentafel(schule, c)
        if sum(tafel.values()) > len(schule.slots):
            raise KeineLoesung(f"{c.name}: {sum(tafel.values())} Lektionen, aber nur {len(schule.slots)} Zeitfenster")
        bloecke += [Block(c.name, c.schulhaus, f, l) for f, l in tafel.items() if l > 0]

    m = cp_model.CpModel()
    a = {}
    for bi, b in enumerate(bloecke):
        klasse = next(c for c in klassen if c.name == b.klasse)
        kandidaten = [ti for ti, lp in enumerate(schule.lehrpersonen) if qualifiziert(lp, klasse, b.fach)]
        if not kandidaten:
            raise KeineLoesung(f"Keine Lehrperson für {b.fach} in {b.klasse} ({b.schulhaus}, "
                               f"Jahrgänge {'/'.join(klasse.jahrgaenge)})")
        for ti in kandidaten:
            a[bi, ti] = m.new_bool_var(f"a_{bi}_{ti}")
        m.add_exactly_one(a[bi, ti] for ti in kandidaten)

    pro_lp = defaultdict(list)
    for (bi, ti), av in a.items():
        pro_lp[ti].append((bi, av))

    kosten = []
    for ti, eintraege in pro_lp.items():
        lp = schule.lehrpersonen[ti]
        verfuegbar = len(schule.slots) - len(lp.nicht_verfuegbar)
        last = sum(bloecke[bi].lektionen * av for bi, av in eintraege)
        m.add(last <= min(lp.pensum_max, verfuegbar))
        if lp.pensum_min:
            unter = m.new_int_var(0, lp.pensum_min, f"unter_{ti}")
            m.add(unter >= lp.pensum_min - last)
            kosten.append(w["pensum_unterschritten"] * unter)

        hier = defaultdict(list)
        for bi, av in eintraege:
            hier[bloecke[bi].schulhaus].append(av)
        if len(hier) > 1:
            dort = []
            for sh, avs in hier.items():
                v = m.new_bool_var(f"sh_{ti}_{sh}")
                for av in avs:
                    m.add_implication(av, v)
                dort.append(v)
            extra = m.new_int_var(0, len(dort), f"extra_{ti}")
            m.add(extra >= sum(dort) - 1)
            kosten.append(w["lehrperson_mehrere_schulhaeuser"] * extra)

    # Notwendige Bedingung für Blockzeiten (Flussmodell pro Tag): die zugeteilten
    # Lehrpersonen müssen die Vormittage aller Klassen gemeinsam abdecken können,
    # wobei jede Lehrperson nur so viele Lektionen gibt, wie sie am Vormittag da ist.
    if schule.blockzeiten:
        vm = schule.slots[0].halbtag
        anz_vm = sum(s.halbtag == vm for s in schule.slots)
        voll = {c.name for c in klassen
                if sum(b.lektionen for b in bloecke if b.klasse == c.name) >= anz_vm}
        klasse_von = {c.name: c for c in klassen}
        gesperrt = {(bi, ti): gesperrte_slots(schule, klasse_von[bloecke[bi].klasse], bloecke[bi].fach,
                                              schule.lehrpersonen[ti])
                    for (bi, ti) in a if bloecke[bi].klasse in voll}
        for tag in dict.fromkeys(s.tag for s in schule.slots):
            vm_alle = [s.index for s in schule.slots if s.tag == tag and s.halbtag == vm]
            angebot = defaultdict(list)  # (lehrperson, klasse) -> Ausdrücke
            for (bi, ti), av in a.items():
                b = bloecke[bi]
                if b.klasse not in voll:
                    continue
                frei = sum(1 for i in vm_alle if i not in gesperrt[bi, ti])
                fach = schule.faecher[b.fach]
                cap = min(b.lektionen, max(fach.max_pro_tag, fach.dauer), frei)
                if cap:
                    angebot[ti, b.klasse].append(cap * av)
            deckung = defaultdict(list)
            pro_lp_tag = defaultdict(list)
            for (ti, kl), terme in angebot.items():
                frei = sum(1 for i in vm_alle if i not in schule.lehrpersonen[ti].nicht_verfuegbar)
                f = m.new_int_var(0, frei, f"fluss_{tag}_{ti}_{kl}")
                m.add(f <= sum(terme))
                deckung[kl].append(f)
                pro_lp_tag[ti, frei].append(f)
            for (ti, frei), fs in pro_lp_tag.items():
                m.add(sum(fs) <= frei)
            for kl in voll:
                pflicht = [i for i in vm_alle if i not in schule.schulhaus(klasse_von[kl].schulhaus).nicht_verfuegbar]
                m.add(sum(deckung[kl]) >= len(pflicht))

    pro_klasse = defaultdict(lambda: defaultdict(list))
    for (bi, ti), av in a.items():
        pro_klasse[bloecke[bi].klasse][ti].append(av)
    for kl, lps in pro_klasse.items():
        u = []
        for ti, avs in lps.items():
            uv = m.new_bool_var(f"u_{kl}_{ti}")
            for av in avs:
                m.add_implication(av, uv)
            u.append(uv)
        kosten.append(w["lehrperson_pro_klasse"] * sum(u))

    m.minimize(sum(kosten))
    try:
        sol, info = loese(m, "Lehraufträge", zeitlimit)
    except KeineLoesung as fehler:
        raise KeineLoesung(f"{fehler} Häufige Ursachen: zu kleine Pensen, fehlende Qualifikationen oder "
                           "Blockzeiten, die an einem Tag wegen gesperrter Lehrpersonen/Räume/Schulhäuser "
                           "nicht abgedeckt werden können.") from None
    for (bi, ti), av in a.items():
        if sol.value(av):
            bloecke[bi].lehrperson = schule.lehrpersonen[ti].name
    return bloecke, info

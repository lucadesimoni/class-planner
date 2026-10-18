"""Verteilung der Lektionen (Klasse x Fach) auf Lehrpersonen.

Exaktes Optimierungsmodell: jede Lektionengruppe bekommt genau eine qualifizierte
Lehrperson. Pensum (max hart, min weich), Verfügbarkeit und Schulhäuser werden
eingehalten; möglichst wenige Lehrpersonen pro Klasse (Klassenlehrprinzip),
möglichst wenige Schulhäuser pro Lehrperson und Kontinuität (eine Lehrperson
führt ihre bisherige Klasse weiter).

Förderangebote (IF, DaZ, …) werden als eigene Lektionengruppen pro Klasse gebildet
und an dafür qualifizierte Lehrpersonen (Fach = Name des Angebots) vergeben.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from .daten import Kind, Lehrperson, Schule
from .klassen import Klasse
from .solver import KeineLoesung, Loesungsinfo, Regeln, loese_mit_regeln


@dataclass
class Block:
    klasse: str
    schulhaus: str
    fach: str
    lektionen: int
    lehrperson: str = ""
    art: str = "unterricht"          # "unterricht" oder "foerder" (parallel zum Unterricht)
    parallel_zu: list[str] = field(default_factory=list)
    gruppe: int = 0                  # Anzahl Kinder einer Fördergruppe (0 = ganze Klasse)
    klassen: list[str] = field(default_factory=list)  # beteiligte Klassen (Fördergruppen über Klassen)

    def __post_init__(self):
        if not self.klassen:
            self.klassen = [self.klasse]


def foerderbloecke(schule: Schule, klassen: list[Klasse], kinder: dict[str, Kind]) -> list[Block]:
    """Förderlektionen gemäss den konfigurierten Förderangeboten.

    gruppierung "klasse":    eine Gruppe pro Klasse (z.B. IF im Klassenverband)
    gruppierung "schulhaus": Gruppen pro Schulhaus und Stufe über Klassen hinweg (z.B. DaZ),
                             bei mehr als max_gruppe Kindern geteilt
    """
    bloecke = []
    tafeln = {c.name: stundentafel(schule, c) for c in klassen}

    def parallel_faecher(a, namen: list[str]) -> list[str]:
        gemeinsam = [f for f in (a.parallel_zu or tafeln[namen[0]]) if all(tafeln[n].get(f) for n in namen)]
        return gemeinsam or [f for f in tafeln[namen[0]] if all(tafeln[n].get(f) for n in namen)]

    for a in schule.foerderangebote:
        gruppen: list[tuple[list[Klasse], int, list[str]]] = []  # (Klassen, Anzahl Kinder, Jahrgänge)
        if a.gruppierung == "schulhaus":
            stufen = a.stufen or [schule.jahrgaenge]
            for sh in schule.schulhaeuser:
                for stufe in stufen:
                    pro_klasse = []
                    for c in klassen:
                        if c.schulhaus != sh.name:
                            continue
                        n = sum(1 for i in c.kinder if kinder[i].hat(a.merkmal) and kinder[i].jahrgang in stufe)
                        if n:
                            pro_klasse.append((c, n))
                    total = sum(n for _, n in pro_klasse)
                    if not total:
                        continue
                    teile = -(-total // a.max_gruppe)
                    ziel = -(-total // teile)
                    aktuell: list[Klasse] = []
                    anzahl = 0
                    for c, n in pro_klasse:  # Klassen der Reihe nach auf Teilgruppen verteilen
                        if aktuell and anzahl + n > ziel:
                            gruppen.append((aktuell, anzahl, stufe))
                            aktuell, anzahl = [], 0
                        aktuell.append(c)
                        anzahl += n
                    gruppen.append((aktuell, anzahl, stufe))
        else:
            for c in klassen:
                n = sum(kinder[i].hat(a.merkmal) for i in c.kinder if i in kinder)
                gruppen.append(([c], n if a.merkmal != "alle" else len(c.kinder), c.jahrgaenge))
        for ks, anzahl, jg in gruppen:
            lekt = a.lektionen([j for j in jg if any(j in c.jahrgaenge for c in ks)] or jg, anzahl)
            if lekt <= 0:
                continue
            namen = [c.name for c in ks]
            parallel = parallel_faecher(a, namen)
            verfuegbar = min(sum(tafeln[n][f] for f in parallel) for n in namen) if parallel else 0
            if lekt > verfuegbar:
                raise KeineLoesung(f"{'/'.join(namen)}: {lekt} Lektionen {a.name}, aber nur {verfuegbar} Lektionen "
                                   f"{'/'.join(parallel) or '–'} gleichzeitig parallel möglich")
            bloecke.append(Block(namen[0], ks[0].schulhaus, a.name, lekt, art="foerder", parallel_zu=parallel,
                                 gruppe=0 if a.merkmal == "alle" else anzahl, klassen=namen))
    return bloecke


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
    if typ == "":
        return gesperrt
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


def verteile_lehrauftraege(schule: Schule, klassen: list[Klasse], zeitlimit: float = 30,
                           kinder: list[Kind] | None = None,
                           verbote: list[list[tuple[str, str, str]]] | None = None) -> tuple[list[Block], Loesungsinfo]:
    """``verbote``: Listen von (Klasse, Fach, Lehrperson), die nicht alle zugleich gelten dürfen
    (Rückmeldung aus einem unlösbaren Stundenplan)."""
    w = schule.gewichte
    nach_id = {k.id: k for k in kinder or []}
    bloecke = []
    for c in klassen:
        tafel = stundentafel(schule, c)
        if sum(tafel.values()) > len(schule.slots):
            raise KeineLoesung(f"{c.name}: {sum(tafel.values())} Lektionen, aber nur {len(schule.slots)} Zeitfenster")
        bloecke += [Block(c.name, c.schulhaus, f, l) for f, l in tafel.items() if l > 0]
    if nach_id:
        bloecke += foerderbloecke(schule, klassen, nach_id)

    m = cp_model.CpModel()
    regeln = Regeln(m)
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
        if verfuegbar < lp.pensum_max:
            regeln.nur_wenn(m.add(last <= verfuegbar), f"Verfügbarkeit {lp.name} ({verfuegbar} Zeitfenster)")
        regeln.nur_wenn(m.add(last <= lp.pensum_max), f"Maximalpensum {lp.name} ({lp.pensum_max} L)")
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
                if sum(b.lektionen for b in bloecke if b.klasse == c.name and b.art == "unterricht") >= anz_vm}
        klasse_von = {c.name: c for c in klassen}
        gesperrt = {(bi, ti): gesperrte_slots(schule, klasse_von[bloecke[bi].klasse], bloecke[bi].fach,
                                              schule.lehrpersonen[ti])
                    for (bi, ti) in a if bloecke[bi].klasse in voll and bloecke[bi].art == "unterricht"}
        # Fluss pro Lektionengruppe und Tag: jede Gruppe gibt pro Tag höchstens so viele
        # Lektionen, wie Fach-Tageslimit und freie Vormittagslektionen erlauben, und über
        # die Woche höchstens ihre Lektionenzahl.
        tage = list(dict.fromkeys(s.tag for s in schule.slots))
        vm_tag = {tag: [s.index for s in schule.slots if s.tag == tag and s.halbtag == vm] for tag in tage}
        deckung = defaultdict(list)       # (klasse, tag) -> Flüsse
        pro_lp_tag = defaultdict(list)    # (lehrperson, tag) -> Flüsse
        for (bi, ti), av in a.items():
            b = bloecke[bi]
            if b.klasse not in voll or b.art != "unterricht":
                continue
            fach = schule.faecher[b.fach]
            woche = []
            for tag in tage:
                frei = sum(1 for i in vm_tag[tag] if i not in gesperrt[bi, ti])
                cap = min(b.lektionen, max(fach.max_pro_tag, fach.dauer), frei)
                if not cap:
                    continue
                f = m.new_int_var(0, cap, f"fluss_{bi}_{ti}_{tag}")
                m.add(f <= cap * av)
                woche.append(f)
                deckung[b.klasse, tag].append(f)
                pro_lp_tag[ti, tag].append(f)
            if woche:
                m.add(sum(woche) <= b.lektionen)
        for (ti, tag), fs in pro_lp_tag.items():
            m.add(sum(fs) <= sum(1 for i in vm_tag[tag] if i not in schule.lehrpersonen[ti].nicht_verfuegbar))
        for kl in voll:
            for tag in tage:
                pflicht = [i for i in vm_tag[tag] if i not in schule.schulhaus(klasse_von[kl].schulhaus).nicht_verfuegbar]
                if pflicht:
                    regeln.nur_wenn(m.add(sum(deckung[kl, tag]) >= len(pflicht)), f"Blockzeiten {kl} am {tag}")

    pro_klasse = defaultdict(lambda: defaultdict(list))
    for (bi, ti), av in a.items():
        if bloecke[bi].art == "unterricht":
            pro_klasse[bloecke[bi].klasse][ti].append(av)
    for kl, lps in pro_klasse.items():
        u = []
        for ti, avs in lps.items():
            uv = m.new_bool_var(f"u_{kl}_{ti}")
            for av in avs:
                m.add_implication(av, uv)
            u.append(uv)
        kosten.append(w["lehrperson_pro_klasse"] * sum(u))

    # Kontinuität: Lehrperson führt ihre bisherige Klasse weiter (Bonus nach Anteil der Kinder)
    if nach_id:
        klasse_von = {c.name: c for c in klassen}
        total = defaultdict(int)
        for b in bloecke:
            if b.art == "unterricht":
                total[b.klasse] += b.lektionen
        for (bi, ti), av in a.items():
            b, lp = bloecke[bi], schule.lehrpersonen[ti]
            if b.art != "unterricht" or not lp.bisherige_klasse:
                continue
            ks = klasse_von[b.klasse].kinder
            anteil = sum(nach_id[i].bisherige_klasse == lp.bisherige_klasse for i in ks) / max(1, len(ks))
            bonus = round(w["lehrperson_kontinuitaet"] * anteil * b.lektionen / total[b.klasse])
            if bonus:
                kosten.append(-bonus * av)

    lp_index = {lp.name: ti for ti, lp in enumerate(schule.lehrpersonen)}
    for verbot in verbote or []:
        terme = [a[bi, lp_index[lp]] for bi, b in enumerate(bloecke) for kl, fach, lp in verbot
                 if b.klasse == kl and b.fach == fach and (bi, lp_index.get(lp)) in a]
        if terme:
            m.add(sum(terme) <= len(terme) - 1)

    m.minimize(sum(kosten))
    sol, info = loese_mit_regeln(m, regeln, "Lehraufträge", zeitlimit)
    for (bi, ti), av in a.items():
        if sol.value(av):
            bloecke[bi].lehrperson = schule.lehrpersonen[ti].name
    return bloecke, info

"""Klasseneinteilung in zwei exakten Schritten.

Schritt A (Schulhaus & Klassen): Jedes Kind wird einem Schulhaus zugeteilt und in
jedem Schulzimmer wird höchstens eine Klasse eröffnet (mit erlaubtem Klassentyp).
Gezählt wird nur, wie viele Kinder welchen Jahrgangs in jede Klasse kommen – das
macht das Modell klein und symmetriefrei. Ziel: kurze Schulwege, wenige Klassen,
Klassengrössen nahe am Ideal, Geschwister im selben Schulhaus.

Schritt B (Kinder auf Parallelklassen): Pro Schulhaus werden die konkreten Kinder
auf die eröffneten Klassen verteilt (Anzahl je Jahrgang aus Schritt A), so dass
Geschlecht und Förderbedarf ausgeglichen sind und "nicht_mit"-Wünsche erfüllt.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from .daten import Kind, Raum, Schule, Vorlage
from .geo import luftlinie_m
from .solver import Loesungsinfo, loese


@dataclass
class Klasse:
    name: str
    schulhaus: str
    raum: Raum
    vorlage: Vorlage
    anzahl_pro_jahrgang: dict[str, int]
    kinder: list[str] = field(default_factory=list)

    @property
    def jahrgaenge(self) -> list[str]:
        return [j for j in self.vorlage.jahrgaenge if self.anzahl_pro_jahrgang.get(j, 0) > 0]

    @property
    def groesse(self) -> int:
        return sum(self.anzahl_pro_jahrgang.values())


@dataclass
class Einteilung:
    klassen: list[Klasse]
    schulhaus_von: dict[str, str]       # Kind-ID -> Schulhaus
    klasse_von: dict[str, str]          # Kind-ID -> Klassenname
    schulweg_m: dict[str, float]        # Kind-ID -> geschätzter Schulweg
    infos: list[Loesungsinfo]
    warnungen: list[str]


def tafel_fuer_vorlage(schule: Schule, v: Vorlage) -> dict[str, int]:
    """Stundentafel eines Klassentyps (Mischklassen: pro Fach das Maximum)."""
    if v.bezeichnung in schule.stundentafel:
        return dict(schule.stundentafel[v.bezeichnung])
    tafel: dict[str, int] = {}
    for j in v.jahrgaenge:
        for fach, lekt in schule.stundentafel.get(j, {}).items():
            tafel[fach] = max(tafel.get(fach, 0), lekt)
    return tafel


def schulwege(schule: Schule, kinder: list[Kind]) -> dict[tuple[str, str], float]:
    d = {}
    for k in kinder:
        if k.lat is None or k.lon is None:
            raise ValueError(f"Kind {k.id} hat keine Koordinaten (Adresse geocodieren oder lat/lon angeben)")
        for s in schule.schulhaeuser:
            d[k.id, s.name] = luftlinie_m(k.lat, k.lon, s.lat, s.lon) * schule.umweg_faktor
    return d


def teile_ein(schule: Schule, kinder: list[Kind], zeitlimit: float = 60) -> Einteilung:
    warnungen: list[str] = []
    dist = schulwege(schule, kinder)
    w = schule.gewichte

    # ---------------- Schritt A ----------------
    m = cp_model.CpModel()
    x = {}  # (kind, schulhaus) -> bool
    for k in kinder:
        if k.jahrgang not in schule.jahrgaenge:
            raise ValueError(f"Kind {k.id}: unbekannter Jahrgang '{k.jahrgang}'")
        if k.schulhaus_fix:
            erlaubt = [schule.schulhaus(k.schulhaus_fix).name]
        else:
            erlaubt = [s.name for s in schule.schulhaeuser
                       if dist[k.id, s.name] <= schule.max_schulweg(k.jahrgang)]
        if not erlaubt:
            naechstes = min(schule.schulhaeuser, key=lambda s: dist[k.id, s.name]).name
            warnungen.append(f"{k.id}: kein Schulhaus innerhalb max. Schulweg – nächstes ({naechstes}) zugelassen")
            erlaubt = [naechstes]
        for s in erlaubt:
            x[k.id, s] = m.new_bool_var(f"x_{k.id}_{s}")
        m.add_exactly_one(x[k.id, s] for s in erlaubt)

    y = {}   # (schulhaus, raumindex, vorlagenindex) -> bool
    n = {}   # (schulhaus, raumindex, vorlagenindex, jahrgang) -> int
    kosten = []
    for s in schule.schulhaeuser:
        vorheriger: dict[tuple[str, int], list] = {}
        for ri, raum in enumerate(s.raeume):
            optionen = []
            for vi, v in enumerate(schule.vorlagen):
                if v.raumtyp != raum.typ or (v.schulhaeuser and s.name not in v.schulhaeuser):
                    continue
                cap = min(v.max, raum.plaetze)
                if cap < v.min:
                    continue
                yv = m.new_bool_var(f"y_{s.name}_{ri}_{vi}")
                y[s.name, ri, vi] = yv
                optionen.append(yv)
                for j in v.jahrgaenge:
                    nv = m.new_int_var(0, cap, f"n_{s.name}_{ri}_{vi}_{j}")
                    n[s.name, ri, vi, j] = nv
                    m.add(nv >= v.min_pro_jahrgang * yv)
                groesse = sum(n[s.name, ri, vi, j] for j in v.jahrgaenge)
                m.add(groesse >= v.min * yv)
                m.add(groesse <= cap * yv)
                abw = m.new_int_var(0, cap, f"abw_{s.name}_{ri}_{vi}")
                m.add(abw >= groesse - v.ideal * yv)
                m.add(abw >= v.ideal * yv - groesse)
                kosten += [(w["klasse"] + v.strafe) * yv, w["groessen_abweichung"] * abw]
            if optionen:
                m.add_at_most_one(optionen)
                # Symmetriebrechung: gleichwertige Räume werden der Reihe nach belegt
                gleich = (raum.typ, raum.plaetze)
                if gleich in vorheriger:
                    m.add(sum(optionen) <= sum(vorheriger[gleich]))
                vorheriger[gleich] = optionen

    # Kinder je Schulhaus und Jahrgang = Plätze in den Klassen dieses Jahrgangs
    for s in schule.schulhaeuser:
        for j in schule.jahrgaenge:
            kinder_sj = [x[k.id, s.name] for k in kinder if k.jahrgang == j and (k.id, s.name) in x]
            plaetze_sj = [nv for (sn, _, _, jj), nv in n.items() if sn == s.name and jj == j]
            m.add(sum(kinder_sj) == sum(plaetze_sj))

    # Spezialräume (Turnhalle, Werkraum, …): Lektionen pro Woche dürfen die freien
    # Raum-Zeitfenster am jeweiligen Ort nicht übersteigen.
    bedarf = defaultdict(list)
    for (sn, ri, vi), yv in y.items():
        tafel = tafel_fuer_vorlage(schule, schule.vorlagen[vi])
        for fach, lekt in tafel.items():
            typ = schule.faecher[fach].raumtyp
            if typ != "Klassenzimmer" and lekt:
                ort = schule.schulhaus(sn).nutzt.get(typ, sn)
                bedarf[ort, typ].append(lekt * yv)
    for (ort, typ), terme in bedarf.items():
        sh = schule.schulhaus(ort)
        kapazitaet = sum(1 for r in sh.raeume if r.typ == typ for sl in schule.slots
                         if sl.index not in r.nicht_verfuegbar and sl.index not in sh.nicht_verfuegbar)
        m.add(sum(terme) <= kapazitaet)

    if schule.max_klassen:
        m.add(sum(y.values()) <= schule.max_klassen)

    for (kid, s), xv in x.items():
        kosten.append(round(dist[kid, s] * w["schulweg_pro_km"] / 1000) * xv)

    familien = defaultdict(list)
    for k in kinder:
        if k.familie:
            familien[k.familie].append(k.id)
    for fam, ids in familien.items():
        if len(ids) < 2:
            continue
        e = {}
        for s in schule.schulhaeuser:
            vars_s = [x[i, s.name] for i in ids if (i, s.name) in x]
            if not vars_s:
                continue
            e[s.name] = m.new_bool_var(f"fam_{fam}_{s.name}")
            for v in vars_s:
                m.add_implication(v, e[s.name])
        kosten.append(w["geschwister_getrennt"] * (sum(e.values()) - 1))

    m.minimize(sum(kosten))
    sol, info_a = loese(m, "Klasseneinteilung A (Schulhaus/Klassen)", zeitlimit * 0.6)

    schulhaus_von = {kid: s for (kid, s), xv in x.items() if sol.value(xv)}
    klassen: list[Klasse] = []
    zaehler: dict[tuple[str, str], int] = defaultdict(int)
    for (sn, ri, vi), yv in sorted(y.items(), key=lambda t: (t[0][0], schule.vorlagen[t[0][2]].jahrgaenge[0], t[0][1])):
        if not sol.value(yv):
            continue
        sh = schule.schulhaus(sn)
        v = schule.vorlagen[vi]
        anz = {j: sol.value(n[sn, ri, vi, j]) for j in v.jahrgaenge}
        stufe = v.bezeichnung or "/".join(j for j in v.jahrgaenge if anz[j] > 0)
        zaehler[sn, stufe] += 1
        name = f"{sh.kuerzel} {stufe}{chr(ord('a') + zaehler[sn, stufe] - 1)}"
        klassen.append(Klasse(name, sn, sh.raeume[ri], v, anz))

    # ---------------- Schritt B ----------------
    klasse_von: dict[str, str] = {}
    infos = [info_a]
    nach_kind = {k.id: k for k in kinder}
    for sh in schule.schulhaeuser:
        ks = [k for k in kinder if schulhaus_von[k.id] == sh.name]
        kl = [c for c in klassen if c.schulhaus == sh.name]
        if not ks:
            continue
        info_b = _verteile_kinder(schule, ks, kl, nach_kind, zeitlimit * 0.4 / len(schule.schulhaeuser))
        infos.append(info_b)
        for c in kl:
            for kid in c.kinder:
                klasse_von[kid] = c.name

    return Einteilung(klassen, schulhaus_von, klasse_von,
                      {kid: dist[kid, s] for kid, s in schulhaus_von.items()}, infos, warnungen)


def _verteile_kinder(schule: Schule, ks: list[Kind], kl: list[Klasse],
                     nach_kind: dict[str, Kind], zeitlimit: float) -> Loesungsinfo:
    w = schule.gewichte
    m = cp_model.CpModel()
    z = {}
    for k in ks:
        moegliche = [ci for ci, c in enumerate(kl) if c.anzahl_pro_jahrgang.get(k.jahrgang, 0) > 0]
        for ci in moegliche:
            z[k.id, ci] = m.new_bool_var(f"z_{k.id}_{ci}")
        m.add_exactly_one(z[k.id, ci] for ci in moegliche)

    kosten = []
    for ci, c in enumerate(kl):
        for j, anzahl in c.anzahl_pro_jahrgang.items():
            if anzahl == 0:
                continue
            kj = [k for k in ks if k.jahrgang == j]
            m.add(sum(z[k.id, ci] for k in kj) == anzahl)
            for merkmal, gewicht in ((lambda k: k.geschlecht == "w", w["geschlecht_ungleich"]),
                                     (lambda k: k.foerderbedarf, w["foerderbedarf_ungleich"])):
                gruppe = [k for k in kj if merkmal(k)]
                if not gruppe:
                    continue
                ziel = round(len(gruppe) * anzahl / len(kj))
                abw = m.new_int_var(0, anzahl, "abw")
                summe = sum(z[k.id, ci] for k in gruppe)
                m.add(abw >= summe - ziel)
                m.add(abw >= ziel - summe)
                kosten.append(gewicht * abw)

    ids = {k.id for k in ks}
    for k in ks:
        for anderer in k.nicht_mit:
            if anderer not in ids or anderer < k.id and k.id in nach_kind[anderer].nicht_mit:
                continue  # anderes Schulhaus oder Paar bereits erfasst
            for ci in range(len(kl)):
                if (k.id, ci) in z and (anderer, ci) in z:
                    verletzt = m.new_bool_var("nm")
                    m.add(z[k.id, ci] + z[anderer, ci] <= 1 + verletzt)
                    kosten.append(w["nicht_zusammen"] * verletzt)

    m.minimize(sum(kosten))
    sol, info = loese(m, f"Klasseneinteilung B ({kl[0].schulhaus})", max(zeitlimit, 2))
    for (kid, ci), zv in z.items():
        if sol.value(zv):
            kl[ci].kinder.append(kid)
    return info

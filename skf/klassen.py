# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Klasseneinteilung in zwei exakten Schritten.

Schritt A (Schulhaus & Klassen): Jedes Kind wird einem Schulhaus zugeteilt und in
jedem Schulzimmer wird höchstens eine Klasse eröffnet (mit erlaubtem Klassentyp).
Gezählt wird nur, wie viele Kinder welchen Jahrgangs in jede Klasse kommen – das
macht das Modell klein und symmetriefrei. Ziel: kurze Schulwege, wenige Klassen,
Klassengrössen nahe am Ideal, Geschwister im selben Schulhaus.

Schritt B (Kinder auf Parallelklassen): Pro Schulhaus werden die konkreten Kinder
auf die eröffneten Klassen verteilt (Anzahl je Jahrgang aus Schritt A), so dass
Geschlecht und Förderbedarf ausgeglichen sind, Wünsche der Erziehungsberechtigten
("zusammen mit", "nicht zusammen mit") möglichst erfüllt werden und niemand als einziges
Kind aus seiner bisherigen Klasse bzw. Kindergartengruppe kommt (Gspänli-Regel).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .daten import Kind, Raum, Schule, Vorlage
from .geo import luftlinie_m
from .solver import Loesungsinfo, Regeln, cp_model, loese_mit_regeln


@dataclass
class Klasse:
    name: str
    schulhaus: str
    raum: Raum
    vorlage: Vorlage
    anzahl_pro_jahrgang: dict[str, int]
    kinder: list[str] = field(default_factory=list)
    is_pro_jahrgang: dict[str, int] = field(default_factory=dict)  # IS-Kinder je Jahrgang (aus Schritt A)

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
        for fach, lekt in (schule.tafel(j) or {}).items():
            tafel[fach] = max(tafel.get(fach, 0), lekt)
    return tafel


def schulwege(schule: Schule, kinder: list[Kind]) -> dict[tuple[str, str], float]:
    d = {}
    for k in kinder:
        if k.lat is None or k.lon is None:  # ohne Adresse: Schulweg spielt keine Rolle (Vorprüfung warnt)
            for s in schule.schulhaeuser:
                d[k.id, s.name] = 0.0
            continue
        for s in schule.schulhaeuser:
            d[k.id, s.name] = luftlinie_m(k.lat, k.lon, s.lat, s.lon) * schule.umweg_faktor
    return d


def moegliche_schulhaeuser(schule: Schule, k: Kind) -> list[str]:
    """Schulhäuser mit einem Klassentyp für den Jahrgang des Kindes – und einem Raum dafür."""
    return [s.name for s in schule.schulhaeuser
            if (s.stufen is None or k.jahrgang in s.stufen)
            and any(k.jahrgang in v.jahrgaenge and (not v.schulhaeuser or s.name in v.schulhaeuser)
                   and any(r.typ == v.raumtyp for r in s.raeume)
                   for v in schule.vorlagen)]


def geschwistergruppen(schule: Schule, kinder: list[Kind]) -> dict[str, list[list[str]]]:
    """Familie → Gruppen von Geschwistern, die überhaupt im selben Schulhaus sein können
    (z.B. Primar und Oberstufe in getrennten Schulhäusern bilden je eine eigene Gruppe)."""
    familien = defaultdict(list)
    for k in kinder:
        if k.familie:
            familien[k.familie].append(k)
    out = {}
    for fam, ks in familien.items():
        # jede Gruppe hat mindestens ein Schulhaus, das alle ihre Kinder führen kann (Schnittmenge, keine Kette:
        # KG nur in A/B, 1. Klasse nur in C, 2. Klasse in B/C wären sonst eine Gruppe ohne gemeinsames Schulhaus)
        gruppen: list[tuple[set[str], list[str]]] = []
        orte_von = {k.id: set(moegliche_schulhaeuser(schule, k)) for k in ks}
        for k in sorted(ks, key=lambda k: (len(orte_von[k.id]), k.id)):
            orte = orte_von[k.id]
            treffer = next((g for g in gruppen if g[0] & orte), None)
            if treffer:
                gruppen[gruppen.index(treffer)] = (treffer[0] & orte, treffer[1] + [k.id])
            else:
                gruppen.append((set(orte), [k.id]))
        out[fam] = [sorted(g[1]) for g in gruppen]
    return out


def teile_ein(schule: Schule, kinder: list[Kind], zeitlimit: float = 60,
              andere_als: list[dict[tuple[str, int], int]] | None = None) -> Einteilung:
    """Klassen bilden und Lernende zuteilen.

    ``andere_als``: Klassenmuster (Anzahl Klassen je Schulhaus und Klassentyp), die nicht noch
    einmal gewählt werden dürfen – Rückkopplung, wenn mit einem Muster keine Lehraufträge möglich sind."""
    warnungen: list[str] = []
    dist = schulwege(schule, kinder)
    w = schule.gewichte

    # ---------------- Schritt A ----------------
    m = cp_model.CpModel()
    regeln = Regeln(m)
    x = {}  # (kind, schulhaus) -> bool
    for k in kinder:
        if k.jahrgang not in schule.jahrgaenge:
            raise ValueError(f"Kind {k.id}: unbekannter Jahrgang '{k.jahrgang}'")
        moegliche = moegliche_schulhaeuser(schule, k)
        linie = schule.buslinie(k.bus) if k.bus else None
        if linie:  # Schulbus ersetzt den Fussweg: nur Schulhäuser, die die Linie anfährt
            nah = [s for s in moegliche if s in linie.schulhaeuser]
            grund = f"Schulbus {linie.name}: nur angefahrene Schulhäuser"
            if not nah:
                warnungen.append(f"{k.id}: Buslinie {linie.name} fährt kein passendes Schulhaus an – "
                                 "max. Schulweg gilt")
        if not linie or not nah:
            nah = [s for s in moegliche if dist[k.id, s] <= schule.max_schulweg(k.jahrgang)]
            grund = f"Max. Schulweg Jahrgang {k.jahrgang} ({schule.max_schulweg(k.jahrgang)} m)"
        if not nah and moegliche:
            naechstes = min(moegliche, key=lambda s: dist[k.id, s])
            warnungen.append(f"{k.id}: kein Schulhaus innerhalb max. Schulweg – nächstes ({naechstes}) zugelassen")
            nah = [naechstes]
        for s in moegliche:
            x[k.id, s] = m.new_bool_var(f"x_{k.id}_{s}")
            if s not in nah:
                regeln.nur_wenn(m.add(x[k.id, s] == 0), grund)
            if k.schulhaus_fix and s != k.schulhaus_fix:
                regeln.nur_wenn(m.add(x[k.id, s] == 0), "Fixe Schulhaus-Zuteilungen")
        m.add_exactly_one(x[k.id, s] for s in moegliche)

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
                if s.stufen is not None and not set(v.jahrgaenge) & set(s.stufen):
                    continue
                cap = min(v.max, raum.plaetze)
                if cap < v.min:
                    continue
                # notwendig: der Raum ist mindestens so oft offen, wie die Klasse Lektionen im Schulzimmer hat
                im_zimmer = sum(l for f, l in tafel_fuer_vorlage(schule, v).items()
                                if schule.faecher[f].raumtyp == "Klassenzimmer") if v.raumtyp == "Klassenzimmer" else 0
                offen = sum(1 for sl in schule.slots if sl.index not in raum.nicht_verfuegbar
                            and sl.index not in s.nicht_verfuegbar)
                if offen < im_zimmer:
                    continue
                name_v = v.bezeichnung or "/".join(v.jahrgaenge)
                yv = m.new_bool_var(f"y_{s.name}_{ri}_{vi}")
                y[s.name, ri, vi] = yv
                optionen.append(yv)
                gross = max(v.max, raum.plaetze) * 2
                for j in v.jahrgaenge:
                    nv = m.new_int_var(0, gross, f"n_{s.name}_{ri}_{vi}_{j}")
                    n[s.name, ri, vi, j] = nv
                    if v.min_pro_jahrgang:
                        regeln.nur_wenn(m.add(nv >= v.min_pro_jahrgang * yv),
                                        f"Mehrjahrgangsklasse {name_v}: mind. {v.min_pro_jahrgang} Lernende pro Jahrgang")
                groesse = sum(n[s.name, ri, vi, j] for j in v.jahrgaenge)
                m.add(groesse <= gross * yv)
                regeln.nur_wenn(m.add(groesse >= v.min * yv), f"Mindestgrösse Klassen {name_v} ({v.min})")
                regeln.nur_wenn(m.add(groesse <= cap * yv), f"Höchstgrösse Klassen {name_v} ({v.max}) bzw. Raumgrösse")
                abw = m.new_int_var(0, gross, f"abw_{s.name}_{ri}_{vi}")
                m.add(abw >= groesse - v.ideal * yv)
                m.add(abw >= v.ideal * yv - groesse)
                kosten += [(w["klasse"] + v.strafe) * yv, w["groessen_abweichung"] * abw]
                if raum.nicht_verfuegbar:  # bei Gleichstand frei verfügbare Räume bevorzugen
                    kosten.append(len(raum.nicht_verfuegbar) * yv)
            if optionen:
                m.add_at_most_one(optionen)
                # Symmetriebrechung: gleichwertige Räume werden der Reihe nach belegt
                # gleichwertig nur bei gleicher Verfügbarkeit (ein zeitweise gesperrter Raum ist nicht austauschbar)
                gleich = (raum.typ, raum.plaetze, frozenset(raum.nicht_verfuegbar))
                if gleich in vorheriger:
                    m.add(sum(optionen) <= sum(vorheriger[gleich]))
                vorheriger[gleich] = optionen

    # Kinder je Schulhaus und Jahrgang = Plätze in den Klassen dieses Jahrgangs
    for s in schule.schulhaeuser:
        for j in schule.jahrgaenge:
            kinder_sj = [x[k.id, s.name] for k in kinder if k.jahrgang == j and (k.id, s.name) in x]
            plaetze_sj = [nv for (sn, _, _, jj), nv in n.items() if sn == s.name and jj == j]
            if kinder_sj or plaetze_sj:  # benannt: die Konfliktanalyse kann fehlende Plätze nennen
                regeln.nur_wenn(m.add(sum(kinder_sj) == sum(plaetze_sj)), f"Plätze für Jahrgang {j} in {s.name}")

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
        regeln.nur_wenn(m.add(sum(terme) <= kapazitaet),
                        f"Kapazität {typ} in {ort} ({kapazitaet} Lektionen/Woche)")

    if schule.max_klassen:
        regeln.nur_wenn(m.add(sum(y.values()) <= schule.max_klassen), f"Max. {schule.max_klassen} Klassen")

    nach_id = {k.id: k for k in kinder}
    for (kid, s), xv in x.items():
        kosten.append(round(dist[kid, s] * w["schulweg_pro_km"] / 1000) * xv)
        bisher = nach_id[kid].bisheriges_schulhaus
        if bisher and bisher != s and any(sh.name == bisher for sh in schule.schulhaeuser):
            kosten.append(w["schulhaus_gewechselt"] * xv)  # Kontinuität: Schulhaus aus dem Vorjahr
        wunsch = nach_id[kid].wunsch_schulhaus
        if wunsch and wunsch != s and any(sh.name == wunsch for sh in schule.schulhaeuser):
            kosten.append(w["wunsch_schulhaus"] * xv)  # Wunsch-Schulhaus der Erziehungsberechtigten

    # Wunsch "zusammen mit": beide Kinder im selben Schulhaus (Klasse folgt in Schritt B)
    for a, b in _wunschpaare(kinder):
        orte = {s for (kid, s) in x if kid in (a, b)}
        getrennt = m.new_bool_var(f"wz_{a}_{b}")
        for s_ in orte:
            m.add(getrennt >= x.get((a, s_), 0) - x.get((b, s_), 0))
        kosten.append(w["wunsch_zusammen"] * getrennt)

    # Integrative Sonderschulung: IS-Kinder zählen bei der Klassengrösse ggf. mehrfach
    # und es gibt höchstens max_is_pro_klasse IS-Kinder pro Klasse (Feinverteilung in Schritt B).
    # Integrative Sonderschulung: pro Klasse wird festgelegt, wie viele IS-Kinder je Jahrgang
    # hineinkommen; sie zählen bei der Klassengrösse is_zaehlt_als-fach.
    is_n = {}  # (schulhaus, raumindex, vorlagenindex, jahrgang) -> int
    if any(k.is_ for k in kinder):
        zusatz = round((schule.is_zaehlt_als - 1) * 100)  # in Hundertsteln: 1.25 → 25, 1.05 → 5 (exakt)
        for (sn, ri, vi), yv in y.items():
            v = schule.vorlagen[vi]
            cap = min(v.max, schule.schulhaus(sn).raeume[ri].plaetze)
            for j in v.jahrgaenge:
                is_n[sn, ri, vi, j] = m.new_int_var(0, cap, f"is_{sn}_{ri}_{vi}_{j}")
                m.add(is_n[sn, ri, vi, j] <= n[sn, ri, vi, j])
            summe_is = sum(is_n[sn, ri, vi, j] for j in v.jahrgaenge)
            if zusatz > 0:
                groesse = sum(n[sn, ri, vi, j] for j in v.jahrgaenge)
                regeln.nur_wenn(m.add(100 * groesse + zusatz * summe_is <= 100 * cap * yv),
                                f"IS zählt {schule.is_zaehlt_als:g}-fach bei der Klassengrösse")
            if schule.max_is_pro_klasse is not None:
                regeln.nur_wenn(m.add(summe_is <= schule.max_is_pro_klasse * yv),
                                f"Max. {schule.max_is_pro_klasse} IS-Lernende pro Klasse")
        for sh in schule.schulhaeuser:
            for j in schule.jahrgaenge:
                is_sj = [xv for (kid, sn), xv in x.items()
                         if sn == sh.name and nach_id[kid].is_ and nach_id[kid].jahrgang == j]
                plaetze = [iv for (sn, _, _, jj), iv in is_n.items() if sn == sh.name and jj == j]
                m.add(sum(is_sj) == sum(plaetze))

    for fam, ids in ((f"{f}_{n}", g) for f, gs in geschwistergruppen(schule, kinder).items()
                     for n, g in enumerate(gs)):
        if len(ids) < 2 or schule.geschwister == "aus":
            continue
        e = {}
        for s in schule.schulhaeuser:
            vars_s = [x[i, s.name] for i in ids if (i, s.name) in x]
            if not vars_s:
                continue
            e[s.name] = m.new_bool_var(f"fam_{fam}_{s.name}")
            for v in vars_s:
                m.add_implication(v, e[s.name])
            if schule.geschwister == "hart":
                # alle Geschwister im selben Schulhaus: wer dort nicht hin kann, sperrt es
                for i in ids:
                    if (i, s.name) in x:
                        regeln.nur_wenn(m.add(x[i, s.name] == e[s.name]), "Geschwister im selben Schulhaus")
                    else:
                        regeln.nur_wenn(m.add(e[s.name] == 0), "Geschwister im selben Schulhaus")
        if schule.geschwister == "hart":
            regeln.nur_wenn(m.add(sum(e.values()) <= 1), "Geschwister im selben Schulhaus")
        else:
            kosten.append(w["geschwister_getrennt"] * (sum(e.values()) - 1))

    m.minimize(sum(kosten))
    for muster in andere_als or []:  # mindestens eine Anzahl (Schulhaus, Klassentyp) muss sich ändern
        abweichung = []
        for (sn, vi), anzahl in {**{(sn, vi): 0 for sn, _, vi in y}, **muster}.items():
            terme = [yv for (s2, _, v2), yv in y.items() if s2 == sn and v2 == vi]
            if terme:
                b = m.new_bool_var(f"anders_{sn}_{vi}")
                m.add(sum(terme) != anzahl).only_enforce_if(b)
                abweichung.append(b)
        regeln.nur_wenn(m.add_bool_or(abweichung), "Andere Klasseneinteilung als die bereits geprüften")
    sol, info_a = loese_mit_regeln(m, regeln, "Klassenbildung A (Schulhaus und Klassen)", zeitlimit * 0.6)

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
        klassen.append(Klasse(name, sn, sh.raeume[ri], v, anz,
                              is_pro_jahrgang={j: sol.value(is_n[sn, ri, vi, j]) for j in v.jahrgaenge
                                               if (sn, ri, vi, j) in is_n}))

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
    regeln = Regeln(m)
    z = {}
    for k in ks:
        moegliche = [ci for ci, c in enumerate(kl) if c.anzahl_pro_jahrgang.get(k.jahrgang, 0) > 0]
        for ci in moegliche:
            z[k.id, ci] = m.new_bool_var(f"z_{k.id}_{ci}")
        m.add_exactly_one(z[k.id, ci] for ci in moegliche)

    kosten = []
    ausgleich = [(lambda k: k.geschlecht == "w", w["geschlecht_ungleich"])] + [
        (lambda k, mm=mm: k.hat(mm), w["foerderbedarf_ungleich"]) for mm in schule.ausgleich]
    for ci, c in enumerate(kl):
        # IS: höchstens max_is_pro_klasse, und gewichtete Grösse innerhalb der Raum-/Klassengrenze
        for j, anzahl_is in c.is_pro_jahrgang.items():  # Anzahl IS-Kinder je Jahrgang aus Schritt A
            is_cj = [z[k.id, ci] for k in ks if k.is_ and k.jahrgang == j and (k.id, ci) in z]
            regeln.nur_wenn(m.add(sum(is_cj) == anzahl_is), "IS-Verteilung aus Schritt A")
        for j, anzahl in c.anzahl_pro_jahrgang.items():
            if anzahl == 0:
                continue
            kj = [k for k in ks if k.jahrgang == j]
            m.add(sum(z[k.id, ci] for k in kj) == anzahl)
            for merkmal, gewicht in ausgleich:
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

    # Wunsch "zusammen mit": in dieselbe Klasse, sofern beide dort möglich sind
    for a, b in _wunschpaare(ks):
        gemeinsam = [ci for ci in range(len(kl)) if (a, ci) in z and (b, ci) in z]
        if not gemeinsam:
            continue
        zusammen = []
        for ci in gemeinsam:
            beide = m.new_bool_var("zus")
            m.add(beide <= z[a, ci])
            m.add(beide <= z[b, ci])
            zusammen.append(beide)
        kosten.append(w["wunsch_zusammen"] * (1 - sum(zusammen)))

    # Kontinuität: Kinder einer bisherigen Klasse (z.B. KG-Gruppe) möglichst zusammen lassen
    bisher = defaultdict(list)
    for k in ks:
        if k.bisherige_klasse:
            bisher[k.bisherige_klasse].append(k)
    for name, gruppe in bisher.items():
        if len(gruppe) < 2:
            continue
        # Gspänli-Regel: niemand als einziges Kind seiner bisherigen Klasse in der neuen Klasse
        for k in gruppe:
            allein = m.new_bool_var("allein")
            for ci in range(len(kl)):
                if (k.id, ci) in z:
                    andere = [z[o.id, ci] for o in gruppe if o.id != k.id and (o.id, ci) in z]
                    m.add(allein >= z[k.id, ci] - sum(andere))
            kosten.append(w["allein_aus_klasse"] * allein)
        genutzt = []
        for ci in range(len(kl)):
            vars_c = [z[k.id, ci] for k in gruppe if (k.id, ci) in z]
            if vars_c:
                u = m.new_bool_var("bk")
                for v in vars_c:
                    m.add_implication(v, u)
                genutzt.append(u)
        kosten.append(w["klasse_getrennt"] * (sum(genutzt) - 1))

    m.minimize(sum(kosten))
    sol, info = loese_mit_regeln(m, regeln, f"Klassenbildung B (Zuteilung {kl[0].schulhaus})", max(zeitlimit, 2))
    for (kid, ci), zv in z.items():
        if sol.value(zv):
            kl[ci].kinder.append(kid)
    return info


def _wunschpaare(kinder: list[Kind]) -> list[tuple[str, str]]:
    """Paare aus "zusammen_mit" (ungeordnet, ohne Doppelte, nur vorhandene Kinder)."""
    ids = {k.id for k in kinder}
    paare = set()
    for k in kinder:
        for anderer in k.zusammen_mit:
            if anderer in ids and anderer != k.id:
                paare.add(tuple(sorted((k.id, anderer))))
    return sorted(paare)


def klassenmuster(schule: Schule, e: Einteilung) -> dict[tuple[str, int], int]:
    """Anzahl Klassen je (Schulhaus, Klassentyp-Index) – für ``teile_ein(andere_als=…)``."""
    muster: dict[tuple[str, int], int] = {}
    for c in e.klassen:
        schluessel = (c.schulhaus, next(i for i, v in enumerate(schule.vorlagen) if v is c.vorlage))
        muster[schluessel] = muster.get(schluessel, 0) + 1
    return muster

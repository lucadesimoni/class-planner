# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Empfehlungen für Schulleitung und Behörden: Lehrpersonen, Verfügbarkeiten, Räume, Ausbau.

Alle Auswertungen beruhen auf dem berechneten Ergebnis und sind bewusst einfach
nachvollziehbar (Zählungen, keine Blackbox):

* Pensenbilanz pro Schulhaus und Fach: Bedarf, freie Pensen qualifizierter Lehrpersonen
* Stellvertretungsreserve: verfügbare, aber nicht unterrichtende Lehrpersonen pro Halbtag
* Verfügbarkeiten: welche Teilzeit-Lehrperson an knappen Halbtagen fehlt
* Raumauslastung: Schulzimmer und Spezialräume
* Prognose: Lernende und benötigte Klassen/Schulzimmer der nächsten Schuljahre
  (Jahrgänge rücken nach, neue KG1-Jahrgänge aus Durchschnitt und Wachstum)
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .daten import Kind, Schule


@dataclass
class Empfehlung:
    bereich: str          # Lehrpersonen | Verfügbarkeit | Räume | Ausbau
    titel: str
    text: str
    dringlich: bool = False


@dataclass
class Planung:
    empfehlungen: list[Empfehlung] = field(default_factory=list)
    pensenbilanz: list[dict] = field(default_factory=list)
    reserve: list[dict] = field(default_factory=list)
    raeume: list[dict] = field(default_factory=list)
    prognose: list[dict] = field(default_factory=list)


def _schuljahr_plus(schuljahr: str, n: int) -> str:
    m = re.match(r"(\d{4})\s*/\s*(\d{2,4})", schuljahr or "")
    if not m:
        return f"+{n} Jahr{'e' if n > 1 else ''}"
    a = int(m.group(1)) + n
    return f"{a}/{str(a + 1)[-2:]}"


def plane(schule: Schule, kinder: list[Kind], ergebnis) -> Planung:
    p = Planung()
    e = ergebnis.einteilung
    if not e:
        return p
    _pensenbilanz(schule, ergebnis, p)
    if ergebnis.lektionen:
        _reserve(schule, ergebnis, p)
    _raeume(schule, ergebnis, p)
    _prognose(schule, kinder, ergebnis, p)
    return p


def _pensenbilanz(schule: Schule, r, p: Planung) -> None:
    last = Counter()
    for b in r.bloecke:
        last[b.lehrperson] += b.lektionen
    bedarf = Counter((b.schulhaus, b.fach) for b in r.bloecke for _ in range(b.lektionen))
    for (sh, fach), lekt in sorted(bedarf.items()):
        qualifiziert = [lp for lp in schule.lehrpersonen if fach in lp.faecher
                        and (lp.schulhaeuser is None or sh in lp.schulhaeuser)]
        frei = sum(max(0, lp.pensum_max - last[lp.name]) for lp in qualifiziert)
        p.pensenbilanz.append({"Schulhaus": sh, "Fach": fach, "Bedarf (L)": lekt,
                               "Lehrpersonen": len(qualifiziert), "freie Pensen (L)": frei})
        if frei < max(2, 0.1 * lekt):
            p.empfehlungen.append(Empfehlung(
                "Lehrpersonen", f"Knappe Reserve {fach} in {sh}",
                f"{lekt} Lektionen {fach} benötigt, qualifizierte Lehrpersonen haben nur noch {frei} Lektionen frei. "
                f"Für Ausfälle und Wachstum eine weitere Lehrperson mit {fach} (Teilpensum) suchen.", frei == 0))
    for lp in schule.lehrpersonen:
        if last[lp.name] < lp.pensum_min:
            p.empfehlungen.append(Empfehlung(
                "Lehrpersonen", f"{lp.name}: Pensum nicht ausgeschöpft",
                f"{last[lp.name]} statt mindestens {lp.pensum_min} Lektionen. Möglich: zusätzliche Fächer "
                f"({', '.join(lp.faecher[:4])}), Einsatz in einem weiteren Schulhaus oder Stellvertretungspool."))


def _reserve(schule: Schule, r, p: Planung) -> None:
    """Stellvertretungsreserve: verfügbare Lehrpersonen eines Schulhauses, die nicht unterrichten."""
    unterrichtet = defaultdict(set)
    for l in r.lektionen:
        unterrichtet[l.slot].add(l.lehrperson)
    orte = defaultdict(set)
    for b in r.bloecke:
        orte[b.lehrperson].add(b.schulhaus)
    knapp = []
    for sh in schule.schulhaeuser:
        team = [lp for lp in schule.lehrpersonen if sh.name in orte[lp.name]]
        if not team:
            continue
        for tag, ht in schule.halbtage():
            slots = [s for s in schule.slots if s.tag == tag and s.halbtag == ht]
            frei_min = min(sum(1 for lp in team if s.index not in lp.nicht_verfuegbar
                               and lp.name not in unterrichtet[s.index]) for s in slots)
            fehlen = sorted(lp.name for lp in team if all(s.index in lp.nicht_verfuegbar for s in slots))
            p.reserve.append({"Schulhaus": sh.name, "Halbtag": f"{tag}-{ht}", "Reserve": frei_min,
                              "abwesend (Teilzeit)": ", ".join(fehlen)})
            if frei_min <= 1:
                knapp.append((sh.name, tag, ht, frei_min, fehlen))
    pro_schulhaus = defaultdict(list)
    for sh, tag, ht, frei, fehlen in knapp:
        pro_schulhaus[sh].append((tag, ht, frei, fehlen))
    for sh, eintraege in pro_schulhaus.items():
        null = [f"{t}-{h}" for t, h, frei, _ in eintraege if frei == 0]
        text = (f"An {len(eintraege)} Halbtagen ({', '.join(f'{t}-{h}' for t, h, _, _ in eintraege)}) ist in {sh} "
                f"zeitweise höchstens eine Lehrperson verfügbar, die nicht unterrichtet"
                f"{f' (keine: {chr(44).join(null)})' if null else ''}. Für Ausfälle externe Stellvertretungen "
                "einplanen oder Teilpensen so legen, dass an jedem Halbtag eine Lehrperson Reserve hat.")
        abwesend = Counter(name for _, _, _, fehlen in eintraege for name in fehlen)
        if abwesend:
            text += " Grösste Wirkung hätte mehr Verfügbarkeit von: " + ", ".join(
                f"{n} ({k} Halbtage)" for n, k in abwesend.most_common(3)) + "."
        p.empfehlungen.append(Empfehlung("Verfügbarkeit", f"Stellvertretungsreserve in {sh}", text, bool(null)))


def _raeume(schule: Schule, r, p: Planung) -> None:
    e = r.einteilung
    belegt = Counter((l.raum_ort, l.raum) for l in r.lektionen if l.raum)
    for sh in schule.schulhaeuser:
        typen = defaultdict(list)
        for raum in sh.raeume:
            typen[raum.typ].append(raum)
        for typ, raeume in typen.items():
            stamm = sum(1 for c in e.klassen if c.schulhaus == sh.name and c.raum.typ == typ)
            if stamm or any(v.raumtyp == typ for v in schule.vorlagen):
                quote = stamm / len(raeume)
                p.raeume.append({"Schulhaus": sh.name, "Raumtyp": typ, "Räume": len(raeume),
                                 "genutzt": f"{stamm} als Schulzimmer", "Auslastung": round(100 * quote)})
                if quote >= 1:
                    p.empfehlungen.append(Empfehlung(
                        "Räume", f"{sh.name}: alle Räume vom Typ {typ} belegt",
                        f"{'Der einzige Raum' if len(raeume) == 1 else f'Alle {len(raeume)} Räume'} vom Typ {typ} "
                        f"{'ist' if len(raeume) == 1 else 'sind'} Schulzimmer einer Klasse. Ohne Reserve für "
                        "zusätzliche Klassen, Gruppen- oder Förderunterricht.", True))
                continue
            if not r.lektionen:
                continue
            kapazitaet = sum(1 for raum in raeume for s in schule.slots
                             if s.index not in raum.nicht_verfuegbar and s.index not in sh.nicht_verfuegbar)
            genutzt = sum(belegt[sh.name, raum.name] for raum in raeume)
            quote = genutzt / kapazitaet if kapazitaet else 0
            p.raeume.append({"Schulhaus": sh.name, "Raumtyp": typ, "Räume": len(raeume),
                             "genutzt": f"{genutzt} von {kapazitaet} Lektionen", "Auslastung": round(100 * quote)})
            if quote >= 0.85:
                p.empfehlungen.append(Empfehlung(
                    "Räume", f"{sh.name}: {typ} zu {100 * quote:.0f}% ausgelastet",
                    f"{genutzt} von {kapazitaet} möglichen Lektionen sind belegt. Zusätzliche {typ}-Kapazität "
                    "(Raum oder Mitbenutzung eines anderen Schulhauses) prüfen.", quote >= 0.95))


def _prognose(schule: Schule, kinder: list[Kind], r, p: Planung, jahre: int = 4) -> None:
    """Jahrgänge rücken nach; neuer KG1-Jahrgang = Durchschnitt aller Jahrgänge x (1 + Wachstum)^n."""
    e = r.einteilung
    planung = getattr(schule, "planung", {}) or {}
    wachstum = float(planung.get("wachstum_prozent", 0)) / 100
    jg = schule.jahrgaenge
    anzahl = Counter(k.jahrgang for k in kinder)
    basis = planung.get("neue_kg1_pro_jahr") or anzahl[jg[0]]  # neuer jüngster Jahrgang wie heute
    anteil = defaultdict(Counter)  # Jahrgang -> Schulhaus -> Anteil (heutige Zuteilung)
    for k in kinder:
        anteil[k.jahrgang][e.schulhaus_von[k.id]] += 1

    def klassen_noetig(n: float, j: str) -> int:
        v = [v for v in schule.vorlagen if j in v.jahrgaenge and len(v.jahrgaenge) == 1] or \
            [v for v in schule.vorlagen if j in v.jahrgaenge]
        return math.ceil(n / max(x.max for x in v)) if v and n > 0 else 0

    stand = {j: float(anzahl[j]) for j in jg}
    for n in range(jahre + 1):
        if n:
            stand = {jg[0]: basis * (1 + wachstum) ** n, **{jg[i]: stand[jg[i - 1]] for i in range(1, len(jg))}}
        for sh in schule.schulhaeuser:
            raumtypen = {raum.typ for raum in sh.raeume} & {v.raumtyp for v in schule.vorlagen
                                                           if not v.schulhaeuser or sh.name in v.schulhaeuser}
            for typ in sorted(raumtypen):
                stufen = [j for j in jg if any(j in v.jahrgaenge and v.raumtyp == typ for v in schule.vorlagen)]
                lernende = 0.0
                klassen = 0
                for j in stufen:
                    gesamt = sum(anteil[j].values()) or 1
                    n_sh = stand[j] * anteil[j][sh.name] / gesamt
                    lernende += n_sh
                    klassen += klassen_noetig(n_sh, j) if len(stufen) > 2 else 0
                if len(stufen) <= 2:  # KG: Jahrgänge gemischt
                    v = [v for v in schule.vorlagen if v.raumtyp == typ]
                    klassen = math.ceil(lernende / max(x.max for x in v)) if lernende else 0
                raeume = sum(1 for raum in sh.raeume if raum.typ == typ)
                p.prognose.append({"Schuljahr": schule.schuljahr if n == 0 and schule.schuljahr else
                                   _schuljahr_plus(schule.schuljahr, n), "Jahr": n, "Schulhaus": sh.name,
                                   "Raumtyp": typ, "Lernende": round(lernende), "Klassen (mind.)": klassen,
                                   "Räume": raeume, "Differenz": raeume - klassen})
    gemeldet = set()
    for zeile in p.prognose:
        schluessel = (zeile["Schulhaus"], zeile["Raumtyp"])
        if zeile["Jahr"] and zeile["Differenz"] < 0 and schluessel not in gemeldet:
            gemeldet.add(schluessel)
            p.empfehlungen.append(Empfehlung(
                "Ausbau", f"{zeile['Schulhaus']}: ab {zeile['Schuljahr']} fehlen {typ_text(zeile)}",
                f"Prognose {zeile['Lernende']} Lernende → mindestens {zeile['Klassen (mind.)']} Klassen, aber nur "
                f"{zeile['Räume']} {'Raum' if zeile['Räume'] == 1 else 'Räume'} vom Typ {zeile['Raumtyp']}. "
                "Ausbau, Provisorium oder Umverteilung auf andere "
                f"Schulhäuser prüfen (Annahme: {wachstum * 100:.1f}% Wachstum pro Jahr, Einzugsgebiete wie heute).",
                zeile["Jahr"] <= 2))


def typ_text(zeile: dict) -> str:
    n = -zeile["Differenz"]
    return f"{n} {'Raum' if n == 1 else 'Räume'} vom Typ {zeile['Raumtyp']}"

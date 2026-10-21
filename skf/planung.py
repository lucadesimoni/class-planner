# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Empfehlungen für Schulleitung und Behörden: Lehrpersonen, Verfügbarkeiten, Räume, Ausbau.

Alle Auswertungen beruhen auf dem berechneten Ergebnis und sind bewusst einfach
nachvollziehbar (Zählungen, keine Blackbox):

* Pensenbilanz pro Schulhaus und Fach: Bedarf, freie Pensen qualifizierter Lehrpersonen
* Stellvertretungsreserve: verfügbare, aber nicht unterrichtende Lehrpersonen pro Halbtag
* Verfügbarkeiten: welche Teilzeit-Lehrperson an knappen Halbtagen fehlt
* Raumauslastung: Schulzimmer und Spezialräume
* Langfristplanung: Lernende, Klassen, Schulzimmer, Stellen und Kosten der nächsten
  Schuljahre (Kohorten nach Stufenfolge, Austritte, Wachstum, Quartierentwicklung)
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .daten import Kind, Schule, stamm


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
    prognose: list[dict] = field(default_factory=list)   # pro Jahr, Schulhaus und Raumtyp
    jahre: list[dict] = field(default_factory=list)      # pro Jahr: Lernende, Klassen, Stellen, Kosten


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


def _fuehrt(schule: Schule, sh, j: str) -> bool:
    """Geht Jahrgang j in diesem Schulhaus zur Schule (Stufen und passender Raum)?"""
    if sh.stufen is not None:
        return j in sh.stufen
    typen = {raum.typ for raum in sh.raeume}
    return any(j in v.jahrgaenge and v.raumtyp in typen and (not v.schulhaeuser or sh.name in v.schulhaeuser)
               for v in schule.vorlagen)


def _ab_jahr(schule: Schule, ab: str) -> int:
    """"2029/30" → Jahre ab dem Planjahr; "2" → 2 Jahre (mindestens 1)."""
    m, heute = re.match(r"\s*(\d{4})", ab), re.match(r"\s*(\d{4})", schule.schuljahr or "")
    if m:
        return max(1, int(m.group(1)) - int(heute.group(1))) if heute else 1
    try:
        return max(1, int(float(ab)))
    except ValueError:
        return 1


def _prognose(schule: Schule, kinder: list[Kind], r, p: Planung) -> None:
    """Kohortenmodell: jede Stufe rückt in ihre nächste(n) Stufe(n) nach (skf.uebertritt.naechste).

    * Verzweigungen (6 → S1A/S1B/S1C) im heutigen Verhältnis der Zielstufen
    * Austritte nach einer Stufe (Kanti, Privatschule …): planung.austritt_prozent
    * neuer jüngster Jahrgang: heutige Grösse (oder planung.neue_kg1_pro_jahr) × (1 + Wachstum)^n
    * Quartierentwicklung: zuziehende Kinder ab einem Schuljahr, gleichmässig über alle Stufen
    * Schulhaus: bleibt, wenn es die nächste Stufe führt, sonst Verteilung wie heute
    """
    from .uebertritt import (
        naechste,  # uebertritt importiert daten → hier lokal, ohne Zyklus
    )

    e = r.einteilung
    planung = schule.planung or {}
    wachstum = float(planung.get("wachstum_prozent", 0)) / 100
    jahre = int(planung.get("jahre", 4))
    austritt = planung.get("austritt_prozent") or {}
    quartiere = planung.get("quartiere") or []
    jg, folge = schule.jahrgaenge, naechste(schule)
    anzahl = Counter(k.jahrgang for k in kinder)
    basis = float(planung.get("neue_kg1_pro_jahr") or anzahl[jg[0]])
    heute: dict[str, Counter] = defaultdict(Counter)  # Jahrgang → Schulhaus → Lernende (Zuteilung)
    for k in kinder:
        if k.id in e.schulhaus_von:
            heute[k.jahrgang][e.schulhaus_von[k.id]] += 1

    def verteile(j: str) -> dict[str, float]:
        if heute[j]:
            gesamt = sum(heute[j].values())
            return {sh: n / gesamt for sh, n in heute[j].items()}
        orte = [sh.name for sh in schule.schulhaeuser if _fuehrt(schule, sh, j)]
        return {sh: 1 / len(orte) for sh in orte}

    def dazu(stand, j: str, sh: str | None, n: float) -> None:
        if sh and _fuehrt(schule, schule.schulhaus(sh), j):
            stand[j, sh] += n
        else:
            for ort, a in verteile(j).items():
                stand[j, ort] += n * a

    def anteile(ziele: list[str]) -> dict[str, float]:
        gesamt = sum(anzahl[z] for z in ziele)
        return {z: (anzahl[z] / gesamt if gesamt else 1 / len(ziele)) for z in ziele}

    def klassen_noetig(n: float, j: str) -> int:
        v = [v for v in schule.vorlagen if j in v.jahrgaenge and len(v.jahrgaenge) == 1] or \
            [v for v in schule.vorlagen if j in v.jahrgaenge]
        return math.ceil(n / max(x.max for x in v) - 1e-9) if v and n > 0.5 else 0

    namen = {sh.name for sh in schule.schulhaeuser}
    stand: dict[tuple[str, str], float] = defaultdict(float)
    for j in jg:
        for sh, n in heute[j].items():
            stand[j, sh] = float(n)
    zuzug = Counter()
    for n in range(jahre + 1):
        if n:
            alt, stand = stand, defaultdict(float)
            for (j, sh), m in alt.items():
                ziele = [z for z in folge.get(j, []) if z in jg]
                if not ziele or m <= 0:
                    continue  # Abschluss
                bleibt = m * (1 - float(austritt.get(j, austritt.get(stamm(j), 0))) / 100)
                for z, a in anteile(ziele).items():
                    dazu(stand, z, sh, bleibt * a)
            for sh, a in verteile(jg[0]).items():
                stand[jg[0], sh] += basis * (1 + wachstum) ** n * a
            for q in quartiere:
                if _ab_jahr(schule, q["ab"]) == n:
                    total = q["kinder"] if q["kinder"] is not None else q["wohnungen"] * q["kinder_pro_wohnung"]
                    zuzug[n] += total
                    stufen = schule.stufen()
                    for st in stufen:
                        teil = [j for j in jg if stamm(j) == st]
                        for j, a in anteile(teil).items():
                            dazu(stand, j, q["schulhaus"] if q["schulhaus"] in namen else None,
                                 total / len(stufen) * a)
        schuljahr = schule.schuljahr if n == 0 and schule.schuljahr else _schuljahr_plus(schule.schuljahr, n)
        for sh in schule.schulhaeuser:
            raumtypen = {raum.typ for raum in sh.raeume} & {v.raumtyp for v in schule.vorlagen
                                                           if not v.schulhaeuser or sh.name in v.schulhaeuser}
            for typ in sorted(raumtypen):
                stufen = [j for j in jg if any(j in v.jahrgaenge and v.raumtyp == typ for v in schule.vorlagen)
                          and _fuehrt(schule, sh, j)]
                if not stufen:
                    continue
                lernende = sum(stand[j, sh.name] for j in stufen)
                if len(stufen) <= 2:  # KG: Jahrgänge gemischt
                    v = [v for v in schule.vorlagen if v.raumtyp == typ]
                    klassen = math.ceil(lernende / max(x.max for x in v) - 1e-9) if lernende > 0.5 else 0
                else:
                    klassen = sum(klassen_noetig(stand[j, sh.name], j) for j in stufen)
                raeume = sum(1 for raum in sh.raeume if raum.typ == typ)
                p.prognose.append({"Schuljahr": schuljahr, "Jahr": n, "Schulhaus": sh.name, "Raumtyp": typ,
                                   "Lernende": round(lernende), "Klassen (mind.)": klassen,
                                   "Räume": raeume, "Differenz": raeume - klassen})
        p.jahre.append({"Schuljahr": schuljahr, "Jahr": n, "Lernende": round(sum(stand.values())),
                        "davon Zuzug Quartiere": round(zuzug[n]) if zuzug[n] else 0})
    _jahre_ergaenzen(schule, r, p, wachstum)
    gemeldet = set()
    for zeile in p.prognose:
        schluessel = (zeile["Schulhaus"], zeile["Raumtyp"])
        if zeile["Jahr"] and zeile["Differenz"] < 0 and schluessel not in gemeldet:
            gemeldet.add(schluessel)
            p.empfehlungen.append(Empfehlung(
                "Ausbau", f"{zeile['Schulhaus']}: ab {zeile['Schuljahr']} fehlen {typ_text(zeile)}",
                f"Prognose {zeile['Lernende']} Lernende → mindestens {zeile['Klassen (mind.)']} Klassen, aber nur "
                f"{zeile['Räume']} {'Raum' if zeile['Räume'] == 1 else 'Räume'} vom Typ {zeile['Raumtyp']}. "
                "Ausbau, Provisorium oder Umverteilung auf andere Schulhäuser prüfen "
                f"({annahmen_text(schule)}).", zeile["Jahr"] <= 2))


def annahmen_text(schule: Schule) -> str:
    """Die Annahmen der Prognose in einem Satz."""
    pl = schule.planung or {}
    teile = [f"Wachstum {float(pl.get('wachstum_prozent', 0)):.1f} % pro Jahr"]
    if pl.get("austritt_prozent"):
        teile.append("Austritte nach " + ", ".join(f"{j}: {v:g} %" for j, v in pl["austritt_prozent"].items()))
    for q in pl.get("quartiere") or []:
        kinder = q["kinder"] if q["kinder"] is not None else q["wohnungen"] * q["kinder_pro_wohnung"]
        teile.append(f"{q['name']} ab {q['ab']}: +{kinder:.0f} Lernende")
    return "Annahmen: " + "; ".join(teile) + "; Einzugsgebiete wie heute"


def _jahre_ergaenzen(schule: Schule, r, p: Planung, wachstum: float) -> None:
    """Pro Jahr: Klassen, Lektionen, Stellen und Kosten – skaliert mit der Zahl der Klassen."""
    from .kosten import kosten

    vollpensum = float((schule.planung or {}).get("vollpensum_lektionen", 28))
    lektionen0 = sum(b.lektionen for b in r.bloecke)
    kapazitaet = sum(lp.pensum_max for lp in schule.lehrpersonen) / vollpensum
    posten = {z["Posten"]: z["CHF"] for z in kosten(r)}
    variabel = sum(v for k, v in posten.items() if k == "Lehrpersonal" or k.startswith("Räume"))
    fix = posten.get("Schulhausbetrieb", 0)
    bus = posten.get("Schulbus", 0)
    klassen0 = sum(z["Klassen (mind.)"] for z in p.prognose if z["Jahr"] == 0) or 1
    lernende0 = p.jahre[0]["Lernende"] if p.jahre else 0
    fehlt_gemeldet = False
    for j in p.jahre:
        klassen = sum(z["Klassen (mind.)"] for z in p.prognose if z["Jahr"] == j["Jahr"])
        faktor = klassen / klassen0
        j["Klassen (mind.)"] = klassen
        j["fehlende Räume"] = sum(-z["Differenz"] for z in p.prognose if z["Jahr"] == j["Jahr"] and z["Differenz"] < 0)
        if lektionen0:
            j["Lektionen/Woche"] = round(lektionen0 * faktor)
            j["Stellen (Vollpensum)"] = round(lektionen0 * faktor / vollpensum, 1)
            j["Stellen fehlen"] = round(max(0.0, lektionen0 * faktor / vollpensum - kapazitaet), 1)
            if j["Stellen fehlen"] >= 0.5 and not fehlt_gemeldet:
                fehlt_gemeldet = True
                p.empfehlungen.append(Empfehlung(
                    "Lehrpersonen", f"Ab {j['Schuljahr']} fehlen rund {j['Stellen fehlen']:.1f} Stellen",
                    f"Prognose {klassen} Klassen ≈ {j['Lektionen/Woche']} Lektionen pro Woche = "
                    f"{j['Stellen (Vollpensum)']:.1f} Vollzeitstellen ({vollpensum:.0f} L). Die heutigen Lehrpersonen "
                    f"können höchstens {kapazitaet:.1f} Stellen leisten. Rekrutierung früh planen "
                    f"({annahmen_text(schule)}).", j["Jahr"] <= 1))
        if posten:
            lernend = j["Lernende"] / lernende0 if lernende0 else 1
            j["Kosten/Jahr (CHF)"] = round(variabel * faktor + fix + bus * lernend, -3)


def typ_text(zeile: dict) -> str:
    n = -zeile["Differenz"]
    return f"{n} {'Raum' if n == 1 else 'Räume'} vom Typ {zeile['Raumtyp']}"

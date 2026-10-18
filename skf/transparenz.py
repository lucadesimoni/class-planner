# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Luca De Simoni. Alle Rechte vorbehalten.
"""Transparenz: nachvollziehbar machen, was der Optimierer entschieden hat und warum.

* regeln(r)          – jede harte Regel mit Prüfstatus (wie viele Verstösse)
* kriterien(r)       – jedes weiche Ziel mit Messwert, Gewicht und Strafpunkten
                       (= was gegeneinander abgewogen wurde)
* guete(r)           – Lösungsgüte pro Rechenschritt (beweisbar optimal / mind. x %)
* begruendung(r, id) – warum ein Kind in diesem Schulhaus und dieser Klasse ist

Alles wird aus dem Ergebnis nachgerechnet, nicht aus dem Solver übernommen.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from .ablauf import Ergebnis

# Harte Regeln: (Name, Bereich, Schlüsselwörter in Fehlermeldungen)
REGELN = [
    ("Jedes Kind ist genau einer passenden Klasse zugeteilt", "Klassen", ("eingeteilt", "falscher Stufe")),
    ("Fixe Schulhaus-Zuteilungen eingehalten", "Klassen", ("fixen Schulhaus",)),
    ("Klassengrösse im erlaubten Rahmen und Raum gross genug", "Klassen", ("Grösse", "gewichtete Grösse")),
    ("Jedes Schulzimmer höchstens einer Klasse", "Klassen", ("Raum", "doppelt vergeben")),
    ("IS: höchstens zulässige Anzahl pro Klasse", "Klassen", ("IS-Lernende",)),
    ("Geschwister im selben Schulhaus (falls verlangt)", "Klassen", ("Familie",)),
    ("Lehrpersonen nur in ihren Fächern, Jahrgängen, Schulhäusern", "Lehraufträge", ("nicht qualifiziert",)),
    ("Maximalpensum eingehalten", "Lehraufträge", ("über Pensum",)),
    ("Stundentafel vollständig", "Stundenplan", ("statt",)),
    ("Keine Doppelbelegung von Klasse, Lehrperson oder Raum", "Stundenplan", ("doppelt belegt",)),
    ("Verfügbarkeiten von Lehrpersonen, Schulhäusern, Räumen", "Stundenplan", ("nicht verfügbar", "geschlossen")),
    ("Höchstens erlaubte Lektionen pro Fach und Tag", "Stundenplan", ("Lektionen am",)),
    ("Blockzeiten am Vormittag", "Stundenplan", ("Blockzeit",)),
    ("Keine Lücken im Halbtag für Lernende", "Stundenplan", ("Lücke",)),
    ("Förderlektionen parallel zum passenden Unterricht", "Stundenplan", ("parallel zu",)),
]


def regeln(r: Ergebnis) -> list[dict]:
    fehler = [m for m in r.meldungen if m.schwere == "Fehler" and m.bereich in ("Klassen", "Lehraufträge",
                                                                                "Stundenplan")]
    geprueft = {"Klassen": r.einteilung is not None, "Lehraufträge": bool(r.bloecke), "Stundenplan": bool(r.lektionen)}
    out = []
    for name, bereich, woerter in REGELN:
        treffer = [m for m in fehler if m.bereich == bereich and any(w in m.text for w in woerter)]
        out.append({"regel": name, "bereich": bereich, "geprueft": geprueft[bereich], "verstoesse": len(treffer),
                    "beispiele": [m.text for m in treffer[:3]]})
    return out


def kriterien(r: Ergebnis) -> list[dict]:
    """Messwert und Strafpunkte jedes weichen Ziels, nachgerechnet aus dem Ergebnis."""
    if not r.einteilung:
        return []
    s, e, w = r.schule, r.einteilung, r.schule.gewichte
    nach_id = {k.id: k for k in r.kinder}
    out = []

    def neu(bereich, name, wert, anzahl, gewicht_schluessel, punkte=None, einheit=""):
        g = w.get(gewicht_schluessel, 0)
        out.append({"bereich": bereich, "kriterium": name, "wert": wert, "anzahl": anzahl, "gewicht": g,
                    "gewicht_schluessel": gewicht_schluessel,
                    "strafpunkte": round(punkte if punkte is not None else anzahl * g), "einheit": einheit})

    km = sum(e.schulweg_m.values()) / 1000
    neu("Klassenbildung", "Schulwege (Summe)", f"{km:.0f} km", km, "schulweg_pro_km",
        sum(round(d * w["schulweg_pro_km"] / 1000) for d in e.schulweg_m.values()))
    neu("Klassenbildung", "Anzahl Klassen", f"{len(e.klassen)} Klassen", len(e.klassen), "klasse",
        sum(w["klasse"] + c.vorlage.strafe for c in e.klassen))
    abw = sum(abs(len(c.kinder) - c.vorlage.ideal) for c in e.klassen)
    neu("Klassenbildung", "Abweichung von der Idealgrösse", f"{abw} Plätze", abw, "groessen_abweichung")
    familien = defaultdict(set)
    for k in r.kinder:
        if k.familie:
            familien[k.familie].add(e.schulhaus_von[k.id])
    getrennt = sum(len(v) - 1 for v in familien.values())
    neu("Klassenbildung", "Geschwister in verschiedenen Schulhäusern", f"{getrennt} Familien", getrennt,
        "geschwister_getrennt")
    gew = sum(1 for k in r.kinder if k.bisheriges_schulhaus and k.bisheriges_schulhaus != e.schulhaus_von[k.id]
              and any(sh.name == k.bisheriges_schulhaus for sh in s.schulhaeuser))
    neu("Klassenbildung", "Schulhauswechsel gegenüber Vorjahr", f"{gew} Lernende", gew, "schulhaus_gewechselt")
    from .pruefung import wuensche
    wu = wuensche(r.kinder, e)
    n = len(wu["zusammen"][0]) - len(wu["zusammen"][1])
    neu("Klassenbildung", "Wunsch „zusammen mit“ nicht erfüllt", f"{n} von {len(wu['zusammen'][0])}", n,
        "wunsch_zusammen")
    n = len(wu["nicht"][0]) - len(wu["nicht"][1])
    neu("Klassenbildung", "Wunsch „nicht zusammen mit“ nicht erfüllt", f"{n} von {len(wu['nicht'][0])}", n,
        "nicht_zusammen")
    n = len(wu["schulhaus"][0]) - len(wu["schulhaus"][1])
    neu("Klassenbildung", "Wunsch-Schulhaus nicht erfüllt", f"{n} von {len(wu['schulhaus'][0])}", n, "wunsch_schulhaus")
    neu("Klassenbildung", "Allein aus bisheriger Klasse/KG-Gruppe (Gspänli-Regel)", f"{len(wu['allein'])} Lernende",
        len(wu["allein"]), "allein_aus_klasse")
    split = 0
    for bisher, neue in wu["gruppen"].items():
        pro_sh = Counter(e.schulhaus_von[ids[0]] for ids in neue.values())
        split += sum(v - 1 for v in pro_sh.values())
    neu("Klassenbildung", "Bisherige Klassen auf mehrere Klassen verteilt", f"{split} Aufteilungen", split,
        "klasse_getrennt")
    ungleich = defaultdict(int)
    for c in e.klassen:
        for j, anzahl in c.anzahl_pro_jahrgang.items():
            if not anzahl:
                continue
            alle_j = [k for k in r.kinder if k.jahrgang == j and e.schulhaus_von[k.id] == c.schulhaus]
            hier = [nach_id[i] for i in c.kinder if nach_id[i].jahrgang == j]
            for merkmal, f in [("Geschlecht", lambda k: k.geschlecht == "w")] + [
                    (m_, (lambda k, m_=m_: k.hat(m_))) for m_ in s.ausgleich]:
                gruppe = sum(f(k) for k in alle_j)
                if gruppe:
                    ziel = round(gruppe * anzahl / len(alle_j))
                    ungleich["Geschlecht" if merkmal == "Geschlecht" else "Förderung"] += abs(sum(f(k) for k in hier)
                                                                                           - ziel)
    neu("Klassenbildung", "Ungleiche Verteilung Mädchen/Knaben", f"{ungleich['Geschlecht']} Abweichungen",
        ungleich["Geschlecht"], "geschlecht_ungleich")
    neu("Klassenbildung", "Ungleiche Verteilung IF/DaZ/IS", f"{ungleich['Förderung']} Abweichungen",
        ungleich["Förderung"], "foerderbedarf_ungleich")

    if r.bloecke:
        lps = defaultdict(set)
        last = Counter()
        orte = defaultdict(set)
        for b in r.bloecke:
            if b.art == "unterricht":
                lps[b.klasse].add(b.lehrperson)
            last[b.lehrperson] += b.lektionen
            orte[b.lehrperson].add(b.schulhaus)
        n = sum(len(v) for v in lps.values())
        neu("Lehraufträge", "Lehrpersonen pro Klasse (Klassenlehrprinzip)",
            f"Ø {n / max(1, len(lps)):.1f} pro Klasse", n, "lehrperson_pro_klasse")
        unter = sum(max(0, lp.pensum_min - last[lp.name]) for lp in s.lehrpersonen if last[lp.name])
        neu("Lehraufträge", "Mindestpensum unterschritten", f"{unter} Lektionen", unter, "pensum_unterschritten")
        mehr = sum(len(v) - 1 for v in orte.values())
        neu("Lehraufträge", "Lehrpersonen an mehreren Schulhäusern", f"{mehr} zusätzliche Schulhäuser", mehr,
            "lehrperson_mehrere_schulhaeuser")
    if r.lektionen:
        from .pruefung import springstunden
        praesenz = len({(l.lehrperson, s.slots[l.slot].tag, s.slots[l.slot].halbtag) for l in r.lektionen})
        neu("Stundenplan", "Präsenz-Halbtage der Lehrpersonen", f"{praesenz} Halbtage", praesenz, "praesenz_halbtag")
        spr = sum(len(springstunden(s, r.lektionen, lp.name)) for lp in s.lehrpersonen)
        neu("Stundenplan", "Springstunden", f"{spr}", spr, "springstunde")
        wechsel = Counter()
        for l in r.lektionen:
            wechsel[l.lehrperson, s.slots[l.slot].tag, s.slots[l.slot].halbtag, l.schulhaus] += 1
        halbt = Counter((a, b, c) for a, b, c, _ in wechsel)
        n = sum(v - 1 for v in halbt.values() if v > 1)
        neu("Stundenplan", "Schulhauswechsel im selben Halbtag", f"{n}", n, "schulhauswechsel")
    return out


def guete(r: Ergebnis) -> list[dict]:
    out = []
    for i in r.infos:
        if i.optimal or not i.zielwert:
            prozent = 100.0
        else:
            prozent = max(0.0, 100 * (1 - (i.zielwert - i.schranke) / abs(i.zielwert)))
        out.append({"schritt": i.schritt, "status": "beweisbar optimal" if i.optimal else "gute Lösung",
                    "mindestens": round(prozent, 1), "sekunden": round(i.sekunden, 1)})
    return out


def begruendung(r: Ergebnis, kid: str) -> dict:
    """Warum ist dieses Kind in diesem Schulhaus und dieser Klasse? Mit Alternativen."""
    s, e = r.schule, r.einteilung
    nach_id = {k.id: k for k in r.kinder}
    k = nach_id[kid]
    from .geo import luftlinie_m
    geschwister = [g for g in r.kinder if k.familie and g.familie == k.familie and g.id != kid]
    zeilen = []
    for sh in s.schulhaeuser:
        klassen = [c for c in e.klassen if c.schulhaus == sh.name and k.jahrgang in c.vorlage.jahrgaenge]
        if not klassen and e.schulhaus_von[kid] != sh.name:
            continue
        weg = luftlinie_m(k.lat, k.lon, sh.lat, sh.lon) * s.umweg_faktor if k.lat is not None else None
        gruende = []
        if weg is not None and weg > s.max_schulweg(k.jahrgang):
            gruende.append("über max. Schulweg")
        gs = [g for g in geschwister if e.schulhaus_von[g.id] == sh.name]
        if gs:
            gruende.append("Geschwister: " + ", ".join(g.vorname or g.name for g in gs))
        if k.bisheriges_schulhaus == sh.name:
            gruende.append("Schulhaus im Vorjahr")
        if k.wunsch_schulhaus == sh.name:
            gruende.append("Wunsch-Schulhaus")
        if k.schulhaus_fix == sh.name:
            gruende.append("fix zugeteilt")
        plaetze = sum(min(c.vorlage.max, c.raum.plaetze) - len(c.kinder) for c in klassen)
        zeilen.append({"schulhaus": sh.name, "gewaehlt": e.schulhaus_von[kid] == sh.name,
                       "weg_km": None if weg is None else round(weg / 1000, 2),
                       "klassen": ", ".join(f"{c.name} ({len(c.kinder)})" for c in klassen),
                       "freie_plaetze": plaetze, "gruende": "; ".join(gruende)})
    zeilen.sort(key=lambda z: (z["weg_km"] is None, z["weg_km"] or 0))
    gewaehlt = next(z for z in zeilen if z["gewaehlt"])
    satz = []
    if zeilen and zeilen[0]["gewaehlt"]:
        satz.append(f"{gewaehlt['schulhaus']} ist das nächstgelegene Schulhaus ({gewaehlt['weg_km']} km).")
    else:
        naechstes = zeilen[0]
        satz.append(f"Nächstgelegen wäre {naechstes['schulhaus']} ({naechstes['weg_km']} km), zugeteilt ist "
                    f"{gewaehlt['schulhaus']} ({gewaehlt['weg_km']} km).")
        if gewaehlt["gruende"]:
            satz.append(f"Dafür spricht: {gewaehlt['gruende']}.")
        if naechstes["freie_plaetze"] <= 0:
            satz.append(f"In {naechstes['schulhaus']} sind die Klassen dieses Jahrgangs voll.")
        elif not gewaehlt["gruende"]:
            satz.append("Grund ist der Ausgleich zwischen den Schulhäusern (Klassengrössen, Anzahl Klassen, "
                        "Spezialräume) – sonst bräuchte es eine zusätzliche oder eine zu kleine Klasse.")
    klasse = next(c for c in e.klassen if c.name == e.klasse_von[kid])
    parallel = [c for c in e.klassen if c.schulhaus == klasse.schulhaus and k.jahrgang in c.vorlage.jahrgaenge]
    klassen_satz = []
    if len(parallel) > 1:
        zus = [nach_id[a].vorname or a for a in k.zusammen_mit if a in nach_id and e.klasse_von[a] == klasse.name]
        if zus:
            klassen_satz.append(f"Wunsch „zusammen mit“ erfüllt ({', '.join(zus)}).")
        getrennt = [nach_id[a].vorname or a for a in k.nicht_mit if a in nach_id and e.klasse_von[a] != klasse.name]
        if getrennt:
            klassen_satz.append(f"Wunsch „nicht zusammen mit“ erfüllt ({', '.join(getrennt)}).")
        if k.bisherige_klasse:
            n = sum(1 for g in r.kinder if g.bisherige_klasse == k.bisherige_klasse and g.id != kid
                    and e.klasse_von[g.id] == klasse.name)
            klassen_satz.append(f"{n} weitere Kinder aus {k.bisherige_klasse} sind in derselben Klasse.")
        klassen_satz.append("Unter den Parallelklassen " + ", ".join(c.name for c in parallel) +
                            " sorgt die Verteilung für ausgeglichene Grössen, Mädchen/Knaben und IF/DaZ/IS.")
    else:
        klassen_satz.append(f"{klasse.name} ist die einzige passende Klasse in {klasse.schulhaus}.")
    return {"schulhaeuser": zeilen, "schulhaus_text": " ".join(satz), "klasse_text": " ".join(klassen_satz)}

# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Kosten und Qualität eines Ergebnisses – einfache, nachvollziehbare Zählungen.

Kostenmodell (optional, Konfiguration ``kosten``; alle Ansätze CHF pro Jahr):

    kosten:
      lektion_chf: 4300                   # eine Wochenlektion während eines Schuljahres (inkl. Sozialleistungen)
      raum_chf: {Klassenzimmer: 12000, Turnhalle: 40000}   # Unterhalt/Miete je genutztem Raum
      schulhaus_chf: 80000                # Betrieb je Schulhaus mit Klassen
      transport_chf_pro_kind: 1500        # Schulbus je Kind

Ohne Kostenmodell werden nur die Mengen gezählt (Lektionen, Räume, Schulhäuser).
"""
from __future__ import annotations


def chf(betrag: float) -> str:
    return f"CHF {betrag:,.0f}".replace(",", "’")


def mengen(r) -> dict[str, int]:
    """Was das Ergebnis an Ressourcen braucht."""
    e = r.einteilung
    if not e:
        return {}
    spezial = {(l.raum_ort, l.raum) for l in r.lektionen if l.raum} - {(c.schulhaus, c.raum.name) for c in e.klassen}
    return {"Lektionen/Woche": sum(b.lektionen for b in r.bloecke),
            "Schulzimmer (Klassen)": len(e.klassen), "Spezialräume genutzt": len(spezial),
            "Schulhäuser in Betrieb": len({c.schulhaus for c in e.klassen}),
            "Lernende mit Schulbus": sum(bool(k.bus) for k in r.kinder)}


def kosten(r) -> list[dict]:
    """Kostenposten pro Jahr (leer ohne Kostenmodell). Letzte Zeile = Total."""
    modell, e = r.schule.kosten or {}, r.einteilung
    if not any(v for key, v in modell.items() if key != "annahme") or not e:
        return []
    raum = modell.get("raum_chf") or {}
    genutzt: dict[str, int] = {}
    for c in e.klassen:
        genutzt[c.raum.typ] = genutzt.get(c.raum.typ, 0) + 1
    gesehen = {(c.schulhaus, c.raum.name) for c in e.klassen}
    for l in r.lektionen:
        if l.raum and (l.raum_ort, l.raum) not in gesehen:
            gesehen.add((l.raum_ort, l.raum))
            typ = next((x.typ for x in r.schule.schulhaus(l.raum_ort).raeume if x.name == l.raum), "")
            genutzt[typ] = genutzt.get(typ, 0) + 1
    m = mengen(r)
    zeilen = [{"Posten": "Lehrpersonal", "Menge": f"{m['Lektionen/Woche']} Lektionen/Woche",
               "Ansatz": chf(modell.get("lektion_chf", 0)), "CHF": m["Lektionen/Woche"] * modell.get("lektion_chf", 0)}]
    for typ, n in sorted(genutzt.items()):
        if raum.get(typ):
            zeilen.append({"Posten": f"Räume: {typ}", "Menge": f"{n}", "Ansatz": chf(raum[typ]), "CHF": n * raum[typ]})
    if modell.get("schulhaus_chf"):
        zeilen.append({"Posten": "Schulhausbetrieb", "Menge": f"{m['Schulhäuser in Betrieb']}",
                       "Ansatz": chf(modell["schulhaus_chf"]),
                       "CHF": m["Schulhäuser in Betrieb"] * modell["schulhaus_chf"]})
    if modell.get("transport_chf_pro_kind") and m["Lernende mit Schulbus"]:
        zeilen.append({"Posten": "Schulbus", "Menge": f"{m['Lernende mit Schulbus']} Lernende",
                       "Ansatz": chf(modell["transport_chf_pro_kind"]),
                       "CHF": m["Lernende mit Schulbus"] * modell["transport_chf_pro_kind"]})
    zeilen.append({"Posten": "Total", "Menge": "", "Ansatz": "", "CHF": sum(z["CHF"] for z in zeilen)})
    return zeilen


def qualitaet(r) -> dict[str, str]:
    """Qualitätskennzahlen zu Klassen, Lehrpersonal und Schulraum."""
    e = r.einteilung
    if not e:
        return {}
    nahe = sum(abs(len(c.kinder) - c.vorlage.ideal) <= 2 for c in e.klassen)
    lp_pro_klasse = {}
    for b in r.bloecke:
        if b.art == "unterricht":
            lp_pro_klasse.setdefault(b.klasse, set()).add(b.lehrperson)
    q = {"Klassen nahe Idealgrösse": f"{nahe}/{len(e.klassen)}"}
    if lp_pro_klasse:
        q["Lehrpersonen pro Klasse"] = f"{sum(map(len, lp_pro_klasse.values())) / len(lp_pro_klasse):.1f}"
    if r.lektionen:  # Anteil der Zeitfenster, in denen das eigene Schulzimmer genutzt wird
        im_zimmer = {c.name: c.raum.name for c in e.klassen}
        eigen = sum(1 for l in r.lektionen if l.art == "unterricht" and im_zimmer.get(l.klasse) == l.raum)
        q["Auslastung Schulzimmer"] = f"{100 * eigen / (len(e.klassen) * len(r.schule.slots)):.0f} %"
    return q

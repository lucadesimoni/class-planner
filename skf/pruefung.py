# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Prüfungen mit Schweregrad: Vorprüfung der Daten, harte Regeln, Qualität.

Schweregrade:
  Fehler  – Regel verletzt oder Daten unbrauchbar; Ergebnis so nicht verwendbar
  Warnung – zulässig, aber wahrscheinlich nicht gewollt (z.B. Schulweg über Maximum)
  Hinweis – Verbesserungspotenzial (z.B. Springstunden, Pensum unterschritten)
Die Prüfung rechnet nichts mit dem Solver, sondern zählt nur nach.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .daten import Kind, Schule
from .geo import luftlinie_m
from .mobilitaet import (bus_halbtag, buslinien_der_klassen, halbtage_der_klasse, lektionsort, wegzeit,
                         zu_knapp)
from .klassen import Einteilung, geschwistergruppen, moegliche_schulhaeuser
from .lehrauftrag import Block, qualifiziert, stundentafel
from .stundenplan import Lektion, blockzeit_slots

SCHWEREGRADE = ("Fehler", "Warnung", "Hinweis")


@dataclass
class Meldung:
    schwere: str          # Fehler | Warnung | Hinweis
    bereich: str          # Daten | Klassen | Lehraufträge | Stundenplan | Solver
    text: str
    bezug: str = ""       # Klasse, Lehrperson, Kind oder Raum – für die Hervorhebung
    slot: int | None = None
    quelle: str = ""      # Schlüssel einer Rechtsquelle/Richtlinie im Kantonsprofil

    def __str__(self) -> str:
        return f"[{self.schwere}] {self.bereich}: {self.text}"


def _doppelte(werte) -> list[str]:
    return sorted(w for w, n in Counter(werte).items() if n > 1)


def referenzen(schule: Schule, kinder: list[Kind]) -> list[Meldung]:
    """Saubere Referenzen: eindeutige Schlüssel und Verweise, die auf Vorhandenes zeigen."""
    m: list[Meldung] = []

    def fehler(text, bezug=""):
        m.append(Meldung("Fehler", "Daten", text, bezug))

    schulhaeuser = {s.name for s in schule.schulhaeuser}
    for d in _doppelte(s.name for s in schule.schulhaeuser):
        fehler(f"Schulhaus '{d}' ist mehrfach definiert")
    for d in _doppelte(s.kuerzel for s in schule.schulhaeuser):
        fehler(f"Schulhaus-Kürzel '{d}' ist mehrfach vergeben")
    for s in schule.schulhaeuser:
        for d in _doppelte(r.name for r in s.raeume):
            fehler(f"{s.name}: Raum '{d}' ist mehrfach definiert", s.name)
        for typ, ziel in s.nutzt.items():
            if ziel not in schulhaeuser:
                fehler(f"{s.name}: 'nutzt' verweist auf unbekanntes Schulhaus '{ziel}'", s.name)
            elif not any(r.typ == typ for r in schule.schulhaus(ziel).raeume):
                fehler(f"{s.name}: 'nutzt {typ}' – {ziel} hat keinen Raum vom Typ '{typ}'", s.name)
    for v in schule.vorlagen:
        for j in v.jahrgaenge:
            if j not in schule.jahrgaenge:
                fehler(f"Klassentyp {'/'.join(v.jahrgaenge)}: unbekannter Jahrgang '{j}'")
        for sh in v.schulhaeuser or []:
            if sh not in schulhaeuser:
                fehler(f"Klassentyp {'/'.join(v.jahrgaenge)}: unbekanntes Schulhaus '{sh}'")
        if v.min > v.max:
            fehler(f"Klassentyp {'/'.join(v.jahrgaenge)}: min {v.min} > max {v.max}")
    for stufe in schule.stundentafel:
        if (stufe not in schule.jahrgaenge and stufe not in schule.stufen()
                and not any(v.bezeichnung == stufe for v in schule.vorlagen)):
            fehler(f"Stundentafel '{stufe}' gehört zu keinem Jahrgang und keinem Klassentyp")
    lp_namen = [lp.name for lp in schule.lehrpersonen]
    for d in _doppelte(lp_namen):
        fehler(f"Lehrperson '{d}' ist mehrfach definiert", d)
    faecher = set(schule.faecher)
    for lp in schule.lehrpersonen:
        for f in lp.faecher:
            if f not in faecher:
                fehler(f"{lp.name}: unbekanntes Fach '{f}'", lp.name)
        for sh in lp.schulhaeuser or []:
            if sh not in schulhaeuser:
                fehler(f"{lp.name}: unbekanntes Schulhaus '{sh}'", lp.name)
        for j in lp.jahrgaenge or []:
            if j not in schule.jahrgaenge and j not in schule.stufen():
                fehler(f"{lp.name}: unbekannter Jahrgang '{j}'", lp.name)
        if lp.pensum_min > lp.pensum_max:
            fehler(f"{lp.name}: Mindestpensum {lp.pensum_min} > Maximalpensum {lp.pensum_max}", lp.name)
    for a in schule.foerderangebote:
        if a.quelle and a.quelle not in schule.profil.get("quellen", {}):
            m.append(Meldung("Warnung", "Daten", f"Förderangebot {a.name}: unbekannte Quelle '{a.quelle}'"))
        if not any(a.name in lp.faecher for lp in schule.lehrpersonen) and any(k.hat(a.merkmal) for k in kinder):
            fehler(f"Keine Lehrperson für das Förderangebot '{a.name}' (Fach '{a.name}' bei Lehrpersonen ergänzen)")

    ids = [k.id for k in kinder]
    for d in _doppelte(ids):
        fehler(f"Kind-ID '{d}' ist mehrfach vergeben", d)
    ids_set = set(ids)
    for k in kinder:
        if not k.id:
            fehler("Kind ohne ID")
        for feld in ("nicht_mit", "zusammen_mit"):
            for anderer in getattr(k, feld):
                if anderer not in ids_set:  # z.B. weggezogen: Wunsch entfällt, Rechnung läuft weiter
                    m.append(Meldung("Warnung", "Daten", f"{k.id}: '{feld}' verweist auf unbekanntes Kind "
                                     f"'{anderer}' – dieser Wunsch wird nicht berücksichtigt", k.id))
                elif anderer == k.id:
                    fehler(f"{k.id}: '{feld}' verweist auf sich selbst", k.id)
        widerspruch = set(k.zusammen_mit) & set(k.nicht_mit)
        if widerspruch:
            fehler(f"{k.id}: {', '.join(sorted(widerspruch))} gleichzeitig 'zusammen mit' und 'nicht mit'", k.id)
        if k.wunsch_schulhaus and k.wunsch_schulhaus not in schulhaeuser:
            m.append(Meldung("Warnung", "Daten", f"{k.id}: Wunsch-Schulhaus '{k.wunsch_schulhaus}' existiert nicht",
                             k.id))
        if k.bisheriges_schulhaus and k.bisheriges_schulhaus not in schulhaeuser:
            m.append(Meldung("Hinweis", "Daten", f"{k.id}: bisheriges Schulhaus '{k.bisheriges_schulhaus}' "
                             "existiert nicht mehr – Kontinuität wird ignoriert", k.id))
        if k.daz and k.daz not in ("anfang", "aufbau"):
            m.append(Meldung("Warnung", "Daten", f"{k.id}: DaZ-Wert '{k.daz}' – erwartet 'anfang' oder 'aufbau'",
                             k.id))
    return m


def vorpruefung(schule: Schule, kinder: list[Kind]) -> list[Meldung]:
    """Plausibilitätsprüfung vor dem Rechnen – findet die häufigsten Ursachen für 'keine Lösung'."""
    m: list[Meldung] = referenzen(schule, kinder)
    namen = {s.name for s in schule.schulhaeuser}
    if not kinder:
        m.append(Meldung("Fehler", "Daten", "Keine Lernenden – Liste der Lernenden laden oder erfassen"))
    ohne_koord = [k.id for k in kinder if k.lat is None or k.lon is None]
    if ohne_koord:
        m.append(Meldung("Warnung", "Daten", f"{len(ohne_koord)} Lernende ohne Koordinaten (z.B. "
                         f"{', '.join(ohne_koord[:5])}) – werden ohne Schulweg eingeteilt (bisheriges Schulhaus, "
                         "Geschwister und Wünsche zählen weiter); lat/lon ergänzen oder --geocodieren"))
    ohne_ort = sorted({k.jahrgang for k in kinder if k.jahrgang in schule.jahrgaenge
                       and not moegliche_schulhaeuser(schule, k)})
    for j in ohne_ort:
        m.append(Meldung("Fehler", "Daten", f"Jahrgang {j}: kein Schulhaus führt diese Stufe mit passendem Klassentyp "
                         "und Raum (Schulhaus 'stufen', Klassentypen, Räume prüfen)"))
    for k in kinder:
        if k.jahrgang not in schule.jahrgaenge:
            m.append(Meldung("Fehler", "Daten", f"{k.id}: unbekannter Jahrgang '{k.jahrgang}'", k.id))
        if k.schulhaus_fix and k.schulhaus_fix not in namen:
            m.append(Meldung("Fehler", "Daten", f"{k.id}: unbekanntes Schulhaus '{k.schulhaus_fix}'", k.id))

    # Platz: Kinder pro Jahrgangsgruppe vs. maximal mögliche Plätze
    anzahl = Counter(k.jahrgang for k in kinder)
    for j in schule.jahrgaenge:
        vorlagen = [v for v in schule.vorlagen if j in v.jahrgaenge]
        if anzahl[j] and not vorlagen:
            m.append(Meldung("Fehler", "Klassen", f"Kein Klassentyp (Vorlage) für Jahrgang {j}"))
    # Jahrgänge, die über Klassentypen verbunden sind, teilen sich die Räume
    gruppen: list[tuple[set[str], set[str]]] = []  # (Jahrgänge, Raumtypen)
    for v in schule.vorlagen:
        jg, typen = set(v.jahrgaenge), {v.raumtyp}
        for g in [g for g in gruppen if g[0] & jg]:
            gruppen.remove(g)
            jg, typen = jg | g[0], typen | g[1]
        gruppen.append((jg, typen))
    for jg, typen in gruppen:
        kinder_gruppe = sum(anzahl[j] for j in jg)
        plaetze = 0
        for s in schule.schulhaeuser:
            for r in s.raeume:
                # ein Raum zählt nur, wenn die Mindestgrösse eines Klassentyps darin Platz hat
                caps = [min(v.max, r.plaetze) for v in schule.vorlagen if v.raumtyp == r.typ and r.typ in typen
                        and set(v.jahrgaenge) <= jg and (not v.schulhaeuser or s.name in v.schulhaeuser)
                        and (s.stufen is None or set(v.jahrgaenge) & set(s.stufen))
                        and min(v.max, r.plaetze) >= v.min]
                plaetze += max(caps, default=0)
        art = "/".join(sorted(typen))
        if kinder_gruppe > plaetze:
            m.append(Meldung("Fehler", "Klassen", f"{kinder_gruppe} Lernende ({'/'.join(sorted(jg))}) aber höchstens "
                             f"{plaetze} Plätze in Räumen vom Typ '{art}'"))
        elif plaetze and kinder_gruppe > 0.95 * plaetze:
            m.append(Meldung("Warnung", "Klassen", f"Räume '{art}' zu {100 * kinder_gruppe / plaetze:.0f}% "
                             "ausgelastet – kaum Spielraum für eine gute Einteilung"))

    # Schulwege
    for k in kinder:
        if k.bus and not schule.buslinie(k.bus):
            m.append(Meldung("Fehler", "Daten", f"{k.id}: unbekannte Buslinie '{k.bus}' "
                             f"(vorhanden: {', '.join(b.name for b in schule.buslinien) or 'keine'})", k.id))
    for b in schule.buslinien:
        for sh in b.schulhaeuser:
            if sh not in {x.name for x in schule.schulhaeuser}:
                m.append(Meldung("Fehler", "Daten", f"Buslinie {b.name}: unbekanntes Schulhaus '{sh}'"))
        for sh in schule.schulhaeuser:
            if sh.name not in b.schulhaeuser:
                continue
            for hs in halbtage_der_klasse(schule, sh.name).values():
                moeglich, ende_ok, _ = bus_halbtag(schule, {b.name}, hs)
                if not moeglich:
                    m.append(Meldung("Warnung", "Daten", f"Buslinie {b.name}: Ankunft passt nicht zum "
                                     f"Unterrichtsbeginn {hs[0].label} in {sh.name} – an diesem Halbtag kein "
                                     "Unterricht für Buskinder möglich"))
                elif not ende_ok:
                    m.append(Meldung("Warnung", "Daten", f"Buslinie {b.name}: keine Abfahrt passt zu einem "
                                     f"Unterrichtsschluss am {hs[0].tag} {hs[0].halbtag} in {sh.name}"))
    zu_weit = [k.id for k in kinder if k.lat is not None and k.jahrgang in schule.jahrgaenge and not k.bus and all(
        luftlinie_m(k.lat, k.lon, s.lat, s.lon) * schule.umweg_faktor > schule.max_schulweg(k.jahrgang)
        for s in schule.schulhaeuser)]
    if zu_weit:
        m.append(Meldung("Warnung", "Daten", f"{len(zu_weit)} Lernende wohnen weiter als der max. Schulweg von "
                         f"jedem Schulhaus (z.B. {', '.join(zu_weit[:5])})"))

    # Stundentafel und Lehrpersonen
    for j, tafel in schule.stundentafel.items():
        if sum(tafel.values()) > len(schule.slots):
            m.append(Meldung("Fehler", "Stundenplan", f"Stundentafel {j}: {sum(tafel.values())} Lektionen, "
                             f"aber nur {len(schule.slots)} Zeitfenster"))
        for fach in tafel:
            jg = [j] if j in schule.jahrgaenge else next(
                (v.jahrgaenge for v in schule.vorlagen if v.bezeichnung == j), [])
            if not any(fach in lp.faecher and (lp.jahrgaenge is None or any(x in lp.jahrgaenge for x in jg))
                       for lp in schule.lehrpersonen):
                m.append(Meldung("Fehler", "Lehraufträge", f"Keine Lehrperson unterrichtet {fach} in {j}"))
    bedarf = 0.0  # grobe Schätzung: Klassen pro Jahrgang x Lektionen der Stundentafel
    for j in schule.jahrgaenge:
        vorlagen = sorted((v for v in schule.vorlagen if j in v.jahrgaenge), key=lambda v: len(v.jahrgaenge))
        if not vorlagen:
            continue
        v = vorlagen[0]
        tafel = schule.stundentafel.get(v.bezeichnung) or schule.stundentafel.get(j, {})
        bedarf += anzahl[j] / v.ideal / len(v.jahrgaenge) * sum(tafel.values())
    angebot = sum(lp.pensum_max for lp in schule.lehrpersonen)
    if bedarf > angebot:
        m.append(Meldung("Fehler", "Lehraufträge", f"Geschätzter Bedarf {bedarf:.0f} Lektionen, "
                         f"Pensen ergeben höchstens {angebot}"))
    elif bedarf > 0.95 * angebot:
        m.append(Meldung("Warnung", "Lehraufträge", f"Pensen fast ausgeschöpft (Bedarf ≈ {bedarf:.0f} "
                         f"von {angebot} Lektionen)"))

    # Spezialräume vorhanden?
    for s in schule.schulhaeuser:
        typen = {r.typ for r in s.raeume}
        jg = {j for v in schule.vorlagen if v.raumtyp in typen and (not v.schulhaeuser or s.name in v.schulhaeuser)
              for j in v.jahrgaenge}
        faecher = {f for j, tafel in schule.stundentafel.items() if j in jg for f in tafel}
        for f in sorted(faecher):
            typ = schule.faecher[f].raumtyp
            if typ != "Klassenzimmer" and typ not in typen and typ not in s.nutzt:
                m.append(Meldung("Warnung", "Stundenplan", f"{s.name} hat keinen Raum '{typ}' für {f} "
                                 f"(Raum ergänzen oder 'nutzt' setzen)", s.name))
        if schule.blockzeiten and s.nicht_verfuegbar & {sl.index for sl in schule.slots
                                                        if sl.halbtag == schule.vormittag()}:
            m.append(Meldung("Hinweis", "Stundenplan", f"{s.name} ist an Vormittagen teilweise geschlossen – "
                             "Blockzeiten gelten dort nur für die offenen Lektionen", s.name))
    for lp in schule.lehrpersonen:
        if len(schule.slots) - len(lp.nicht_verfuegbar) < lp.pensum_min:
            m.append(Meldung("Warnung", "Lehraufträge", f"{lp.name}: Mindestpensum {lp.pensum_min} grösser "
                             f"als verfügbare Zeitfenster", lp.name))
    m += _planung_kosten(schule)
    return m


def _planung_kosten(schule: Schule) -> list[Meldung]:
    """Bezüge in Langfristplanung und Kostenmodell (die Werte selbst prüft schon das Einlesen)."""
    m = []
    namen = {s.name for s in schule.schulhaeuser}
    for q in (schule.planung or {}).get("quartiere") or []:
        if q["schulhaus"] and q["schulhaus"] not in namen:
            m.append(Meldung("Warnung", "Planung", f"Quartier '{q['name']}': unbekanntes Schulhaus "
                             f"'{q['schulhaus']}' – die Kinder werden wie heute auf die Schulhäuser verteilt"))
    linien = {l.name for l in schule.buslinien}
    for g in schule.gebiete or []:
        for sh in sorted(set(g.aufteilung or {}) - namen):
            m.append(Meldung("Fehler", "Daten", f"Gebiet '{g.name}': unbekanntes Schulhaus '{sh}'"))
        if g.schulbus and g.schulbus not in linien:
            m.append(Meldung("Fehler", "Daten", f"Gebiet '{g.name}': unbekannte Schulbuslinie '{g.schulbus}'"))
    raumtypen = {r.typ for s in schule.schulhaeuser for r in s.raeume}
    for typ in sorted(set((schule.kosten or {}).get("raum_chf") or {}) - raumtypen):
        m.append(Meldung("Hinweis", "Kosten", f"Kostenansatz für Raumtyp '{typ}', den kein Schulhaus hat"))
    for j in sorted(set((schule.planung or {}).get("austritt_prozent") or {})
                    - set(schule.jahrgaenge) - set(schule.stufen())):
        m.append(Meldung("Warnung", "Planung", f"Austritte nach '{j}': unbekannte Stufe (vorhanden: "
                         f"{', '.join(schule.stufen())})"))
    return m


def pruefe(schule: Schule, kinder: list[Kind], e: Einteilung,
           bloecke: list[Block] | None = None, lektionen: list[Lektion] | None = None) -> list[Meldung]:
    """Harte Regeln nachzählen. Jede Verletzung ist ein Fehler."""
    f: list[Meldung] = []
    klassen = {c.name: c for c in e.klassen}

    zugeteilt = Counter(kid for c in e.klassen for kid in c.kinder)
    nach_id_alle = {k.id: k for k in kinder}
    for k in kinder:
        if zugeteilt[k.id] != 1:
            f.append(Meldung("Fehler", "Klassen", f"{k.id} ist {zugeteilt[k.id]}x eingeteilt", k.id))
        elif k.jahrgang not in klassen[e.klasse_von[k.id]].vorlage.jahrgaenge:
            f.append(Meldung("Fehler", "Klassen", f"{k.id} ({k.jahrgang}) in falscher Stufe", e.klasse_von[k.id]))
        if k.schulhaus_fix and e.schulhaus_von[k.id] != k.schulhaus_fix:
            f.append(Meldung("Fehler", "Klassen", f"{k.id} nicht im fixen Schulhaus {k.schulhaus_fix}", k.id))
        sh_k = schule.schulhaus(e.schulhaus_von[k.id]) if k.id in e.schulhaus_von else None
        if sh_k and sh_k.stufen is not None and k.jahrgang not in sh_k.stufen:
            f.append(Meldung("Fehler", "Klassen", f"{k.id}: Schulhaus {sh_k.name} führt Stufe {k.jahrgang} nicht", k.id))
        linie = schule.buslinie(k.bus) if k.bus else None
        if linie and e.schulhaus_von.get(k.id) not in linie.schulhaeuser and any(
                k.jahrgang in v.jahrgaenge and (not v.schulhaeuser or sh in v.schulhaeuser)
                for sh in linie.schulhaeuser for v in schule.vorlagen):
            f.append(Meldung("Fehler", "Klassen", f"{k.id}: Schulhaus {e.schulhaus_von.get(k.id)} wird von "
                             f"Buslinie {linie.name} nicht angefahren", k.id))
        if k.id in e.klasse_von and k.id in e.schulhaus_von and \
                e.schulhaus_von[k.id] != klassen[e.klasse_von[k.id]].schulhaus:
            f.append(Meldung("Fehler", "Klassen", f"{k.id}: Schulhaus {e.schulhaus_von[k.id]} ist nicht das "
                             f"Schulhaus der Klasse {e.klasse_von[k.id]}", k.id))
    if schule.max_klassen is not None and len(e.klassen) > schule.max_klassen:
        f.append(Meldung("Fehler", "Klassen", f"{len(e.klassen)} Klassen, höchstens {schule.max_klassen} erlaubt"))
    for c in e.klassen:
        if c.raum.typ != c.vorlage.raumtyp:
            f.append(Meldung("Fehler", "Klassen", f"{c.name}: Raum {c.raum.name} ist vom Typ {c.raum.typ}, der "
                             f"Klassentyp verlangt Raumtyp {c.vorlage.raumtyp}", c.name))
        if c.vorlage.schulhaeuser and c.schulhaus not in c.vorlage.schulhaeuser:
            f.append(Meldung("Fehler", "Klassen", f"{c.name}: Klassentyp nur in {', '.join(c.vorlage.schulhaeuser)} "
                             "zugelassen", c.name))
        if len(c.vorlage.jahrgaenge) > 1 and c.vorlage.min_pro_jahrgang:
            je_jg = Counter(nach_id_alle[i].jahrgang for i in c.kinder if i in nach_id_alle)
            for j in c.vorlage.jahrgaenge:
                if je_jg[j] < c.vorlage.min_pro_jahrgang:
                    f.append(Meldung("Fehler", "Klassen", f"{c.name}: {je_jg[j]} Lernende im Jahrgang {j}, "
                                     f"mindestens {c.vorlage.min_pro_jahrgang} pro Jahrgang", c.name))
    raeume = Counter((c.schulhaus, c.raum.name) for c in e.klassen)
    f += [Meldung("Fehler", "Klassen", f"Raum {r[1]} doppelt vergeben", r[1]) for r, n in raeume.items() if n > 1]
    for c in e.klassen:
        g, hoechst = len(c.kinder), min(c.vorlage.max, c.raum.plaetze)
        if not c.vorlage.min <= g <= hoechst:
            f.append(Meldung("Fehler", "Klassen", f"{c.name}: Grösse {g} ausserhalb {c.vorlage.min}–{hoechst}", c.name))
    nach_id = {k.id: k for k in kinder}
    for c in e.klassen:
        anz_is = sum(nach_id[i].is_ for i in c.kinder)
        if schule.max_is_pro_klasse is not None and anz_is > schule.max_is_pro_klasse:
            f.append(Meldung("Fehler", "Klassen", f"{c.name}: {anz_is} IS-Lernende (max. {schule.max_is_pro_klasse})",
                             c.name))
        gewichtet = gewichtete_groesse(schule, c, nach_id)
        if gewichtet > min(c.vorlage.max, c.raum.plaetze) + 1e-9:
            f.append(Meldung("Fehler", "Klassen", f"{c.name}: gewichtete Grösse {gewichtet:g} (IS zählt "
                             f"{schule.is_zaehlt_als:g}-fach) über {min(c.vorlage.max, c.raum.plaetze)}", c.name))
    if schule.geschwister == "hart":
        familien = defaultdict(set)
        for fam, gruppen in geschwistergruppen(schule, kinder).items():
            for n, ids in enumerate(gruppen):
                for i in ids:
                    familien[fam if len(gruppen) == 1 else f"{fam} ({n + 1})"].add(e.schulhaus_von[i])
        f += [Meldung("Fehler", "Klassen", f"Familie {fam}: Geschwister in {', '.join(sorted(sh))}")
              for fam, sh in familien.items() if len(sh) > 1]
    if bloecke is None or lektionen is None:
        return f

    lp = {l.name: l for l in schule.lehrpersonen}
    last = Counter()
    for b in bloecke:
        if not qualifiziert(lp[b.lehrperson], klassen[b.klasse], b.fach):
            f.append(Meldung("Fehler", "Lehraufträge", f"{b.lehrperson} nicht qualifiziert für {b.fach} in {b.klasse}",
                             b.lehrperson))
        last[b.lehrperson] += b.lektionen
    f += [Meldung("Fehler", "Lehraufträge", f"{n}: {l} Lektionen über Pensum {lp[n].pensum_max}", n)
          for n, l in last.items() if l > lp[n].pensum_max]

    soll = Counter()
    for c in e.klassen:
        for fach, n in stundentafel(schule, c).items():
            soll[c.name, fach] += n
    for b in bloecke:
        if b.art == "foerder":
            soll[b.klasse, b.fach] += b.lektionen
    ist = Counter((l.klasse, l.fach) for l in lektionen)
    f += [Meldung("Fehler", "Stundenplan", f"{k} {fach}: {ist[k, fach]} statt {n} Lektionen", k)
          for (k, fach), n in soll.items() if ist[k, fach] != n]

    unterricht = [l for l in lektionen if l.art == "unterricht"]
    teamteaching = {(l.klasse, l.slot) for l in lektionen
                    if l.art == "foerder" and schule.faecher[l.fach].raumtyp == "Klassenzimmer"}
    for art, schluessel, bezug, menge in (
            ("Klasse", lambda l: l.klasse, lambda l: l.klasse, unterricht),
            ("Lehrperson", lambda l: l.lehrperson, lambda l: l.lehrperson, lektionen),
            ("Raum", lambda l: (l.raum_ort, l.raum), lambda l: l.klasse,
             [l for l in lektionen if l.raum and (l.art == "unterricht" or (l.klasse, l.slot) not in teamteaching)])):
        gruppen = defaultdict(list)
        for l in menge:
            gruppen[schluessel(l), l.slot].append(l)
        for (x, s), ls in gruppen.items():
            if len(ls) > 1:
                name = x if isinstance(x, str) else ls[0].raum_label
                for l in ls:
                    f.append(Meldung("Fehler", "Stundenplan", f"{art} {name} doppelt belegt: "
                                     f"{schule.slots[s].label}", bezug(l), s))
    for l in lektionen:
        wann = schule.slots[l.slot].label
        if l.slot in lp[l.lehrperson].nicht_verfuegbar:
            f.append(Meldung("Fehler", "Stundenplan", f"{l.lehrperson} nicht verfügbar: {wann}", l.lehrperson, l.slot))
        if l.slot in schule.schulhaus(l.schulhaus).nicht_verfuegbar:
            f.append(Meldung("Fehler", "Stundenplan", f"Schulhaus {l.schulhaus} geschlossen: {wann}", l.klasse, l.slot))
        raum = next((r for r in schule.schulhaus(l.raum_ort).raeume if r.name == l.raum), None)
        if raum and l.slot in raum.nicht_verfuegbar:
            f.append(Meldung("Fehler", "Stundenplan", f"Raum {l.raum_label} nicht verfügbar: {wann}", l.klasse, l.slot))
        typ = schule.faecher[l.fach].raumtyp
        if raum and typ not in ("", "Klassenzimmer"):
            if raum.typ != typ:
                f.append(Meldung("Fehler", "Stundenplan", f"{l.klasse} {l.fach}: Raum {l.raum_label} ist vom Typ "
                                 f"{raum.typ}, das Fach braucht {typ}", l.klasse, l.slot))
            else:  # wie im Modell: so gross wie die Gruppe, höchstens wie der grösste Raum dieses Typs
                groesste = max((r.plaetze for r in schule.schulhaus(l.raum_ort).raeume
                                if r.typ == typ and l.slot not in r.nicht_verfuegbar), default=raum.plaetze)
                bedarf = min(l.gruppe or klassen[l.klasse].groesse, groesste)
                if raum.plaetze < bedarf:
                    f.append(Meldung("Fehler", "Stundenplan", f"{l.klasse} {l.fach}: Raum {l.raum_label} zu klein "
                                     f"({raum.plaetze} Plätze für {bedarf} Lernende), {wann}", l.klasse, l.slot))

    pro_tag = Counter((l.klasse, l.fach, schule.slots[l.slot].tag) for l in lektionen)
    for (k, fach, tag), n in pro_tag.items():
        fa = schule.faecher[fach]
        if n > max(fa.max_pro_tag, fa.dauer):
            f.append(Meldung("Fehler", "Stundenplan", f"{k} {fach}: {n} Lektionen am {tag}", k))

    parallel = {(tuple(b.klassen), b.fach): b.parallel_zu for b in bloecke if b.art == "foerder"}
    fach_in = {(l.klasse, l.slot): l.fach for l in unterricht}
    for l in lektionen:
        if l.art != "foerder":
            continue
        erlaubt = parallel.get((tuple(l.klassen), l.fach), [])
        for kl in l.klassen:
            if fach_in.get((kl, l.slot)) not in erlaubt:
                f.append(Meldung("Fehler", "Stundenplan", f"{kl}: {l.fach} {schule.slots[l.slot].label} nicht "
                                 f"parallel zu {'/'.join(erlaubt)}", kl, l.slot))

    belegt = defaultdict(set)
    for l in unterricht:
        belegt[l.klasse].add(l.slot)
    for name, slots in belegt.items():
        sh = klassen[name].schulhaus
        offen = schule.offene_slots(sh)
        for vorher, s in zip(offen, offen[1:]):
            if (vorher.tag, vorher.halbtag) == (s.tag, s.halbtag) and s.index in slots and vorher.index not in slots:
                f.append(Meldung("Fehler", "Stundenplan", f"{name}: Lücke vor {s.label}", name, vorher.index))
        pflicht = blockzeit_slots(schule, sh)
        if len(slots) >= len(pflicht):
            f += [Meldung("Fehler", "Stundenplan", f"{name}: Blockzeit {schule.slots[i].label} nicht besetzt", name, i)
                  for i in pflicht if i not in slots]

    # Schulbus: Beginn nach Ankunft, Schluss passend zu einer Abfahrt
    linien = buslinien_der_klassen(e.klassen, kinder)
    for name, slots in belegt.items():
        if not linien.get(name):
            continue
        for hs in halbtage_der_klasse(schule, klassen[name].schulhaus).values():
            da = [s for s in hs if s.index in slots]
            if not da:
                continue
            moeglich, ende_ok, gruende = bus_halbtag(schule, linien[name], hs)
            if not moeglich or da[-1].index not in ende_ok:
                f.append(Meldung("Fehler", "Stundenplan", f"{name}: Unterricht {da[0].tag} {da[0].halbtag} passt "
                                 f"nicht zum Schulbus ({'; '.join(gruende)})", name, da[-1].index))

    # Wegzeiten der Lehrpersonen zwischen Schulhäusern
    knapp = zu_knapp(schule)
    if knapp:
        wo = defaultdict(dict)
        for l in lektionen:
            wo[l.lehrperson][l.slot] = lektionsort(schule, l.schulhaus, l.fach)
        for name, orte in wo.items():
            for (a, b), paare in knapp.items():
                for s1, s2 in paare:
                    if orte.get(s1) == a and orte.get(s2) == b:
                        f.append(Meldung("Fehler", "Stundenplan", f"{name}: Wegzeit {a} → {b} "
                                         f"({wegzeit(schule, a, b)} min) reicht nicht zwischen "
                                         f"{schule.slots[s1].label} und {schule.slots[s2].label}", name, s2))
    return f


def gewichtete_groesse(schule: Schule, klasse, nach_id: dict[str, Kind]) -> float:
    """Klassengrösse, bei der IS-Kinder mit is_zaehlt_als gezählt werden."""
    return len(klasse.kinder) + (schule.is_zaehlt_als - 1) * sum(nach_id[i].is_ for i in klasse.kinder)


def springstunden(schule: Schule, lektionen: list[Lektion], lehrperson: str) -> list[int]:
    """Freie Slots einer Lehrperson zwischen zwei Lektionen im selben Halbtag."""
    belegt = {l.slot for l in lektionen if l.lehrperson == lehrperson}
    luecken = []
    for tag, ht in schule.halbtage():
        idx = [s.index for s in schule.slots if s.tag == tag and s.halbtag == ht]
        besetzt = [i for i in idx if i in belegt]
        if besetzt:
            luecken += [i for i in idx if besetzt[0] < i < besetzt[-1] and i not in belegt]
    return luecken


def qualitaet(schule: Schule, kinder: list[Kind], e: Einteilung,
              bloecke: list[Block], lektionen: list[Lektion]) -> list[Meldung]:
    """Weiche Kriterien: zulässig, aber verbesserungswürdig."""
    m: list[Meldung] = []
    nach_id = {k.id: k for k in kinder}
    for c in e.klassen:
        ks = [nach_id[i] for i in c.kinder]
        w = sum(k.geschlecht == "w" for k in ks)
        if ks and abs(2 * w - len(ks)) > 0.4 * len(ks):
            m.append(Meldung("Hinweis", "Klassen", f"{c.name}: Geschlechterverhältnis {w}:{len(ks) - w}", c.name))
        weit = [k.id for k in ks if e.schulweg_m[k.id] > schule.max_schulweg(k.jahrgang) and not k.bus]
        if weit:
            m.append(Meldung("Warnung", "Klassen", f"{c.name}: {len(weit)} Kind(er) mit Schulweg über Maximum "
                             f"({', '.join(weit)})", c.name))
    if not bloecke:
        return m
    lps_pro_klasse = defaultdict(set)
    last = Counter()
    for b in bloecke:
        if b.art == "unterricht":
            lps_pro_klasse[b.klasse].add(b.lehrperson)
        last[b.lehrperson] += b.lektionen
    for kl, lps in lps_pro_klasse.items():
        if len(lps) > 4:
            m.append(Meldung("Hinweis", "Lehraufträge", f"{kl}: {len(lps)} verschiedene Lehrpersonen", kl))
    for lp in schule.lehrpersonen:
        if 0 < last[lp.name] < lp.pensum_min:
            m.append(Meldung("Hinweis", "Lehraufträge", f"{lp.name}: {last[lp.name]} Lektionen, "
                             f"Mindestpensum {lp.pensum_min}", lp.name))
        elif last[lp.name] == 0 and lp.pensum_min > 0:
            m.append(Meldung("Warnung", "Lehraufträge", f"{lp.name}: nicht eingesetzt (Mindestpensum {lp.pensum_min})",
                             lp.name))
        for i in springstunden(schule, lektionen, lp.name):
            m.append(Meldung("Hinweis", "Stundenplan", f"{lp.name}: Springstunde {schule.slots[i].label}", lp.name, i))
    return m


def rechtspruefung(schule: Schule, kinder: list[Kind], e: Einteilung, bloecke: list[Block]) -> list[Meldung]:
    """Prüft das Ergebnis gegen die Regeln des Kantonsprofils – jede Meldung nennt ihre Quelle."""
    regeln = (schule.profil or {}).get("regeln", {}) or {}
    m: list[Meldung] = []
    verbindlich = bool(schule.profil.get("verbindlich"))
    nach_id = {k.id: k for k in kinder}

    for name, regel in (regeln.get("klassengroessen") or {}).items():
        jg = set(regel["jahrgaenge"])
        for c in e.klassen:
            if not set(c.jahrgaenge) & jg:
                continue
            n = len(c.kinder)
            if n > regel["max"]:
                m.append(Meldung("Fehler" if verbindlich else "Warnung", "Recht",
                                 f"{c.name}: {n} Lernende über der Höchstzahl {regel['max']} ({name})",
                                 c.name, quelle=regel.get("quelle", "")))
            elif n < regel["min"]:
                m.append(Meldung("Fehler" if verbindlich else "Warnung", "Recht",
                                 f"{c.name}: {n} Lernende unter der Mindestzahl {regel['min']} ({name})",
                                 c.name, quelle=regel.get("quelle", "")))
            if n > regel["max"] and any(nach_id[i].is_ for i in c.kinder):
                q = (regeln.get("sonderschulung") or {}).get("quelle", "")
                m.append(Meldung("Warnung", "Recht", f"{c.name}: Klasse mit integrativer Sonderschulung über der "
                                 "maximalen Klassengrösse", c.name, quelle=q))

    bz = regeln.get("blockzeiten") or {}
    if bz.get("pflicht") and not schule.blockzeiten:
        m.append(Meldung("Warnung", "Recht", "Blockzeiten sind ausgeschaltet, aber vorgeschrieben",
                         quelle=bz.get("quelle", "")))

    sw = regeln.get("schulweg") or {}
    if sw.get("zumutbar_minuten"):
        tempo = sw.get("gehtempo_kmh", {}) or {}
        pro_klasse = defaultdict(list)
        for k in kinder:
            kmh = float(tempo.get(k.jahrgang, tempo.get("default", 4.0)))
            minuten = e.schulweg_m[k.id] / 1000 / kmh * 60
            if minuten > sw["zumutbar_minuten"]:
                pro_klasse[e.klasse_von[k.id]].append(f"{k.id} ({minuten:.0f} min)")
        for kl, ks in pro_klasse.items():
            m.append(Meldung("Hinweis", "Recht", f"{kl}: {len(ks)} Kind(er) mit Fussweg über "
                             f"{sw['zumutbar_minuten']} min – Zumutbarkeit prüfen, ggf. Schultransport: "
                             f"{', '.join(ks)}", kl, quelle=sw.get("quelle", "")))

    ifr = regeln.get("integrative_foerderung") or {}
    if ifr and bloecke:
        soll = len(kinder) / ifr["lernende_pro_vollpensum"] * ifr["vollpensum_lektionen"]
        ist = sum(b.lektionen for b in bloecke if b.art == "foerder" and b.fach == "IF")
        if ist + 0.5 < soll:
            m.append(Meldung("Hinweis", "Recht", f"IF-Lektionen {ist} unter dem Richtwert von ca. {soll:.0f} "
                             f"({len(kinder)} Lernende, 1 Vollpensum pro {ifr['lernende_pro_vollpensum']})",
                             quelle=ifr.get("quelle", "")))
    return m


def wuensche(kinder: list[Kind], e: Einteilung) -> dict:
    """Auswertung der Wünsche der Erziehungsberechtigten und der Gspänli-Regel."""
    nach_id = {k.id: k for k in kinder}
    paare_zus = sorted({tuple(sorted((k.id, a))) for k in kinder for a in k.zusammen_mit if a in nach_id})
    paare_nicht = sorted({tuple(sorted((k.id, a))) for k in kinder for a in k.nicht_mit if a in nach_id})
    zus_ok = [p for p in paare_zus if e.klasse_von[p[0]] == e.klasse_von[p[1]]]
    nicht_ok = [p for p in paare_nicht if e.klasse_von[p[0]] != e.klasse_von[p[1]]]
    mit_wunsch_sh = [k for k in kinder if k.wunsch_schulhaus]
    sh_ok = [k for k in mit_wunsch_sh if e.schulhaus_von[k.id] == k.wunsch_schulhaus]
    gruppen = defaultdict(lambda: defaultdict(list))  # bisherige Klasse -> neue Klasse -> Kinder
    for k in kinder:
        if k.bisherige_klasse:
            gruppen[k.bisherige_klasse][e.klasse_von[k.id]].append(k.id)
    allein = [(bisher, neu, ids[0]) for bisher, neue in gruppen.items() for neu, ids in neue.items()
              if len(ids) == 1 and sum(len(v) for v in neue.values()) > 1]
    return {"zusammen": (paare_zus, zus_ok), "nicht": (paare_nicht, nicht_ok),
            "schulhaus": (mit_wunsch_sh, sh_ok), "gruppen": gruppen, "allein": allein}


def wunsch_meldungen(kinder: list[Kind], e: Einteilung) -> list[Meldung]:
    w = wuensche(kinder, e)
    m = []
    paare, ok = w["zusammen"]
    for a, b in sorted(set(paare) - set(ok)):
        m.append(Meldung("Hinweis", "Wünsche", f"Wunsch 'zusammen mit' nicht erfüllt: {a} ({e.klasse_von[a]}) und "
                         f"{b} ({e.klasse_von[b]})", e.klasse_von[a]))
    paare, ok = w["nicht"]
    for a, b in sorted(set(paare) - set(ok)):
        m.append(Meldung("Warnung", "Wünsche", f"Wunsch 'nicht zusammen mit' nicht erfüllt: {a} und {b} in "
                         f"{e.klasse_von[a]}", e.klasse_von[a]))
    alle, ok = w["schulhaus"]
    for k in alle:
        if k not in ok:
            m.append(Meldung("Hinweis", "Wünsche", f"{k.id}: Wunsch-Schulhaus {k.wunsch_schulhaus} nicht erfüllt "
                             f"(zugeteilt: {e.schulhaus_von[k.id]})", e.klasse_von[k.id]))
    for bisher, neu, kid in w["allein"]:
        m.append(Meldung("Hinweis", "Wünsche", f"{kid} kommt als einziges Kind aus {bisher} in {neu}", neu))
    return m

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
from .klassen import Einteilung
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

    def __str__(self) -> str:
        return f"[{self.schwere}] {self.bereich}: {self.text}"


def vorpruefung(schule: Schule, kinder: list[Kind]) -> list[Meldung]:
    """Plausibilitätsprüfung vor dem Rechnen – findet die häufigsten Ursachen für 'keine Lösung'."""
    m: list[Meldung] = []
    namen = {s.name for s in schule.schulhaeuser}
    ohne_koord = [k.id for k in kinder if k.lat is None or k.lon is None]
    if ohne_koord:
        m.append(Meldung("Fehler", "Daten", f"{len(ohne_koord)} Kinder ohne Koordinaten "
                         f"(z.B. {', '.join(ohne_koord[:5])}) – lat/lon ergänzen oder --geocodieren"))
    for k in kinder:
        if k.jahrgang not in schule.jahrgaenge:
            m.append(Meldung("Fehler", "Daten", f"{k.id}: unbekannter Jahrgang '{k.jahrgang}'", k.id))
        if k.schulhaus_fix and k.schulhaus_fix not in namen:
            m.append(Meldung("Fehler", "Daten", f"{k.id}: unbekanntes Schulhaus '{k.schulhaus_fix}'", k.id))
    for s in schule.schulhaeuser:
        for typ in s.nutzt.values():
            if typ not in namen:
                m.append(Meldung("Fehler", "Daten", f"{s.name}: 'nutzt' verweist auf unbekanntes Schulhaus '{typ}'"))

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
                caps = [min(v.max, r.plaetze) for v in schule.vorlagen if v.raumtyp == r.typ and r.typ in typen
                        and set(v.jahrgaenge) <= jg and (not v.schulhaeuser or s.name in v.schulhaeuser)]
                plaetze += max(caps, default=0)
        art = "/".join(sorted(typen))
        if kinder_gruppe > plaetze:
            m.append(Meldung("Fehler", "Klassen", f"{kinder_gruppe} Kinder ({'/'.join(sorted(jg))}) aber höchstens "
                             f"{plaetze} Plätze in Räumen vom Typ '{art}'"))
        elif kinder_gruppe > 0.95 * plaetze:
            m.append(Meldung("Warnung", "Klassen", f"Räume '{art}' zu {100 * kinder_gruppe / plaetze:.0f}% "
                             "ausgelastet – kaum Spielraum für eine gute Einteilung"))

    # Schulwege
    zu_weit = [k.id for k in kinder if k.lat is not None and k.jahrgang in schule.jahrgaenge and all(
        luftlinie_m(k.lat, k.lon, s.lat, s.lon) * schule.umweg_faktor > schule.max_schulweg(k.jahrgang)
        for s in schule.schulhaeuser)]
    if zu_weit:
        m.append(Meldung("Warnung", "Daten", f"{len(zu_weit)} Kinder wohnen weiter als der max. Schulweg von "
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
                                                        if sl.halbtag == schule.slots[0].halbtag}:
            m.append(Meldung("Hinweis", "Stundenplan", f"{s.name} ist an Vormittagen teilweise geschlossen – "
                             "Blockzeiten gelten dort nur für die offenen Lektionen", s.name))
    for lp in schule.lehrpersonen:
        if len(schule.slots) - len(lp.nicht_verfuegbar) < lp.pensum_min:
            m.append(Meldung("Warnung", "Lehraufträge", f"{lp.name}: Mindestpensum {lp.pensum_min} grösser "
                             f"als verfügbare Zeitfenster", lp.name))
    return m


def pruefe(schule: Schule, kinder: list[Kind], e: Einteilung,
           bloecke: list[Block] | None = None, lektionen: list[Lektion] | None = None) -> list[Meldung]:
    """Harte Regeln nachzählen. Jede Verletzung ist ein Fehler."""
    f: list[Meldung] = []
    klassen = {c.name: c for c in e.klassen}

    zugeteilt = Counter(kid for c in e.klassen for kid in c.kinder)
    for k in kinder:
        if zugeteilt[k.id] != 1:
            f.append(Meldung("Fehler", "Klassen", f"{k.id} ist {zugeteilt[k.id]}x eingeteilt", k.id))
        elif k.jahrgang not in klassen[e.klasse_von[k.id]].vorlage.jahrgaenge:
            f.append(Meldung("Fehler", "Klassen", f"{k.id} ({k.jahrgang}) in falscher Stufe", e.klasse_von[k.id]))
        if k.schulhaus_fix and e.schulhaus_von[k.id] != k.schulhaus_fix:
            f.append(Meldung("Fehler", "Klassen", f"{k.id} nicht im fixen Schulhaus {k.schulhaus_fix}", k.id))
    raeume = Counter((c.schulhaus, c.raum.name) for c in e.klassen)
    f += [Meldung("Fehler", "Klassen", f"Raum {r[1]} doppelt vergeben", r[1]) for r, n in raeume.items() if n > 1]
    for c in e.klassen:
        g, hoechst = len(c.kinder), min(c.vorlage.max, c.raum.plaetze)
        if not c.vorlage.min <= g <= hoechst:
            f.append(Meldung("Fehler", "Klassen", f"{c.name}: Grösse {g} ausserhalb {c.vorlage.min}–{hoechst}", c.name))
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
    ist = Counter((l.klasse, l.fach) for l in lektionen)
    f += [Meldung("Fehler", "Stundenplan", f"{k} {fach}: {ist[k, fach]} statt {n} Lektionen", k)
          for (k, fach), n in soll.items() if ist[k, fach] != n]

    for art, schluessel, bezug in (("Klasse", lambda l: l.klasse, lambda l: l.klasse),
                                   ("Lehrperson", lambda l: l.lehrperson, lambda l: l.lehrperson),
                                   ("Raum", lambda l: (l.raum_ort, l.raum), lambda l: l.klasse)):
        gruppen = defaultdict(list)
        for l in lektionen:
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
        raum = next(r for r in schule.schulhaus(l.raum_ort).raeume if r.name == l.raum)
        if l.slot in raum.nicht_verfuegbar:
            f.append(Meldung("Fehler", "Stundenplan", f"Raum {l.raum_label} nicht verfügbar: {wann}", l.klasse, l.slot))

    pro_tag = Counter((l.klasse, l.fach, schule.slots[l.slot].tag) for l in lektionen)
    for (k, fach, tag), n in pro_tag.items():
        fa = schule.faecher[fach]
        if n > max(fa.max_pro_tag, fa.dauer):
            f.append(Meldung("Fehler", "Stundenplan", f"{k} {fach}: {n} Lektionen am {tag}", k))

    belegt = defaultdict(set)
    for l in lektionen:
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
    return f


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
        weit = [k.id for k in ks if e.schulweg_m[k.id] > schule.max_schulweg(k.jahrgang)]
        if weit:
            m.append(Meldung("Warnung", "Klassen", f"{c.name}: {len(weit)} Kind(er) mit Schulweg über Maximum "
                             f"({', '.join(weit)})", c.name))
    if not bloecke:
        return m
    lps_pro_klasse = defaultdict(set)
    last = Counter()
    for b in bloecke:
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

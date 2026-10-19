# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Gesamtablauf: Vorprüfung → Klassen → Lehraufträge → Stundenplan → Prüfung."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .daten import Kind, Schule
from .klassen import Einteilung, teile_ein
from .lehrauftrag import Block, verteile_lehrauftraege
from .planung import Planung, plane
from .pruefung import Meldung, pruefe, qualitaet, rechtspruefung, vorpruefung, wuensche, wunsch_meldungen
from .solver import KeineLoesung, Loesungsinfo
from .mobilitaet import buslinien_der_klassen
from .stundenplan import Lektion, erstelle_stundenplan


@dataclass
class Ergebnis:
    schule: Schule
    kinder: list[Kind]
    einteilung: Einteilung | None = None
    bloecke: list[Block] = field(default_factory=list)
    lektionen: list[Lektion] = field(default_factory=list)
    infos: list[Loesungsinfo] = field(default_factory=list)
    meldungen: list[Meldung] = field(default_factory=list)
    sekunden: float = 0.0
    planung: Planung = field(default_factory=Planung)
    manuell: list[str] = field(default_factory=list)   # manuelle Anpassungen (Protokoll)

    def anzahl(self, schwere: str) -> int:
        return sum(m.schwere == schwere for m in self.meldungen)

    @property
    def vollstaendig(self) -> bool:
        return self.einteilung is not None and bool(self.lektionen)

    def _wunschquote(self) -> str:
        return _wunschquote_text(wuensche(self.kinder, self.einteilung))

    def kennzahlen(self) -> dict[str, str]:
        e = self.einteilung
        mit_adresse = {k.id for k in self.kinder if k.lat is not None}
        wege = [w for kid, w in e.schulweg_m.items() if kid in mit_adresse] if e else []
        return {
            "Klassen": str(len(e.klassen)) if e else "–",
            "Ø Klassengrösse": f"{len(self.kinder) / len(e.klassen):.1f}" if e and e.klassen else "–",
            "Ø Schulweg": f"{sum(wege) / len(wege) / 1000:.2f} km" if wege else "–",
            "Max. Schulweg": f"{max(wege) / 1000:.2f} km" if wege else "–",
            "Mehrjahrgangsklassen": str(sum(len(c.jahrgaenge) > 1 and c.vorlage.bezeichnung == "" for c in e.klassen))
            if e else "–",
            "Lehrpersonen im Einsatz": str(len({b.lehrperson for b in self.bloecke})) if self.bloecke else "–",
            "Förderlektionen": str(sum(b.lektionen for b in self.bloecke if b.art == "foerder"))
            if self.bloecke else "–",
            "Springstunden": str(sum("Springstunde" in m.text for m in self.meldungen)) if self.lektionen else "–",
            "Wünsche erfüllt": self._wunschquote() if e else "–",
            "Fehler": str(self.anzahl("Fehler")),
            "Warnungen": str(self.anzahl("Warnung")),
            "Hinweise": str(self.anzahl("Hinweis")),
            "Rechenzeit": f"{self.sekunden:.0f} s",
        }


def _wunschquote_text(w: dict) -> str:
    gesamt = sum(len(w[k][0]) for k in ("zusammen", "nicht", "schulhaus"))
    erfuellt = sum(len(w[k][1]) for k in ("zusammen", "nicht", "schulhaus"))
    return f"{erfuellt}/{gesamt}" if gesamt else "–"


def rechne(schule: Schule, kinder: list[Kind], zeitlimit: float = 120, nur_klassen: bool = False,
           protokoll=print) -> Ergebnis:
    start = time.time()
    r = Ergebnis(schule, kinder, meldungen=vorpruefung(schule, kinder))
    if r.anzahl("Fehler"):
        protokoll("Vorprüfung hat Fehler gefunden – es wird nicht gerechnet.")
        r.sekunden = time.time() - start
        return r
    try:
        r.einteilung = teile_ein(schule, kinder, zeitlimit=zeitlimit * 0.25)
        r.infos += r.einteilung.infos
        r.meldungen += [Meldung("Warnung", "Klassen", w, w.split(":")[0]) for w in r.einteilung.warnungen]
        for i in r.einteilung.infos:
            protokoll(f"  {i}")
        if not nur_klassen:
            verbote: list[list[tuple[str, str, str]]] = []
            for versuch in range(4):
                r.bloecke, info = verteile_lehrauftraege(schule, r.einteilung.klassen, zeitlimit=zeitlimit * 0.15,
                                                         kinder=kinder, verbote=verbote)
                protokoll(f"  {info}")
                try:
                    r.lektionen, infos, warnungen = erstelle_stundenplan(
                        schule, r.einteilung.klassen, r.bloecke, zeitlimit=zeitlimit * 0.6,
                        buslinien=buslinien_der_klassen(r.einteilung.klassen, kinder))
                except KeineLoesung as fehler:
                    # Rückkopplung: Lehraufträge der am Konflikt beteiligten Lehrpersonen neu verteilen
                    beteiligt = _beteiligte_lehrpersonen(fehler.konflikt, schule) or {
                        lp.name for lp in schule.lehrpersonen if lp.nicht_verfuegbar}  # Teilzeit als Engpass
                    verbot = [(b.klasse, b.fach, b.lehrperson) for b in r.bloecke if b.lehrperson in beteiligt]
                    if versuch == 3 or not verbot:
                        raise
                    verbote.append(verbot)
                    namen = sorted(beteiligt)
                    kurz = ", ".join(namen[:5]) + (f" und {len(namen) - 5} weitere" if len(namen) > 5 else "")
                    protokoll(f"  Stundenplan mit diesen Lehraufträgen unlösbar – neue Verteilung "
                              f"(Versuch {versuch + 2}, beteiligt: {kurz})")
                    r.meldungen.append(Meldung("Hinweis", "Solver", f"Versuch {versuch + 1}: Stundenplan mit den "
                                               f"Lehraufträgen unlösbar, neu verteilt (beteiligt: {kurz})"))
                    continue
                r.infos += [info] + infos
                for i in infos:
                    protokoll(f"  {i}")
                r.meldungen += [Meldung("Warnung", "Stundenplan", w, w.split(" (")[0]) for w in warnungen]
                break
    except KeineLoesung as fehler:
        r.meldungen.append(Meldung("Fehler", "Solver", str(fehler)))
    if r.einteilung:
        teil = (r.bloecke, r.lektionen) if r.lektionen else ()
        r.meldungen += pruefe(schule, kinder, r.einteilung, *teil)
        r.meldungen += qualitaet(schule, kinder, r.einteilung, r.bloecke, r.lektionen)
        r.meldungen += rechtspruefung(schule, kinder, r.einteilung, r.bloecke)
        r.meldungen += wunsch_meldungen(kinder, r.einteilung)
        r.planung = plane(schule, kinder, r)
    for i in r.infos:
        if not i.optimal and i.zielwert and (i.zielwert - i.schranke) / abs(i.zielwert) > 0.05:
            r.meldungen.append(Meldung("Hinweis", "Solver", f"{i.schritt}: Lösung ist bis zu "
                                       f"{100 * (i.zielwert - i.schranke) / abs(i.zielwert):.0f}% vom Optimum "
                                       "entfernt – mehr Rechenzeit (-t) kann sie verbessern"))
    r.sekunden = time.time() - start
    return r


def _beteiligte_lehrpersonen(konflikt: list[str], schule: Schule) -> set[str]:
    namen = {lp.name for lp in schule.lehrpersonen}
    beteiligt = set()
    for regel in konflikt:
        for name in namen:
            if regel == f"Verfügbarkeit {name}" or regel.startswith((f"{name}:", f"Wegzeit {name}:")):
                beteiligt.add(name)
    return beteiligt


def verschiebe(r: Ergebnis, kid: str, ziel: str) -> str:
    """Manuelle Anpassung: ein Kind in eine andere Klasse verschieben und alles neu prüfen.

    Der Stundenplan bleibt bestehen (Klassen ändern sich nicht); Förderlektionen, die von
    der Zusammensetzung abhängen, werden als Hinweis gemeldet.
    """
    from .geo import luftlinie_m
    e = r.einteilung
    klassen = {c.name: c for c in e.klassen}
    kind = next(k for k in r.kinder if k.id == kid)
    alt, neu = klassen[e.klasse_von[kid]], klassen[ziel]
    if kind.jahrgang not in neu.vorlage.jahrgaenge:
        raise ValueError(f"{ziel} führt den Jahrgang {kind.jahrgang} nicht")
    if alt is neu:
        return "keine Änderung"
    alt.kinder.remove(kid)
    alt.anzahl_pro_jahrgang[kind.jahrgang] -= 1
    neu.kinder.append(kid)
    neu.anzahl_pro_jahrgang[kind.jahrgang] = neu.anzahl_pro_jahrgang.get(kind.jahrgang, 0) + 1
    e.klasse_von[kid] = neu.name
    e.schulhaus_von[kid] = neu.schulhaus
    sh = r.schule.schulhaus(neu.schulhaus)
    if kind.lat is not None:
        e.schulweg_m[kid] = luftlinie_m(kind.lat, kind.lon, sh.lat, sh.lon) * r.schule.umweg_faktor
    text = f"{kid} manuell von {alt.name} nach {neu.name} verschoben"
    r.manuell.append(text)
    pruefe_neu(r)
    return text


def pruefe_neu(r: Ergebnis) -> None:
    """Meldungen und Empfehlungen nach einer manuellen Änderung neu berechnen."""
    schule, kinder, e = r.schule, r.kinder, r.einteilung
    behalten = [m for m in r.meldungen if m.bereich in ("Daten", "Solver") and "manuell" not in m.text]
    r.meldungen = behalten + [Meldung("Hinweis", "Manuell", t) for t in r.manuell]
    teil = (r.bloecke, r.lektionen) if r.lektionen else ()
    r.meldungen += pruefe(schule, kinder, e, *teil)
    r.meldungen += qualitaet(schule, kinder, e, r.bloecke, r.lektionen)
    r.meldungen += rechtspruefung(schule, kinder, e, r.bloecke)
    r.meldungen += wunsch_meldungen(kinder, e)
    if r.manuell and r.lektionen:
        r.meldungen.append(Meldung("Hinweis", "Manuell", "Klassen wurden manuell angepasst: Förderlektionen (IF/DaZ) "
                                   "hängen von der Zusammensetzung ab – Stundenplan bei Bedarf neu berechnen."))
    r.planung = plane(schule, kinder, r)

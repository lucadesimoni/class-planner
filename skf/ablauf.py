"""Gesamtablauf: Vorprüfung → Klassen → Lehraufträge → Stundenplan → Prüfung."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .daten import Kind, Schule
from .klassen import Einteilung, teile_ein
from .lehrauftrag import Block, verteile_lehrauftraege
from .pruefung import Meldung, pruefe, qualitaet, vorpruefung
from .solver import KeineLoesung, Loesungsinfo
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

    def anzahl(self, schwere: str) -> int:
        return sum(m.schwere == schwere for m in self.meldungen)

    @property
    def vollstaendig(self) -> bool:
        return self.einteilung is not None and bool(self.lektionen)

    def kennzahlen(self) -> dict[str, str]:
        e = self.einteilung
        wege = list(e.schulweg_m.values()) if e else []
        return {
            "Klassen": str(len(e.klassen)) if e else "–",
            "Ø Klassengrösse": f"{len(self.kinder) / len(e.klassen):.1f}" if e and e.klassen else "–",
            "Ø Schulweg": f"{sum(wege) / len(wege) / 1000:.2f} km" if wege else "–",
            "Max. Schulweg": f"{max(wege) / 1000:.2f} km" if wege else "–",
            "Mischklassen": str(sum(len(c.jahrgaenge) > 1 and c.vorlage.bezeichnung == "" for c in e.klassen))
            if e else "–",
            "Lehrpersonen im Einsatz": str(len({b.lehrperson for b in self.bloecke})) if self.bloecke else "–",
            "Springstunden": str(sum("Springstunde" in m.text for m in self.meldungen)) if self.lektionen else "–",
            "Fehler": str(self.anzahl("Fehler")),
            "Warnungen": str(self.anzahl("Warnung")),
            "Hinweise": str(self.anzahl("Hinweis")),
            "Rechenzeit": f"{self.sekunden:.0f} s",
        }


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
            r.bloecke, info = verteile_lehrauftraege(schule, r.einteilung.klassen, zeitlimit=zeitlimit * 0.15)
            r.infos.append(info)
            protokoll(f"  {info}")
            r.lektionen, infos, warnungen = erstelle_stundenplan(schule, r.einteilung.klassen, r.bloecke,
                                                                 zeitlimit=zeitlimit * 0.6)
            r.infos += infos
            for i in infos:
                protokoll(f"  {i}")
            r.meldungen += [Meldung("Warnung", "Stundenplan", w, w.split(" (")[0]) for w in warnungen]
    except KeineLoesung as fehler:
        r.meldungen.append(Meldung("Fehler", "Solver", str(fehler)))
    if r.einteilung:
        teil = (r.bloecke, r.lektionen) if r.lektionen else ()
        r.meldungen += pruefe(schule, kinder, r.einteilung, *teil)
        r.meldungen += qualitaet(schule, kinder, r.einteilung, r.bloecke, r.lektionen)
    for i in r.infos:
        if not i.optimal and i.zielwert and (i.zielwert - i.schranke) / abs(i.zielwert) > 0.05:
            r.meldungen.append(Meldung("Hinweis", "Solver", f"{i.schritt}: Lösung ist bis zu "
                                       f"{100 * (i.zielwert - i.schranke) / abs(i.zielwert):.0f}% vom Optimum "
                                       "entfernt – mehr Rechenzeit (-t) kann sie verbessern"))
    r.sekunden = time.time() - start
    return r

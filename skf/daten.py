"""Datenmodell: lädt die Schul-Konfiguration (YAML) und die Kinderliste (CSV).

Alles ist bewusst flach gehalten: ein YAML für die Schule, ein CSV für die Kinder.
Fehlende Angaben werden mit sinnvollen Standardwerten ergänzt.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import yaml

STANDARD_GEWICHTE = {
    # Klasseneinteilung
    "schulweg_pro_km": 100,       # Strafe pro km Schulweg und Kind
    "klasse": 400,                # Kosten pro eröffnete Klasse (Lehrperson, Raum)
    "groessen_abweichung": 20,    # pro Kind Abweichung von der Idealgrösse
    "geschwister_getrennt": 300,  # Geschwister in verschiedenen Schulhäusern
    "geschlecht_ungleich": 30,    # pro Kind Ungleichgewicht Mädchen/Knaben
    "foerderbedarf_ungleich": 40, # pro Kind ungleiche Verteilung Förderbedarf
    "nicht_zusammen": 1000,       # Wunsch "nicht in dieselbe Klasse" verletzt
    # Lehraufträge
    "lehrperson_pro_klasse": 200, # jede Lehrperson in einer Klasse (Klassenlehrprinzip)
    "pensum_unterschritten": 20,  # pro fehlende Lektion unter Mindestpensum
    "lehrperson_mehrere_schulhaeuser": 200,
    # Stundenplan
    "praesenz_halbtag": 10,       # pro Halbtag, an dem eine Lehrperson anwesend ist
    "schulhauswechsel": 100,      # Lehrperson an 2 Schulhäusern im selben Halbtag
    "springstunde": 15,           # Lücke im Halbtag einer Lehrperson
}


@dataclass
class Raum:
    name: str
    typ: str
    plaetze: int


@dataclass
class Schulhaus:
    name: str
    kuerzel: str
    lat: float
    lon: float
    raeume: list[Raum]
    nutzt: dict[str, str] = field(default_factory=dict)  # Raumtyp -> anderes Schulhaus


@dataclass
class Vorlage:
    """Ein erlaubter Klassentyp, z.B. 3. Klasse oder Mischklasse 1./2."""
    jahrgaenge: list[str]
    min: int
    max: int
    ideal: int
    raumtyp: str = "Klassenzimmer"
    strafe: int = 0
    min_pro_jahrgang: int = 0
    schulhaeuser: list[str] | None = None  # None = alle
    bezeichnung: str = ""                   # z.B. "KG" statt "KG1/KG2"


@dataclass
class Fach:
    name: str
    raumtyp: str = "Klassenzimmer"  # Klassenzimmer = eigenes Zimmer der Klasse
    dauer: int = 1                  # 2 = Doppellektion
    max_pro_tag: int = 2


@dataclass
class Lehrperson:
    name: str
    faecher: list[str]
    pensum_min: int
    pensum_max: int
    jahrgaenge: list[str] | None = None
    schulhaeuser: list[str] | None = None
    nicht_verfuegbar: set[int] = field(default_factory=set)  # Slot-Indizes


@dataclass
class Kind:
    id: str
    name: str
    jahrgang: str
    geschlecht: str
    adresse: str
    lat: float | None
    lon: float | None
    familie: str = ""
    foerderbedarf: bool = False
    schulhaus_fix: str = ""
    nicht_mit: list[str] = field(default_factory=list)


@dataclass
class Slot:
    index: int
    tag: str
    halbtag: str      # z.B. "VM" oder "NM"
    nr: int           # Lektion innerhalb des Halbtags (0-basiert)
    zeit: str

    @property
    def label(self) -> str:
        return f"{self.tag} {self.zeit}"


@dataclass
class Schule:
    name: str
    jahrgaenge: list[str]
    schulhaeuser: list[Schulhaus]
    vorlagen: list[Vorlage]
    max_schulweg_m: dict[str, int]
    umweg_faktor: float
    faecher: dict[str, Fach]
    stundentafel: dict[str, dict[str, int]]
    lehrpersonen: list[Lehrperson]
    slots: list[Slot]
    blockzeiten: bool
    gewichte: dict[str, int]
    max_klassen: int | None = None

    def schulhaus(self, name: str) -> Schulhaus:
        for s in self.schulhaeuser:
            if s.name == name:
                return s
        raise KeyError(f"Unbekanntes Schulhaus: {name}")

    def max_schulweg(self, jahrgang: str) -> int:
        return self.max_schulweg_m.get(jahrgang, self.max_schulweg_m.get("default", 10**9))

    def halbtage(self) -> list[tuple[str, str]]:
        seen: list[tuple[str, str]] = []
        for s in self.slots:
            if (s.tag, s.halbtag) not in seen:
                seen.append((s.tag, s.halbtag))
        return seen


def _parse_slots(raster: dict) -> list[Slot]:
    tage = raster.get("tage", ["Mo", "Di", "Mi", "Do", "Fr"])
    bloecke: dict[str, list[str]] = raster["halbtage"]
    frei = set(raster.get("frei", []))
    slots: list[Slot] = []
    for tag in tage:
        for ht, zeiten in bloecke.items():
            if tag in frei or f"{tag}-{ht}" in frei:
                continue
            for nr, zeit in enumerate(zeiten):
                slots.append(Slot(len(slots), tag, ht, nr, zeit))
    return slots


def _slot_set(angaben: list[str], slots: list[Slot]) -> set[int]:
    """Übersetzt z.B. ["Mi", "Fr-NM", "Mo-VM-1"] in Slot-Indizes (Lektion 1-basiert)."""
    result: set[int] = set()
    for a in angaben:
        teile = a.split("-")
        for s in slots:
            if s.tag != teile[0]:
                continue
            if len(teile) >= 2 and s.halbtag != teile[1]:
                continue
            if len(teile) >= 3 and s.nr != int(teile[2]) - 1:
                continue
            result.add(s.index)
    return result


def _liste(wert) -> list[str] | None:
    if wert is None:
        return None
    if isinstance(wert, (str, int)):
        return [str(wert)]
    return [str(v) for v in wert]


def lade_schule(pfad: str | Path) -> Schule:
    cfg = yaml.safe_load(Path(pfad).read_text(encoding="utf-8"))

    schulhaeuser = []
    for sh in cfg["schulhaeuser"]:
        raeume = []
        for r in sh.get("raeume", []):
            anzahl = r.get("anzahl", 1)
            for i in range(anzahl):
                name = r.get("name") or f"{r['typ']} {i + 1}"
                if anzahl > 1 and r.get("name"):
                    name = f"{r['name']} {i + 1}"
                raeume.append(Raum(name, r["typ"], int(r.get("plaetze", 25))))
        schulhaeuser.append(Schulhaus(
            name=sh["name"], kuerzel=sh.get("kuerzel", sh["name"][:2].upper()),
            lat=float(sh["lat"]), lon=float(sh["lon"]), raeume=raeume,
            nutzt=dict(sh.get("nutzt", {}))))

    kb = cfg.get("klassenbildung", {})
    vorlagen = []
    for v in kb["vorlagen"]:
        jg = _liste(v["jahrgaenge"])
        vorlagen.append(Vorlage(
            jahrgaenge=jg, min=int(v["min"]), max=int(v["max"]),
            ideal=int(v.get("ideal", (v["min"] + v["max"]) // 2)),
            raumtyp=v.get("raumtyp", "Klassenzimmer"), strafe=int(v.get("strafe", 0)),
            min_pro_jahrgang=int(v.get("min_pro_jahrgang", 4 if len(jg) > 1 else 0)),
            schulhaeuser=_liste(v.get("schulhaeuser")), bezeichnung=v.get("bezeichnung", "")))

    slots = _parse_slots(cfg["zeitraster"])

    faecher = {name: Fach(name, **(f or {})) for name, f in cfg["faecher"].items()}
    stundentafel = {str(k): v for k, v in cfg["stundentafel"].items()}
    for jg, tafel in stundentafel.items():
        for f in tafel:
            if f not in faecher:
                raise ValueError(f"Stundentafel {jg}: Fach '{f}' ist nicht unter 'faecher' definiert")

    lehrpersonen = []
    for lp in cfg.get("lehrpersonen", []):
        pensum = lp.get("pensum", [0, len(slots)])
        if isinstance(pensum, int):
            pensum = [pensum, pensum]
        lehrpersonen.append(Lehrperson(
            name=lp["name"], faecher=_liste(lp["faecher"]),
            pensum_min=int(pensum[0]), pensum_max=int(pensum[1]),
            jahrgaenge=_liste(lp.get("jahrgaenge")),
            schulhaeuser=_liste(lp.get("schulhaeuser")),
            nicht_verfuegbar=_slot_set(lp.get("nicht_verfuegbar", []), slots)))

    gewichte = dict(STANDARD_GEWICHTE)
    gewichte.update(cfg.get("gewichte", {}))

    return Schule(
        name=cfg.get("name", "Schule"),
        jahrgaenge=[str(j) for j in cfg["jahrgaenge"]],
        schulhaeuser=schulhaeuser, vorlagen=vorlagen,
        max_schulweg_m={str(k): int(v) for k, v in kb.get("max_schulweg_m", {}).items()},
        umweg_faktor=float(kb.get("umweg_faktor", 1.3)),
        faecher=faecher, stundentafel=stundentafel, lehrpersonen=lehrpersonen,
        slots=slots, blockzeiten=bool(cfg["zeitraster"].get("blockzeiten", True)),
        gewichte=gewichte, max_klassen=kb.get("max_klassen"))


def lade_kinder(pfad: str | Path) -> list[Kind]:
    kinder = []
    with open(pfad, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            def num(key):
                v = (row.get(key) or "").strip()
                return float(v) if v else None
            kinder.append(Kind(
                id=row["id"].strip(), name=row.get("name", "").strip(),
                jahrgang=row["jahrgang"].strip(),
                geschlecht=(row.get("geschlecht") or "").strip().lower()[:1],
                adresse=(row.get("adresse") or "").strip(),
                lat=num("lat"), lon=num("lon"),
                familie=(row.get("familie") or "").strip(),
                foerderbedarf=(row.get("foerderbedarf") or "").strip().lower() in ("1", "ja", "true", "x"),
                schulhaus_fix=(row.get("schulhaus_fix") or "").strip(),
                nicht_mit=[x.strip() for x in (row.get("nicht_mit") or "").split(";") if x.strip()]))
    return kinder

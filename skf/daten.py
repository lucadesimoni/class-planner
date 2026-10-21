# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Datenmodell: lädt die Schul-Konfiguration (YAML) und die Kinderliste (CSV).

Alles ist bewusst flach gehalten: ein YAML für die Schule, ein CSV für die Kinder.
Fehlende Angaben werden mit sinnvollen Standardwerten ergänzt. Ein Kantonsprofil
(z.B. ``basis_profil: luzern``) liefert rechtliche Vorgaben samt Quellen; die
Schul-Konfiguration überschreibt das Profil.
"""
from __future__ import annotations

from collections import Counter

import math
import re
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
    "foerderbedarf_ungleich": 40, # pro Kind ungleiche Verteilung Förderbedarf/IF/DaZ/IS
    "nicht_zusammen": 1000,       # Wunsch "nicht in dieselbe Klasse" verletzt
    "schulhaus_gewechselt": 150,  # Kind wechselt gegenüber Vorjahr das Schulhaus
    "klasse_getrennt": 60,        # bisherige Klasse wird auf mehrere Klassen verteilt
    "allein_aus_klasse": 200,     # Gspänli-Regel: Kind als einziges aus seiner bisherigen Klasse/KG-Gruppe
    "wunsch_zusammen": 250,       # Wunsch der Erziehungsberechtigten "zusammen mit" nicht erfüllt
    "wunsch_schulhaus": 150,      # Wunsch-Schulhaus der Erziehungsberechtigten nicht erfüllt
    # Lehraufträge
    "lehrperson_pro_klasse": 200, # jede Lehrperson in einer Klasse (Klassenlehrprinzip)
    "pensum_unterschritten": 20,  # pro fehlende Lektion unter Mindestpensum
    "lehrperson_mehrere_schulhaeuser": 200,
    "lehrperson_kontinuitaet": 300, # Lehrperson führt ihre bisherige Klasse weiter (Bonus)
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
    nicht_verfuegbar: set[int] = field(default_factory=set)  # Slot-Indizes


@dataclass
class Schulhaus:
    name: str
    kuerzel: str
    lat: float
    lon: float
    raeume: list[Raum]
    nutzt: dict[str, str] = field(default_factory=dict)  # Raumtyp -> anderes Schulhaus
    nicht_verfuegbar: set[int] = field(default_factory=set)  # Schulhaus geschlossen
    stufen: list[str] | None = None  # Jahrgänge, die hier zur Schule gehen (None = alle mit passendem Raum)


def stufen_liste(angabe, jahrgaenge: list[str]) -> list[str] | None:
    """"KG1-6" / ["KG1-KG2", "1-6"] / "S1-S3" / "5-S3" → Jahrgänge in Schulfolge.
    Eine Stufe ohne Niveau ("S1") steht für alle ihre Niveaus (S1A, S1B, S1C)."""
    if angabe in (None, "", []):
        return None
    teile = [t.strip() for x in (angabe if isinstance(angabe, list) else [angabe])
             for t in re.split(r"[;,]", str(x)) if t.strip()]
    folge = list(dict.fromkeys(stamm(j) for j in jahrgaenge))

    def jg(stufe: str) -> list[str]:
        return [j for j in jahrgaenge if j == stufe or stamm(j) == stufe]

    out: list[str] = []
    for t in teile:
        von, _, bis = t.partition("-")
        von, bis = von.strip(), bis.strip()
        if bis:
            a, b = stamm(von), stamm(bis)
            if a not in folge or b not in folge:
                raise ValueError(f"Stufen '{t}': unbekannt (vorhanden: {', '.join(folge)})")
            for s in folge[folge.index(a):folge.index(b) + 1]:
                out += jg(s)
        else:
            if not jg(von):
                raise ValueError(f"Stufe '{von}': unbekannt (vorhanden: {', '.join(folge)})")
            out += jg(von)
    return list(dict.fromkeys(out))


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
    bisherige_klasse: str = ""   # Klasse aus dem Vorjahr, die weitergeführt werden soll
    kuerzel: str = ""


MERKMALE = ("if", "daz", "is", "foerderbedarf")


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
    if_: bool = False             # Integrative Förderung
    daz: str = ""                 # Deutsch als Zweitsprache: "" | "anfang" | "aufbau"
    is_: bool = False             # Integrative Sonderschulung
    bisheriges_schulhaus: str = ""
    bisherige_klasse: str = ""       # z.B. KG-Gruppe im Vorjahr ("BM KGb")
    zusammen_mit: list[str] = field(default_factory=list)  # Wunsch der Erziehungsberechtigten (IDs)
    wunsch_schulhaus: str = ""       # Wunsch der Erziehungsberechtigten
    bemerkung: str = ""
    bus: str = ""                    # Schulbuslinie (optional)
    uebertritt: str = ""             # Entscheid für das nächste Schuljahr (z.B. "A", "Kanti", "repetiert")
    vorname: str = ""
    nachname: str = ""
    zusatz: dict[str, str] = field(default_factory=dict)  # weitere Spalten (unverändert exportiert)

    def hat(self, merkmal: str) -> bool:
        """Merkmal wie "if", "is", "daz", "daz=anfang", "foerderbedarf" oder "alle"."""
        name, _, wert = merkmal.partition("=")
        if name == "alle":
            return True
        if name == "daz":
            return self.daz == wert if wert else bool(self.daz)
        return bool({"if": self.if_, "is": self.is_, "foerderbedarf": self.foerderbedarf}.get(name))


@dataclass
class Foerderangebot:
    """Förderlektionen pro Klasse, parallel zum Klassenunterricht (Teamteaching oder Gruppe).

    Lektionen = basis (sobald mind. 1 Kind das Merkmal hat; bei "alle" immer)
                + pro_kind x max(0, Anzahl - frei_bis), aufgerundet, höchstens max.
    """
    name: str                       # zugleich Fach, für das Lehrpersonen qualifiziert sein müssen
    merkmal: str = "alle"
    basis: dict[str, float] = field(default_factory=dict)   # Jahrgang/default -> Lektionen
    pro_kind: float = 0.0
    frei_bis: int = 0
    max: int = 99
    parallel_zu: list[str] = field(default_factory=list)    # leer = zu jedem Unterricht
    raumtyp: str = "Klassenzimmer"  # "" = Raum wird nicht geplant
    quelle: str = ""                # Schlüssel einer Quelle im Kantonsprofil
    gruppierung: str = "klasse"     # "klasse" oder "schulhaus" (Gruppen über Klassen hinweg)
    stufen: list[list[str]] = field(default_factory=list)   # Jahrgangsgruppen bei "schulhaus"
    max_gruppe: int = 99            # grössere Gruppen werden geteilt

    def lektionen(self, jahrgaenge: list[str], anzahl: int) -> int:
        if anzahl == 0 and self.merkmal != "alle":
            return 0
        basis = max((self.basis.get(j, self.basis.get("default", 0)) for j in jahrgaenge), default=0)
        return min(self.max, math.ceil(basis + self.pro_kind * max(0, anzahl - self.frei_bis) - 1e-9))


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


# Oberstufe: Jahrgang + Niveau, z.B. "S1A" = 1. Sek Niveau A. "S1" (Stamm) gilt für alle Niveaus.
_SEK = re.compile(r"^(S\d+)([A-D])$")


def stamm(jahrgang: str) -> str:
    """"S1A" → "S1"; alle anderen Jahrgänge bleiben unverändert."""
    m = _SEK.match(jahrgang)
    return m.group(1) if m else jahrgang


def niveau(jahrgang: str) -> str:
    """"S2B" → "B"; ohne Niveau ""."""
    m = _SEK.match(jahrgang)
    return m.group(2) if m else ""


@dataclass
class Buslinie:
    """Schulbus (optional): bindet Unterrichtsbeginn und -schluss der Kinder dieser Linie."""
    name: str
    schulhaeuser: list[str]
    ankunft: dict[str, int] = field(default_factory=dict)        # "NM" oder "Mi-VM" -> Minuten ab 0:00
    abfahrt: dict[str, list[int]] = field(default_factory=dict)  # "VM"/"NM" oder "Mo-NM" -> Abfahrten

    def zeiten(self, art: str, tag: str, halbtag: str):
        d = self.ankunft if art == "ankunft" else self.abfahrt
        return d.get(f"{tag}-{halbtag}", d.get(halbtag))


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
    szenario: str = "Basis"
    geschwister: str = "weich"            # "weich" | "hart" | "aus"
    is_zaehlt_als: float = 1.0            # Gewicht eines IS-Kindes bei der Klassengrösse
    max_is_pro_klasse: int | None = None
    ausgleich: tuple[str, ...] = MERKMALE  # gleichmässig auf Parallelklassen verteilen
    foerderangebote: list["Foerderangebot"] = field(default_factory=list)
    profil: dict = field(default_factory=dict)   # Kantonsprofil inkl. Quellen und Regeln
    schuljahr: str = ""
    planung: dict = field(default_factory=dict)  # Prognose: wachstum_prozent, neue_kg1_pro_jahr
    lektion_minuten: int = 45
    buslinien: list[Buslinie] = field(default_factory=list)
    bus_wartezeit: int = 15                      # Minuten, die Kinder höchstens auf Bus/Unterricht warten
    wegzeiten: dict | None = None                # None = aus; sonst {"minuten": {(a, b): min}, "kmh": float}
    uebertritte: dict = field(default_factory=dict)  # Konfiguration Schuljahreswechsel (siehe skf.uebertritt)
    kosten: dict = field(default_factory=dict)   # Kostenmodell CHF/Jahr (siehe skf.kosten), leer = nur Mengen
    hypothese: str = ""                          # Szenario: "Was wäre, wenn …" in Worten
    ziel: str = ""                               # Szenario: Kosten | Qualität | Planung
    gebiete: list = field(default_factory=list)  # geografische Hypothesen (skf.gebiete.Gebiet)

    def tafel(self, jahrgang: str) -> dict[str, int] | None:
        """Stundentafel eines Jahrgangs; Oberstufe: eigene Tafel je Niveau oder gemeinsame ("S1")."""
        return self.stundentafel.get(jahrgang, self.stundentafel.get(stamm(jahrgang)))

    def stufen(self) -> list[str]:
        """Stufen in Schulfolge ohne Niveau, z.B. KG1, KG2, 1 … 6, S1, S2, S3."""
        return list(dict.fromkeys(stamm(j) for j in self.jahrgaenge))

    def buslinie(self, name: str) -> Buslinie | None:
        return next((b for b in self.buslinien if b.name == name), None)

    def quelle(self, schluessel: str) -> dict:
        return self.profil.get("quellen", {}).get(schluessel, {})

    def schulhaus(self, name: str) -> Schulhaus:
        for s in self.schulhaeuser:
            if s.name == name:
                return s
        raise KeyError(f"Unbekanntes Schulhaus: {name}")

    def offene_slots(self, schulhaus: str) -> list:
        zu = self.schulhaus(schulhaus).nicht_verfuegbar
        return [s for s in self.slots if s.index not in zu]

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


def _mische(basis, patch):
    """Szenario-Änderungen anwenden: Dicts werden rekursiv gemischt, Listen von
    Einträgen mit 'name' werden pro Name gemischt (neu = anhängen,
    'entfernen: true' = löschen), alle anderen Werte ersetzt."""
    if isinstance(basis, dict) and isinstance(patch, dict):
        out = dict(basis)
        for k, v in patch.items():
            out[k] = _mische(basis[k], v) if k in basis else v
        return out
    if (isinstance(basis, list) and isinstance(patch, list)
            and all(isinstance(x, dict) and "name" in x for x in basis + patch)):
        out = [dict(x) for x in basis]
        for p in patch:
            treffer = next((i for i, x in enumerate(out) if x["name"] == p["name"]), None)
            if p.get("entfernen"):
                if treffer is not None:
                    out.pop(treffer)
            elif treffer is None:
                out.append(p)
            else:
                out[treffer] = _mische(out[treffer], p)
        return out
    return patch


def szenarien(pfad: str | Path) -> list[str]:
    cfg = yaml.safe_load(Path(pfad).read_text(encoding="utf-8"))
    return ["Basis"] + list((cfg.get("szenarien") or {}).keys())


SZENARIO_ZIELE = ("Kosten", "Qualität", "Planung")
_SZENARIO_INFO = ("hypothese", "ziel")  # Beschreibung eines Szenarios, keine Änderung der Daten


# Hebel für Hypothesen: verständliche Namen → Gewichte (gleiche Werte wie im Beispiel Malters)
GEWICHT_HEBEL = {
    "Weniger, grössere Klassen": ("Kosten", {"klasse": 1500, "groessen_abweichung": 5}),
    "Klassen nahe Idealgrösse": ("Qualität", {"klasse": 150, "groessen_abweichung": 60}),
    "Wenige Lehrpersonen pro Klasse, kompakte Pensen": (
        "Qualität", {"lehrperson_pro_klasse": 500, "lehrperson_kontinuitaet": 600, "springstunde": 40,
                     "praesenz_halbtag": 25}),
    "Kurze Schulwege": ("Qualität", {"schulweg_pro_km": 400, "klasse": 300}),
}


def szenario_aus_hebeln(hypothese: str, hebel: list[str] = (), wachstum_prozent: float | None = None,
                        quartier: dict | None = None, ohne_lehrpersonen: list[str] = ()) -> dict:
    """Ein Szenario (Patch wie unter 'szenarien') aus einfachen Hebeln – für App und Skripte."""
    patch: dict = {"hypothese": hypothese}
    ziele = []
    for h in hebel:
        ziel, gewichte = GEWICHT_HEBEL[h]
        ziele.append(ziel)
        patch.setdefault("gewichte", {}).update(gewichte)
    if wachstum_prozent is not None or quartier:
        ziele.append("Planung")
        patch["planung"] = {}
        if wachstum_prozent is not None:
            patch["planung"]["wachstum_prozent"] = float(wachstum_prozent)
        if quartier:
            patch["planung"]["quartiere"] = [quartier]
    if ohne_lehrpersonen:
        ziele.append("Planung")
        patch["lehrpersonen"] = [{"name": n, "entfernen": True} for n in ohne_lehrpersonen]
    if ziele:
        patch["ziel"] = Counter(ziele).most_common(1)[0][0]
    return patch


def szenario_infos(cfg: dict) -> dict[str, dict[str, str]]:
    """Szenario → {"hypothese", "ziel"} (leer, wenn nicht angegeben) – für Auswahl und Vergleich."""
    return {"Basis": {"hypothese": "Heutige Angaben ohne Änderung", "ziel": ""},
            **{str(n): {k: str((v or {}).get(k) or "") for k in _SZENARIO_INFO}
               for n, v in (cfg.get("szenarien") or {}).items()}}


PROFIL_ORDNER = Path(__file__).parent / "profile"


def beispiel_ordner() -> Path:
    """Beispieldaten: im Quellcode unter beispiele/, nach der Installation im Paket skf.beispiele."""
    quelle = Path(__file__).parent.parent / "beispiele"
    if (quelle / "vorlage").exists():
        return quelle
    return Path(__file__).parent / "beispiele"  # installiert: Paket skf.beispiele


def profile() -> list[str]:
    return sorted(p.stem for p in PROFIL_ORDNER.glob("*.yaml"))


def lade_profil(name: str) -> dict:
    pfad = PROFIL_ORDNER / f"{name}.yaml"
    if not pfad.exists():
        raise ValueError(f"Unbekanntes Kantonsprofil '{name}'. Vorhanden: {', '.join(profile())}")
    return yaml.safe_load(pfad.read_text(encoding="utf-8"))


def lese_konfiguration(pfad: str | Path, szenario: str = "Basis",
                       gewichte: dict[str, int] | None = None) -> dict:
    """Rohdaten der Konfiguration (Profil + Schule + Szenario + Gewichte) als dict."""
    cfg = yaml.safe_load(Path(pfad).read_text(encoding="utf-8"))
    if cfg.get("basis_profil"):
        cfg = _mische(lade_profil(cfg["basis_profil"]), cfg)
    alle = cfg.pop("szenarien", None) or {}
    if szenario != "Basis":
        if szenario not in alle:
            raise ValueError(f"Unbekanntes Szenario '{szenario}'. Vorhanden: {', '.join(alle) or '-'}")
        patch = dict(alle[szenario] or {})
        info = {k: str(patch.pop(k) or "") for k in _SZENARIO_INFO if k in patch}
        cfg = _mische(cfg, patch)
        cfg["_hypothese"], cfg["_ziel"] = info.get("hypothese", ""), info.get("ziel", "")
    if gewichte:
        cfg["gewichte"] = {**cfg.get("gewichte", {}), **gewichte}
    unbekannt = set(cfg.get("gewichte", {})) - set(STANDARD_GEWICHTE)
    if unbekannt:
        raise ValueError(f"Unbekannte Gewichte: {', '.join(sorted(unbekannt))}. "
                         f"Erlaubt: {', '.join(STANDARD_GEWICHTE)}")
    cfg["_szenario"] = szenario
    return cfg


def lade_schule(pfad: str | Path, szenario: str = "Basis",
                gewichte: dict[str, int] | None = None) -> Schule:
    """Lädt die Konfiguration, wendet Kantonsprofil, Szenario und Gewichte an."""
    return baue_schule(lese_konfiguration(pfad, szenario, gewichte))


def baue_schule(cfg: dict) -> Schule:
    szenario = cfg.get("_szenario", "Basis")
    slots = _parse_slots(cfg["zeitraster"])

    schulhaeuser = []
    for sh in cfg["schulhaeuser"]:
        raeume = []
        for r in sh.get("raeume", []):
            anzahl = r.get("anzahl", 1)
            for i in range(anzahl):
                name = r.get("name") or f"{r['typ']} {i + 1}"
                if anzahl > 1 and r.get("name"):
                    name = f"{r['name']} {i + 1}"
                raeume.append(Raum(name, r["typ"], int(r.get("plaetze", 25)),
                                   _slot_set(r.get("nicht_verfuegbar", []), slots)))
        schulhaeuser.append(Schulhaus(
            name=sh["name"], kuerzel=sh.get("kuerzel", sh["name"][:2].upper()),
            lat=float(sh["lat"]), lon=float(sh["lon"]), raeume=raeume,
            nutzt=dict(sh.get("nutzt", {})),
            nicht_verfuegbar=_slot_set(sh.get("nicht_verfuegbar", []), slots),
            stufen=stufen_liste(sh.get("stufen"), [str(j) for j in cfg["jahrgaenge"]])))

    kb = cfg.get("klassenbildung", {})
    profil = cfg.get("profil", {}) or {}
    groessen = (profil.get("regeln", {}) or {}).get("klassengroessen", {}) or {}
    vorlagen = []
    for v in kb["vorlagen"]:
        jg = _liste(v["jahrgaenge"])
        lo, hi = int(v["min"]), int(v["max"])
        if profil.get("verbindlich"):
            # verbindliches Profil: Klassengrössen auf den gesetzlichen Rahmen begrenzen
            for regel in groessen.values():
                if set(jg) & set(_liste(regel["jahrgaenge"])):
                    lo, hi = max(lo, int(regel["min"])), min(hi, int(regel["max"]))
        vorlagen.append(Vorlage(
            jahrgaenge=jg, min=lo, max=hi,
            ideal=min(hi, max(lo, int(v.get("ideal", (lo + hi) // 2)))),
            raumtyp=v.get("raumtyp", "Klassenzimmer"), strafe=int(v.get("strafe", 0)),
            min_pro_jahrgang=int(v.get("min_pro_jahrgang", 4 if len(jg) > 1 else 0)),
            schulhaeuser=_liste(v.get("schulhaeuser")), bezeichnung=v.get("bezeichnung", "")))

    faecher = {name: Fach(name, **(f or {})) for name, f in cfg["faecher"].items()}
    sp = cfg.get("sonderpaedagogik", {}) or {}
    angebote = []
    for a in sp.get("foerderangebote", []) or []:
        basis = a.get("basis", 0)
        basis = {str(k): float(v) for k, v in basis.items()} if isinstance(basis, dict) else {"default": float(basis)}
        angebote.append(Foerderangebot(
            name=a["name"], merkmal=a.get("merkmal", "alle"), basis=basis,
            pro_kind=float(a.get("pro_kind", 0)), frei_bis=int(a.get("frei_bis", 0)), max=int(a.get("max", 99)),
            parallel_zu=_liste(a.get("parallel_zu")) or [], raumtyp=a.get("raumtyp", "Klassenzimmer") or "",
            quelle=a.get("quelle", ""), gruppierung=a.get("gruppierung", "klasse"),
            stufen=[_liste(x) for x in a.get("stufen", [])], max_gruppe=int(a.get("max_gruppe", 99))))
        faecher.setdefault(a["name"], Fach(a["name"], raumtyp=a.get("raumtyp", "Klassenzimmer") or "",
                                           max_pro_tag=int(a.get("max_pro_tag", 2))))
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
            nicht_verfuegbar=_slot_set(lp.get("nicht_verfuegbar", []), slots),
            bisherige_klasse=str(lp.get("bisherige_klasse", "")), kuerzel=str(lp.get("kuerzel", ""))))

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
        gewichte=gewichte, max_klassen=kb.get("max_klassen"), szenario=szenario,
        geschwister=str(kb.get("geschwister", "weich")),
        is_zaehlt_als=float(sp.get("is_zaehlt_als", 1)), max_is_pro_klasse=sp.get("max_is_pro_klasse"),
        ausgleich=tuple(sp.get("ausgleich", MERKMALE)), foerderangebote=angebote, profil=profil,
        schuljahr=str(cfg.get("schuljahr", "")), planung=_planung(cfg.get("planung")),
        lektion_minuten=int(cfg["zeitraster"].get("lektion_minuten", 45)),
        buslinien=_buslinien(cfg.get("schulbus") or {}),
        bus_wartezeit=int((cfg.get("schulbus") or {}).get("wartezeit_max", 15)),
        wegzeiten=_wegzeiten(cfg.get("wegzeiten")), uebertritte=dict(cfg.get("uebertritte") or {}),
        kosten=_kosten(cfg.get("kosten")), hypothese=str(cfg.get("_hypothese", "")),
        ziel=_ziel(cfg.get("_ziel")), gebiete=_gebiete(cfg.get("gebiete")))


def _gebiete(roh) -> list:
    from .gebiete import lese_gebiete  # gebiete importiert daten
    return lese_gebiete(roh)


def _zahl(wert, wo: str) -> float:
    try:
        x = float(wert)
    except (TypeError, ValueError):
        raise ValueError(f"{wo}: Zahl erwartet, nicht '{wert}'") from None
    if x < 0 or x != x:
        raise ValueError(f"{wo}: darf nicht negativ sein ({wert})")
    return x


def _kosten(roh) -> dict:
    """Kostenmodell prüfen: alle Ansätze Zahlen ≥ 0, Raumansätze je Raumtyp."""
    if not roh:
        return {}
    if not isinstance(roh, dict):
        raise ValueError("kosten: Angaben als Liste 'Posten: Betrag' erwarten")
    erlaubt = {"lektion_chf", "raum_chf", "schulhaus_chf", "transport_chf_pro_kind", "annahme"}
    fremd = set(roh) - erlaubt
    if fremd:
        raise ValueError(f"kosten: unbekannte Angabe {', '.join(sorted(fremd))}. Erlaubt: {', '.join(sorted(erlaubt))}")
    out = {k: _zahl(v, f"kosten.{k}") for k, v in roh.items() if k not in ("raum_chf", "annahme")}
    out["raum_chf"] = {str(t): _zahl(v, f"kosten.raum_chf.{t}") for t, v in (roh.get("raum_chf") or {}).items()}
    if roh.get("annahme"):
        out["annahme"] = str(roh["annahme"])
    return out


def _planung(roh) -> dict:
    """Annahmen der Langfristplanung prüfen (siehe skf.planung)."""
    if not roh:
        return {}
    if not isinstance(roh, dict):
        raise ValueError("planung: Angaben als 'Name: Wert' erwarten")
    out = dict(roh)
    if "wachstum_prozent" in roh:
        w = roh["wachstum_prozent"]
        try:
            w = float(w)
        except (TypeError, ValueError):
            raise ValueError(f"planung.wachstum_prozent: Zahl erwartet, nicht '{w}'") from None
        if not -50 <= w <= 50:
            raise ValueError(f"planung.wachstum_prozent: {w} liegt ausserhalb von -50 bis 50 % pro Jahr")
        out["wachstum_prozent"] = w
    for k in ("neue_kg1_pro_jahr", "vollpensum_lektionen", "jahre"):
        if roh.get(k) is not None:
            out[k] = _zahl(roh[k], f"planung.{k}")
    if out.get("vollpensum_lektionen") == 0:
        raise ValueError("planung.vollpensum_lektionen: muss grösser als 0 sein")
    out["austritt_prozent"] = {}
    for j, v in (roh.get("austritt_prozent") or {}).items():
        x = _zahl(v, f"planung.austritt_prozent.{j}")
        if x > 100:
            raise ValueError(f"planung.austritt_prozent.{j}: höchstens 100 %")
        out["austritt_prozent"][str(j)] = x
    quartiere = []
    for i, q in enumerate(roh.get("quartiere") or []):
        if not isinstance(q, dict):
            raise ValueError(f"planung.quartiere[{i + 1}]: Angaben als 'name, schulhaus, ab, wohnungen' erwarten")
        name = str(q.get("name") or f"Quartier {i + 1}")
        wo = f"planung.quartiere '{name}'"
        if q.get("kinder") is None and q.get("wohnungen") is None:
            raise ValueError(f"{wo}: 'wohnungen' (mit kinder_pro_wohnung) oder 'kinder' angeben")
        quartiere.append({"name": name, "schulhaus": str(q.get("schulhaus") or ""), "ab": str(q.get("ab") or 1),
                          "wohnungen": _zahl(q.get("wohnungen") or 0, f"{wo}.wohnungen"),
                          "kinder_pro_wohnung": _zahl(q.get("kinder_pro_wohnung", 0.3), f"{wo}.kinder_pro_wohnung"),
                          "kinder": None if q.get("kinder") is None else _zahl(q["kinder"], f"{wo}.kinder")})
    out["quartiere"] = quartiere
    return out


def _ziel(wert) -> str:
    if not wert:
        return ""
    ziel = next((z for z in SZENARIO_ZIELE if z.lower() == str(wert).strip().lower()
                 or (z == "Qualität" and str(wert).strip().lower() == "qualitaet")), None)
    if ziel is None:
        raise ValueError(f"Szenario-Ziel '{wert}' unbekannt. Erlaubt: {', '.join(SZENARIO_ZIELE)}")
    return ziel


def minuten(zeit: str) -> int:
    """"07:50" → 470."""
    h, _, m = str(zeit).strip().partition(":")
    return int(h) * 60 + int(m or 0)


def _buslinien(cfg: dict) -> list[Buslinie]:
    linien = []
    for l in cfg.get("linien", []) or []:
        linien.append(Buslinie(
            name=str(l["name"]), schulhaeuser=_liste(l.get("schulhaeuser")) or [],
            ankunft={str(k): minuten(v) for k, v in (l.get("ankunft") or {}).items()},
            abfahrt={str(k): sorted(minuten(x) for x in _liste(v)) for k, v in (l.get("abfahrt") or {}).items()}))
    return linien


def _wegzeiten(cfg) -> dict | None:
    """wegzeiten: {minuten: {"A-B": 12}, geschwindigkeit_kmh: 20}; true = nur aus Koordinaten."""
    if not cfg:
        return None
    cfg = {} if cfg is True else cfg
    paare = {}
    eintraege = cfg.get("minuten") or {}
    if isinstance(eintraege, dict):  # {"A - B": 12} (Bindestrich mit Leerzeichen, falls Namen "-" enthalten)
        eintraege = [[*str(k).partition(" - " if " - " in str(k) else "-")[::2], v] for k, v in eintraege.items()]
    for a, b, v in eintraege:
        paare[str(a).strip(), str(b).strip()] = paare[str(b).strip(), str(a).strip()] = int(v)
    return {"minuten": paare, "kmh": float(cfg.get("geschwindigkeit_kmh", 20))}


def lade_kinder(pfad: str | Path, spalten: dict[str, str] | None = None) -> list[Kind]:
    """Kinderliste aus CSV (Komma/Semikolon, UTF-8/Windows-1252) oder Excel laden.

    Spaltennamen werden tolerant erkannt (z.B. Vorname/Nachname, Strasse/PLZ/Ort,
    LV95-Koordinaten), siehe skf.austausch.
    """
    from .austausch import lese_kinder
    return lese_kinder(pfad, spalten)

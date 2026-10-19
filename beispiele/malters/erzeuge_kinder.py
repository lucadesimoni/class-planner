# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Erzeugt eine fiktive, aber realistisch verteilte Kinderliste für Malters.

Es werden KEINE echten Personendaten verwendet: Namen, Adressen und Wohnorte sind
zufällig (fester Seed, daher reproduzierbar). Die Wohnorte streuen um das Dorf
Malters sowie die Ortsteile Schachen und Blatten und um einzelne Höfe.

    python beispiele/malters/erzeuge_kinder.py > beispiele/malters/kinder.csv
"""
import csv
import random
import sys

random.seed(6102)  # PLZ Malters

JAHRGAENGE = {"KG1": 78, "KG2": 82, "1": 84, "2": 80, "3": 79, "4": 83, "5": 77, "6": 81}
# (Name, Breite, Länge, Streuung in m, Anteil) – Koordinaten approximativ
GEBIETE = [
    ("Malters Dorf", 47.0363, 8.1818, 550, 0.70),
    ("Malters Nord", 47.0440, 8.1850, 350, 0.10),
    ("Schachen", 47.0350, 8.1440, 400, 0.11),
    ("Blatten", 47.0470, 8.2190, 300, 0.05),
    ("Höfe", 47.0300, 8.1700, 1200, 0.04),
]
VORNAMEN_W = ["Lea", "Mia", "Lina", "Emma", "Elena", "Sara", "Nina", "Laura", "Alina", "Lara", "Julia",
              "Anna", "Livia", "Malea", "Zoe", "Leonie", "Ella", "Noemi", "Elin", "Amelie"]
VORNAMEN_M = ["Noah", "Luca", "Leon", "Elias", "Levin", "Nico", "Jonas", "Gian", "Samuel", "Tim",
              "Lian", "Matteo", "Nils", "Lio", "David", "Jan", "Robin", "Fabio", "Louis", "Ben"]
NACHNAMEN = ["Muster", "Beispiel", "Probst", "Exempel", "Testa", "Fiktiv", "Erfunden", "Demo",
             "Platzhalter", "Annahme", "Modell", "Vorlage"]
STRASSEN = ["Ahornweg", "Birkenweg", "Eschenweg", "Lindenweg", "Ulmenweg", "Erlenweg", "Föhrenweg",
            "Tannenweg", "Weidenweg", "Buchenweg"]  # fiktiv


def ort():
    r, acc = random.random(), 0.0
    for name, lat, lon, sigma, anteil in GEBIETE:
        acc += anteil
        if r <= acc:
            dlat = random.gauss(0, sigma) / 111_320
            dlon = random.gauss(0, sigma) / (111_320 * 0.68)
            return name, round(lat + dlat, 5), round(lon + dlon, 5)
    return ort()


SCHULHAEUSER = {"Bündtmättli": ("BM", 47.0338, 8.1862), "Eischachen": ("EI", 47.0402, 8.1765)}


def vorjahres_schulhaus(lat, lon):
    """Bisheriges Schulhaus: meist das nächstgelegene, manchmal das andere."""
    nah = min(SCHULHAEUSER, key=lambda s: (SCHULHAEUSER[s][1] - lat) ** 2 + ((SCHULHAEUSER[s][2] - lon) * 0.68) ** 2)
    return nah if random.random() < 0.85 else next(s for s in SCHULHAEUSER if s != nah)


def bisherige_klasse(schulhaus, jg):
    """Klasse im Vorjahr, z.B. 3. Klasse → "BM 2a"; KG2 → "BM KGb"."""
    kuerzel = SCHULHAEUSER[schulhaus][0]
    if jg == "KG1":
        return ""
    if jg in ("KG2", "1"):  # KG2 und 1. Klasse: Kindergartengruppe im Vorjahr
        return f"{kuerzel} KG{random.choice('abcd')}"
    return f"{kuerzel} {int(jg) - 1}{random.choice('ab')}"


# Oberstufe (Sek A/B/C): eigener Zufallsgenerator, damit KG und Primar unverändert bleiben
# Lernende je Stufe und Niveau (nach Übertrittsverfahren; so gewählt, dass die Klassengrössen
# des Kantonsprofils aufgehen – sonst meldet die Konfliktanalyse genau diesen Engpass)
OBERSTUFE = {"S1": {"A": 34, "B": 32, "C": 15}, "S2": {"A": 33, "B": 22, "C": 24}, "S3": {"A": 32, "B": 33, "C": 15}}


def oberstufe(primar):
    rng = random.Random(6104)
    out, nr = [], len(primar)
    for stufe, je_niveau in OBERSTUFE.items():
        niveaus = [n for n, anzahl in je_niveau.items() for _ in range(anzahl)]
        rng.shuffle(niveaus)
        for niveau in niveaus:
            nr += 1
            if rng.random() < 0.3:  # Geschwister eines Primarkindes
                g = rng.choice(primar)
                adresse, lat, lon, familie, nachname = g["adresse"], g["lat"], g["lon"], g["familie"], g["nachname"]
                gebiet = next((x[0] for x in GEBIETE if x[0] in adresse), "")
            else:
                r, acc = rng.random(), 0.0
                for gebiet, glat, glon, sigma, anteil in GEBIETE:
                    acc += anteil
                    if r <= acc:
                        break
                lat = round(glat + rng.gauss(0, sigma) / 111_320, 5)
                lon = round(glon + rng.gauss(0, sigma) / (111_320 * 0.68), 5)
                adresse = f"{rng.choice(STRASSEN)} {rng.randint(1, 60)}, {gebiet} (fiktiv)"
                familie, nachname = f"FO{nr:04d}", rng.choice(NACHNAMEN)
            w = rng.random() < 0.49
            if stufe == "S1":  # Vorjahr: 6. Klasse in einem Primarschulhaus
                sh = rng.choice(list(SCHULHAEUSER))
                bisher = f"{SCHULHAEUSER[sh][0]} 6{rng.choice('ab')}"
            else:
                sh = "Oberstufe"
                bisher = f"OS S{int(stufe[1]) - 1}{niveau}{rng.choice('ab') if niveau != 'C' else 'a'}"
            out.append({
                "id": f"K{nr:04d}", "vorname": rng.choice(VORNAMEN_W if w else VORNAMEN_M), "nachname": nachname,
                "jahrgang": f"{stufe}{niveau}", "geschlecht": "w" if w else "m",
                "adresse": adresse, "lat": lat, "lon": lon, "familie": familie,
                "if": "ja" if rng.random() < 0.08 else "",
                "daz": rng.choices(["", "anfang", "aufbau"], [0.93, 0.02, 0.05])[0],
                "is": "ja" if rng.random() < 0.01 else "",
                "schulhaus_fix": "", "bisheriges_schulhaus": sh, "bisherige_klasse": bisher,
                "zusammen_mit": "", "nicht_mit": "", "wunsch_schulhaus": "",
                "bus": "Schulbus Blatten" if gebiet == "Blatten" else "",
                "bemerkung": "",
            })
    return out


def uebertritt(kinder):
    """Beispiel für den Schuljahreswechsel: Entscheide (Übertrittsverfahren, Repetitionen, Wegzüge)
    und Neueintritte in den Kindergarten. Eigener Zufallsgenerator."""
    rng = random.Random(6105)
    entscheide = {}
    sechste = [k for k in kinder if k["jahrgang"] == "6"]
    wahl = ["A"] * 33 + ["B"] * 27 + ["C"] * 13 + ["Langzeitgymnasium"] * 8
    rng.shuffle(wahl)
    for k, w in zip(sechste, wahl):
        entscheide[k["id"]] = w
    for jg, e, n in (("S2A", "Kurzzeitgymnasium", 3), ("S2B", "A", 2), ("S1A", "B", 2), ("S1C", "B", 2),
                     ("3", "repetiert", 2), ("KG2", "repetiert", 2)):
        for k in rng.sample([k for k in kinder if k["jahrgang"] == jg and k["id"] not in entscheide], n):
            entscheide[k["id"]] = e
    for k in rng.sample([k for k in kinder if k["id"] not in entscheide], 7):
        entscheide[k["id"]] = "Wegzug"
    neu = []
    for i in range(1, 80):
        r, acc = rng.random(), 0.0
        for gebiet, glat, glon, sigma, anteil in GEBIETE:
            acc += anteil
            if r <= acc:
                break
        w = rng.random() < 0.49
        neu.append({"id": f"N{i:04d}", "vorname": rng.choice(VORNAMEN_W if w else VORNAMEN_M),
                    "nachname": rng.choice(NACHNAMEN), "jahrgang": "KG1", "geschlecht": "w" if w else "m",
                    "adresse": f"{rng.choice(STRASSEN)} {rng.randint(1, 60)}, {gebiet} (fiktiv)",
                    "lat": round(glat + rng.gauss(0, sigma) / 111_320, 5),
                    "lon": round(glon + rng.gauss(0, sigma) / (111_320 * 0.68), 5),
                    "familie": f"FN{i:04d}", "daz": rng.choices(["", "anfang"], [0.9, 0.1])[0],
                    "bus": "Schulbus Blatten" if gebiet == "Blatten" else ""})
    return entscheide, neu


def main():
    kinder = []
    reihenfolge = list(JAHRGAENGE)
    offen = dict(JAHRGAENGE)
    fam = 0
    while any(offen.values()):
        fam += 1
        gebiet, lat, lon = ort()
        adresse = f"{random.choice(STRASSEN)} {random.randint(1, 60)}, {gebiet} (fiktiv)"
        nachname = random.choice(NACHNAMEN)
        # 1–3 Geschwister mit Altersabstand
        start = random.choice([j for j in reihenfolge if offen[j]])
        idx = reihenfolge.index(start)
        for g in range(random.choices([1, 2, 3], [0.55, 0.35, 0.10])[0]):
            i = idx + g * random.choice([1, 2, 3])
            if i >= len(reihenfolge) or not offen[reihenfolge[i]]:
                break
            jg = reihenfolge[i]
            offen[jg] -= 1
            w = random.random() < 0.49
            vorjahr = vorjahres_schulhaus(lat, lon)
            kinder.append({
                "id": f"K{len(kinder) + 1:04d}",
                "vorname": random.choice(VORNAMEN_W if w else VORNAMEN_M), "nachname": nachname,
                "jahrgang": jg, "geschlecht": "w" if w else "m",
                "adresse": adresse, "lat": lat, "lon": lon, "familie": f"F{fam:03d}",
                "if": "ja" if random.random() < 0.10 else "",
                "daz": random.choices(["", "anfang", "aufbau"], [0.90, 0.03, 0.07])[0],
                "is": "ja" if random.random() < 0.015 else "",
                "schulhaus_fix": "",
                "bisheriges_schulhaus": vorjahr if jg != "KG1" else "",
                "bisherige_klasse": bisherige_klasse(vorjahr, jg),
                "zusammen_mit": "", "nicht_mit": "",
                "wunsch_schulhaus": random.choice(list(SCHULHAEUSER)) if random.random() < 0.06 else "",
                "bus": "Schulbus Blatten" if gebiet == "Blatten" else "",  # Weiler: Schulbus statt Fussweg
                "bemerkung": "",
            })
    # Wünsche der Erziehungsberechtigten: "nicht zusammen mit" und "zusammen mit" (Gspänli,
    # bevorzugt aus derselben Kindergartengruppe bzw. Klasse)
    for _ in range(12):
        jg = random.choice(reihenfolge[2:])
        a, b = random.sample([k for k in kinder if k["jahrgang"] == jg], 2)
        a["nicht_mit"] = b["id"]
        a["bemerkung"] = "Wunsch der Erziehungsberechtigten: getrennt"
    for _ in range(30):
        jg = random.choice(reihenfolge[1:])
        a = random.choice([k for k in kinder if k["jahrgang"] == jg and not k["zusammen_mit"]])
        kandidaten = [k for k in kinder if k["jahrgang"] == jg and k is not a and k["id"] not in a["nicht_mit"]
                      and a["id"] not in k["nicht_mit"]
                      and (k["bisherige_klasse"] == a["bisherige_klasse"] or random.random() < 0.1)]
        if kandidaten:
            a["zusammen_mit"] = random.choice(kandidaten)["id"]

    kinder += oberstufe(kinder)
    if len(sys.argv) > 1 and sys.argv[1] == "uebertritt":  # Beispieldaten für den Schuljahreswechsel
        from pathlib import Path
        ordner = Path(__file__).parent / "uebertritt"
        ordner.mkdir(exist_ok=True)
        entscheide, neu = uebertritt(kinder)
        with open(ordner / "entscheide.csv", "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(["id", "entscheid"])
            wr.writerows(sorted(entscheide.items()))
        with open(ordner / "neueintritte_kg1.csv", "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(neu[0]))
            wr.writeheader()
            wr.writerows(neu)
        return
    wr = csv.DictWriter(sys.stdout, fieldnames=list(kinder[0]))
    wr.writeheader()
    wr.writerows(sorted(kinder, key=lambda k: k["id"]))


if __name__ == "__main__":
    main()

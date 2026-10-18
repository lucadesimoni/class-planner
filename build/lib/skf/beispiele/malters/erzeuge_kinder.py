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

    wr = csv.DictWriter(sys.stdout, fieldnames=list(kinder[0]))
    wr.writeheader()
    wr.writerows(sorted(kinder, key=lambda k: k["id"]))


if __name__ == "__main__":
    main()

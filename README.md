# stunden-klassen-fitter

Klasseneinteilung **und** Stundenplan für Schulen mit mehreren Schulhäusern – als
exakte mathematische Optimierung (Google OR-Tools CP-SAT), konfiguriert mit **einer
YAML-Datei** für die Schule und **einer CSV-Datei** für die Kinder.

Berücksichtigt werden:

| Bereich | Harte Regeln (immer erfüllt) | Weiche Ziele (gewichtet, optimiert) |
|---|---|---|
| **Klassen** | Jahrgang passt zum Klassentyp, Klassengrösse min/max, Raumgrösse, ein Raum pro Klasse, max. Schulweg, fixes Schulhaus, Kapazität der Spezialräume (z.B. Turnhallen-Lektionen) | kurze Schulwege (Adresse → Schulhaus), wenige Klassen, Grösse nahe am Ideal, Geschwister im selben Schulhaus, ausgeglichene Geschlechter & Förderbedarf, "nicht zusammen"-Wünsche, wenig Mischklassen |
| **Lehraufträge** | Qualifikation (Fach, Jahrgang, Schulhaus), max. Pensum, Verfügbarkeit, Blockzeiten an jedem Tag abdeckbar | Klassenlehrprinzip (wenige Lehrpersonen pro Klasse), Mindestpensum, wenige Schulhäuser pro Lehrperson |
| **Stundenplan** | Stundentafel, keine Doppelbelegung von Klasse/Lehrperson/Raum, Verfügbarkeit von Lehrpersonen, **Schulhäusern und Räumen**, Raum gross genug, Doppellektionen, max. Lektionen pro Fach/Tag, Blockzeiten, keine Lücken für Kinder | wenige Präsenz-Halbtage und keine Springstunden für Lehrpersonen, keine Schulhauswechsel im Halbtag |

Dazu kommen **Szenarien** (Varianten nebeneinander vergleichen), **einstellbare
Gewichte**, **Meldungen mit Schweregrad** (Fehler / Warnung / Hinweis) und ein
**visueller HTML-Bericht**.

## Schnellstart (Beispiel Malters)

```bash
pip install -e .            # oder: pip install ortools pyyaml
python -m skf beispiele/malters/schule.yaml beispiele/malters/kinder.csv -o ausgabe
# alle Szenarien rechnen und vergleichen:
python -m skf beispiele/malters/schule.yaml beispiele/malters/kinder.csv -o ausgabe -s alle
```

Danach `ausgabe/bericht.html` (bzw. `ausgabe/vergleich.html`) im Browser öffnen.
Ein fertig gerechnetes Ergebnis liegt in [`beispiele/malters/ergebnis/`](beispiele/malters/ergebnis/).

Das Beispiel bildet die Primarschule Malters (LU) nach: Schulhäuser **Bündtmättli**
und **Eischachen** (je mit 4 Kindergärten) und den Wald-Kindergarten **Im Feld**.
**Kinder, Adressen, Lehrpersonen, Raumzahlen, Koordinaten und Stundentafel sind fiktiv
bzw. Annahmen** – die Kinderliste wird mit `beispiele/malters/erzeuge_kinder.py`
zufällig, aber reproduzierbar erzeugt (644 Kinder in Dorf, Schachen, Blatten und auf Höfen).

## Ausgabe

| Datei | Inhalt |
|---|---|
| `bericht.html` | Kennzahlen, Status-Banner, filterbare Meldungen, Karte der Wohnorte, Klassenliste, Auslastung der Lehrpersonen, Raumbelegungs-Heatmap, Stundenpläne je Klasse und Lehrperson (mit markierten Problemstellen) |
| `vergleich.html` | Szenarien nebeneinander (nur bei mehreren Szenarien) |
| `einteilung.csv` | Kind → Schulhaus, Klasse, Schulweg |
| `klassen.csv` | Klassen mit Raum, Grösse, ♀/♂, Förderbedarf |
| `lehrauftraege.csv` | Lehrperson × Klasse × Fach × Lektionen |
| `stundenplan.csv` | Tag, Zeit, Klasse, Fach, Lehrperson, Raum |
| `meldungen.csv` | alle Meldungen mit Schweregrad |

### Meldungen und Schweregrade

| Schweregrad | Bedeutung | Beispiele |
|---|---|---|
| ⛔ **Fehler** | Regel verletzt oder Daten unbrauchbar – Ergebnis so nicht verwendbar | zu wenig Plätze, Fach ohne Lehrperson, keine Lösung möglich |
| ⚠ **Warnung** | zulässig, aber vermutlich nicht gewollt | Schulweg über Maximum, Räume zu >95 % ausgelastet, Lehrperson nicht eingesetzt |
| ℹ **Hinweis** | Verbesserungspotenzial | Springstunde, Pensum unterschritten, unausgeglichene Klasse, Lösung noch nicht beweisbar optimal |

Die **Vorprüfung** läuft vor dem Rechnen und findet die häufigsten Ursachen für
"keine Lösung" (Platz, Pensen, fehlende Räume/Qualifikationen). Nach dem Rechnen
prüft ein **unabhängiger Prüfer** alle harten Regeln nochmals durch Nachzählen.
Im Bericht sind betroffene Klassen, Lehrpersonen und Zellen im Stundenplan farbig
markiert (Tooltip zeigt den Grund).

## Kinderliste (CSV)

```csv
id,name,jahrgang,geschlecht,adresse,lat,lon,familie,foerderbedarf,schulhaus_fix,nicht_mit
K0001,Lara Beispiel,3,w,"Ahornweg 4, 6102 Malters",47.0349,8.1971,F001,,,
K0002,Noah Beispiel,KG2,m,"Ahornweg 4, 6102 Malters",47.0349,8.1971,F001,ja,,K0007
```

Pflicht sind `id` und `jahrgang` sowie Koordinaten (`lat`/`lon`) **oder** eine
`adresse` zusammen mit `--geocodieren` (Abfrage bei geo.admin.ch, mit Cache).
Optional: `familie` (Geschwister), `foerderbedarf` (ja), `schulhaus_fix`,
`nicht_mit` (IDs mit `;` getrennt).

## Schul-Konfiguration (YAML)

Vollständiges Beispiel: [`beispiele/malters/schule.yaml`](beispiele/malters/schule.yaml).

```yaml
schulhaeuser:
  - name: Bündtmättli
    lat: 47.0338
    lon: 8.1862
    nicht_verfuegbar: [Mi-NM]              # Schulhaus geschlossen
    nutzt: {Wald: Im Feld}                 # Raumtyp eines anderen Schulhauses mitbenutzen
    raeume:
      - {name: BM-Zi, typ: Klassenzimmer, anzahl: 13, plaetze: 25}
      - {name: BM-Halle, typ: Turnhalle, anzahl: 2, plaetze: 30, nicht_verfuegbar: [Fr-NM]}

klassenbildung:
  max_schulweg_m: {KG1: 4000, default: 6000}
  vorlagen:                                # erlaubte Klassentypen
    - {jahrgaenge: ["1"], min: 16, max: 24, ideal: 21}
    - {jahrgaenge: ["1", "2"], min: 16, max: 22, strafe: 150}   # Mischklasse

zeitraster:
  halbtage: {VM: ["08:00", "08:50", "09:55", "10:45"], NM: ["13:30", "14:20"]}
  frei: [Mi-NM]
  blockzeiten: true

faecher:
  Sport: {raumtyp: Turnhalle, max_pro_tag: 1}
  TTG: {raumtyp: Werkraum, dauer: 2}       # Doppellektion

stundentafel:
  "1": {Deutsch: 6, Mathematik: 5, Sport: 3, TTG: 2}

lehrpersonen:
  - {name: A. Muster, faecher: [Deutsch, Mathematik], jahrgaenge: ["1", "2"],
     schulhaeuser: Bündtmättli, pensum: [20, 28], nicht_verfuegbar: [Mi, Fr-NM, Mo-VM-1]}
```

**Verfügbarkeiten** (`nicht_verfuegbar`) gibt es für Lehrpersonen, Schulhäuser und
Räume: `Mi` = ganzer Tag, `Fr-NM` = Halbtag, `Mo-VM-1` = einzelne Lektion.

### Gewichte

Jedes weiche Ziel hat ein Gewicht (Strafpunkte). Höheres Gewicht bedeutet wichtiger.
Einstellbar unter `gewichte:` in der YAML, pro Szenario oder auf der Kommandozeile:

```bash
python -m skf schule.yaml kinder.csv -g schulweg_pro_km=400 -g klasse=300
python -m skf --gewichte-anzeigen                            # alle Gewichte mit Standardwert
```

### Szenarien

Ein Szenario beschreibt nur die **Änderungen** gegenüber der Basis. Dicts werden
gemischt, Listen mit `name` pro Eintrag gemischt, `entfernen: true` löscht einen
Eintrag:

```yaml
szenarien:
  Kurze Schulwege:
    gewichte: {schulweg_pro_km: 400}
  Umbau Eischachen:
    schulhaeuser:
      - name: Eischachen
        raeume:
          - {name: EI-Zi, anzahl: 8}
  Lehrpersonenmangel:
    lehrpersonen:
      - {name: BM Lehrperson 12, entfernen: true}
```

```bash
python -m skf schule.yaml kinder.csv -s "Kurze Schulwege"    # ein Szenario
python -m skf schule.yaml kinder.csv -s alle                 # alle + vergleich.html
```

## Wie es rechnet

1. **Vorprüfung**: Plausibilität, Kapazitäten, Qualifikationen.
2. **Klasseneinteilung A**: Schulhaus pro Kind und Klassentyp pro Raum. Gezählt wird
   nur, wie viele Kinder welchen Jahrgangs in eine Klasse kommen. Das macht das Modell
   klein und frei von Symmetrien.
3. **Klasseneinteilung B**: pro Schulhaus konkrete Kinder auf Parallelklassen
   (Ausgleich Geschlecht/Förderbedarf, "nicht_mit").
4. **Lehraufträge**: Klasse × Fach → Lehrperson, inkl. Fluss-Bedingung, dass die
   Blockzeiten an jedem Tag mit den verfügbaren Lehrpersonen und Räumen abdeckbar sind.
5. **Stundenplan**: Zeitfenster und Spezialräume. Schulhäuser ohne gemeinsame
   Lehrpersonen oder Räume werden getrennt gelöst. Das ist schneller und bleibt exakt.
6. **Prüfung**: Harte Regeln werden unabhängig nachgezählt, dazu kommen Qualitätshinweise.

Jeder Schritt meldet, ob die Lösung **beweisbar optimal** ist oder wie weit sie
höchstens vom Optimum entfernt ist. Mehr Rechenzeit (`-t`) verkleinert diese Lücke.
Die Zerlegung in Schritte macht grosse Schulen schnell lösbar. Den Schritten liegen
notwendige Bedingungen der späteren Schritte zugrunde (Raumkapazität,
Blockzeit-Abdeckung), damit sie zueinander passen.

Schulwege werden als Luftlinie × `umweg_faktor` (Standard 1.3) geschätzt.

## Tests

```bash
pip install -e ".[test]"
pytest
```

## Lizenz

GPL-3.0, siehe [LICENSE](LICENSE).

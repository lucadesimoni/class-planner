# stunden-klassen-fitter

Klasseneinteilung **und** Stundenplan für Volksschulen mit mehreren Schulhäusern, gelöst
als exakte mathematische Optimierung mit Google OR-Tools CP-SAT. Die Eingaben sind
bewusst schlicht: **eine YAML-Datei** für die Schule und **eine CSV- oder Excel-Liste**
für die Kinder. Ein **Kantonsprofil** (aktuell Luzern) liefert die rechtlichen Vorgaben
samt Quellenangaben.

| Bereich | Harte Regeln (immer erfüllt) | Weiche Ziele (gewichtet, optimiert) |
|---|---|---|
| **Klassen** | Jahrgang passt zum Klassentyp, Klassengrösse (optional verbindlich nach Kantonsrecht), Raumgrösse, ein Raum pro Klasse, max. Schulweg, fixes Schulhaus, Kapazität der Spezialräume, **IS**: max. Anzahl pro Klasse und Mehrfachzählung bei der Klassengrösse, Geschwister im selben Schulhaus (Modus `hart`) | kurze Schulwege, wenige Klassen, Grösse nahe am Ideal, Geschwister im selben Schulhaus (Modus `weich`), **Kontinuität** (bisheriges Schulhaus, bisherige Klasse zusammen), ausgeglichene Verteilung von Geschlecht, **IF, DaZ, IS**, "nicht zusammen"-Wünsche, wenig Mischklassen |
| **Lehraufträge** | Qualifikation (Fach, Jahrgang, Schulhaus), max. Pensum, Verfügbarkeit, Blockzeiten an jedem Tag abdeckbar, **Förderlektionen IF/DaZ** nur an qualifizierte Lehrpersonen | Klassenlehrprinzip, **gleiche Lehrperson führt ihre bisherige Klasse weiter**, Mindestpensum, wenige Schulhäuser pro Lehrperson |
| **Stundenplan** | Stundentafel, keine Doppelbelegung von Klasse/Lehrperson/Raum, Verfügbarkeit von Lehrpersonen, **Schulhäusern und Räumen**, Raum gross genug, Doppellektionen, max. Lektionen pro Fach/Tag, Blockzeiten, keine Lücken für Kinder, **Förderlektionen parallel** zu passenden Fächern (Teamteaching bzw. DaZ-Gruppen über Klassen hinweg) | wenige Präsenz-Halbtage, keine Springstunden, keine Schulhauswechsel im Halbtag |

Dazu gibt es Szenarien zum Vergleichen von Varianten, einstellbare Gewichte,
**Meldungen mit Schweregrad und Quellenangabe**, eine **Konfliktanalyse** bei unlösbaren
Vorgaben, standardisierten **Import/Export** sowie druckfertige **Klassenlisten und
Stundenpläne**.

## Schnellstart (Beispiel Malters)

```bash
pip install -e .                       # benötigt Python ≥ 3.10
python -m skf rechnen beispiele/malters/schule.yaml beispiele/malters/kinder.csv -o ausgabe
python -m skf rechnen beispiele/malters/schule.yaml beispiele/malters/kinder.csv -o ausgabe -s alle   # alle Szenarien
```

Danach `ausgabe/bericht.html` öffnen (bei Szenarien `ausgabe/vergleich.html`). Ein fertig
gerechnetes Ergebnis liegt in [`beispiele/malters/ergebnis/`](beispiele/malters/ergebnis/).

Das Beispiel bildet Kindergarten und Primarschule Malters (LU) nach: die Schulhäuser
**Bündtmättli** und **Eischachen** (je mit Kindergärten) und den Wald-Kindergarten
**Im Feld**. **Kinder, Adressen, Lehrpersonen, Raumzahlen, Koordinaten und Stundentafel
sind fiktiv bzw. Annahmen.** Die Kinderliste erzeugt `beispiele/malters/erzeuge_kinder.py`
zufällig, aber reproduzierbar: 644 Kinder in Dorf, Schachen, Blatten und auf Höfen, inkl.
IF/DaZ/IS und Vorjahresklassen.

Eigene Schule: `python -m skf vorlage -o meine_schule` erzeugt eine kleine, lauffähige
Vorlage (YAML, CSV und Excel), siehe [`beispiele/vorlage/`](beispiele/vorlage/).

## Befehle

| Befehl | Zweck |
|---|---|
| `skf rechnen schule.yaml kinder.csv -o ausgabe` | alles berechnen, Berichte und Listen schreiben (Kurzform: `skf schule.yaml kinder.csv`) |
| `skf pruefen schule.yaml kinder.csv` | nur Vorprüfung: Daten, Referenzen, Kapazitäten |
| `skf export schule.yaml kinder.csv -o daten.xlsx` | Stammdaten als Excel (ein Blatt pro Tabelle) oder `.json` |
| `skf import daten.xlsx -o ordner` | Stammdaten importieren → `schule.yaml` + `kinder.csv` (mit Referenzprüfung) |
| `skf kinder export.csv -o kinder.csv` | Export einer Schulverwaltung in die Standard-Kinderliste umwandeln |
| `skf vorlage -o ordner` | Vorlagen zum Erfassen eigener Daten |
| `skf profile` | verfügbare Kantonsprofile |
| `skf --gewichte-anzeigen` | alle Gewichte mit Standardwert |

Wichtige Optionen für `rechnen`: `-t SEKUNDEN` (Zeitlimit pro Szenario), `-s SZENARIO`
bzw. `-s alle`, `-g NAME=ZAHL` (Gewicht), `--spalte FELD=Spaltenname`,
`--mit-foerderdaten` (IF/DaZ/IS in Klassenlisten), `--geocodieren`, `--nur-klassen`.

## Ausgabe

| Datei | Inhalt |
|---|---|
| `bericht.html` | Status, Kennzahlen, filterbare Meldungen mit Quellen, Rechtsgrundlagen, Karte, Klassen, Auslastung der Lehrpersonen, Raumbelegungs-Heatmap, Stundenpläne mit markierten Problemstellen |
| `klassenlisten.xlsx` | Übersicht + ein druckfertiges Blatt pro Klasse (A4, Kopfzeile wiederholt) |
| `stundenplaene.xlsx` | ein Blatt pro Klasse, Lehrperson und Spezialraum + Liste aller Lektionen |
| `druck.html` | Klassenlisten und Stundenpläne, eine Seite pro Klasse/Lehrperson (Browser → Drucken/PDF) |
| `vergleich.html` | Szenarien nebeneinander |
| `einteilung.csv`, `klassen.csv`, `lehrauftraege.csv`, `stundenplan.csv`, `meldungen.csv` | Rohdaten für Weiterverarbeitung |

Förder- und Sonderschuldaten sind besonders schützenswerte Personendaten. Sie erscheinen
in Klassenlisten nur mit `--mit-foerderdaten`.

### Meldungen, Schweregrade und Konfliktanalyse

| Schweregrad | Bedeutung | Beispiele |
|---|---|---|
| ⛔ **Fehler** | Regel verletzt oder Daten unbrauchbar, Ergebnis so nicht verwendbar | unbekannte Referenz, zu wenig Plätze, keine Lösung möglich |
| ⚠ **Warnung** | zulässig, aber vermutlich nicht gewollt | Schulweg über Maximum, Klassengrösse ausserhalb des kantonalen Rahmens (nicht verbindlich), Lehrperson nicht eingesetzt |
| ℹ **Hinweis** | Verbesserungspotenzial | Springstunde, Fussweg über 30 min (Zumutbarkeit prüfen), IF unter Richtwert, Lösung noch nicht beweisbar optimal |

Bei Meldungen mit rechtlichem Bezug steht die **Quelle** dabei, verlinkt im Bericht und
mit Titel und URL in `meldungen.csv`.

Ist eine Vorgabe unlösbar, ermittelt der Solver die **Regeln, die sich widersprechen**.
Beispiel: *„Lehraufträge: nachweislich keine Lösung möglich. Diese Regeln widersprechen
sich: Blockzeiten B 1a am Mo; Blockzeiten B 2a am Mo."* Technisch hängt jede Regelgruppe
an einem Literal, und CP-SAT liefert eine Menge widersprüchlicher Annahmen, die
anschliessend verkleinert wird.

## Kantonales Recht und Richtlinien

`basis_profil: luzern` lädt [`skf/profile/luzern.yaml`](skf/profile/luzern.yaml).
Die Schul-Konfiguration kann jeden Wert überschreiben.

| Regel | Umsetzung | Quelle |
|---|---|---|
| Klassengrössen KG und Primar 16–22 | Prüfung; mit `profil: {verbindlich: true}` harte Grenze | VBV § 7 (SRL 405), DVS „Klassen & Pensen“ |
| Blockzeiten am Vormittag | Vormittage lückenlos | VBV § 3 Abs. 4 (SRL 405) |
| Integrative Förderung | ≈ 1 Vollpensum pro 140 Lernende, im Klassenverband | Förderverordnung (SRL 406), DVS-Richtlinie IF |
| DaZ Anfangs-/Aufbauunterricht | Gruppen pro Schulhaus/Stufe; 3 L (KG–2.) bzw. 4 L (ab 3.) bei 1–3 Lernenden, +0.5 L je weitere; Aufbau 2 L | DaZ-Umsetzungshilfe DVS, § 17 Förderverordnung |
| Integrative Sonderschulung | max. IS pro Klasse, Mehrfachzählung (schulintern), Warnung bei Überschreitung der Höchstgrösse | Sonderschulverordnung § 30a (SRL 409), BehiG Art. 20 |
| Schulweg | Hinweis ab 30 min Fussweg (Zumutbarkeit prüfen, ggf. Schultransport) | VBG § 36a (SRL 400a), DVS Schulweg |
| Stundentafel | Werte selbst erfassen | WOST 2017 |
| Datenschutz | Förderdaten nur auf Wunsch in Listen | KDSG § 2 (SRL 38) |

> **Ohne Gewähr.** Stand der Recherche: Oktober 2026. Massgebend sind die aktuellen
> Fassungen auf [srl.lu.ch](https://srl.lu.ch) und die Vorgaben der Dienststelle
> Volksschulbildung. Zum Mindestwert der Klassengrösse nennen ältere Fassungen 12 (KG)
> bzw. 15 (Primar) statt 16; das ist im Profil vermerkt. Die DaZ-Formel für den
> Aufbauunterricht ab 4 Lernenden und das IF-Vollpensum (28 L) sind Annahmen. Weitere
> Kantone lassen sich als zusätzliche Profil-Datei ergänzen.

## Kinderliste

```csv
id,vorname,nachname,jahrgang,geschlecht,adresse,lat,lon,familie,if,daz,is,schulhaus_fix,bisheriges_schulhaus,bisherige_klasse,nicht_mit
K0001,Lara,Beispiel,3,w,"Ahornweg 4, 6102 Malters",47.0349,8.1971,F001,ja,,,,Bündtmättli,BM 2a,
K0002,Noah,Beispiel,KG2,m,"Ahornweg 4, 6102 Malters",47.0349,8.1971,F001,,anfang,,,Bündtmättli,BM KGb,K0007
```

Pflicht sind `id` und `jahrgang`, dazu Koordinaten oder eine Adresse mit `--geocodieren`
(geo.admin.ch, mit Cache). Der Import ist tolerant und versteht unter anderem:

- **CSV mit Komma oder Semikolon**, UTF-8 oder Windows-1252, sowie **Excel (.xlsx)**
- Spaltennamen wie `Schüler-Nr`, `Vorname`/`Nachname`, `Stufe`, `Strasse`/`PLZ`/`Ort`,
  `Klasse Vorjahr`; eigene Zuordnung mit `--spalte id="Schüler-Nr"`
- **Schweizer Landeskoordinaten LV95/LV03** (`E`/`N`) → WGS84
- `1. Klasse` → `1`, `2. Kindergarten` → `KG2`; `weiblich`/`männlich`; `ja`/`x`/`1`
- `daz`: `anfang` oder `aufbau` (ein blosses `ja` gilt als Aufbauunterricht)

Unbekannte Spalten bleiben erhalten und werden mit exportiert.

## Stammdaten-Austausch

- **Excel**: `skf export … -o daten.xlsx` schreibt die Blätter Info, Schulhaeuser,
  Raeume, Klassentypen, Faecher, Lehrpersonen, Foerderangebote, Stundentafel, Kinder
  und Einstellungen. Bearbeiten und mit `skf import daten.xlsx -o ordner` zurücklesen.
- **JSON**: Format `skf-stammdaten`, Version 1, mit JSON-Schema
  [`schema/skf-stammdaten.schema.json`](schema/skf-stammdaten.schema.json).
- Export und Import sind verlustfrei (in den Tests geprüft). Beim Import und vor jeder
  Berechnung läuft eine **Referenzprüfung**: eindeutige IDs und Namen, Verweise auf
  Schulhäuser, Räume, Fächer, Jahrgänge, Kinder (`nicht_mit`) und Quellen.

## Schul-Konfiguration (YAML)

Vollständige Beispiele: [`beispiele/vorlage/schule.yaml`](beispiele/vorlage/schule.yaml) (klein) und
[`beispiele/malters/schule.yaml`](beispiele/malters/schule.yaml).

```yaml
basis_profil: luzern
profil: {verbindlich: true}               # Klassengrössen nach VBV § 7 erzwingen

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
  geschwister: weich                       # weich | hart | aus
  max_schulweg_m: {KG1: 4000, default: 6000}
  vorlagen:
    - {jahrgaenge: ["1"], min: 16, max: 22, ideal: 20}
    - {jahrgaenge: ["1", "2"], min: 16, max: 22, strafe: 150}   # Mischklasse

sonderpaedagogik:
  is_zaehlt_als: 2                         # IS-Kind zählt doppelt (schulinterne Festlegung)
  max_is_pro_klasse: 2
  foerderangebote:                         # überschreibt/ergänzt das Kantonsprofil (pro Name)
    - {name: IF, merkmal: alle, pro_kind: 0.2, parallel_zu: [Deutsch, Mathematik]}

lehrpersonen:
  - {name: A. Muster, faecher: [Deutsch, Mathematik], jahrgaenge: ["1", "2"], schulhaeuser: Bündtmättli,
     pensum: [20, 28], nicht_verfuegbar: [Mi, Fr-NM, Mo-VM-1], bisherige_klasse: BM 1a}
  - {name: SHP, faecher: [IF]}             # Förderangebote: Fach = Name des Angebots
```

**Verfügbarkeiten** (`nicht_verfuegbar`) gibt es für Lehrpersonen, Schulhäuser und Räume:
`Mi` = ganzer Tag, `Fr-NM` = Halbtag, `Mo-VM-1` = einzelne Lektion.

**Förderangebote**: Lektionen = `basis` + `pro_kind` × (Anzahl − `frei_bis`), aufgerundet,
höchstens `max`. `merkmal` ist `alle`, `if`, `is`, `daz`, `daz=anfang` oder `daz=aufbau`.
Mit `gruppierung: schulhaus` (und `stufen`, `max_gruppe`) entstehen Gruppen über Klassen
hinweg. Die Lektionen liegen dann gleichzeitig zu einem `parallel_zu`-Fach aller
beteiligten Klassen.

**Kontinuität**: `bisheriges_schulhaus` und `bisherige_klasse` bei den Kindern,
`bisherige_klasse` bei Lehrpersonen. Die Lehrperson bekommt dann bevorzugt die Klasse,
in der die meisten ihrer bisherigen Kinder sind.

### Gewichte und Szenarien

```bash
python -m skf rechnen schule.yaml kinder.csv -g schulweg_pro_km=400 -g lehrperson_kontinuitaet=600
```

```yaml
szenarien:                                 # nur Änderungen gegenüber der Basis
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

## Wie es rechnet

1. **Vorprüfung**: Referenzen, Plausibilität, Kapazitäten, Qualifikationen.
2. **Klasseneinteilung A**: Schulhaus pro Kind, Klassentyp pro Raum, Anzahl Kinder und
   IS-Kinder je Jahrgang und Klasse. Gezählt wird statt einzeln zugeteilt, deshalb bleibt
   das Modell klein und frei von Symmetrien.
3. **Klasseneinteilung B**: pro Schulhaus konkrete Kinder auf Parallelklassen.
4. **Lehraufträge**: Klasse × Fach → Lehrperson, inklusive Förderlektionen und einer
   Fluss-Bedingung für die Blockzeiten.
5. **Stundenplan**: Zeitfenster und Spezialräume. Unabhängige Schulhäuser werden getrennt
   gelöst; das ist schneller und bleibt exakt.
6. **Prüfung**: Die harten Regeln werden unabhängig nachgezählt, dazu kommen
   Qualitätshinweise und die Rechtsprüfung.

Jeder Schritt meldet, ob die Lösung **beweisbar optimal** ist oder wie weit sie höchstens
vom Optimum entfernt ist. Mehr Rechenzeit (`-t`) verkleinert diese Lücke. Schulwege
werden als Luftlinie × `umweg_faktor` (Standard 1.3) geschätzt.

## Tests

```bash
pip install -e ".[test]"
pytest
```

## Lizenz

GPL-3.0, siehe [LICENSE](LICENSE).

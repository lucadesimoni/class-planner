# Datenformate und Ablage

Alle Daten liegen als **offene Dateien** vor – lesbar mit Excel, LibreOffice, einem
Browser, einem Texteditor oder jedem Programm, ohne *Klassenbildung & Stundenplan*.
Für Menschen gibt es HTML, Excel und eine `LIESMICH.txt` in jedem Ordner, für Programme
JSON mit Schema und CSV.

**Gemeinsame Regeln:** Zeichensatz UTF-8 · CSV mit Komma, Kopfzeile, Anführungszeichen
bei Kommas im Text · Listen in einer Zelle mit `;` getrennt (z.B. `K0012; K0044`) ·
Zeiten `HH:MM` · Zeitfenster als `Mo-VM-1` (Tag, Halbtag, Lektion), `Fr-NM` (Halbtag) oder
`Mi` (ganzer Tag) · Jahrgänge `KG1`, `KG2`, `1`–`6`, Oberstufe `S1A` (1. Sek Niveau A) ·
Koordinaten WGS84 (lat/lon) oder Schweizer LV95 (E/N) beim Einlesen.

## Wo was liegt

```
<Datenordner>/                    Standard: Benutzerordner/Klassenbildung (änderbar mit SKF_DATEN)
├── arbeitsstand/                 laufende Eingaben – die App sichert bei jeder Änderung
│   ├── stammdaten.json           alle Eingaben (skf-stammdaten)
│   ├── schule.yaml               Schul-Konfiguration als Text
│   ├── kinder.csv                Lernende
│   └── LIESMICH.txt
└── verlauf/
    └── 2027-06-14_101500_Basis/  ein Ordner pro gespeicherter Berechnung
        ├── LIESMICH.txt          was im Ordner liegt
        ├── meta.json             Zeitpunkt, Notiz, Kennzahlen, Programm- und Profilversion
        ├── stammdaten.json/.xlsx Eingabedaten dieses Standes
        ├── ergebnis.json         vollständiges Ergebnis (skf-ergebnis)
        ├── zuteilung.json        Lernende → Schulhaus und Klasse
        ├── einteilung.csv, klassen.csv, lehrauftraege.csv, stundenplan.csv, meldungen.csv
        ├── bericht.html, druck.html
        └── klassenlisten.xlsx, stundenplaene.xlsx
```

`skf rechnen … -o ausgabe/` schreibt dieselben Dateien in den Ausgabeordner (ohne Notiz).
Gespeicherte Stände werden nie überschrieben; gelöscht wird nur auf ausdrücklichen Wunsch
(App: *Verlauf → Stand löschen*). Datensicherung: den Datenordner sichern genügt.

## Eingaben

### `stammdaten.json` – Format `skf-stammdaten`, Version 1

Schema: [`schema/skf-stammdaten.schema.json`](../schema/skf-stammdaten.schema.json).

| Feld | Inhalt |
|---|---|
| `format`, `version` | `"skf-stammdaten"`, `1` (Format-Version; ein neueres Format wird beim Einlesen abgelehnt) |
| `programm` | Programmversion beim Export |
| `exportiert` | Datum |
| `schule` | Schul-Konfiguration – gleicher Aufbau wie `schule.yaml` (siehe README, *Schul-Konfiguration*) |
| `kinder` | Liste der Lernenden, Felder wie in `kinder.csv` |

### `stammdaten.xlsx`

Dieselben Daten zum Bearbeiten in Excel: Blätter *Info*, *Schulhaeuser*, *Raeume*,
*Klassentypen*, *Faecher*, *Lehrpersonen*, *Foerderangebote*, *Stundentafel*, *Kinder*,
*Einstellungen* (übrige Angaben als YAML). Einlesen: App *Daten → Eigene Dateien
hochladen* oder `skf import stammdaten.xlsx -o ordner/`.

### `kinder.csv` – Lernende

| Spalte | Inhalt |
|---|---|
| `id` | eindeutige ID (Pflicht) |
| `vorname`, `nachname` (oder `name`) | Name |
| `jahrgang` | Stufe im **geplanten** Schuljahr (Pflicht), z.B. `KG1`, `3`, `S2B` |
| `geschlecht` | `w`, `m`, `d` oder leer |
| `adresse`, `lat`, `lon` | Wohnort; ohne Koordinaten wird ohne Schulweg eingeteilt |
| `familie` | gleiche Angabe = Geschwister |
| `if`, `is`, `foerderbedarf` | `ja` oder leer; `daz`: `anfang`, `aufbau` oder leer |
| `schulhaus_fix` | Schulhaus fest vorgegeben |
| `bisheriges_schulhaus`, `bisherige_klasse` | Vorjahr (Kontinuität, Gspänli-Regel) |
| `zusammen_mit`, `nicht_mit` | Wünsche der Erziehungsberechtigten (IDs, `;`-getrennt) |
| `wunsch_schulhaus` | Wunsch-Schulhaus |
| `bus` | Schulbuslinie |
| `uebertritt` | Entscheid für das **nächste** Schuljahr (`A`, `B`, `C`, `repetiert`, `überspringt`, `Kanti`, `Wegzug` …) |
| `bemerkung` | freier Text |

Weitere Spalten bleiben unverändert erhalten. Beim Einlesen werden viele Schreibweisen
erkannt (z.B. *Schüler-Nr*, *Stufe*, *KG-Gruppe*, *Buslinie*, *Entscheid*).

### `schule.yaml`

Die Schul-Konfiguration als lesbarer Text – Schulhäuser (mit Stufen und Räumen),
Klassentypen, Zeitraster, Fächer, Stundentafel, Lehrpersonen, Gewichte, Szenarien
(mit `hypothese` und `ziel`), optional Schulbus, Wegzeiten, Übertritte, Langfristplanung
(`planung`), Kostenmodell (`kosten`) und Bereiche auf der Karte (`gebiete`: Dorfzone ohne
Schulbus, Aufteilung nach Schulhaus, angenommene Lernende). Aufbau und Beispiele: README und
[`beispiele/malters/schule.yaml`](../beispiele/malters/schule.yaml).

## Ergebnisse

### `ergebnis.json` – Format `skf-ergebnis`, Version 1

Schema: [`schema/skf-ergebnis.schema.json`](../schema/skf-ergebnis.schema.json). Enthält
alles, was berechnet wurde, in einer Datei:

| Feld | Inhalt |
|---|---|
| `format`, `version`, `programm`, `profilversion`, `erstellt` | Herkunft |
| `schule`, `schuljahr`, `szenario`, `hypothese`, `ziel`, `vollstaendig` | Rahmen |
| `kennzahlen` | wie in der App (Klassen, Ø Klassengrösse, Ø Schulweg, Qualität, Kosten …) |
| `kosten` | Kostenposten pro Jahr: `posten`, `menge`, `chf`; letzte Zeile Total (leer ohne Kostenmodell) |
| `langfristplanung` | pro Schuljahr: Lernende, Zuzug Quartiere, Klassen, fehlende Räume, Lektionen, Stellen, Kosten |
| `loesungsguete` | je Rechenschritt: `beweisbar optimal` oder Mindestgüte in % |
| `zeitfenster` | Index → Tag, Halbtag, Lektion, Beginn |
| `klassen` | Name, Schulhaus, Raum, Klassentyp, Jahrgänge, IDs der Lernenden, Anzahl |
| `zuteilung` | ID → Schulhaus, Klasse, geschätzter Schulweg in m |
| `lehrauftraege` | Lehrperson, Klasse(n), Fach, Lektionen, Art (`unterricht`/`foerder`) |
| `stundenplan` | eine Zeile pro Lektion: Zeitfenster, Tag, Beginn, Klasse(n), Fach, Lehrperson, Raum |
| `meldungen` | Schweregrad, Bereich, Text, Bezug, Zeitfenster, Rechtsquelle |

### CSV-Tabellen

| Datei | Spalten |
|---|---|
| `einteilung.csv` | `id, name, jahrgang, schulhaus, klasse, schulweg_m` |
| `klassen.csv` | `klasse, schulhaus, raum, jahrgaenge, kinder, maedchen, knaben, if, daz, is, foerderbedarf` |
| `lehrauftraege.csv` | `lehrperson, klasse, fach, lektionen` |
| `stundenplan.csv` | `tag, zeit, klasse, fach, lehrperson, raum, schulhaus` |
| `meldungen.csv` | `schweregrad, bereich, text, bezug, zeit, quelle, quelle_titel, quelle_url` |

### `meta.json` und `zuteilung.json`

`meta.json`: `zeit`, `szenario`, `schule`, `schuljahr`, `notiz`, `kennzahlen`, `manuell`
(manuelle Anpassungen), `programmversion`, `profilversion`. `zuteilung.json`:
`{ "<ID>": {"schulhaus": …, "klasse": …} }` – Grundlage für Vergleiche und den
Schuljahreswechsel (`skf uebertritt --zuteilung`).

### Für Menschen

`bericht.html` (alles auf einen Blick, im Browser), `druck.html` (Klassenlisten und
Stundenpläne zum Drucken oder als PDF), `klassenlisten.xlsx`, `stundenplaene.xlsx`
(je Klasse, Lehrperson und Spezialraum).

## Schuljahreswechsel

`skf uebertritt` schreibt die Lernenden des nächsten Jahres (`kinder.csv`-Format) und ein
Protokoll `…_uebertritte.csv` mit `id, name, von, nach, art, klasse_bisher, hinweis`.
Entscheide können als eigene Liste kommen (`entscheide.csv`: `id, entscheid`).

## Datenschutz

Die Dateien enthalten Personendaten von Lernenden, teils besonders schützenswert
(IF/DaZ/IS, kantonales Datenschutzgesetz). Nur auf Geräten der Schule speichern, nicht
per unverschlüsselter E-Mail versenden und nach der kantonalen Aufbewahrungsfrist löschen.
Förderdaten erscheinen in Klassenlisten nur auf ausdrücklichen Wunsch.

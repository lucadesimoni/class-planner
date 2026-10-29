# Änderungen

Alle wesentlichen Änderungen an *Klassenbildung & Stundenplan*. Format nach
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionen nach
[Semantic Versioning](https://semver.org/lang/de/) – siehe *Versionierung* im README.
Neue Version: `python scripts/version.py 0.2.0`.

## [Unveröffentlicht]

### Lizenz
- **Neue Lizenz: Outthinkx Nicht-kommerzielle Lizenz 1.0** (`LicenseRef-Outthinkx-NC-1.0`), Rechteinhaber
  **Outthinkx by Luca De Simoni**. Gratis für Privatpersonen, Lernen und Lehre, nicht-kommerzielle Forschung und
  eine Testphase von 90 Tagen; jeder produktive Einsatz durch oder für Schulen, Gemeinden, Behörden und Firmen
  sowie der Betrieb als Dienst braucht eine schriftliche Lizenz. Gilt auch für die bisher proprietären Stände bis 0.2.0.

### Behoben (Prüfung des Rechenkerns, Oktober 2026 – je ein Regressionstest in `tests/test_haertung.py`)
- Konfliktanalyse nannte eine unbeteiligte Regel, wenn die Ursache eine feste Vorgabe war (z.B. zu kleine
  Räume); die Platz-Gleichung ist jetzt eine benannte Regel, die Vorprüfung zählt nur nutzbare Räume.
- Geschwister wurden über eine Kette gruppiert (KG nur in A, 1. Klasse nur in C …) – „Geschwister zwingend“ war
  dann unlösbar; Gruppen haben jetzt immer ein gemeinsames Schulhaus. Die Transparenz zählt wie der Optimierer.
- Ein (zeitweise) gesperrtes Schulzimmer galt als gleichwertig und wurde einer Klasse gegeben → falsche
  „keine Lösung“. Zimmer brauchen genug offene Zeitfenster, frei verfügbare werden bevorzugt.
- Zeitüberschreitung wurde wie Unlösbarkeit behandelt und bis zu 12-mal wiederholt; jetzt eine Frist für alle
  Versuche, kein Wiederholen bei Zeitüberschreitung.
- Ungequotete Uhrzeiten (YAML liest 13:30 als 810) verschoben Blockzeiten, Bus- und Wegzeiten.
- Lektionenzahl wurde gegen alle statt gegen die offenen Zeitfenster des Schulhauses geprüft.
- Rückmeldung Stundenplan → Lehraufträge überdeckte den eigentlichen Grund; nach mehreren Klasseneinteilungen
  wurde der Grund der letzten statt der ersten gemeldet.
- Konfliktanalyse beschuldigte Lehrpersonen für Zeiten, in denen Raum oder Schulhaus ohnehin geschlossen sind.
- Fördergruppen über mehrere Klassen: Qualifikation der Lehrperson nur für die erste Klasse geprüft.
- Nachprüfung zählte mehrere harte Regeln nicht nach (Raumtyp, Höchstzahl Klassen, Schulhaus des Klassentyps,
  Mindestzahl je Jahrgang, Schulhaus der Lernenden, Spezialraum Typ/Grösse).
- Eingaben: unendliche/negative Zahlen, Gewichte als Text oder negativ, umgekehrte Stufenbereiche, min > max,
  `schulbus: true`, Punkte als Text, Riesen-Mengen (Räume, Zeitfenster, Prognosejahre, Gebiete) – jetzt mit
  klarer Meldung abgelehnt; Rechenserver antwortet immer mit JSON, ohne Programmstellen.
- Szenarien: ein Eintrag ohne Namen ersetzte die ganze Liste, „entfernen“ ohne Gegenstück legte Neues an.
- `neue_kg1_pro_jahr: 0` wurde ignoriert; Stufen ohne Schulhaus verschwanden still aus der Prognose.
- IS-Gewichtung auf Zehntel gerundet (1.25 → 1.2); Modellaufbau in fester Reihenfolge.
- Überspringen in eine Stufe mit Niveaus (5. Klasse → Sek) wählte still Niveau A.

### Hinzugefügt
- **Browser-Version auf Vercel** (wie site-development): die App läuft mit stlite im Browser, gerechnet wird in
  der Vercel-Funktion `api/rechnen.py` mit derselben `skf.ablauf.rechne` (`skf/fernrechnen.py`). Datensparsam:
  Namen, Adressen und Bemerkungen verlassen den Browser nicht. Build `scripts/build_web.py`, `vercel.json`.
  Installierte Version unverändert.

### Geändert
- OR-Tools wird im Browser (Pyodide) nicht installiert (`sys_platform != 'emscripten'`); die Rechenmodule laden
  auch ohne OR-Tools.
- Kantonsprofile nur noch nach Namen aus den mitgelieferten Profilen (kein Dateipfad aus der Konfiguration).
- Planung & Kosten: Kennzahlen in Zeilen zu vier, damit Beträge nicht abgeschnitten werden.

## [0.2.0] – 2026-10-27

### Veröffentlichung
- Das Repository ist öffentlich (Quellcode einsehbar); die Lizenz bleibt proprietär (LICENSE). GitHub Actions
  laufen damit ohne Budget; *Release veröffentlichen* ist nicht mehr auf private Repositories beschränkt.

### Behoben
- Rückkopplung Klassenbildung ↔ Lehraufträge: Statt „nachweislich keine Lösung“ für eine einzelne
  Klasseneinteilung zu melden, wird mit anderen Einteilungen weitergerechnet (bis zu 3). Im Beispiel Malters
  sind damit alle Szenarien ausser dem absichtlich unlösbaren *Umbau Eischachen* planbar.
- Kartenkomponente: unsichtbar, wenn sie in einem zugeklappten Bereich geladen wurde (Höhe 0); Namen nahe
  beieinander liegender Schulhäuser überdecken sich nicht mehr.
- Auswahlfelder mit deutschem Platzhalter statt „Choose options“.
- Zeitraster: Halbtage werden nach Beginn geordnet. Stand der Nachmittag in der Konfiguration vor dem Vormittag,
  galten die Blockzeiten für den Nachmittag (falsche „keine Lösung“).
- Prognose am berechneten Ergebnis abgeglichen (Jahr 0 = tatsächliche Klassen, z.B. Mehrjahrgangsklassen).
- Langfristkosten ohne Lehraufträge (unvollständig) werden nicht mehr ausgewiesen.
- Prognose rückte Jahrgänge nach Listenposition nach (bei Sek-Niveaus falsch: S1C → S2A); jetzt nach Stufenfolge.
- Programm startete unter Python 3.10/3.11 nicht (f-Strings nach Python 3.12); CI prüft nun die Syntax mit 3.10.

### Geändert
- Eingaben für Kosten und Planung werden beim Einlesen geprüft (Zahlen, Bereiche, bekannte Angaben, Bezüge).
- Ergebnis übersichtlicher: 8 statt 11 Reiter – *Anpassen* direkt bei den Klassen (Kinder der gewählten
  Klasse), *Räume* als dritte Ansicht der Stundenpläne, *Transparenz* und *Meldungen* zusammen unter *Prüfung*.
- Mögliche Schulhäuser eines Kindes berücksichtigen nun auch, ob ein passender Raum vorhanden ist.
- Geschwisterregel nur unter Geschwistern, die im selben Schulhaus sein können.
- Kantonsprofil Luzern 2026.10.1: Klassengrössen Sekundarschule (Annahme, zu prüfen), DaZ-Gruppen auch für die Oberstufe.
- Lernende ohne Koordinaten werden ohne Schulweg eingeteilt (Warnung statt Abbruch).
- Wünsche, die auf ein nicht (mehr) vorhandenes Kind verweisen, werden mit Warnung
  übergangen statt die Berechnung zu blockieren.
- Leere Liste der Lernenden ergibt eine klare Fehlermeldung.

### Hinzugefügt
- **Adressen der Schulhäuser** (`adresse`, auch in Tabellen, Excel-Austausch und Karte); `--geocodieren` vergleicht
  die Koordinaten der Schulhäuser mit ihrer Adresse. Beispiel Malters mit den Adressen gemäss schulen-malters.ch
  (Bündtmättli, Eischachen, Naturkindergarten Im Feld, Sekundarschule im Schulhaus Muoshof).
- **Bereiche** (dauerhaft oder im Szenario): Dorfzone ohne Schulbus (`schulbus: false`) und gewünschte Aufteilung
  nach Schulhaus (`aufteilung` in %, als Wunsch oder verbindlich; Geschwister zusammen, Nähe zuerst).
- **Geografische Hypothesen:** Gebiet auf der Karte zeichnen (App) bzw. `gebiete` im Szenario – alle Lernenden
  darin einem Schulhaus zuteilen (Einzugsgebiet) und/oder angenommene Lernende ergänzen; nur Eingaben, die
  Optimierung bleibt unverändert.
- **Kosten und Qualität:** optionales Kostenmodell (`kosten`: Lektion, Räume je Typ, Schulhaus, Schulbus) und
  Qualitätskennzahlen (Klassen nahe Idealgrösse, Lehrpersonen pro Klasse, Auslastung Schulzimmer) in
  Kennzahlen, Bericht, Szenarienvergleich und `ergebnis.json` – reine Auswertung, die Optimierung bleibt unverändert.
- **Langfristplanung als Kohortenmodell:** Stufen rücken nach der Stufenfolge nach (Sek-Niveaus,
  Austritte nach einer Stufe), Wachstum, **Quartierentwicklung** (Zuzug ab einem Schuljahr); pro Jahr Lernende,
  Klassen, fehlende Räume, Lektionen, Stellen und Kosten; App-Reiter *Planung & Kosten*.
- **Szenarien als Hypothesen** (`hypothese`, `ziel`: Kosten/Qualität/Planung); in der App neue Hypothesen über
  einfache Hebel anlegen und mehrere Szenarien nacheinander rechnen und vergleichen. Beispiel Malters mit
  Szenarien für Kosten, Qualität und Planung.
- **Schuljahreswechsel und Übertritte:** jede Stufe hat eine nächste Stufe (KG → Primar → Sek A/B/C,
  Kanti/Gymnasium/Wegzug als Austritt, Repetition, Überspringen, Umstufung), Entscheide pro Kind,
  Neueintritte, Protokoll; `skf uebertritt` und App-Seite *Schuljahreswechsel*.
- **Schulhäuser mit Stufen** (`stufen: KG1-6`, `S1-S3`, `5-S3`): welche Stufen wo zur Schule gehen.
- **Oberstufe** mit Niveaus (`S1A` …), gemeinsame oder eigene Stundentafel je Niveau, kombinierte
  B/C-Klassen; Beispiel Malters mit Oberstufe (Annahmen) und Übertrittsdaten.
- **Offene Datenablage:** `ergebnis.json` (Schema `skf-ergebnis`), `stammdaten.json` und `LIESMICH.txt`
  in jedem Stand; automatische Sicherung des Arbeitsstands mit *Weiterarbeiten*; Beschreibung aller
  Dateien in `docs/datenformate.md`.
- Robustheits-Sweep `scripts/robustheit.py` (23 Grenz- und Zufallsfälle, bis 1288 Lernende).

## [0.1.0] – 2026-10-19

Erste Version.

### Rechenkern
- Klassenbildung in zwei Schritten (Schulhaus und Klassen, dann Zuteilung der Kinder)
  und Stundenplan als exakte Optimierung mit Google OR-Tools CP-SAT; Lösungsgüte pro
  Schritt (beweisbar optimal bzw. Mindestgüte in %).
- Mehrere Schulhäuser, Schulweg, Raumgrössen und Raumtypen, Mehrjahrgangsklassen,
  Verfügbarkeit von Lehrpersonen, Schulhäusern und Räumen, Blockzeiten.
- Lehraufträge mit Klassenlehrprinzip und Kontinuität; Rückkopplung Stundenplan →
  Lehraufträge bei Unlösbarkeit.
- Geschwister, Gspänli-Regel, Wünsche der Erziehungsberechtigten, IF, DaZ, IS.
- Schulbus (angefahrene Schulhäuser, Beginn und Schluss passend zu Ankunft und
  Abfahrt) und Wegzeiten der Lehrpersonen zwischen Schulhäusern – beide optional.
- Konfliktanalyse mit verständlicher Begründung, wenn keine Lösung möglich ist.
- Kantonsprofil Luzern (Profilversion 2026.10) mit Quellen.

### Bedienung und Ergebnisse
- Bedienoberfläche im Browser: Daten, Prüfen, Berechnen, Ergebnis, Verlauf, Hilfe.
- Karte (OpenStreetMap), Klassenlisten, Stundenpläne, Raumbelegung, Wünsche,
  Empfehlungen, Transparenz („Warum hier?“), Meldungen mit Schweregrad und Quelle.
- Szenarien und Gewichte, manuelle Anpassung mit sofortiger Prüfung, Verlauf mit
  Vergleich und Wiederherstellen.
- Import/Export der Stammdaten (Excel, JSON mit Schema, Format-Version 1); Raum- und
  Lehrpersonenlisten mit tolerant erkannten Spalten.

### Installation und Verteilung
- Windows-Installationsprogramm (Inno Setup) und MSIX-Paket für den Microsoft Store,
  beide mit eigenem Python, automatisch gebaut und getestet (GitHub Actions).
- Startskripte für Windows, macOS und Linux ohne vorinstalliertes Python (uv).

### Rechtliches
- Proprietäre Lizenz, Rechteinhaber Outthinkx for Communities; Drittkomponenten mit
  freizügigen Lizenzen (THIRD_PARTY_NOTICES.md); Vertragsvorlagen.

[Unveröffentlicht]: https://github.com/lucadesimoni/class-planner/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/lucadesimoni/class-planner/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/lucadesimoni/class-planner/releases/tag/v0.1.0

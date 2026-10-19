# Änderungen

Alle wesentlichen Änderungen an *Klassenbildung & Stundenplan*. Format nach
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionen nach
[Semantic Versioning](https://semver.org/lang/de/) – siehe *Versionierung* im README.
Neue Version: `python scripts/version.py 0.2.0`.

## [Unveröffentlicht]

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

[Unveröffentlicht]: https://github.com/lucadesimoni/stunden-klassen-fitter/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/lucadesimoni/stunden-klassen-fitter/releases/tag/v0.1.0

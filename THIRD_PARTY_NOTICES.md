# Drittkomponenten und Hinweise

Diese Software (© 2026 Luca De Simoni, proprietär, siehe [LICENSE](LICENSE)) verwendet
die folgenden Komponenten Dritter. Alle stehen unter **freizügigen Lizenzen**, die
den Verkauf und die proprietäre Lizenzierung der eigenen Software erlauben; keine
davon ist eine „Copyleft“-Lizenz (GPL/AGPL/LGPL), die den eigenen Code erfassen würde.
Pflicht ist im Wesentlichen: Urheberrechtsvermerk und Lizenztext mitliefern.

## Im Paket enthalten (mitverteilt)

| Komponente | Version | Lizenz | Verwendung | Lizenztext |
|---|---|---|---|---|
| [Leaflet](https://leafletjs.com) | 1.9.4 | BSD-2-Clause, © 2010–2023 Volodymyr Agafonkin, © 2010–2011 CloudMade | interaktive Karte im Bericht | [`skf/static/leaflet/LICENSE`](skf/static/leaflet/LICENSE) |
| [Material Symbols Rounded](https://fonts.google.com/icons) | 0.48.0 (npm `material-symbols`) | Apache-2.0, © Google LLC | Icon-Pfade in `skf/icons.py` (aus der Schrift erzeugt) | [`skf/static/material-symbols/LICENSE`](skf/static/material-symbols/LICENSE) |

Änderungen: Leaflet unverändert. Von Material Symbols werden nur die Umrisse einzelner
Glyphen als SVG-Pfade übernommen (skaliert, gerundet) – erzeugt mit
`scripts/erzeuge_icons.py`.

## Bei der Installation bezogen (nicht mitverteilt)

Diese Python-Pakete lädt die Installation (`uv`/`pip`) direkt aus dem Python Package
Index; sie werden mit ihren eigenen Lizenzdateien installiert. Versionen gemäss
[`uv.lock`](uv.lock).

| Paket | Lizenz | | Paket | Lizenz |
|---|---|---|---|---|
| ortools (Google OR-Tools) | Apache-2.0 | | numpy | BSD-3-Clause (+ 0BSD, MIT, Zlib, CC0) |
| streamlit | Apache-2.0 | | pyarrow | Apache-2.0 |
| pandas | BSD-3-Clause | | protobuf | BSD-3-Clause |
| openpyxl | MIT | | absl-py | Apache-2.0 |
| et-xmlfile | MIT | | pyyaml | MIT |
| altair | BSD-3-Clause | | narwhals | MIT |
| pydeck | Apache-2.0 | | pillow | MIT-CMU |
| requests | Apache-2.0 | | urllib3 | MIT |
| certifi | MPL-2.0 (unverändert genutzt) | | charset-normalizer | MIT |
| idna | BSD-3-Clause | | jinja2 | BSD-3-Clause |
| markupsafe | BSD-3-Clause | | jsonschema | MIT |
| jsonschema-specifications | MIT | | referencing | MIT |
| rpds-py | MIT | | attrs | MIT |
| click | BSD-3-Clause | | toml | MIT |
| starlette / uvicorn | BSD-3-Clause | | websockets | BSD-3-Clause |
| watchdog | Apache-2.0 | | anyio | MIT |
| h11 | MIT | | httptools | MIT |
| itsdangerous | BSD-3-Clause | | python-multipart | Apache-2.0 |
| python-dateutil | Apache-2.0 / BSD-3-Clause | | pytz | MIT |
| tzdata | Apache-2.0 | | six | MIT |
| packaging | Apache-2.0 oder BSD-2-Clause | | typing-extensions | PSF-2.0 |
| immutabledict | MIT | | colorama | BSD-3-Clause |
| exceptiongroup | MIT | | tomli | MIT |
| greenlet | MIT, PSF-2.0 | | pygments | BSD-2-Clause |

Nur für Tests (nicht Teil des Produkts): pytest (MIT), pluggy (MIT), iniconfig (MIT),
playwright (Apache-2.0), pyee (MIT).

Laufzeit/Installation: [Python](https://www.python.org) (PSF-2.0),
[uv](https://github.com/astral-sh/uv) (Apache-2.0 oder MIT) – die Startskripte laden uv
vom Hersteller herunter; es wird nicht mitverteilt.

**Wer ein Komplettpaket mit Python und allen Abhängigkeiten ausliefert** (z.B. einen
Installer), muss die Lizenztexte dieser Pakete beilegen: `uv run python scripts/lizenzen.py`
schreibt sie aus der installierten Umgebung nach `lizenzen/` (Python ≥ 3.11).

## Dienste und Daten

| Dienst | Bedingungen | Hinweis |
|---|---|---|
| OpenStreetMap-Kartendaten | [ODbL](https://www.openstreetmap.org/copyright) – Namensnennung „© OpenStreetMap-Mitwirkende“ | wird in Karte und Bericht angezeigt |
| OSM-Kartenkacheln (`tile.openstreetmap.org`) | [Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/) – kein Anspruch, nur geringe Nutzung | **für den kommerziellen Betrieb** einen Kachel-Anbieter oder [swisstopo](https://www.geo.admin.ch/de/nutzungsbedingungen) eintragen: Umgebungsvariablen `SKF_KARTE_KACHELN` (URL mit `{z}/{x}/{y}`) und `SKF_KARTE_QUELLE` (Namensnennung) |
| Geocodierung über `api3.geo.admin.ch` (optional, `--geocodieren`) | [Nutzungsbedingungen geo.admin.ch](https://www.geo.admin.ch/de/nutzungsbedingungen) – frei nutzbar mit Quellenangabe „© swisstopo“, Fair-Use | nur auf ausdrücklichen Aufruf; überträgt Adressen an den Bund – mit der Schule abklären |

## Rechtstexte und Beispieldaten

- **Gesetze und Verordnungen** (Bund, Kanton Luzern) sind nach Art. 5 URG nicht
  urheberrechtlich geschützt. Das Kantonsprofil `skf/profile/luzern.yaml` enthält eigene
  Zusammenfassungen und Verweise (Titel, Artikel, Link), keine Kopien von Richtlinien
  oder Handreichungen der Dienststelle Volksschulbildung.
- **Beispiel Malters:** Alle Lernenden, Adressen, Lehrpersonen und Wünsche sind
  **erfunden** (erzeugt mit `beispiele/malters/erzeuge_kinder.py`). Schulhausnamen und
  ungefähre Lagen dienen nur der Anschaulichkeit. Es besteht keine Verbindung zur
  Gemeinde oder Schule Malters, zum Kanton Luzern oder zur Dienststelle
  Volksschulbildung, und keine dieser Stellen hat die Software geprüft oder empfohlen.
- **Gestaltung:** angelehnt an das eigene Projekt
  [genealogy-store](https://github.com/lucadesimoni/genealogy-store) desselben Rechteinhabers.

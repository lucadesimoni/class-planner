# Plan: Geodaten für die Raumplanung (Geoportale)

Stand: Oktober 2026 · Status: **Plan, nicht umgesetzt** · gilt gleich für
*site-development* (`docs/geodata-plan.md`).

Ziel: amtliche Raumplanungsdaten über offene Schnittstellen (WMS = Kartenbild, WFS =
Geometrien) beiziehen, damit Hypothesen auf echten Zonen und Flächen beruhen statt nur auf
gezeichneten Annahmen.

## Quellen

| Quelle | Gebiet | Was | Stand der Abklärung |
|---|---|---|---|
| **Geoportal Kanton Luzern** – [geoportal.lu.ch](https://geoportal.lu.ch/), Geoinformation Kanton Luzern | Kanton Luzern (Beispiel Malters) | *Nutzungsplanung: Zonenpläne* (Bau- und Zonenreglement + Zonenplan der Gemeinden, **rechtsverbindlich**), Planungszonen (Modell `RDP_9061_Planungszonen_LU`), weitere Raumplanungs-Datensätze; Modelldokumentation auf [models.geo.lu.ch](https://models.geo.lu.ch/E1_Raumplanung/) | Datensatz auf [opendata.swiss](https://opendata.swiss/en/organization/geoinformation_kanton_luzern) gelistet, Kontakt raumdatenpool@lu.ch. **WMS-/WFS-Adressen, Lizenz und kommerzielle Nutzung noch bestätigen** (Metadaten auf geoportal.lu.ch bzw. geocat.ch). |
| [geodienste.ch](https://geodienste.ch) | alle Kantone, die liefern | Nutzungsplanung im harmonisierten Bundesmodell `npl_nutzungsplanung` (WMS/WFS/Download) | Verfügbarkeit und Bedingungen legt jeder Kanton fest – pro Kanton prüfen. |
| [geoportal.ch](https://www.geoportal.ch/) (GEOINFO) | v.a. Ostschweiz | Zonenpläne und weitere Ebenen der angeschlossenen Gemeinden | Abdeckung und Bedingungen je Gemeinde prüfen; Luzern ist nicht der Normalfall. |
| ARE (Bund) | Schweiz | ÖV-Güteklassen, Bauzonenstatistik | offen (opendata.swiss); für site-development interessant. |

## Vorgehen

**0. Abklären (1–2 Tage):** Dienst-Adressen (GetCapabilities), Datenmodell, Koordinatensystem
(LV95/EPSG:2056), Lizenz, kommerzielle Nutzung (wichtig für den Verkauf), Gebühren,
Zuschreibung. Nur Dienste mit WFS bzw. Download nutzen, weil WMS nur Bilder liefert.

**1. Baustein `geodaten` (in beiden Repos gleich aufgebaut):**
- WFS-Abruf mit Ausschnitt um Gemeinde/Standort, Umrechnung LV95 → WGS84.
- Ablage als GeoJSON im Datenordner mit Quelle, Abrufdatum, Lizenz und Datenmodell. Danach
  offline und nachvollziehbar.
- Laden ist ein bewusster Schritt (App-Knopf „Geodaten laden“ / CLI), nie während einer
  Berechnung. Fehlt ein Dienst: klare Meldung, das Programm läuft ohne Geodaten weiter.
- Quellen als Profile (`luzern`, `geodienste`, …), passend zu den Kantonsprofilen.

**2. Klassenbildung & Stundenplan (class-planner):**
- Unüberbaute Wohn- und Mischzonen als **Vorschläge für Quartier-Hypothesen**. Die Fläche
  kommt aus der Zone; Wohnungen = Fläche × Annahme Wohnungen/ha; Kinder pro Wohnung wie heute.
  Das ersetzt optional die gezeichnete Fläche (`gebiete`, `planung.quartiere`).
- Zonen für öffentliche Bauten als mögliche Orte für Schulraum oder Provisorien.
- Zonenplan als abschaltbare Kartenebene (Ergebnis, Zeichenkarte).
- Hinweis in der Prüfung, wenn ein Quartier ausserhalb einer Bauzone liegt.
- Später: Gebäude- und Wohnungsregister (GWR) für bestehende Wohnungen pro Gebiet.

**3. Site Capacity Engine (site-development):**
- Zone am Standort (zulässige Nutzung, Ausbaureserve) als Prüfung von `expandable_m2`.
- *What if we open a new site here?*: Die Karte zeigt beim Anklicken die Zone. Ein Standort
  ohne Büronutzung ergibt eine Warnung.
- ÖV-Güteklassen als optionaler Faktor für den Arbeitsweg im Optimierer – neue Gewichtung,
  nur auf ausdrücklichen Entscheid.

**4. Qualität und Recht:** Tests mit gespeicherten Beispielantworten (kein Netz in CI) und
Fehlerfällen (Dienst weg, leere Antwort, falsches Koordinatensystem). Lizenzen in den
Drittanbieter-Hinweisen bzw. im Manifest; kommerzielle Exporte sperren, solange Bedingungen
unklar sind. Abgefragt wird nur die Planungsebene, keine Personendaten.

**5. Reihenfolge:** Abklärung → Baustein mit **Luzern als erster Quelle** (Beispiel Malters)
und Cache → Bauzonen als Quartier-Vorschläge → Zone am Standort (site-development) →
Kartenebenen → weitere Kantone über geodienste.ch → optional GWR und ÖV-Güteklassen.
Grobe Schätzung: 3–5 Arbeitstage für die Schritte bis „Zone am Standort“.

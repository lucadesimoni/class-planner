# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Luca De Simoni. Alle Rechte vorbehalten.
"""Ausgabe als CSV-Dateien, als eigenständiger HTML-Bericht und als Szenarienvergleich."""
from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .icons import PFADE
from .ablauf import Ergebnis
from .pruefung import SCHWEREGRADE, Meldung, springstunden, wuensche

esc = html.escape


def ordnername(szenario: str) -> str:
    return re.sub(r"[^\w-]+", "_", szenario).strip("_") or "Basis"

# Kategoriale Reihenfolge (fix, nie zyklisch) – siehe dataviz-Referenzpalette
SERIEN = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)", "var(--s7)", "var(--s8)"]
KLASSE = {"Fehler": "sev-f", "Warnung": "sev-w", "Hinweis": "sev-h"}

CSS = """
/* Design-System angelehnt an genealogy-store (packages/web/src/index.css): helle Fläche, weisse Karten,
   feine Rahmen, Akzent Wandtafelgrün (#2f5d50 – bewusst keine Datenfarbe), 4-px-Raster, ruhige Schatten. */
:root { color-scheme: light;
  --bg:#f6f7fb; --surface:#ffffff; --surface-hover:#f1f2f8; --fg:#14171f; --fg2:#676e7d; --muted:#9ba1af;
  --grid:#e4e7ee; --base:#cdd2dd; --ring:#e4e7ee;
  --accent:#2f5d50; --accent-soft:#e8f0ed; --chart:#3d7a69;
  --belegt:#e8f0ed; --belegt-fg:#244a40; --bar:#3d7a69; --band:#e4e7ee;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4; --s6:#008300; --s7:#6250d6; --s8:#e34948;
  --crit:#c02b3c; --crit-bg:#fbeaec; --crit-border:#eec3c9; --warn:#b4690e; --warn-bg:#fdf3e3; --warn-border:#f3d9ab;
  --good:#1a8a4c; --good-bg:#eafaf1; --good-text:#1a8a4c; --info:#676e7d;
  --shadow-xs:0 1px 2px rgba(20,23,31,.05); --shadow-sm:0 2px 6px rgba(20,23,31,.07);
  --radius-sm:8px; --radius-md:12px; --radius-pill:999px;
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
* { box-sizing:border-box }
body { background:var(--bg); color:var(--fg); font:13px/1.45 var(--font); margin:0 auto; max-width:1200px;
  padding:28px 24px 48px; -webkit-font-smoothing:antialiased }
a { color:var(--accent) } a:hover { text-decoration:none }
.app-header { display:flex; align-items:center; gap:12px; margin-bottom:16px }
.logo { width:40px; height:40px; border-radius:10px; background:var(--accent); color:#fff; display:grid;
  place-items:center; box-shadow:var(--shadow-sm); flex:none } .logo .icon { width:24px; height:24px }
.app-header h1 { font-size:21px; font-weight:700; letter-spacing:-.01em; margin:0; line-height:1.2 }
.sub { color:var(--fg2); margin:2px 0 0; font-size:13px }
h2 { font-size:13px; margin:0 } h3 { font-size:14px; margin:0 0 6px }
.muted { color:var(--muted) } .fg2 { color:var(--fg2) }
.icon { width:20px; height:20px; flex:none; fill:currentColor } .icon.klein { width:15px; height:15px; vertical-align:-3px }
.section-card { background:var(--surface); border:1px solid var(--ring); border-radius:var(--radius-md);
  box-shadow:var(--shadow-xs); margin:12px 0; overflow:clip }
.section-card > summary { list-style:none; cursor:pointer; display:flex; align-items:center; justify-content:space-between;
  gap:12px; padding:12px 14px; font-size:13px }
.section-card > summary::-webkit-details-marker { display:none }
.section-card > summary:hover { background:var(--surface-hover) }
.section-title { display:inline-flex; align-items:center; gap:8px; min-width:0 } .section-title .icon { color:var(--accent) }
.section-title b { font-weight:600 }
.chevron { color:var(--fg2); transition:transform .16s ease } .section-card[open] > summary .chevron { transform:rotate(180deg) }
.section-body { padding:12px 14px 16px; border-top:1px solid var(--ring) }
.karte-box, .kachel, .banner, .panel { background:var(--surface); border:1px solid var(--ring); border-radius:var(--radius-md);
  box-shadow:var(--shadow-xs) }
.kacheln { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:8px; margin:12px 0 }
.kachel { padding:12px 14px } .kachel b { font-size:24px; display:block; font-weight:600; letter-spacing:-.01em }
.kachel span { color:var(--fg2); font-size:12px; overflow-wrap:anywhere }
.banner { padding:10px 14px; margin:0 0 4px; display:flex; gap:10px; align-items:center }
.banner.ok { background:var(--good-bg); border-color:#bfe6cf; color:#14532d }
.banner.w { background:var(--warn-bg); border-color:var(--warn-border); color:#6b3d06 }
.banner.f { background:var(--crit-bg); border-color:var(--crit-border); color:#7a1522 }
table { border-collapse:separate; border-spacing:0; width:100%; background:var(--surface); border:1px solid var(--ring);
  border-radius:var(--radius-sm); overflow:hidden }
td, th { border-bottom:1px solid var(--grid); padding:6px 9px; text-align:left; vertical-align:top }
th { color:var(--fg2); font-weight:600; font-size:12px; background:#fafbfd } tr:last-child td { border-bottom:0 }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums }
.scroll { overflow-x:auto } details:not(.section-card) { margin:6px 0 }
details:not(.section-card) > summary { cursor:pointer; font-weight:600; padding:4px 0 }
.badge { display:inline-flex; gap:4px; align-items:center; border-radius:var(--radius-pill); padding:1px 8px;
  font-size:11px; font-weight:600; border:1px solid transparent; white-space:nowrap }
.sev-f { color:var(--crit); background:var(--crit-bg); border-color:var(--crit-border) }
.sev-w { color:var(--warn); background:var(--warn-bg); border-color:var(--warn-border) }
.sev-h { color:var(--info); background:#f1f2f8; border-color:var(--ring) }
.ok-badge { color:var(--good); background:var(--good-bg); border-color:#bfe6cf }
.filter { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin:0 0 8px }
.filter button { font:inherit; cursor:pointer; border-radius:var(--radius-pill); padding:3px 10px; border:1px solid var(--base);
  background:var(--surface); color:var(--fg) }
.filter button[aria-pressed="false"] { opacity:.45; text-decoration:line-through }
.filter input { font:inherit; padding:6px 10px; border-radius:var(--radius-sm); border:1px solid var(--base);
  background:var(--surface); color:var(--fg); min-width:200px; flex:1 }
.meldungen { max-height:420px; overflow:auto }
.plan td { font-size:12px; min-width:92px; height:46px; border-right:1px solid var(--grid) }
.plan th { font-size:12px } .plan td:last-child { border-right:0 }
.plan td.zu, .heat td.zu { background:repeating-linear-gradient(45deg, transparent 0 5px, var(--grid) 5px 7px); color:var(--muted) }
.plan td.mark-f { box-shadow:inset 0 0 0 2px var(--crit) } .plan td.mark-w { box-shadow:inset 0 0 0 2px var(--warn) }
.plan td.mark-h { box-shadow:inset 0 0 0 2px var(--base) }
.plan .spring { color:var(--muted); font-style:italic } .plan .foerder { color:var(--accent); font-style:italic }
.heat { font-size:11px } .heat td, .heat th { padding:2px 3px; border-right:1px solid var(--grid); text-align:center;
  white-space:nowrap } .heat th.raum { text-align:left }
.heat td.b { background:var(--belegt); color:var(--belegt-fg) } .heat .tag { border-left:2px solid var(--base) }
.bar-row { display:grid; grid-template-columns:minmax(140px,250px) 1fr minmax(90px,max-content); gap:10px; align-items:center;
  padding:3px 0 } .bar-row .num { white-space:nowrap; text-align:right }
.bar-row .name { white-space:nowrap; overflow:hidden; text-overflow:ellipsis }
.bar-track { position:relative; height:14px }
.bar-band { position:absolute; top:3px; height:8px; background:var(--band); border-radius:4px }
.bar { position:absolute; top:2px; height:10px; background:var(--bar); border-radius:0 4px 4px 0 }
.bar-tick { position:absolute; top:-2px; width:2px; height:18px; background:var(--fg2) }
.fuss { margin-top:28px; font-size:12px; text-align:center }
.legende { display:flex; gap:14px; flex-wrap:wrap; font-size:12px; color:var(--fg2); margin:6px 0 }
.legende i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; vertical-align:-1px }
.legende i.quadrat { background:var(--fg2) } .legende i.rund { background:var(--fg2); border-radius:50%; width:8px; height:8px }
.karte { width:100%; max-width:720px; display:block } .lbl { fill:var(--fg); font-size:12px; font-weight:600 }
.osm { height:480px; border-radius:var(--radius-sm); border:1px solid var(--ring) }
.karten { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:10px }
.karten .panel { padding:12px 14px } .karten h3 { margin:.1em 0 .3em; font-size:14px }
.dringlich { border-left:4px solid var(--crit) } .rein { border-left:4px solid var(--base) }
.pos { color:var(--good) } .neg { color:var(--crit); font-weight:600 }
.groesse { display:inline-block; height:8px; background:var(--bar); border-radius:0 4px 4px 0; vertical-align:middle;
  margin-right:6px }
.checks { list-style:none; margin:0; padding:0; display:grid; gap:4px }
.checks li { display:flex; gap:8px; align-items:flex-start; padding:6px 8px; border-radius:var(--radius-sm) }
.checks li.ok .icon { color:var(--good) } .checks li.x { background:var(--crit-bg) } .checks li.x .icon { color:var(--crit) }
.checks li.n .icon { color:var(--muted) } .checks small { display:block; color:var(--fg2) }
.zwei { display:grid; grid-template-columns:repeat(auto-fit,minmax(360px,1fr)); gap:16px }
.erklaerung { color:var(--fg2); font-size:12px; margin:0 0 10px }
"""

JS = """
const zustand = {Fehler: true, Warnung: true, Hinweis: true};
function filtern() {
  const q = (document.getElementById('suche')?.value || '').toLowerCase();
  document.querySelectorAll('tr[data-sev]').forEach(tr => {
    tr.hidden = !zustand[tr.dataset.sev] || (q && !tr.textContent.toLowerCase().includes(q));
  });
}
document.querySelectorAll('button[data-sev]').forEach(b => b.addEventListener('click', () => {
  zustand[b.dataset.sev] = !zustand[b.dataset.sev];
  b.setAttribute('aria-pressed', zustand[b.dataset.sev]);
  filtern();
}));
document.getElementById('suche')?.addEventListener('input', filtern);
"""


# Einheitliche Icon-Familie: Material Symbols Rounded – dieselbe wie in der App (:material/…:)
_ICON_NAMEN = {
    "info": "info", "schule": "school", "karte": "map", "personen": "groups", "kalender": "calendar_month",
    "warnung": "warning", "ok": "check_circle", "x": "cancel", "minus": "remove_circle", "balken": "bar_chart",
    "herz": "favorite", "buch": "menu_book", "auge": "visibility", "regler": "tune", "raum": "meeting_room",
    "birne": "lightbulb", "liste": "list", "pfeil": "expand_more", "person": "person", "lehrperson": "co_present",
    "weg": "route", "gesetz": "gavel", "familie": "family_restroom",
}


def icon(name: str, klasse: str = "icon") -> str:
    pfad = PFADE[_ICON_NAMEN.get(name, name)]
    return f"<svg class='{klasse}' viewBox='0 0 24 24' aria-hidden='true'><path d='{pfad}'/></svg>"


# Schweregrade: dieselben Symbole wie in der App
ICON = {"Fehler": icon("x", "icon klein"), "Warnung": icon("warnung", "icon klein"), "Hinweis": icon("info", "icon klein")}


FUSS = ("<p class='muted fuss'>Erstellt mit Klassenbildung &amp; Stundenplan · © 2026 Luca De Simoni · "
        "Planungshilfsmittel – Entscheide trifft die Schulbehörde.</p>")


def abschnitt(titel: str, inhalt: str, symbol: str, zusatz: str = "", offen: bool = False, anker: str = "",
              status: str = "") -> str:
    """Aufklappbare Abschnittskarte (wie section-card in genealogy-store)."""
    return (f"<details class='section-card'{' open' if offen else ''}{f' id={chr(39)}{anker}{chr(39)}' if anker else ''}>"
            f"<summary><span class='section-title'>{icon(symbol)}<span><b>{esc(titel)}</b>"
            f"{f' <span class=muted>({esc(zusatz)})</span>' if zusatz else ''}</span></span>"
            f"<span class='section-title'>{status}{icon('pfeil', 'icon chevron')}</span></summary>"
            f"<div class='section-body'>{inhalt}</div></details>")


def schreibe_csv(ordner: Path, r: Ergebnis) -> None:
    ordner.mkdir(parents=True, exist_ok=True)
    schule, e = r.schule, r.einteilung
    with open(ordner / "meldungen.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["schweregrad", "bereich", "text", "bezug", "zeit", "quelle", "quelle_titel", "quelle_url"])
        for m in sorted(r.meldungen, key=lambda m: SCHWEREGRADE.index(m.schwere)):
            q = schule.quelle(m.quelle) if m.quelle else {}
            wr.writerow([m.schwere, m.bereich, m.text, m.bezug,
                         schule.slots[m.slot].label if m.slot is not None else "", m.quelle,
                         q.get("titel", ""), q.get("url", "")])
    if not e:
        return
    nach_id = {k.id: k for k in r.kinder}
    with open(ordner / "einteilung.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["id", "name", "jahrgang", "schulhaus", "klasse", "schulweg_m"])
        for k in r.kinder:
            wr.writerow([k.id, k.name, k.jahrgang, e.schulhaus_von[k.id], e.klasse_von[k.id],
                         round(e.schulweg_m[k.id])])
    with open(ordner / "klassen.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["klasse", "schulhaus", "raum", "jahrgaenge", "kinder", "maedchen", "knaben", "if", "daz", "is",
                     "foerderbedarf"])
        for c in e.klassen:
            ks = [nach_id[i] for i in c.kinder]
            wr.writerow([c.name, c.schulhaus, c.raum.name, "/".join(c.jahrgaenge), len(ks),
                         sum(k.geschlecht == "w" for k in ks), sum(k.geschlecht == "m" for k in ks),
                         sum(k.if_ for k in ks), sum(bool(k.daz) for k in ks), sum(k.is_ for k in ks),
                         sum(k.foerderbedarf for k in ks)])
    if not r.lektionen:
        return
    with open(ordner / "lehrauftraege.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["lehrperson", "klasse", "fach", "lektionen"])
        for b in sorted(r.bloecke, key=lambda b: (b.lehrperson, b.klasse)):
            wr.writerow([b.lehrperson, b.klasse, b.fach, b.lektionen])
    with open(ordner / "stundenplan.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["tag", "zeit", "klasse", "fach", "lehrperson", "raum", "schulhaus"])
        for l in sorted(r.lektionen, key=lambda l: (l.slot, l.klasse)):
            s = schule.slots[l.slot]
            wr.writerow([s.tag, s.zeit, l.klasse, l.fach, l.lehrperson, l.raum_label, l.schulhaus])


def _schwerster(meldungen: list[Meldung]) -> str | None:
    for s in SCHWEREGRADE:
        if any(m.schwere == s for m in meldungen):
            return s
    return None


def _badges(meldungen: list[Meldung]) -> str:
    zaehler = Counter(m.schwere for m in meldungen)
    titel = esc("\n".join(m.text for m in meldungen))
    return " ".join(f"<span class='badge {KLASSE[s]}' title='{titel}'>{ICON[s]} {zaehler[s]} {s}</span>"
                    for s in SCHWEREGRADE if zaehler[s])


def _plan(r: Ergebnis, eintraege: dict[int, str], zu: set[int], marken: dict[int, list[Meldung]],
          extra: dict[int, str] | None = None) -> str:
    schule = r.schule
    tage = list(dict.fromkeys(s.tag for s in schule.slots))
    halbtage = list(dict.fromkeys(s.halbtag for s in schule.slots))
    zeilen = sorted(dict.fromkeys((s.halbtag, s.nr, s.zeit) for s in schule.slots),
                    key=lambda z: (halbtage.index(z[0]), z[1]))
    idx = {(s.tag, s.halbtag, s.nr): s.index for s in schule.slots}
    out = ["<table class='plan'><tr><th></th>" + "".join(f"<th>{t}</th>" for t in tage) + "</tr>"]
    for ht, nr, zeit in zeilen:
        out.append(f"<tr><th>{zeit}</th>")
        for t in tage:
            i = idx.get((t, ht, nr))
            if i is None:
                out.append("<td class='zu' title='kein Unterricht'></td>")
                continue
            klassen, inhalt, titel = [], eintraege.get(i, ""), []
            if i in zu and not inhalt:
                klassen.append("zu")
                inhalt = "<span class='muted'>nicht verfügbar</span>"
            if not inhalt and extra and i in extra:
                inhalt = extra[i]
            if i in marken:
                s = _schwerster(marken[i])
                klassen.append({"Fehler": "mark-f", "Warnung": "mark-w", "Hinweis": "mark-h"}[s])
                inhalt += f"<br><span class='badge {KLASSE[s]}'>{ICON[s]} {s}</span>"
                titel = [m.text for m in marken[i]]
            attr = f" class='{' '.join(klassen)}'" if klassen else ""
            attr += f" title='{esc(chr(10).join(titel))}'" if titel else ""
            out.append(f"<td{attr}>{inhalt}</td>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def _karte(r: Ergebnis) -> str:
    schule, e, kinder = r.schule, r.einteilung, r.kinder
    punkte = [(k.lat, k.lon) for k in kinder] + [(s.lat, s.lon) for s in schule.schulhaeuser]
    lat0, lat1 = min(p[0] for p in punkte), max(p[0] for p in punkte)
    lon0, lon1 = min(p[1] for p in punkte), max(p[1] for p in punkte)
    breite, hoehe, fx = 720, 440, 0.68  # cos(47°): Längengrade sind in der Schweiz kürzer
    skala = min((breite - 60) / ((lon1 - lon0) * fx or 1), (hoehe - 50) / ((lat1 - lat0) or 1))

    def xy(lat, lon):
        return 30 + (lon - lon0) * fx * skala, hoehe - 25 - (lat - lat0) * skala

    farbe = {s.name: SERIEN[i] if i < len(SERIEN) else "var(--muted)" for i, s in enumerate(schule.schulhaeuser)}
    teile = [f"<svg viewBox='0 0 {breite} {hoehe}' class='karte' role='img' aria-label='Wohnorte nach Schulhaus'>"]
    km = 1000 / 111_320 * skala  # Massstab: 1 km
    teile.append(f"<line x1='30' x2='{30 + km:.1f}' y1='{hoehe - 8}' y2='{hoehe - 8}' stroke='var(--fg2)' "
                 f"stroke-width='2'/><text x='{34 + km:.1f}' y='{hoehe - 4}' font-size='11' fill='var(--fg2)'>1 km</text>")
    for k in kinder:
        x, y = xy(k.lat, k.lon)
        sh = e.schulhaus_von[k.id]
        teile.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3' fill='{farbe[sh]}' fill-opacity='.75' "
                     f"stroke='var(--surface)' stroke-width='.8'><title>{esc(k.id)} {esc(k.name)} · {esc(k.jahrgang)}"
                     f" → {esc(e.klasse_von[k.id])} · {e.schulweg_m[k.id] / 1000:.2f} km</title></circle>")
    for s in schule.schulhaeuser:
        x, y = xy(s.lat, s.lon)
        teile.append(f"<rect x='{x - 8:.1f}' y='{y - 8:.1f}' width='16' height='16' rx='3' fill='{farbe[s.name]}' "
                     f"stroke='var(--surface)' stroke-width='2'><title>{esc(s.name)}</title></rect>"
                     f"<text x='{x + 12:.1f}' y='{y - 10:.1f}' class='lbl' paint-order='stroke' stroke='var(--surface)' "
                     f"stroke-width='3'>{esc(s.name)}</text>")
    teile.append("</svg>")
    legende = "".join(f"<span><i style='background:{farbe[s.name]}'></i>{esc(s.name)} "
                      f"({sum(v == s.name for v in e.schulhaus_von.values())} Lernende)</span>"
                      for s in schule.schulhaeuser)
    return f"<div class='legende'>{legende}<span><i class='quadrat'></i>Schulhaus</span><span><i class='rund'></i>Wohnort</span></div>" \
           f"<div class='karte-box'>{''.join(teile)}</div>"


# Kartenkacheln: Standard sind die Kacheln der OpenStreetMap Foundation (nur für geringe Nutzung,
# siehe https://operations.osmfoundation.org/policies/tiles/). Für den kommerziellen Betrieb einen
# Kachel-Anbieter oder swisstopo eintragen: SKF_KARTE_KACHELN (URL mit {z}/{x}/{y}) und SKF_KARTE_QUELLE.
KACHELN = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
KACHEL_QUELLE = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende'


def _kacheln() -> tuple[str, str]:
    import os
    return os.environ.get("SKF_KARTE_KACHELN", KACHELN), os.environ.get("SKF_KARTE_QUELLE", KACHEL_QUELLE)


KARTE_JS = r"""
(function () {
  const D = __DATEN__;
  if (typeof L === "undefined") {  // offline: SVG-Karte zeigen
    document.getElementById("osm").hidden = true; document.getElementById("svgkarte").hidden = false; return;
  }
  const karte = L.map("osm", {scrollWheelZoom: false});
  L.tileLayer(__KACHELN__, {maxZoom: 19, attribution: __QUELLE__}).addTo(karte);
  const sh = Object.fromEntries(D.schulhaeuser.map(s => [s.name, s]));
  const kinder = L.layerGroup().addTo(karte), linien = L.layerGroup().addTo(karte), umriss = L.layerGroup().addTo(karte);
  const zustand = {modus: "schulhaus", klasse: "", geschwister: false, wege: false, familie: ""};

  function farbe(k) { return zustand.modus === "jahrgang" ? D.jahrgangsfarben[k.jg] : sh[k.sh].farbe; }
  function huelle(p) {  // konvexe Hülle (monotone chain)
    p = p.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const x = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const u = [], l = [];
    for (const q of p) { while (l.length > 1 && x(l[l.length - 2], l[l.length - 1], q) <= 0) l.pop(); l.push(q); }
    for (const q of p.reverse()) { while (u.length > 1 && x(u[u.length - 2], u[u.length - 1], q) <= 0) u.pop(); u.push(q); }
    return l.slice(0, -1).concat(u.slice(0, -1));
  }
  function zeichnen() {
    kinder.clearLayers(); linien.clearLayers(); umriss.clearLayers();
    const aktiv = k => !zustand.klasse || k.kl === zustand.klasse;
    for (const k of D.kinder) {
      const an = aktiv(k), fam = zustand.familie && k.fam === zustand.familie;
      const m = L.circleMarker([k.lat, k.lon], {radius: fam ? 8 : (an && zustand.klasse ? 6 : 4),
        color: fam ? "#0b0b0b" : "#fff", weight: fam ? 3 : 1, fillColor: an ? farbe(k) : "#c3c2b7",
        fillOpacity: an ? .9 : .35}).bindTooltip(k.t).addTo(kinder);
      m.on("click", () => { zustand.familie = k.fam && zustand.familie !== k.fam ? k.fam : ""; zeichnen(); });
      if ((zustand.wege && an) || fam)
        L.polyline([[k.lat, k.lon], [sh[k.sh].lat, sh[k.sh].lon]], {color: farbe(k), weight: fam ? 3 : 1,
          opacity: fam ? .9 : .45}).addTo(linien);
    }
    if (zustand.geschwister) for (const f of D.familien) {
      // ohne Klassenwahl nur getrennte Familien, mit Klassenwahl die Familien dieser Klasse
      if (zustand.klasse ? !f.kinder.some(i => D.kinder[i].kl === zustand.klasse) : !f.getrennt) continue;
      for (const k of f.kinder) {
        const kk = D.kinder[k];
        L.polyline([[kk.lat, kk.lon], [sh[kk.sh].lat, sh[kk.sh].lon]], {color: f.getrennt ? "#d03b3b" : "#52514e",
          weight: f.getrennt ? 2.5 : 1, dashArray: f.getrennt ? "6 4" : null, opacity: .8})
          .bindTooltip(f.text).addTo(linien);
      }
    }
    if (zustand.klasse) {
      const pts = D.kinder.filter(aktiv).map(k => [k.lat, k.lon]);
      if (pts.length > 2) L.polygon(huelle(pts), {color: "#0b0b0b", weight: 1.5, dashArray: "4 3", fillOpacity: .06})
        .addTo(umriss);
    }
    for (const s of D.schulhaeuser) L.circleMarker([s.lat, s.lon], {radius: 11, color: "#0b0b0b", weight: 3,
      fillColor: s.farbe, fillOpacity: 1}).bindTooltip("<b>" + s.name + "</b>", {permanent: true, direction: "right"})
      .bindPopup("<b>" + s.name + "</b><br>" + s.klassen.join(", ")).addTo(kinder);
    legende();
  }
  function legende() {
    const el = document.getElementById("kartenlegende");
    let h = zustand.modus === "jahrgang"
      ? Object.entries(D.jahrgangsfarben).map(([j, f]) => `<span><i style="background:${f}"></i>${j}</span>`).join("")
      : D.schulhaeuser.map(s => `<span><i style="background:${s.farbe}"></i>${s.name}</span>`).join("");
    if (zustand.geschwister) h += `<span><b style="color:#d03b3b">- - -</b> ${D.getrennt} Familien auf mehrere Schulhäuser verteilt</span>` +
      (zustand.klasse ? `<span><b style="color:#52514e">——</b> Geschwister im selben Schulhaus</span>` : "");
    if (zustand.klasse) { const n = D.kinder.filter(k => k.kl === zustand.klasse).length;
      h += `<span><b>${zustand.klasse}</b>: ${n} Lernende, Umriss = Einzugsgebiet</span>`; }
    if (zustand.familie) h += `<span>Familie ${zustand.familie} hervorgehoben (erneut klicken zum Aufheben)</span>`;
    el.innerHTML = h;
  }
  const steuerung = L.control({position: "topright"});
  steuerung.onAdd = function () {
    const d = L.DomUtil.create("div", "kartensteuerung");
    const optionen = D.schulhaeuser.map(s => `<optgroup label="${s.name}">` +
      s.klassen.map(k => `<option>${k}</option>`).join("") + "</optgroup>").join("");
    d.innerHTML = `<label>Klasse <select id="k_klasse"><option value="">alle</option>${optionen}</select></label>
      <label>Farbe <select id="k_modus"><option value="schulhaus">nach Schulhaus</option>
      <option value="jahrgang">nach Jahrgang</option></select></label>
      <label><input type="checkbox" id="k_geschw"> Geschwister verbinden</label>
      <label><input type="checkbox" id="k_wege"> Schulwege zeigen</label>`;
    L.DomEvent.disableClickPropagation(d);
    d.querySelector("#k_klasse").onchange = e => { zustand.klasse = e.target.value; zeichnen();
      if (zustand.klasse) karte.fitBounds(D.kinder.filter(k => k.kl === zustand.klasse).map(k => [k.lat, k.lon])
        .concat([[sh[D.klassen[zustand.klasse]].lat, sh[D.klassen[zustand.klasse]].lon]]), {padding: [30, 30]}); };
    d.querySelector("#k_modus").onchange = e => { zustand.modus = e.target.value; zeichnen(); };
    d.querySelector("#k_geschw").onchange = e => { zustand.geschwister = e.target.checked; zeichnen(); };
    d.querySelector("#k_wege").onchange = e => { zustand.wege = e.target.checked; zeichnen(); };
    return d;
  };
  steuerung.addTo(karte);
  karte.fitBounds(D.kinder.map(k => [k.lat, k.lon]).concat(D.schulhaeuser.map(s => [s.lat, s.lon])), {padding: [20, 20]});
  zeichnen();
})();
"""

# Ordinale Jahrgangsfarben: eine Farbe (Blau), hell → dunkel (Stufen 250–700 der Referenzpalette)
JAHRGANG_BLAU = ["#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95",
                 "#104281", "#0d366b"]


def karten_daten(r: Ergebnis) -> dict:
    schule, e = r.schule, r.einteilung
    farben = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
    farbe = {s.name: farben[i] if i < len(farben) else "#898781" for i, s in enumerate(schule.schulhaeuser)}
    stufen = [j for j in schule.jahrgaenge]
    jg_farbe = {j: JAHRGANG_BLAU[min(len(JAHRGANG_BLAU) - 1, round(i * (len(JAHRGANG_BLAU) - 1) /
                                                                     max(1, len(stufen) - 1)))]
                for i, j in enumerate(stufen)}
    mit_koord = [k for k in r.kinder if k.lat is not None]
    index = {k.id: i for i, k in enumerate(mit_koord)}
    familien = {}
    for k in mit_koord:
        if k.familie:
            familien.setdefault(k.familie, []).append(k)
    geschwister_text = {}
    fam_daten = []
    for fam, ks in familien.items():
        if len(ks) < 2:
            continue
        orte = {e.schulhaus_von[k.id] for k in ks}
        text = f"Familie {fam}: " + ", ".join(f"{k.vorname or k.name} ({e.klasse_von[k.id]})" for k in ks)
        fam_daten.append({"kinder": [index[k.id] for k in ks], "getrennt": len(orte) > 1, "text": text})
        for k in ks:
            geschwister_text[k.id] = ", ".join(f"{g.id} {g.vorname or g.name} ({e.klasse_von[g.id]})"
                                               for g in ks if g.id != k.id)
    return {
        "schulhaeuser": [{"name": s.name, "lat": s.lat, "lon": s.lon, "farbe": farbe[s.name],
                          "klassen": [c.name for c in e.klassen if c.schulhaus == s.name]}
                         for s in schule.schulhaeuser],
        "klassen": {c.name: c.schulhaus for c in e.klassen},
        "jahrgangsfarben": jg_farbe,
        "familien": fam_daten,
        "getrennt": sum(f["getrennt"] for f in fam_daten),
        "kinder": [{"lat": k.lat, "lon": k.lon, "sh": e.schulhaus_von[k.id], "kl": e.klasse_von[k.id],
                    "jg": k.jahrgang, "fam": k.familie if k.id in geschwister_text else "",
                    "t": f"<b>{html.escape(k.id)} {html.escape(k.name)}</b> · {html.escape(k.jahrgang)} → "
                         f"{html.escape(e.klasse_von[k.id])} · {e.schulweg_m[k.id] / 1000:.2f} km"
                         + (f"<br>Vorjahr: {html.escape(k.bisherige_klasse)}" if k.bisherige_klasse else "")
                         + (f"<br>Geschwister: {html.escape(geschwister_text[k.id])}"
                            if k.id in geschwister_text else "")}
                   for k in mit_koord],
    }


def _osm_karte(r: Ergebnis) -> str:
    """Interaktive OpenStreetMap-Karte (Leaflet): Klassen, Jahrgänge, Geschwister, Schulwege.
    Ohne Internet bleibt die SVG-Karte sichtbar."""
    leaflet = Path(__file__).parent / "static" / "leaflet"
    daten = json.dumps(karten_daten(r), ensure_ascii=False).replace("</", "<\\/")
    url, quelle = _kacheln()
    skript = (KARTE_JS.replace("__DATEN__", daten).replace("__KACHELN__", json.dumps(url))
              .replace("__QUELLE__", json.dumps(quelle)))
    return f"""<style>{(leaflet / "leaflet.css").read_text(encoding="utf-8")}
.kartensteuerung {{ background:#fff; color:#0b0b0b; padding:8px 10px; border-radius:6px; box-shadow:0 1px 4px rgba(0,0,0,.3);
  display:flex; flex-direction:column; gap:5px; font:13px system-ui,sans-serif; max-width:230px }}
.kartensteuerung select {{ font:inherit; max-width:150px; margin-left:4px }}
.leaflet-tooltip {{ font:12px/1.35 system-ui,sans-serif }}</style>
<div id="osm" class="osm" role="img" aria-label="OpenStreetMap-Karte der Wohnorte, Klassen und Schulhäuser"></div>
<div id="kartenlegende" class="legende"></div>
<p class="muted">Klasse wählen = Einzugsgebiet mit Umriss · Punkt anklicken = Familie hervorheben ·
Kartendaten © OpenStreetMap-Mitwirkende (nur Kartenkacheln werden geladen, keine Daten der Lernenden).</p>
<div id="svgkarte" hidden>{_karte(r)}</div>
<script>/* Leaflet 1.9.4, BSD-2-Clause, © Volodymyr Agafonkin */{(leaflet / "leaflet.js").read_text(encoding="utf-8")}</script>
<script>{skript}</script>"""


def _wuensche_html(r: Ergebnis) -> str:
    w = wuensche(r.kinder, r.einteilung)
    e = r.einteilung

    def quote(paar):
        alle, ok = paar
        return f"{len(ok)} von {len(alle)}" if alle else "–"
    kacheln = (f"<div class='kacheln'><div class='kachel'><b>{quote(w['zusammen'])}</b><span>Wunsch „zusammen mit“ "
               f"erfüllt</span></div><div class='kachel'><b>{quote(w['nicht'])}</b><span>Wunsch „nicht zusammen mit“ "
               f"erfüllt</span></div><div class='kachel'><b>{quote(w['schulhaus'])}</b><span>Wunsch-Schulhaus erfüllt"
               f"</span></div><div class='kachel'><b>{len(w['allein'])}</b><span>Lernende als Einzige aus ihrer "
               "bisherigen Klasse/KG-Gruppe</span></div></div>")
    zeilen = []
    for bisher in sorted(w["gruppen"]):
        neue = w["gruppen"][bisher]
        if sum(len(v) for v in neue.values()) < 2:
            continue
        verteilung = ", ".join(f"{esc(k)} ({len(v)})" for k, v in sorted(neue.items(), key=lambda t: -len(t[1])))
        einzeln = [k for k, v in neue.items() if len(v) == 1]
        zeilen.append(f"<tr><td>{esc(bisher)}</td><td class='num'>{sum(len(v) for v in neue.values())}</td>"
                      f"<td>{verteilung}</td><td>{'<span class="badge sev-h">' + ICON['Hinweis'] + ' allein in ' + esc(', '.join(einzeln)) + '</span>' if einzeln else ''}</td></tr>")
    tabelle = ("<details open><summary>Bisherige Klassen und Kindergartengruppen → neue Klassen</summary><div class='scroll'>"
               "<table><tr><th>bisher</th><th class='num'>Lernende</th><th>neu (Anzahl)</th><th></th></tr>"
               + "".join(zeilen) + "</table></div></details>") if zeilen else ""
    offen = [f"<li>{esc(a)} ({esc(e.klasse_von[a])}) und {esc(b)} ({esc(e.klasse_von[b])})</li>"
             for a, b in sorted(set(w["zusammen"][0]) - set(w["zusammen"][1]))]
    return (kacheln + tabelle + (f"<details><summary>Nicht erfüllte Wünsche „zusammen mit“ ({len(offen)})</summary>"
                                 f"<ul>{''.join(offen)}</ul></details>" if offen else ""))


def _empfehlungen_html(r: Ergebnis) -> str:
    p = r.planung
    if not (p.empfehlungen or p.prognose):
        return ""
    karten = "".join(
        f"<div class='panel {'dringlich' if x.dringlich else 'rein'}'><h3>{icon('warnung', 'icon klein') + ' ' if x.dringlich else ''}"
        f"{esc(x.titel)}</h3><div class='fg2'>{esc(x.bereich)}</div><p>{esc(x.text)}</p></div>"
        for x in sorted(p.empfehlungen, key=lambda x: (not x.dringlich, x.bereich)))

    def tabelle(zeilen, spalten, fmt=None):
        if not zeilen:
            return ""
        kopf = "".join(f"<th>{esc(sp)}</th>" for sp in spalten)
        body = "".join("<tr>" + "".join(f"<td>{(fmt or {}).get(sp, lambda v: esc(str(v)))(z[sp])}</td>"
                                        for sp in spalten) + "</tr>" for z in zeilen)
        return f"<div class='scroll'><table><tr>{kopf}</tr>{body}</table></div>"

    def balken(v):
        farbe = "var(--crit)" if v >= 95 else ("var(--warn)" if v >= 85 else "var(--bar)")
        return (f"<span class='groesse' style='width:{min(100, v) * 0.8:.0f}px;background:{farbe}'></span>{v}%")

    def differenz(v):
        return f"<span class='{'neg' if v < 0 else 'pos'}'>{v:+d}</span>"
    prognose = [z for z in p.prognose]
    return (f"<div class='karten'>{karten}</div>"
            "<details><summary>Pensenbilanz pro Schulhaus und Fach</summary>"
            + tabelle(p.pensenbilanz, ["Schulhaus", "Fach", "Bedarf (L)", "Lehrpersonen", "freie Pensen (L)"])
            + "</details><details><summary>Raumauslastung</summary>"
            + tabelle(p.raeume, ["Schulhaus", "Raumtyp", "Räume", "genutzt", "Auslastung"], {"Auslastung": balken})
            + "</details><details><summary>Prognose Lernende und Schulraum</summary>"
            "<p class='muted'>Jahrgänge rücken nach; neuer KG1-Jahrgang wie heute bzw. gemäss <code>planung</code>; "
            "Einzugsgebiete wie in der aktuellen Zuteilung.</p>"
            + tabelle(prognose, ["Schuljahr", "Schulhaus", "Raumtyp", "Lernende", "Klassen (mind.)", "Räume",
                                 "Differenz"], {"Differenz": differenz})
            + "</details><details><summary>Stellvertretungsreserve pro Halbtag</summary>"
            "<p class='muted'>Kleinste Anzahl verfügbarer Lehrpersonen ohne Unterricht während des Halbtags.</p>"
            + tabelle(p.reserve, ["Schulhaus", "Halbtag", "Reserve", "abwesend (Teilzeit)"])
            + "</details>")


def _auslastung(r: Ergebnis, meldungen_von: dict[str, list[Meldung]]) -> str:
    last = Counter()
    for b in r.bloecke:
        last[b.lehrperson] += b.lektionen
    skala = max([lp.pensum_max for lp in r.schule.lehrpersonen] + list(last.values()) + [1])
    zeilen = []
    for lp in r.schule.lehrpersonen:
        n = last[lp.name]
        pct = lambda v: 100 * v / skala  # noqa: E731
        zeilen.append(
            f"<div class='bar-row' title='{esc(lp.name)}: {n} Lektionen (Pensum {lp.pensum_min}–{lp.pensum_max})'>"
            f"<span class='name'>{esc(lp.name)}</span><span class='bar-track'>"
            f"<span class='bar-band' style='left:{pct(lp.pensum_min):.1f}%;width:{pct(lp.pensum_max - lp.pensum_min):.1f}%'></span>"
            f"<span class='bar' style='left:0;width:{pct(n):.1f}%'></span>"
            f"<span class='bar-tick' style='left:{pct(lp.pensum_max):.1f}%'></span></span>"
            f"<span class='num'>{n} {_badges([m for m in meldungen_von.get(lp.name, []) if m.bereich == 'Lehraufträge'])}"
            f"</span></div>")
    return ("<div class='legende'><span><i style='background:var(--bar)'></i>zugeteilte Lektionen</span>"
            "<span><i style='background:var(--band)'></i>Pensum min–max</span><span>│ Maximum</span></div>"
            f"<div class='panel' style='padding:8px 12px'>{''.join(zeilen)}</div>")


def _raumbelegung(r: Ergebnis) -> str:
    schule = r.schule
    belegung = {(l.raum_ort, l.raum, l.slot): l for l in r.lektionen}
    out = []
    for sh in schule.schulhaeuser:
        if not sh.raeume:
            continue
        kopf = "".join(f"<th class='{'tag' if s.nr == 0 and (s.index == 0 or schule.slots[s.index - 1].tag != s.tag) else ''}'"
                       f" title='{s.label}'>{s.tag if s.nr == 0 and s.halbtag == schule.slots[0].halbtag else ''}</th>"
                       for s in schule.slots)
        zeilen = []
        for raum in sh.raeume:
            n, zellen = 0, []
            for s in schule.slots:
                tag = " tag" if s.index == 0 or schule.slots[s.index - 1].tag != s.tag else ""
                l = belegung.get((sh.name, raum.name, s.index))
                if s.index in raum.nicht_verfuegbar or s.index in sh.nicht_verfuegbar:
                    zellen.append(f"<td class='zu{tag}' title='{s.label}: nicht verfügbar'></td>")
                elif l:
                    n += 1
                    zellen.append(f"<td class='b{tag}' title='{s.label}: {esc(l.klasse)} – {esc(l.fach)}, "
                                  f"{esc(l.lehrperson)}'>{esc(l.klasse.split(' ', 1)[-1])}</td>")
                else:
                    zellen.append(f"<td class='{tag.strip()}' title='{s.label}: frei'></td>")
            zeilen.append(f"<tr><th class='raum'>{esc(raum.name)} <span class='muted'>({esc(raum.typ)}, "
                          f"{raum.plaetze} Pl.)</span></th>{''.join(zellen)}"
                          f"<td class='num'>{100 * n / len(schule.slots):.0f}%</td></tr>")
        out.append(f"<details><summary>{esc(sh.name)} – {len(sh.raeume)} Räume</summary><div class='scroll'>"
                   f"<table class='heat'><tr><th class='raum'>Raum</th>{kopf}<th>Auslastung</th></tr>"
                   f"{''.join(zeilen)}</table></div></details>")
    return ("<div class='legende'><span><i style='background:var(--belegt)'></i>belegt (Klasse)</span>"
            "<span><i style='background:repeating-linear-gradient(45deg,transparent 0 3px,var(--base) 3px 5px)'></i>"
            "nicht verfügbar</span><span>Zelle überfahren für Details</span></div>" + "".join(out))


def _quelle_link(schule, schluessel: str) -> str:
    if not schluessel:
        return ""
    q = schule.quelle(schluessel)
    if not q:
        return esc(schluessel)
    titel = esc(f"{q.get('titel', '')} {q.get('erlass', '')}".strip())
    return f"<a href='{esc(q.get('url', '#'))}' title='{titel}' target='_blank' rel='noopener'>{esc(schluessel)}</a>"


def _rechtsgrundlagen(r: Ergebnis) -> str:
    profil = r.schule.profil or {}
    quellen = profil.get("quellen") or {}
    if not quellen:
        return ""
    genutzt = Counter(m.quelle for m in r.meldungen if m.quelle)
    zeilen = "".join(
        f"<tr><td><b>{esc(k)}</b></td><td>{esc(q.get('titel', ''))}"
        f"{'<br><span class=muted>' + esc(q['hinweis']) + '</span>' if q.get('hinweis') else ''}</td>"
        f"<td>{esc(q.get('erlass', ''))}</td><td class='num'>{genutzt[k] or ''}</td>"
        f"<td><a href='{esc(q.get('url', '#'))}' target='_blank' rel='noopener'>Link</a></td></tr>"
        for k, q in quellen.items())
    return (f"<p class='fg2'>{esc(profil.get('name', ''))} · "
            f"{esc(profil.get('stand', ''))} · Klassengrössen "
            f"{'verbindlich angewendet' if profil.get('verbindlich') else 'geprüft (nicht erzwungen)'}</p>"
            "<div class='scroll'><table><tr><th>Kürzel</th><th>Inhalt</th><th>Erlass</th><th class='num'>Meldungen</th>"
            f"<th></th></tr>{zeilen}</table></div>")


def transparenz_html(r: Ergebnis) -> str:
    """Regel-Checkliste, Abwägungen (Strafpunkte je Kriterium) und Lösungsgüte."""
    from .transparenz import guete, kriterien, regeln
    teile = ["<div class='zwei'><div><h3>Harte Regeln – immer einzuhalten</h3>"
             "<p class='erklaerung'>Jede Regel wird nach der Berechnung unabhängig nachgezählt.</p><ul class='checks'>"]
    for x in regeln(r):
        if not x["geprueft"]:
            art, sym, info = "n", "minus", "nicht geprüft (Schritt nicht berechnet)"
        elif x["verstoesse"]:
            art, sym, info = "x", "x", f"{x['verstoesse']} Verstösse: " + "; ".join(x["beispiele"])
        else:
            art, sym, info = "ok", "ok", "erfüllt"
        teile.append(f"<li class='{art}'>{icon(sym)}<span>{esc(x['regel'])}<small>{esc(x['bereich'])} · "
                     f"{esc(info)}</small></span></li>")
    teile.append("</ul></div><div><h3>Abwägungen – was der Optimierer gegeneinander abgewogen hat</h3>"
                 "<p class='erklaerung'>Jedes weiche Ziel kostet Strafpunkte = Messwert × Gewicht. Gesucht ist die "
                 "Lösung mit der kleinsten Summe. Ein höheres Gewicht (Einstellungen) macht ein Ziel wichtiger.</p>")
    krit = [k for k in kriterien(r) if k["gewicht"]]
    gesamt = sum(max(0, k["strafpunkte"]) for k in krit) or 1
    for bereich in dict.fromkeys(k["bereich"] for k in krit):
        teile.append(f"<p class='fg2'><b>{esc(bereich)}</b></p>")
        for k in sorted((k for k in krit if k["bereich"] == bereich), key=lambda k: -k["strafpunkte"]):
            anteil = 100 * max(0, k["strafpunkte"]) / gesamt
            teile.append(f"<div class='bar-row' title='{esc(k['kriterium'])}: {esc(k['wert'])} × Gewicht {k['gewicht']} "
                         f"= {k['strafpunkte']} Punkte'><span class='name'>{esc(k['kriterium'])}</span>"
                         f"<span class='bar-track'><span class='bar' style='left:0;width:{anteil:.1f}%'></span></span>"
                         f"<span class='num fg2'>{esc(k['wert'])}</span></div>")
    teile.append("<p class='erklaerung'>Balkenlänge = Anteil an allen Strafpunkten. Details beim Überfahren.</p>"
                 "<h3>Lösungsgüte</h3>")
    for g in guete(r):
        teile.append(f"<div class='bar-row'><span class='name'>{esc(g['schritt'])}</span><span class='bar-track'>"
                     f"<span class='bar-band' style='left:0;width:100%'></span><span class='bar' "
                     f"style='left:0;width:{g['mindestens']}%'></span></span><span class='num fg2'>"
                     f"{'optimal' if g['status'] == 'beweisbar optimal' else '≥ ' + format(g['mindestens'], '.0f') + '%'}"
                     f"</span></div>")
    teile.append("<p class='erklaerung'>„optimal“ = mathematisch bewiesen bestmöglich. „≥ x %“ = höchstens (100−x) % "
                 "vom Optimum entfernt; mehr Rechenzeit verkleinert die Lücke.</p></div></div>")
    return "".join(teile)


def schreibe_html(pfad: Path, r: Ergebnis, vergleich_link: str = "") -> None:
    schule, e = r.schule, r.einteilung
    nach_id = {k.id: k for k in r.kinder}
    meldungen_von: dict[str, list[Meldung]] = defaultdict(list)
    for m in r.meldungen:
        if m.bezug:
            meldungen_von[m.bezug].append(m)
    nf, nw = r.anzahl("Fehler"), r.anzahl("Warnung")
    if nf:
        banner = (f"<div class='banner f'>{icon('x')}<span><b>{nf} Fehler</b> – das Ergebnis ist so nicht verwendbar. "
                  "Details unter <a href='#meldungen'>Meldungen</a>.</span></div>")
    elif nw:
        banner = (f"<div class='banner w'>{icon('warnung')}<span><b>Alle harten Regeln erfüllt.</b> {nw} Warnungen "
                  "bitte prüfen.</span></div>")
    else:
        banner = f"<div class='banner ok'>{icon('ok')}<span><b>Alle harten Regeln erfüllt.</b></span></div>"

    teile = [f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(schule.name)} – {esc(schule.szenario)}</title><style>{CSS}</style></head><body>
<header class="app-header"><div class="logo">{icon('schule')}</div><div><h1>{esc(schule.name)}</h1>
<p class="sub">Klassenbildung & Stundenplan · Szenario <b>{esc(schule.szenario)}</b>{' · ' + esc(schule.schuljahr) if schule.schuljahr else ''}
 · {len(r.kinder)} Lernende · {len(schule.schulhaeuser)} Schulhäuser · {len(schule.lehrpersonen)} Lehrpersonen
{f' · <a href="{vergleich_link}">Szenarienvergleich</a>' if vergleich_link else ''}</p></div></header>
{banner}<div class="kacheln">"""]
    teile += [f"<div class='kachel'><b>{esc(v)}</b><span>{esc(k)}</span></div>" for k, v in r.kennzahlen().items()]
    teile.append("</div>")

    from .transparenz import regeln
    rg = [x for x in regeln(r) if x["geprueft"]]
    ok = sum(1 for x in rg if not x["verstoesse"])
    status = (f"<span class='badge {'ok-badge' if ok == len(rg) else 'sev-f'}'>{ok} von {len(rg)} Regeln erfüllt</span>"
              if rg else "")
    teile.append(abschnitt("Transparenz", transparenz_html(r), "auge", "Regeln, Abwägungen, Lösungsgüte",
                           offen=True, status=status))

    zaehler = Counter(m.schwere for m in r.meldungen)
    filt = ("<div class='filter'>" + "".join(
        f"<button data-sev='{s}' aria-pressed='true'><span class='badge {KLASSE[s]}'>{ICON[s]} {s}</span> "
        f"{zaehler[s]}</button>" for s in SCHWEREGRADE) +
        "<input id='suche' type='search' placeholder='Meldungen durchsuchen …'></div>")
    if r.meldungen:
        zeilen = "".join(
            f"<tr data-sev='{m.schwere}'><td><span class='badge {KLASSE[m.schwere]}'>{ICON[m.schwere]} {m.schwere}"
            f"</span></td><td class='fg2'>{esc(m.bereich)}</td><td>{esc(m.text)}</td><td>{_quelle_link(schule, m.quelle)}"
            "</td></tr>"
            for m in sorted(r.meldungen, key=lambda m: (SCHWEREGRADE.index(m.schwere), m.bereich)))
        liste = (f"<div class='meldungen'><table><tr><th>Schweregrad</th><th>Bereich</th><th>Meldung</th><th>Quelle</th>"
                 f"</tr>{zeilen}</table></div>")
    else:
        liste = "<p class='muted'>Keine Meldungen.</p>"
    status_m = "".join(f"<span class='badge {KLASSE[s]}'>{ICON[s]} {zaehler[s]}</span>" for s in SCHWEREGRADE
                       if zaehler[s])
    teile.append(abschnitt("Meldungen", filt + liste, "liste", f"{len(r.meldungen)}", offen=bool(nf), anker="meldungen",
                           status=status_m))
    if not e:
        teile.append(abschnitt("Rechtsgrundlagen und Richtlinien", _rechtsgrundlagen(r), "buch"))
        teile.append(f"{FUSS}<script>{JS}</script></body></html>")
        pfad.write_text("".join(teile), encoding="utf-8")
        return

    teile.append(abschnitt("Karte: Wohnorte, Klassen, Geschwister", _osm_karte(r), "karte",
                           f"{len(r.kinder)} Lernende, {len(e.klassen)} Klassen", offen=True))
    teile.append(abschnitt("Wünsche der Erziehungsberechtigten und Kindergartengruppen", _wuensche_html(r), "herz",
                           r.kennzahlen().get("Wünsche erfüllt", "") + " Wünsche erfüllt", anker="wuensche"))
    emp = _empfehlungen_html(r)
    if emp:
        dringend = sum(x.dringlich for x in r.planung.empfehlungen)
        teile.append(abschnitt("Empfehlungen: Lehrpersonen, Verfügbarkeit, Räume, Ausbau", emp, "birne",
                               f"{len(r.planung.empfehlungen)} Empfehlungen",
                               status=f"<span class='badge sev-w'>{dringend} dringlich</span>" if dringend else ""))

    lp_pro_klasse = defaultdict(lambda: defaultdict(int))
    for b in r.bloecke:
        lp_pro_klasse[b.klasse][b.lehrperson] += b.lektionen
    groesst = max((c.groesse for c in e.klassen), default=1)
    k_teile = ["<div class='scroll'><table><tr><th>Klasse</th><th>Schulhaus</th><th>Raum</th>"
               "<th>Lernende</th><th class='num'>♀/♂</th><th class='num' title='Integrative Förderung / Deutsch als "
               "Zweitsprache / Integrative Sonderschulung'>IF/DaZ/IS</th><th class='num'>Ø Weg</th>"
               "<th>Lehrpersonen (Lektionen)</th><th>Meldungen</th></tr>"]
    for c in e.klassen:
        ks = [nach_id[i] for i in c.kinder]
        weg = sum(e.schulweg_m[i] for i in c.kinder) / max(1, len(ks)) / 1000
        lps = ", ".join(f"{esc(n)} ({l})" for n, l in sorted(lp_pro_klasse[c.name].items(), key=lambda t: -t[1]))
        k_teile.append(
            f"<tr><td><b>{esc(c.name)}</b></td><td>{esc(c.schulhaus)}</td><td>{esc(c.raum.name)}</td>"
            f"<td title='{len(ks)} von max. {min(c.vorlage.max, c.raum.plaetze)}'><span class='groesse' "
            f"style='width:{60 * len(ks) / groesst:.0f}px'></span>{len(ks)}</td>"
            f"<td class='num'>{sum(k.geschlecht == 'w' for k in ks)}/{sum(k.geschlecht == 'm' for k in ks)}</td>"
            f"<td class='num'>{sum(k.if_ for k in ks)}/{sum(bool(k.daz) for k in ks)}/{sum(k.is_ for k in ks)}</td>"
            f"<td class='num'>{weg:.2f} km</td>"
            f"<td>{lps}</td><td>{_badges(meldungen_von.get(c.name, []))}</td></tr>")
    k_teile.append("</table></div>")
    teile.append(abschnitt("Klassen", "".join(k_teile), "personen", f"{len(e.klassen)} Klassen", offen=True))

    if r.lektionen:
        teile.append(abschnitt("Auslastung der Lehrpersonen", _auslastung(r, meldungen_von), "balken",
                               f"{len({b.lehrperson for b in r.bloecke})} im Einsatz"))
        teile.append(abschnitt("Raumbelegung", _raumbelegung(r), "raum"))
        pl = []
        for c in e.klassen:
            eintr = defaultdict(str)
            for l in sorted(r.lektionen, key=lambda l: l.art != "unterricht"):
                if c.name in l.klassen:
                    eintr[l.slot] += (f"<b>{esc(l.fach)}</b><br>{esc(l.lehrperson)}<br><span class='muted'>"
                                      f"{esc(l.raum_label)}</span>" if l.art == "unterricht" else
                                      f"<br><span class='foerder'>+ {esc(l.fach)}: {esc(l.lehrperson)}</span>")
            zu = schule.schulhaus(c.schulhaus).nicht_verfuegbar | c.raum.nicht_verfuegbar
            marken = defaultdict(list)
            for m in meldungen_von.get(c.name, []):
                if m.slot is not None:
                    marken[m.slot].append(m)
            namen = ", ".join(esc(nach_id[i].name or i) for i in sorted(c.kinder))
            pl.append(f"<details><summary>{esc(c.name)} – {esc(c.schulhaus)}, {len(c.kinder)} Lernende "
                      f"{_badges(meldungen_von.get(c.name, []))}</summary>"
                      f"<div class='scroll'>{_plan(r, dict(eintr), zu, marken)}</div>"
                      f"<p class='muted'>{namen}</p></details>")
        teile.append(abschnitt("Stundenpläne der Klassen", "".join(pl), "kalender", f"{len(e.klassen)}"))
        pensum = Counter()
        for b in r.bloecke:
            pensum[b.lehrperson] += b.lektionen
        pl = []
        for lp in schule.lehrpersonen:
            if lp.name not in pensum:
                pl.append(f"<p class='muted'>{esc(lp.name)}: nicht eingesetzt {_badges(meldungen_von.get(lp.name, []))}</p>")
                continue
            eintr = {l.slot: f"<b>{esc('/'.join(l.klassen))}</b><br>{esc(l.fach)}<br><span class='muted'>"
                             f"{esc(l.raum_label)}</span>" for l in r.lektionen if l.lehrperson == lp.name}
            marken = defaultdict(list)
            for m in meldungen_von.get(lp.name, []):
                if m.slot is not None:
                    marken[m.slot].append(m)
            extra = {i: "<span class='spring'>Springstunde</span>" for i in springstunden(schule, r.lektionen, lp.name)}
            pl.append(f"<details><summary>{esc(lp.name)} – {pensum[lp.name]} Lektionen "
                      f"(Pensum {lp.pensum_min}–{lp.pensum_max}) {_badges(meldungen_von.get(lp.name, []))}</summary>"
                      f"<div class='scroll'>{_plan(r, eintr, lp.nicht_verfuegbar, marken, extra)}</div></details>")
        teile.append(abschnitt("Stundenpläne der Lehrpersonen", "".join(pl), "kalender", f"{len(pensum)}"))
    teile.append(abschnitt("Rechtsgrundlagen und Richtlinien", _rechtsgrundlagen(r), "buch",
                           (schule.profil or {}).get("name", "")))
    teile.append(f"{FUSS}<script>{JS}</script></body></html>")
    pfad.write_text("".join(teile), encoding="utf-8")


def schreibe_vergleich(pfad: Path, ergebnisse: dict[str, Ergebnis]) -> None:
    """Eine Seite, die alle Szenarien nebeneinander stellt."""
    namen = list(ergebnisse)
    kennzahlen = {n: r.kennzahlen() for n, r in ergebnisse.items()}
    zeilen = []
    for k in next(iter(kennzahlen.values())):
        zellen = []
        for n in namen:
            v = kennzahlen[n][k]
            if k in ("Fehler", "Warnungen", "Hinweise") and v not in ("0", "–"):
                s = {"Fehler": "Fehler", "Warnungen": "Warnung", "Hinweise": "Hinweis"}[k]
                v = f"<span class='badge {KLASSE[s]}'>{ICON[s]} {v}</span>"
            else:
                v = esc(v)
            zellen.append(f"<td class='num'>{v}</td>")
        zeilen.append(f"<tr><th>{esc(k)}</th>{''.join(zellen)}</tr>")
    erstes = next(iter(ergebnisse.values()))
    kopf = "".join(f"<th class='num'><a href='{esc(ordnername(n))}/bericht.html'>{esc(n)}</a></th>" for n in namen)
    pfad.write_text(f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Szenarienvergleich</title><style>{CSS}</style></head><body>
<h1>Szenarienvergleich</h1><p class="sub">{esc(erstes.schule.name)} · {len(erstes.kinder)} Lernende ·
Spaltenkopf anklicken für den ausführlichen Bericht</p>
<div class="scroll"><table><tr><th>Kennzahl</th>{kopf}</tr>{''.join(zeilen)}</table></div>
</body></html>""", encoding="utf-8")

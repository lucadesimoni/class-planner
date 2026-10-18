"""Ausgabe als CSV-Dateien, als eigenständiger HTML-Bericht und als Szenarienvergleich."""
from __future__ import annotations

import csv
import html
import re
from collections import Counter, defaultdict
from pathlib import Path

from .ablauf import Ergebnis
from .pruefung import SCHWEREGRADE, Meldung, springstunden

esc = html.escape


def ordnername(szenario: str) -> str:
    return re.sub(r"[^\w-]+", "_", szenario).strip("_") or "Basis"

# Kategoriale Reihenfolge (fix, nie zyklisch) – siehe dataviz-Referenzpalette
SERIEN = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)", "var(--s7)", "var(--s8)"]
ICON = {"Fehler": "⛔", "Warnung": "⚠", "Hinweis": "ℹ"}
KLASSE = {"Fehler": "sev-f", "Warnung": "sev-w", "Hinweis": "sev-h"}

CSS = """
:root { color-scheme: light;
  --bg:#f9f9f7; --surface:#fcfcfb; --fg:#0b0b0b; --fg2:#52514e; --muted:#898781; --grid:#e1e0d9; --base:#c3c2b7;
  --ring:rgba(11,11,11,.10); --belegt:#b7d3f6; --belegt-fg:#0d366b; --bar:#2a78d6; --band:#e1e0d9;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4; --s6:#008300; --s7:#6250d6; --s8:#e34948;
  --crit:#d03b3b; --warn:#fab219; --good:#0ca30c; --good-text:#006300; --info:#52514e; }
@media (prefers-color-scheme: dark) { :root:where(:not([data-theme="light"])) { color-scheme: dark;
  --bg:#0d0d0d; --surface:#1a1a19; --fg:#f0efec; --fg2:#c3c2b7; --muted:#898781; --grid:#2c2c2a; --base:#383835;
  --ring:rgba(255,255,255,.10); --belegt:#184f95; --belegt-fg:#e6effb; --bar:#3987e5; --band:#383835;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --s6:#008300; --s7:#9085e9; --s8:#e66767;
  --good-text:#0ca30c; --info:#c3c2b7; } }
:root[data-theme="dark"] { color-scheme: dark;
  --bg:#0d0d0d; --surface:#1a1a19; --fg:#f0efec; --fg2:#c3c2b7; --muted:#898781; --grid:#2c2c2a; --base:#383835;
  --ring:rgba(255,255,255,.10); --belegt:#184f95; --belegt-fg:#e6effb; --bar:#3987e5; --band:#383835;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --s6:#008300; --s7:#9085e9; --s8:#e66767;
  --good-text:#0ca30c; --info:#c3c2b7; }
* { box-sizing:border-box }
body { background:var(--bg); color:var(--fg); font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;
  margin:0 auto; max-width:1180px; padding:16px; }
a { color:var(--s1) } h1 { margin:.2em 0; font-size:1.6em } .sub { color:var(--fg2); margin:0 0 12px }
h2 { margin:2em 0 .6em; font-size:1.2em; border-bottom:1px solid var(--grid); padding-bottom:.25em }
.muted { color:var(--muted) } .fg2 { color:var(--fg2) }
.karte-box, .kachel, table, .banner, .panel { background:var(--surface); border:1px solid var(--ring); border-radius:8px }
.kacheln { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:8px }
.kachel { padding:10px 12px } .kachel b { font-size:1.45em; display:block; font-weight:600 }
.kachel span { color:var(--fg2); font-size:.9em }
.banner { padding:10px 14px; margin:12px 0; display:flex; gap:10px; align-items:center; border-left:6px solid var(--good) }
.banner.f { border-left-color:var(--crit) } .banner.w { border-left-color:var(--warn) }
table { border-collapse:separate; border-spacing:0; width:100%; overflow:hidden }
td, th { border-bottom:1px solid var(--grid); padding:5px 8px; text-align:left; vertical-align:top }
th { color:var(--fg2); font-weight:600; font-size:.9em } tr:last-child td { border-bottom:0 }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums }
.scroll { overflow-x:auto } details { margin:.35em 0 } summary { cursor:pointer; font-weight:600; padding:4px 0 }
.badge { display:inline-flex; gap:4px; align-items:center; border-radius:999px; padding:1px 8px; font-size:.82em;
  font-weight:600; border:1px solid var(--ring); white-space:nowrap }
.sev-f { color:#fff; background:var(--crit) } .sev-w { color:#0b0b0b; background:var(--warn) }
.sev-h { color:var(--info); background:transparent }
.filter { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin:6px 0 }
.filter button { font:inherit; cursor:pointer; border-radius:999px; padding:3px 12px; border:1px solid var(--base);
  background:var(--surface); color:var(--fg) }
.filter button[aria-pressed="false"] { opacity:.45; text-decoration:line-through }
.filter input { font:inherit; padding:3px 8px; border-radius:6px; border:1px solid var(--base); background:var(--surface);
  color:var(--fg); min-width:200px; flex:1 }
.meldungen { max-height:420px; overflow:auto }
.plan td { font-size:12px; min-width:92px; height:46px; border-right:1px solid var(--grid) }
.plan th { font-size:12px } .plan td:last-child { border-right:0 }
.plan td.leer { background:transparent }
.plan td.zu, .heat td.zu { background:repeating-linear-gradient(45deg, transparent 0 5px, var(--grid) 5px 7px); color:var(--muted) }
.plan td.mark-f { box-shadow:inset 0 0 0 2px var(--crit) } .plan td.mark-w { box-shadow:inset 0 0 0 2px var(--warn) }
.plan td.mark-h { box-shadow:inset 0 0 0 2px var(--base) }
.plan .spring { color:var(--muted); font-style:italic }
.heat { font-size:11px } .heat td, .heat th { padding:2px 3px; border-right:1px solid var(--grid); text-align:center;
  white-space:nowrap } .heat th.raum { text-align:left }
.heat td.b { background:var(--belegt); color:var(--belegt-fg) } .heat .tag { border-left:2px solid var(--base) }
.bar-row { display:grid; grid-template-columns:minmax(120px,220px) 1fr 70px; gap:8px; align-items:center; padding:2px 0 }
.bar-row .name { white-space:nowrap; overflow:hidden; text-overflow:ellipsis }
.bar-track { position:relative; height:14px }
.bar-band { position:absolute; top:3px; height:8px; background:var(--band); border-radius:4px }
.bar { position:absolute; top:2px; height:10px; background:var(--bar); border-radius:0 4px 4px 0 }
.bar-tick { position:absolute; top:-2px; width:2px; height:18px; background:var(--fg2) }
.legende { display:flex; gap:14px; flex-wrap:wrap; font-size:.9em; color:var(--fg2); margin:6px 0 }
.legende i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; vertical-align:-1px }
.karte { width:100%; max-width:720px; display:block } .lbl { fill:var(--fg); font-size:12px; font-weight:600 }
.groesse { display:inline-block; height:8px; background:var(--bar); border-radius:0 4px 4px 0; vertical-align:middle;
  margin-right:6px }
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


def schreibe_csv(ordner: Path, r: Ergebnis) -> None:
    ordner.mkdir(parents=True, exist_ok=True)
    schule, e = r.schule, r.einteilung
    with open(ordner / "meldungen.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["schweregrad", "bereich", "text", "bezug", "zeit"])
        for m in sorted(r.meldungen, key=lambda m: SCHWEREGRADE.index(m.schwere)):
            wr.writerow([m.schwere, m.bereich, m.text, m.bezug,
                         schule.slots[m.slot].label if m.slot is not None else ""])
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
        wr.writerow(["klasse", "schulhaus", "raum", "jahrgaenge", "kinder", "maedchen", "knaben", "foerderbedarf"])
        for c in e.klassen:
            ks = [nach_id[i] for i in c.kinder]
            wr.writerow([c.name, c.schulhaus, c.raum.name, "/".join(c.jahrgaenge), len(ks),
                         sum(k.geschlecht == "w" for k in ks), sum(k.geschlecht == "m" for k in ks),
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
                      f"({sum(v == s.name for v in e.schulhaus_von.values())} Kinder)</span>"
                      for s in schule.schulhaeuser)
    return f"<div class='legende'>{legende}<span>■ Schulhaus · ● Wohnort</span></div>" \
           f"<div class='karte-box'>{''.join(teile)}</div>"


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


def schreibe_html(pfad: Path, r: Ergebnis, vergleich_link: str = "") -> None:
    schule, e = r.schule, r.einteilung
    nach_id = {k.id: k for k in r.kinder}
    meldungen_von: dict[str, list[Meldung]] = defaultdict(list)
    for m in r.meldungen:
        if m.bezug:
            meldungen_von[m.bezug].append(m)
    nf = r.anzahl("Fehler")
    if nf:
        banner = (f"<div class='banner f'><span class='badge sev-f'>⛔ Fehler</span><span>{nf} Fehler – das Ergebnis ist "
                  "so nicht verwendbar. Details unter <a href='#meldungen'>Meldungen</a>.</span></div>")
    elif r.anzahl("Warnung"):
        banner = (f"<div class='banner w'><span class='badge sev-w'>⚠ Warnung</span><span>Alle harten Regeln erfüllt, "
                  f"aber {r.anzahl('Warnung')} Warnungen prüfen.</span></div>")
    else:
        banner = ("<div class='banner'><span class='badge' style='color:var(--good-text)'>✓ OK</span>"
                  "<span>Alle harten Regeln erfüllt.</span></div>")

    teile = [f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(schule.name)} – {esc(schule.szenario)}</title><style>{CSS}</style></head><body>
<h1>{esc(schule.name)}</h1>
<p class="sub">Szenario <b>{esc(schule.szenario)}</b> · {len(r.kinder)} Kinder · {len(schule.schulhaeuser)} Schulhäuser ·
{len(schule.lehrpersonen)} Lehrpersonen{f' · <a href="{vergleich_link}">Szenarienvergleich</a>' if vergleich_link else ''}</p>
{banner}<div class="kacheln">"""]
    teile += [f"<div class='kachel'><b>{esc(v)}</b><span>{esc(k)}</span></div>" for k, v in r.kennzahlen().items()]
    teile.append("</div>")

    # Meldungen
    zaehler = Counter(m.schwere for m in r.meldungen)
    teile.append("<h2 id='meldungen'>Meldungen</h2><div class='filter'>" + "".join(
        f"<button data-sev='{s}' aria-pressed='true'><span class='badge {KLASSE[s]}'>{ICON[s]} {s}</span> "
        f"{zaehler[s]}</button>" for s in SCHWEREGRADE) +
        "<input id='suche' type='search' placeholder='Meldungen durchsuchen …'></div>")
    if r.meldungen:
        zeilen = "".join(
            f"<tr data-sev='{m.schwere}'><td><span class='badge {KLASSE[m.schwere]}'>{ICON[m.schwere]} {m.schwere}"
            f"</span></td><td class='fg2'>{esc(m.bereich)}</td><td>{esc(m.text)}</td></tr>"
            for m in sorted(r.meldungen, key=lambda m: (SCHWEREGRADE.index(m.schwere), m.bereich)))
        teile.append(f"<div class='meldungen panel'><table><tr><th>Schweregrad</th><th>Bereich</th><th>Meldung</th>"
                     f"</tr>{zeilen}</table></div>")
    else:
        teile.append("<p class='muted'>Keine Meldungen.</p>")

    teile.append("<h2>Solver</h2><ul>" + "".join(f"<li>{esc(str(i))}</li>" for i in r.infos) + "</ul>")
    if not e:
        teile.append(f"<script>{JS}</script></body></html>")
        pfad.write_text("".join(teile), encoding="utf-8")
        return

    teile.append("<h2>Wohnorte und Schulhäuser</h2>" + _karte(r))

    lp_pro_klasse = defaultdict(lambda: defaultdict(int))
    for b in r.bloecke:
        lp_pro_klasse[b.klasse][b.lehrperson] += b.lektionen
    groesst = max((c.groesse for c in e.klassen), default=1)
    teile.append("<h2>Klassen</h2><div class='scroll'><table><tr><th>Klasse</th><th>Schulhaus</th><th>Raum</th>"
                 "<th>Kinder</th><th class='num'>♀/♂</th><th class='num'>Förder&shy;bedarf</th><th class='num'>Ø Weg</th>"
                 "<th>Lehrpersonen (Lektionen)</th><th>Meldungen</th></tr>")
    for c in e.klassen:
        ks = [nach_id[i] for i in c.kinder]
        weg = sum(e.schulweg_m[i] for i in c.kinder) / max(1, len(ks)) / 1000
        lps = ", ".join(f"{esc(n)} ({l})" for n, l in sorted(lp_pro_klasse[c.name].items(), key=lambda t: -t[1]))
        teile.append(
            f"<tr><td>{esc(c.name)}</td><td>{esc(c.schulhaus)}</td><td>{esc(c.raum.name)}</td>"
            f"<td title='{len(ks)} von max. {min(c.vorlage.max, c.raum.plaetze)}'><span class='groesse' "
            f"style='width:{60 * len(ks) / groesst:.0f}px'></span>{len(ks)}</td>"
            f"<td class='num'>{sum(k.geschlecht == 'w' for k in ks)}/{sum(k.geschlecht == 'm' for k in ks)}</td>"
            f"<td class='num'>{sum(k.foerderbedarf for k in ks)}</td><td class='num'>{weg:.2f} km</td>"
            f"<td>{lps}</td><td>{_badges(meldungen_von.get(c.name, []))}</td></tr>")
    teile.append("</table></div>")

    if r.lektionen:
        teile.append("<h2>Auslastung der Lehrpersonen</h2>" + _auslastung(r, meldungen_von))
        teile.append("<h2>Raumbelegung</h2>" + _raumbelegung(r))

        teile.append("<h2>Stundenpläne der Klassen</h2>")
        for c in e.klassen:
            eintr = {l.slot: f"<b>{esc(l.fach)}</b><br>{esc(l.lehrperson)}<br><span class='muted'>{esc(l.raum_label)}</span>"
                     for l in r.lektionen if l.klasse == c.name}
            zu = schule.schulhaus(c.schulhaus).nicht_verfuegbar | c.raum.nicht_verfuegbar
            marken = defaultdict(list)
            for m in meldungen_von.get(c.name, []):
                if m.slot is not None:
                    marken[m.slot].append(m)
            namen = ", ".join(esc(nach_id[i].name or i) for i in sorted(c.kinder))
            teile.append(f"<details><summary>{esc(c.name)} – {esc(c.schulhaus)}, {len(c.kinder)} Kinder "
                         f"{_badges(meldungen_von.get(c.name, []))}</summary>"
                         f"<div class='scroll'>{_plan(r, eintr, zu, marken)}</div>"
                         f"<p class='muted'>{namen}</p></details>")

        teile.append("<h2>Stundenpläne der Lehrpersonen</h2>")
        pensum = Counter()
        for b in r.bloecke:
            pensum[b.lehrperson] += b.lektionen
        for lp in schule.lehrpersonen:
            if lp.name not in pensum:
                teile.append(f"<p class='muted'>{esc(lp.name)}: nicht eingesetzt "
                             f"{_badges(meldungen_von.get(lp.name, []))}</p>")
                continue
            eintr = {l.slot: f"<b>{esc(l.klasse)}</b><br>{esc(l.fach)}<br><span class='muted'>{esc(l.raum_label)}</span>"
                     for l in r.lektionen if l.lehrperson == lp.name}
            marken = defaultdict(list)
            for m in meldungen_von.get(lp.name, []):
                if m.slot is not None:
                    marken[m.slot].append(m)
            extra = {i: "<span class='spring'>Springstunde</span>" for i in springstunden(schule, r.lektionen, lp.name)}
            teile.append(f"<details><summary>{esc(lp.name)} – {pensum[lp.name]} Lektionen "
                         f"(Pensum {lp.pensum_min}–{lp.pensum_max}) {_badges(meldungen_von.get(lp.name, []))}</summary>"
                         f"<div class='scroll'>{_plan(r, eintr, lp.nicht_verfuegbar, marken, extra)}</div></details>")
    teile.append(f"<script>{JS}</script></body></html>")
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
<h1>Szenarienvergleich</h1><p class="sub">{esc(erstes.schule.name)} · {len(erstes.kinder)} Kinder ·
Spaltenkopf anklicken für den ausführlichen Bericht</p>
<div class="scroll"><table><tr><th>Kennzahl</th>{kopf}</tr>{''.join(zeilen)}</table></div>
</body></html>""", encoding="utf-8")

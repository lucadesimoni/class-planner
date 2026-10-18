"""Ausgabe als CSV-Dateien und als ein eigenständiger HTML-Bericht."""
from __future__ import annotations

import csv
import html
from collections import defaultdict
from pathlib import Path

from .daten import Kind, Schule
from .klassen import Einteilung
from .lehrauftrag import Block
from .stundenplan import Lektion

FARBEN = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#ca8a04", "#db2777"]


def schreibe_csv(ordner: Path, schule: Schule, kinder: list[Kind], e: Einteilung,
                 bloecke: list[Block], lektionen: list[Lektion]) -> None:
    ordner.mkdir(parents=True, exist_ok=True)
    with open(ordner / "einteilung.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["id", "name", "jahrgang", "schulhaus", "klasse", "schulweg_m"])
        for k in kinder:
            wr.writerow([k.id, k.name, k.jahrgang, e.schulhaus_von[k.id], e.klasse_von[k.id],
                         round(e.schulweg_m[k.id])])
    with open(ordner / "klassen.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["klasse", "schulhaus", "raum", "jahrgaenge", "kinder", "maedchen", "knaben", "foerderbedarf"])
        nach_id = {k.id: k for k in kinder}
        for c in e.klassen:
            ks = [nach_id[i] for i in c.kinder]
            wr.writerow([c.name, c.schulhaus, c.raum.name, "/".join(c.jahrgaenge), len(ks),
                         sum(k.geschlecht == "w" for k in ks), sum(k.geschlecht == "m" for k in ks),
                         sum(k.foerderbedarf for k in ks)])
    with open(ordner / "lehrauftraege.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["lehrperson", "klasse", "fach", "lektionen"])
        for b in sorted(bloecke, key=lambda b: (b.lehrperson, b.klasse)):
            wr.writerow([b.lehrperson, b.klasse, b.fach, b.lektionen])
    with open(ordner / "stundenplan.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["tag", "zeit", "klasse", "fach", "lehrperson", "raum", "schulhaus"])
        for l in sorted(lektionen, key=lambda l: (l.slot, l.klasse)):
            s = schule.slots[l.slot]
            wr.writerow([s.tag, s.zeit, l.klasse, l.fach, l.lehrperson, l.raum_label, l.schulhaus])


def _plan_tabelle(schule: Schule, eintraege: dict[int, str]) -> str:
    tage = list(dict.fromkeys(s.tag for s in schule.slots))
    zeilen = list(dict.fromkeys((s.halbtag, s.nr, s.zeit) for s in schule.slots))
    zeilen.sort(key=lambda z: (list(dict.fromkeys(s.halbtag for s in schule.slots)).index(z[0]), z[1]))
    idx = {(s.tag, s.halbtag, s.nr): s.index for s in schule.slots}
    out = ["<table class='plan'><tr><th></th>" + "".join(f"<th>{t}</th>" for t in tage) + "</tr>"]
    for ht, nr, zeit in zeilen:
        out.append(f"<tr><th>{zeit}</th>")
        for t in tage:
            i = idx.get((t, ht, nr))
            if i is None:
                out.append("<td class='frei'></td>")
            else:
                out.append(f"<td>{eintraege.get(i, '')}</td>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def _karte(schule: Schule, kinder: list[Kind], e: Einteilung) -> str:
    punkte = [(k.lat, k.lon) for k in kinder] + [(s.lat, s.lon) for s in schule.schulhaeuser]
    lat0, lat1 = min(p[0] for p in punkte), max(p[0] for p in punkte)
    lon0, lon1 = min(p[1] for p in punkte), max(p[1] for p in punkte)
    breite, hoehe = 640, 420
    fx = 0.68  # cos(47°): Längengrade sind in der Schweiz kürzer
    skala = min((breite - 40) / ((lon1 - lon0) * fx or 1), (hoehe - 40) / ((lat1 - lat0) or 1))

    def xy(lat, lon):
        return 20 + (lon - lon0) * fx * skala, hoehe - 20 - (lat - lat0) * skala

    farbe = {s.name: FARBEN[i % len(FARBEN)] for i, s in enumerate(schule.schulhaeuser)}
    teile = [f"<svg viewBox='0 0 {breite} {hoehe}' class='karte'>"]
    for k in kinder:
        x, y = xy(k.lat, k.lon)
        teile.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='2.6' fill='{farbe[e.schulhaus_von[k.id]]}' "
                     f"opacity='.65'><title>{html.escape(k.id)} {html.escape(k.jahrgang)} → "
                     f"{html.escape(e.klasse_von[k.id])}</title></circle>")
    for s in schule.schulhaeuser:
        x, y = xy(s.lat, s.lon)
        teile.append(f"<rect x='{x - 7:.1f}' y='{y - 7:.1f}' width='14' height='14' fill='{farbe[s.name]}' "
                     f"stroke='var(--fg)' stroke-width='2'/><text x='{x + 10:.1f}' y='{y - 9:.1f}' "
                     f"class='lbl'>{html.escape(s.name)}</text>")
    teile.append("</svg>")
    return "".join(teile)


def schreibe_html(pfad: Path, schule: Schule, kinder: list[Kind], e: Einteilung,
                  bloecke: list[Block], lektionen: list[Lektion], infos, warnungen) -> None:
    nach_id = {k.id: k for k in kinder}
    esc = html.escape
    teile = [f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(schule.name)} – Klassen &amp; Stundenplan</title>
<style>
:root {{ --bg:#fff; --fg:#1f2937; --muted:#6b7280; --line:#e5e7eb; --card:#f9fafb; --accent:#2563eb; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#111827; --fg:#e5e7eb; --muted:#9ca3af; --line:#374151; --card:#1f2937; --accent:#60a5fa; }} }}
body {{ background:var(--bg); color:var(--fg); font:14px/1.45 system-ui,sans-serif; margin:0 auto; max-width:1100px; padding:16px; }}
h1 {{ margin:.2em 0 }} h2 {{ margin-top:2em; border-bottom:1px solid var(--line); padding-bottom:.2em }}
.muted {{ color:var(--muted) }} .kacheln {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:8px }}
.kachel {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:10px }}
.kachel b {{ font-size:1.5em; display:block }}
table {{ border-collapse:collapse; width:100%; margin:.5em 0 }} td,th {{ border:1px solid var(--line); padding:3px 6px; text-align:left; vertical-align:top }}
.plan td {{ font-size:12px; min-width:90px }} .plan td.frei {{ background:var(--card) }}
.scroll {{ overflow-x:auto }} details {{ margin:.4em 0 }} summary {{ cursor:pointer; font-weight:600 }}
.karte {{ width:100%; max-width:640px; background:var(--card); border-radius:8px }} .lbl {{ fill:var(--fg); font-size:12px; font-weight:600 }}
.warn {{ color:#b45309 }}
</style></head><body>
<h1>{esc(schule.name)}</h1><p class="muted">Klasseneinteilung und Stundenplan, berechnet mit stunden-klassen-fitter (OR-Tools CP-SAT)</p>
<div class="kacheln">
<div class="kachel"><b>{len(kinder)}</b>Kinder</div>
<div class="kachel"><b>{len(e.klassen)}</b>Klassen</div>
<div class="kachel"><b>{len({b.lehrperson for b in bloecke})}</b>Lehrpersonen im Einsatz</div>
<div class="kachel"><b>{sum(e.schulweg_m.values()) / len(kinder) / 1000:.2f} km</b>Ø Schulweg</div>
<div class="kachel"><b>{max(e.schulweg_m.values()) / 1000:.2f} km</b>max. Schulweg</div>
</div>
<h2>Solver</h2><ul>{''.join(f'<li>{esc(str(i))}</li>' for i in infos)}</ul>
{''.join(f'<p class="warn">⚠ {esc(w)}</p>' for w in warnungen)}
<h2>Wohnorte und Schulhäuser</h2>{_karte(schule, kinder, e)}
<h2>Klassen</h2><div class="scroll"><table><tr><th>Klasse</th><th>Schulhaus</th><th>Raum</th><th>Kinder</th>
<th>♀/♂</th><th>Förder&shy;bedarf</th><th>Ø Weg</th><th>Lehrpersonen (Lektionen)</th></tr>"""]
    lp_pro_klasse = defaultdict(lambda: defaultdict(int))
    for b in bloecke:
        lp_pro_klasse[b.klasse][b.lehrperson] += b.lektionen
    for c in e.klassen:
        ks = [nach_id[i] for i in c.kinder]
        weg = sum(e.schulweg_m[i] for i in c.kinder) / max(1, len(ks)) / 1000
        lps = ", ".join(f"{esc(n)} ({l})" for n, l in sorted(lp_pro_klasse[c.name].items(), key=lambda t: -t[1]))
        teile.append(f"<tr><td>{esc(c.name)}</td><td>{esc(c.schulhaus)}</td><td>{esc(c.raum.name)}</td>"
                     f"<td>{len(ks)}</td><td>{sum(k.geschlecht == 'w' for k in ks)}/"
                     f"{sum(k.geschlecht == 'm' for k in ks)}</td><td>{sum(k.foerderbedarf for k in ks)}</td>"
                     f"<td>{weg:.2f} km</td><td>{lps}</td></tr>")
    teile.append("</table></div>")

    teile.append("<h2>Stundenpläne der Klassen</h2>")
    for c in e.klassen:
        eintr = {l.slot: f"<b>{esc(l.fach)}</b><br>{esc(l.lehrperson)}<br><span class='muted'>{esc(l.raum_label)}</span>"
                 for l in lektionen if l.klasse == c.name}
        namen = ", ".join(esc(nach_id[i].name or i) for i in sorted(c.kinder))
        teile.append(f"<details><summary>{esc(c.name)} – {esc(c.schulhaus)}, {len(c.kinder)} Kinder</summary>"
                     f"<div class='scroll'>{_plan_tabelle(schule, eintr)}</div>"
                     f"<p class='muted'>{namen}</p></details>")

    teile.append("<h2>Stundenpläne der Lehrpersonen</h2>")
    pensum = defaultdict(int)
    for b in bloecke:
        pensum[b.lehrperson] += b.lektionen
    for lp in schule.lehrpersonen:
        if lp.name not in pensum:
            teile.append(f"<p class='muted'>{esc(lp.name)}: nicht eingesetzt</p>")
            continue
        eintr = {l.slot: f"<b>{esc(l.klasse)}</b><br>{esc(l.fach)}<br><span class='muted'>{esc(l.raum_label)}</span>"
                 for l in lektionen if l.lehrperson == lp.name}
        teile.append(f"<details><summary>{esc(lp.name)} – {pensum[lp.name]} Lektionen "
                     f"(Pensum {lp.pensum_min}–{lp.pensum_max})</summary>"
                     f"<div class='scroll'>{_plan_tabelle(schule, eintr)}</div></details>")
    teile.append("</body></html>")
    pfad.write_text("".join(teile), encoding="utf-8")

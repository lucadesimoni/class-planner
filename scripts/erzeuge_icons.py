# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Erzeugt skf/icons.py aus der Schrift Material Symbols Rounded (Apache-2.0).

Die App (Streamlit) zeigt dieselbe Icon-Familie (`:material/…:`); der Bericht
bettet die Glyphen als kleine Inline-SVGs ein – offline, druckbar, keine Schrift
im HTML. Aufruf (nur bei neuen Icons nötig):

    npm pack material-symbols && tar xzf material-symbols-*.tgz
    pip install fonttools brotli
    python scripts/erzeuge_icons.py package/material-symbols-rounded.woff2
"""
import re
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

NAMEN = ["info", "school", "map", "groups", "calendar_month", "warning", "check_circle", "cancel",
         "remove_circle", "bar_chart", "favorite", "menu_book", "visibility", "tune", "meeting_room",
         "lightbulb", "list", "expand_more", "person", "co_present", "route", "verified", "gavel",
         "family_restroom", "door_open", "table_view", "download", "upload", "history", "insights",
         "fact_check", "calculate", "home", "child_care", "category", "volunteer_activism", "error",
         "schedule", "location_on", "swap_horiz", "description", "print", "search", "filter_list"]


def main(pfad: str) -> None:
    font = TTFont(pfad)
    font = instantiateVariableFont(font, {"FILL": 0, "wght": 400, "GRAD": 0, "opsz": 24})
    cmap = font.getBestCmap()
    rev = {g: c for c, g in cmap.items()}
    # Ligaturen: Folge von Buchstaben-Glyphen -> Icon-Glyphe
    ligaturen = {}
    for lookup in font["GSUB"].table.LookupList.Lookup:
        for sub in lookup.SubTable:
            sub = getattr(sub, "ExtSubTable", sub)
            for erstes, ligs in getattr(sub, "ligatures", {}).items():
                for lig in ligs:
                    folge = [erstes] + list(lig.Component)
                    if all(g in rev for g in folge):
                        ligaturen["".join(chr(rev[g]) for g in folge)] = lig.LigGlyph
    glyphen = font.getGlyphSet()
    upm = font["head"].unitsPerEm
    zeilen = ["# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0 AND Apache-2.0",
              "# Copyright (c) 2026 Outthinkx by Luca De Simoni (Erzeugung); Glyphen: Material Symbols, (c) Google LLC, Apache-2.0",
              '"""Icons: Material Symbols Rounded (Google, Apache-2.0), erzeugt von scripts/erzeuge_icons.py."""',
              "", "# viewBox 0 0 24 24, Füllfarbe currentColor", "PFADE = {"]
    for name in NAMEN:
        g = ligaturen[name]
        pen = SVGPathPen(glyphen)
        s = 24 / upm
        glyphen[g].draw(TransformPen(pen, (s, 0, 0, -s, 0, upm * s)))
        d = pen.getCommands()
        # Zahlen kürzen
        d = re.sub(r"-?\d+\.\d+", lambda m: f"{float(m.group()):.2f}".rstrip("0").rstrip("."), d)
        zeilen.append(f'    "{name}": "{d}",')
    zeilen.append("}")
    ziel = Path(__file__).resolve().parent.parent / "skf" / "icons.py"
    ziel.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    print(ziel, len(NAMEN), "Icons")


if __name__ == "__main__":
    main(sys.argv[1])

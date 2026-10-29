# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Lizenztexte aller installierten Laufzeit-Abhängigkeiten nach lizenzen/ schreiben.

Für ein Komplettpaket (Installer mit Python und allen Paketen), das die Lizenztexte
der Drittkomponenten beilegen muss:  uv run python scripts/lizenzen.py [zielordner]
"""
import re
import sys
from importlib import metadata
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent


def abhaengigkeiten() -> list[str]:
    """Alle Laufzeit-Abhängigkeiten laut pyproject.toml (transitiv, ohne Extras wie 'test')."""
    import tomllib
    direkt = tomllib.loads((WURZEL / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    offen = [re.match(r"[A-Za-z0-9_.\-]+", d).group().lower() for d in direkt]
    gesehen = set(offen)
    while offen:
        name = offen.pop()
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        for anf in dist.requires or []:
            if "extra ==" in anf:
                continue
            teil = re.match(r"[A-Za-z0-9_.\-]+", anf).group().lower().replace("_", "-")
            if teil not in gesehen:
                gesehen.add(teil)
                offen.append(teil)
    return sorted(gesehen)


def main(ziel: str = "lizenzen") -> None:
    ordner = WURZEL / ziel
    ordner.mkdir(exist_ok=True)
    zeilen = ["# Lizenzen der mitgelieferten Pakete", ""]
    for name in abhaengigkeiten():
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        lizenz = dist.metadata.get("License-Expression") or "; ".join(
            c.split("::")[-1].strip() for c in dist.metadata.get_all("Classifier") or [] if c.startswith("License ::"))
        texte = [f for f in dist.files or [] if re.search(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", f.name, re.I)]
        for f in texte:
            (ordner / f"{name}-{f.name}").write_bytes(Path(dist.locate_file(f)).read_bytes())
        zeilen.append(f"- {name} {dist.version}: {lizenz or 'siehe Lizenztext'} ({len(texte)} Datei(en))")
    for datei in ("skf/static/leaflet/LICENSE", "skf/static/material-symbols/LICENSE"):
        (ordner / f"{datei.split('/')[2]}-LICENSE").write_bytes((WURZEL / datei).read_bytes())
    (ordner / "UEBERSICHT.md").write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    print(f"{len(zeilen) - 2} Pakete → {ordner}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(*sys.argv[1:])

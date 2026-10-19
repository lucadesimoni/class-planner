# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Neue Programmversion setzen – überall gleichzeitig.

    python scripts/version.py            zeigt die aktuelle Version und prüft, ob alles übereinstimmt
    python scripts/version.py 0.2.0      setzt 0.2.0 in skf/version.py, pyproject.toml und uv.lock
                                         und macht aus "Unveröffentlicht" im CHANGELOG den Abschnitt 0.2.0

Danach: committen und mit `git tag -a v0.2.0 -m "Version 0.2.0"` + `git push --tags`
veröffentlichen – der Workflow baut daraus die Windows-Pakete als Release-Entwurf.
"""
import re
import sys
from datetime import date
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
DATEIEN = {
    "skf/version.py": r'^__version__ = "([^"]+)"',
    "pyproject.toml": r'^version = "([^"]+)"',
    "uv.lock": r'^name = "stunden-klassen-fitter"\nversion = "([^"]+)"',
}


def versionen() -> dict[str, str]:
    out = {}
    for datei, muster in DATEIEN.items():
        treffer = re.search(muster, (WURZEL / datei).read_text(encoding="utf-8"), re.M)
        out[datei] = treffer.group(1) if treffer else "?"
    kopf = re.search(r"^## \[(\d+\.\d+\.\d+)\]", (WURZEL / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
    out["CHANGELOG.md"] = kopf.group(1) if kopf else "?"
    return out


def setze(neu: str) -> None:
    if not SEMVER.match(neu):
        sys.exit(f"'{neu}' ist keine Version der Form MAJOR.MINOR.PATCH")
    alt = versionen()["skf/version.py"]
    if tuple(map(int, neu.split("."))) <= tuple(map(int, alt.split("."))):
        sys.exit(f"{neu} ist nicht grösser als die aktuelle Version {alt}")
    for datei, muster in DATEIEN.items():
        pfad = WURZEL / datei
        text = pfad.read_text(encoding="utf-8")
        text, n = re.subn(muster, lambda m: m.group(0).replace(m.group(1), neu), text, count=1, flags=re.M)
        if n != 1:
            sys.exit(f"Version in {datei} nicht gefunden")
        pfad.write_text(text, encoding="utf-8")
    log = WURZEL / "CHANGELOG.md"
    text = log.read_text(encoding="utf-8")
    if "## [Unveröffentlicht]" not in text:
        sys.exit("CHANGELOG.md: Abschnitt '## [Unveröffentlicht]' fehlt")
    text = text.replace("## [Unveröffentlicht]", f"## [Unveröffentlicht]\n\n## [{neu}] – {date.today().isoformat()}", 1)
    repo = "https://github.com/lucadesimoni/stunden-klassen-fitter"
    text = re.sub(r"^\[Unveröffentlicht\]: .*$", f"[Unveröffentlicht]: {repo}/compare/v{neu}...HEAD\n"
                  f"[{neu}]: {repo}/compare/v{alt}...v{neu}", text, count=1, flags=re.M)
    log.write_text(text, encoding="utf-8")
    print(f"{alt} → {neu}. Jetzt CHANGELOG.md ergänzen, committen und taggen: git tag -a v{neu} -m \"Version {neu}\"")


def main() -> None:
    if len(sys.argv) > 1:
        setze(sys.argv[1])
    v = versionen()
    for datei, wert in v.items():
        print(f"  {datei:16} {wert}")
    if len(set(v.values())) != 1:
        sys.exit("Versionen stimmen nicht überein")
    print(f"Version {v['skf/version.py']} – überall gleich.")


if __name__ == "__main__":
    main()

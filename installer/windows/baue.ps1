# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
#
# Baut den Windows-Installer: Python (eigenständig, aus uv) + alle Pakete laut uv.lock
# + skf, dann Inno Setup. Läuft in GitHub Actions (windows-latest) oder lokal mit
# installiertem uv und Inno Setup 6:   powershell -File installer\windows\baue.ps1
$ErrorActionPreference = "Stop"
$wurzel = Resolve-Path "$PSScriptRoot\..\.."
$build = Join-Path $wurzel "installer\build"
if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory $build | Out-Null

# 1. Eigenständiges Python (python-build-standalone über uv), in den Build-Ordner kopiert
uv python install 3.12
if ($LASTEXITCODE) { throw "uv python install fehlgeschlagen" }
$python = (uv python find --managed-python 3.12).Trim()
Copy-Item (Split-Path $python -Parent) (Join-Path $build "python") -Recurse
Remove-Item (Join-Path $build "python\Lib\EXTERNALLY-MANAGED") -ErrorAction SilentlyContinue
$py = Join-Path $build "python\python.exe"

# 2. Pakete in genau den geprüften Versionen (uv.lock), dann das Programm selbst
Push-Location $wurzel
uv export --frozen --no-dev --no-hashes --no-emit-project --format requirements-txt -o (Join-Path $build "requirements.txt")
if ($LASTEXITCODE) { throw "uv export fehlgeschlagen" }
uv pip install --python $py --break-system-packages -r (Join-Path $build "requirements.txt")
if ($LASTEXITCODE) { throw "Installation der Pakete fehlgeschlagen" }
uv pip install --python $py --break-system-packages --no-deps --reinstall .
if ($LASTEXITCODE) { throw "Installation von skf fehlgeschlagen" }
Pop-Location
& $py -c "import skf, ortools, streamlit; print('ok', skf.__file__)"
if ($LASTEXITCODE) { throw "Import-Test fehlgeschlagen" }

# 3. Lizenzen und Hinweise
& $py (Join-Path $wurzel "scripts\lizenzen.py") (Join-Path $build "lizenzen")
if ($LASTEXITCODE) { throw "Lizenztexte konnten nicht gesammelt werden" }
Copy-Item (Join-Path $wurzel "LICENSE") (Join-Path $build "LICENSE.txt")
Copy-Item (Join-Path $wurzel "THIRD_PARTY_NOTICES.md") $build
Get-ChildItem (Join-Path $build "python") -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

# 4. Installer
$version = (Select-String -Path (Join-Path $wurzel "pyproject.toml") -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
$iscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
& $iscc "/DVersion=$version" (Join-Path $PSScriptRoot "klassenbildung.iss")
if ($LASTEXITCODE) { throw "Inno Setup fehlgeschlagen" }
Get-ChildItem (Join-Path $build "ausgabe")

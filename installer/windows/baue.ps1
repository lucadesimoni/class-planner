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

# 4. Version – einzige Quelle skf/version.py (mit pyproject.toml/uv.lock/CHANGELOG abgeglichen)
& $py (Join-Path $wurzel "scripts\version.py")
if ($LASTEXITCODE) { throw "Versionsangaben stimmen nicht überein" }
$version = (Select-String -Path (Join-Path $wurzel "skf\version.py") -Pattern '^__version__ = "(.+)"').Matches[0].Groups[1].Value
if ($env:GITHUB_REF -like "refs/tags/v*" -and $env:GITHUB_REF -ne "refs/tags/v$version") {
  throw "Tag $env:GITHUB_REF passt nicht zur Programmversion $version"
}

# 5. Starter Klassenbildung.exe (csc des .NET Framework – auf jedem Windows vorhanden), mit Versionsangaben
$info = Join-Path $build "VersionInfo.cs"
@"
using System.Reflection;
[assembly: AssemblyTitle("Klassenbildung & Stundenplan")]
[assembly: AssemblyProduct("Klassenbildung & Stundenplan")]
[assembly: AssemblyCompany("Outthinkx for Communities")]
[assembly: AssemblyCopyright("© 2026 Outthinkx for Communities")]
[assembly: AssemblyVersion("$version.0")]
[assembly: AssemblyFileVersion("$version.0")]
[assembly: AssemblyInformationalVersion("$version")]
"@ | Set-Content -Path $info -Encoding UTF8
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
& $csc /nologo /target:exe /optimize+ "/win32icon:$PSScriptRoot\klassenbildung.ico" "/out:$build\Klassenbildung.exe" "$PSScriptRoot\Starter.cs" $info
if ($LASTEXITCODE) { throw "Starter konnte nicht kompiliert werden" }
Copy-Item "$PSScriptRoot\klassenbildung.ico" $build
$ausgabe = Join-Path $build "ausgabe"
New-Item -ItemType Directory $ausgabe -Force | Out-Null

# 6. Installationsprogramm (Inno Setup)
$iscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
& $iscc "/DVersion=$version" (Join-Path $PSScriptRoot "klassenbildung.iss")
if ($LASTEXITCODE) { throw "Inno Setup fehlgeschlagen" }

# 7. MSIX-Paket (für den Microsoft Store; der Store signiert es). Identität aus dem
#    Partner Center über Umgebungsvariablen, sonst Platzhalter für Tests.
$stufe = Join-Path $build "msix"
New-Item -ItemType Directory $stufe | Out-Null
foreach ($teil in "python", "lizenzen", "Klassenbildung.exe", "LICENSE.txt", "THIRD_PARTY_NOTICES.md") {
  Copy-Item (Join-Path $build $teil) $stufe -Recurse
}
Copy-Item "$PSScriptRoot\msix\Assets" $stufe -Recurse
$name = if ($env:MSIX_NAME) { $env:MSIX_NAME } else { "OutthinkxforCommunities.Klassenbildung" }
$publisher = if ($env:MSIX_PUBLISHER) { $env:MSIX_PUBLISHER } else { "CN=Outthinkx for Communities" }
$anzeige = if ($env:MSIX_PUBLISHER_NAME) { $env:MSIX_PUBLISHER_NAME } else { "Outthinkx for Communities" }
$manifest = Get-Content "$PSScriptRoot\msix\AppxManifest.xml" -Raw -Encoding UTF8
$manifest = $manifest.Replace("__NAME__", $name).Replace("__VERSION__", "$version.0")
$manifest = $manifest.Replace("__PUBLISHER_NAME__", [Security.SecurityElement]::Escape($anzeige))
$manifest = $manifest.Replace("__PUBLISHER__", [Security.SecurityElement]::Escape($publisher))
[IO.File]::WriteAllText((Join-Path $stufe "AppxManifest.xml"), $manifest, (New-Object Text.UTF8Encoding $false))
$sdk = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\10.*\x64\makeappx.exe" | Sort-Object FullName | Select-Object -Last 1
& $sdk.FullName pack /o /h SHA256 /d $stufe /p (Join-Path $ausgabe "Klassenbildung-$version.msix")
if ($LASTEXITCODE) { throw "makeappx fehlgeschlagen" }
Get-ChildItem $ausgabe

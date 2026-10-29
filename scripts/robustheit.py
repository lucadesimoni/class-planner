# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Robustheits-Sweep: Grenzfälle und Zufallsdaten. Ein Fall besteht, wenn kein Absturz
(nur verständliche Fehlermeldungen) und bei Erfolg die unabhängige Prüfung 0 Fehler meldet."""
import copy, random, sys, time, traceback
from pathlib import Path
WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
from skf.daten import baue_schule, lade_kinder, lese_konfiguration
from skf.ablauf import rechne

M = str(WURZEL / "beispiele" / "malters") + "/"
V = str(WURZEL / "beispiele" / "vorlage") + "/"
cfg_m = lese_konfiguration(M + "schule.yaml", "Basis")
cfg_v = lese_konfiguration(V + "schule.yaml", "Basis")
kinder_m = lade_kinder(M + "kinder.csv")
kinder_v = lade_kinder(V + "kinder.csv")
ergebnisse = []

def fall(name, cfg, kinder, t=30):
    t0 = time.time()
    try:
        schule = baue_schule(copy.deepcopy(cfg))
        r = rechne(schule, kinder, zeitlimit=t, protokoll=lambda *_: None)
        f = [m for m in r.meldungen if m.schwere == "Fehler"]
        status = "OK" if r.vollstaendig and not f else "FEHLERMELDUNG"
        detail = "" if status == "OK" else f[0].text[:150] if f else "unvollständig ohne Fehler!"
        # Lösung vorhanden aber Fehler aus der Nachprüfung = echter Defekt
        if r.lektionen and any(m.bereich in ("Klassen", "Stundenplan", "Lehraufträge") for m in f):
            status = "DEFEKT"
        if not r.vollstaendig and not f:
            status = "DEFEKT"
    except (ValueError, KeyError) as e:
        status, detail = "ABGELEHNT", f"{type(e).__name__}: {e}"[:150]
    except Exception as e:
        status, detail = "ABSTURZ", traceback.format_exc().strip().splitlines()[-1][:200]
    ergebnisse.append((status, name, round(time.time() - t0), detail))
    print(f"{status:14} {name:45} {time.time()-t0:5.0f}s  {detail}", flush=True)

kv = kinder_v
fall("Vorlage normal", cfg_v, kv)
fall("Vorlage ohne Kinder", cfg_v, [])
fall("Vorlage 1 Kind", cfg_v, kv[:1])
k = copy.deepcopy(kv); [setattr(x, "lat", None) or setattr(x, "lon", None) for x in k[:20]]
fall("20 Kinder ohne Koordinaten", cfg_v, k)
k = copy.deepcopy(kv); k[0].jahrgang = "7"
fall("unbekannter Jahrgang", cfg_v, k)
k = copy.deepcopy(kv); k[1].id = k[0].id
fall("doppelte ID", cfg_v, k)
k = copy.deepcopy(kv); k[0].nicht_mit = ["XYZ"]; k[1].zusammen_mit = ["K-gibts-nicht"]
fall("Wunsch auf unbekannte ID", cfg_v, k)
c = copy.deepcopy(cfg_v); c["lehrpersonen"] = c["lehrpersonen"][:3]
fall("viel zu wenige Lehrpersonen", c, kv)
c = copy.deepcopy(cfg_v); c["lehrpersonen"] = []
fall("keine Lehrpersonen", c, kv)
c = copy.deepcopy(cfg_v); c["schulhaeuser"][1]["raeume"] = []
fall("Schulhaus ohne Räume", c, kv)
c = copy.deepcopy(cfg_v); c["schulhaeuser"] = c["schulhaeuser"][:1]
fall("nur ein Schulhaus", c, kv)
c = copy.deepcopy(cfg_v); c["klassenbildung"]["vorlagen"] = [v for v in c["klassenbildung"]["vorlagen"] if len(v["jahrgaenge"]) == 1]
fall("keine Mehrjahrgangsklassen", c, kv)
k = copy.deepcopy(kv)
for x in k: x.familie = "F1"
fall("alle Kinder eine Familie", cfg_v, k)
c = copy.deepcopy(cfg_v); c.setdefault("klassenbildung", {})["geschwister"] = "hart"
k = copy.deepcopy(kv)
for x in k: x.familie = "F1"
fall("eine Familie + Geschwister hart", c, k)
k = copy.deepcopy(kv)
for x in k: x.if_ = True; x.daz = "anfang"
fall("alle IF und DaZ", cfg_v, k)
k = copy.deepcopy(kv)
for x in k[:30]: x.is_ = True
fall("30 IS-Kinder", cfg_v, k)
c = copy.deepcopy(cfg_v); c["zeitraster"]["halbtage"] = {"VM": ["08:00", "08:50"]}
fall("zu wenig Zeitfenster", c, kv)
c = copy.deepcopy(cfg_v); c["schulbus"] = {"linien": [{"name": "L", "schulhaeuser": ["Gibts nicht"]}]}
k = copy.deepcopy(kv); k[0].bus = "L"
fall("Buslinie mit unbekanntem Schulhaus", c, k)
c = copy.deepcopy(cfg_v); c["wegzeiten"] = {"minuten": {"Schulhaus A-Schulhaus B": 60}}
fall("Wegzeit 60 min", c, kv)

# Zufallsdaten: Teilmengen und Vervielfachung von Malters
rnd = random.Random(7)
for anteil in (0.15, 0.4, 0.7):
    sub = rnd.sample(kinder_m, int(len(kinder_m) * anteil))
    fall(f"Malters {int(anteil*100)}% ({len(sub)} Kinder)", cfg_m, sub, t=60)
gross = []
for i, x in enumerate(kinder_m * 2):
    y = copy.copy(x); y.id = f"{x.id}-{i // len(kinder_m)}"; y.familie = f"{x.familie}-{i // len(kinder_m)}" if x.familie else ""
    y.zusammen_mit = []; y.nicht_mit = []
    gross.append(y)
c = copy.deepcopy(cfg_m)
for sh in c["schulhaeuser"]:
    for r in sh.get("raeume", []):
        r["anzahl"] = r.get("anzahl", 1) * 2
c["lehrpersonen"] = c["lehrpersonen"] + [dict(lp, name=lp["name"] + " (2)", **({"bisherige_klasse": ""} if lp.get("bisherige_klasse") else {})) for lp in c["lehrpersonen"]]
fall(f"Malters doppelt, Räume+LP doppelt ({len(gross)} Kinder)", c, gross, t=300)

print()
from collections import Counter
print(Counter(s for s, *_ in ergebnisse))

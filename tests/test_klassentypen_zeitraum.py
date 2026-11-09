# SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
# Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
"""Klassentypen mit Zeitraum: z.B. Mischklassen 1./2. nur bis 2027/28, danach reine 1., 2., 3. Klassen."""
from __future__ import annotations

import pytest

from skf.ablauf import rechne
from skf.austausch import exportiere_stammdaten, importiere_stammdaten
from skf.daten import Kind, Vorlage, bisherige_gruppen, lade_kinder, lade_schule, schuljahr_beginn
from skf.pruefung import vorpruefung
from tests.test_planung_kosten import VORLAGE, _cfg, _schreibe

MISCH = 3   # Index der Mischklasse 1./2. in beispiele/vorlage/schule.yaml


def _schule(tmp_path, **misch):
    cfg = _cfg()
    cfg["klassenbildung"]["vorlagen"][MISCH].update(misch)
    return lade_schule(_schreibe(tmp_path, cfg))


def test_schuljahr_und_gueltigkeit():
    assert schuljahr_beginn("2028/29") == 2028 == schuljahr_beginn("2028") == schuljahr_beginn(" 2028 / 2029 ")
    assert schuljahr_beginn("") is None and schuljahr_beginn("nächstes Jahr") is None
    v = Vorlage(["1", "2"], 16, 22, 20, ab="2025/26", bis="2027/28")
    assert [v.gilt(j) for j in ("2024/25", "2025/26", "2027/28", "2028/29")] == [False, True, True, False]
    assert v.gilt("") and Vorlage(["1"], 16, 22, 20).gilt("2040/41")


def test_mischklasse_endet_vor_dem_planjahr(tmp_path):
    s = _schule(tmp_path, bis="2026/27")   # Planjahr 2027/28: nur noch reine Jahrgangsklassen
    assert all(len(v.jahrgaenge) == 1 or v.raumtyp == "Kindergarten" for v in s.vorlagen)
    assert len(s.alle_vorlagen) == len(s.vorlagen) + 1
    hinweise = [m.text for m in vorpruefung(s, lade_kinder(VORLAGE / "kinder.csv")) if m.schwere == "Hinweis"]
    assert any("1/2 gilt bis 2026/27" in t and "2027/28 nicht verwendet" in t for t in hinweise)


def test_mischklasse_ab_spaeter(tmp_path):
    s = _schule(tmp_path, ab="2029/30")
    assert ["1", "2"] not in [v.jahrgaenge for v in s.vorlagen]
    assert ["1", "2"] in [v.jahrgaenge for v in s.vorlagen_im("2029/30")]


@pytest.mark.parametrize("misch, ohne_jahr, meldung", [
    ({"bis": "bald"}, False, "kein Schuljahr"),
    ({"ab": "2029/30", "bis": "2027/28"}, False, "liegt nach"),
    ({"bis": "2027/28"}, True, "brauchen das Schuljahr"),
])
def test_ungueltige_angaben(tmp_path, misch, ohne_jahr, meldung):
    cfg = _cfg()
    cfg["klassenbildung"]["vorlagen"][MISCH].update(misch)
    if ohne_jahr:
        cfg.pop("schuljahr")
    with pytest.raises(ValueError, match=meldung):
        lade_schule(_schreibe(tmp_path, cfg))


def test_prognose_folgt_den_klassentypen_des_jahres(tmp_path):
    """Kleine Jahrgänge: solange 1./2. gemischt werden darf, reicht eine Klasse; danach braucht jeder Jahrgang eine."""
    kinder = lade_kinder(VORLAGE / "kinder.csv")

    def klassen(schule):
        r = rechne(schule, kinder, zeitlimit=20, protokoll=lambda t: None)
        return {(z["Schuljahr"], z["Schulhaus"]): z["Klassen (mind.)"] for z in r.planung.prognose
                if z["Raumtyp"] == "Klassenzimmer"}
    (tmp_path / "a").mkdir(), (tmp_path / "b").mkdir()
    immer, bis = klassen(_schule(tmp_path / "a")), klassen(_schule(tmp_path / "b", bis="2028/29"))
    assert {k: v for k, v in immer.items() if k[0] <= "2028/29"} == {k: v for k, v in bis.items() if k[0] <= "2028/29"}
    spaeter = [k for k in immer if k[0] >= "2029/30"]
    assert spaeter and all(bis[k] >= immer[k] for k in spaeter) and any(bis[k] > immer[k] for k in spaeter)


def _kind(i, jahrgang, bisher):
    return Kind(id=f"K{i}", name="", jahrgang=jahrgang, geschlecht="w", adresse="", lat=None, lon=None,
                bisherige_klasse=bisher)


def test_bisherige_mischklasse_wird_nach_jahrgang_geteilt():
    """Aus einer 1./2. Mischklasse werden reine 2. und 3. Klassen – die Trennung zählt nicht als aufgeteilte Klasse."""
    kinder = [_kind(1, "2", "1/2a"), _kind(2, "2", "1/2a"), _kind(3, "3", "1/2a"), _kind(4, "3", "3a")]
    rein = [Vorlage([j], 16, 22, 20) for j in ("2", "3")]
    gruppen = bisherige_gruppen(kinder, rein)
    assert {n: [k.id for k in ks] for n, ks in gruppen.items()} == \
        {"1/2a (2)": ["K1", "K2"], "1/2a (3)": ["K3"], "3a": ["K4"]}
    gemischt = rein + [Vorlage(["2", "3"], 16, 22, 20)]
    assert [k.id for k in bisherige_gruppen(kinder, gemischt)["1/2a"]] == ["K1", "K2", "K3"]


def test_austausch_behaelt_zeitraum(tmp_path):
    cfg = _cfg()
    cfg["klassenbildung"]["vorlagen"][MISCH]["bis"] = "2027/28"
    for endung in (".xlsx", ".json"):
        exportiere_stammdaten(cfg, lade_kinder(VORLAGE / "kinder.csv"), tmp_path / f"d{endung}")
        cfg2, _ = importiere_stammdaten(tmp_path / f"d{endung}")
        assert str(cfg2["klassenbildung"]["vorlagen"][MISCH]["bis"]) == "2027/28"


def test_cli_schuljahr_waehlt_klassentypen(tmp_path, monkeypatch):
    """`skf rechnen --schuljahr` (nach dem Schuljahreswechsel) rechnet mit den Klassentypen dieses Jahres."""
    from skf import ablauf, cli
    gesehen = {}

    def merken(schule, kinder, **_):
        gesehen["typen"] = [v.jahrgaenge for v in schule.vorlagen]
        raise SystemExit(0)
    monkeypatch.setattr(ablauf, "rechne", merken)
    monkeypatch.setattr(cli, "rechne", merken)
    cfg = _cfg()
    cfg["klassenbildung"]["vorlagen"][MISCH]["ab"] = "2028/29"
    pfad = _schreibe(tmp_path, cfg)
    with pytest.raises(SystemExit):
        cli.main(["rechnen", str(pfad), str(VORLAGE / "kinder.csv"), "-o", str(tmp_path / "o"), "--schuljahr", "2028/29"])
    assert ["1", "2"] in gesehen["typen"]

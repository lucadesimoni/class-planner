"""Browser-End-zu-End-Test: echte App im echten Browser (Chromium via Playwright).

Startet `skf app`, klickt sich durch Daten → Prüfen → Berechnen → Ergebnis und legt
Screenshots in docs/screenshots/ ab. Wird übersprungen, wenn Playwright/Chromium fehlen.
    pytest tests/test_browser_e2e.py -s
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
WURZEL = Path(__file__).parent.parent
BILDER = WURZEL / "docs" / "screenshots"
CHROMIUM = os.environ.get("SKF_CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def _freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def app_url(tmp_path_factory):
    port = _freier_port()
    umgebung = {**os.environ, "SKF_DATEN": str(tmp_path_factory.mktemp("daten"))}
    prozess = subprocess.Popen([sys.executable, "-m", "skf", "app", "--port", str(port), "--ohne-browser"],
                               cwd=WURZEL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=umgebung)
    url = f"http://localhost:{port}"
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                break
        except OSError:
            time.sleep(0.5)
    yield url
    prozess.terminate()
    prozess.wait(timeout=10)


def _navigiere(seite, ziel):
    seite.locator("section[data-testid='stSidebar']").get_by_text(ziel, exact=True).click()
    time.sleep(1.5)


def test_bedienung_im_browser(app_url):
    BILDER.mkdir(parents=True, exist_ok=True)
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM if Path(CHROMIUM).exists() else None)
        seite = browser.new_page(viewport={"width": 1400, "height": 900})
        seite.goto(app_url)
        seite.get_by_text("Loslegen").wait_for(timeout=60_000)
        time.sleep(1)
        seite.screenshot(path=BILDER / "0-start.png")

        seite.get_by_role("button", name="Beispiel Malters ansehen").click()
        seite.get_by_text("644 Lernende").first.wait_for(timeout=60_000)
        time.sleep(1.5)
        seite.screenshot(path=BILDER / "1-daten.png")
        seite.get_by_role("tab", name="Gewichtung").click()
        time.sleep(1)
        seite.screenshot(path=BILDER / "1b-gewichtung.png")

        seite.get_by_role("button", name="Weiter: 2 · Prüfen →").click()
        seite.get_by_text("Keine Fehler").first.wait_for(timeout=60_000)
        time.sleep(1)
        seite.screenshot(path=BILDER / "2-pruefen.png")

        seite.get_by_role("button", name="Weiter: 3 · Berechnen →").click()
        seite.get_by_placeholder("z.B. Variante").fill("Browser-Test")
        seite.get_by_role("button", name="▶ Klassen und Stundenplan berechnen").click()
        seite.get_by_role("button", name="Zum Ergebnis →").wait_for(timeout=600_000)
        time.sleep(1)
        seite.screenshot(path=BILDER / "3-berechnen.png")

        seite.get_by_role("button", name="Zum Ergebnis →").click()
        seite.get_by_text("Alle harten Regeln erfüllt").first.wait_for(timeout=60_000)
        time.sleep(3)
        karte = seite.frame_locator("iframe").first
        karte.locator("#k_klasse").select_option("BM 1a")
        karte.locator("#k_geschw").check()
        time.sleep(2)
        seite.screenshot(path=BILDER / "4-ergebnis-karte.png")

        for tab, datei in (("Klassen", "5-klassen.png"), ("Lernende", "6-lernende.png"),
                           ("Anpassen", "7-anpassen.png"), ("Stundenpläne", "8-stundenplan.png"),
                           ("Wünsche & KG-Gruppen", "9-wuensche.png"), ("Empfehlungen", "10-empfehlungen.png"),
                           ("Herunterladen", "11-herunterladen.png")):
            seite.get_by_role("tab", name=tab).click()
            time.sleep(2.5)
            seite.screenshot(path=BILDER / datei)
        with seite.expect_download() as download:
            seite.get_by_role("button", name="⬇ Klassenlisten (Excel, druckfertig)").click()
        assert download.value.suggested_filename == "klassenlisten.xlsx"

        seite.get_by_role("tab", name="Anpassen").click()
        time.sleep(1)
        seite.get_by_role("button", name="Verschieben und prüfen").wait_for()

        _navigiere(seite, "🕘 Verlauf")
        seite.get_by_text("Zwei Stände vergleichen").wait_for(timeout=30_000)
        assert seite.get_by_text("Browser-Test").count() > 0  # Notiz des gespeicherten Standes
        time.sleep(1)
        seite.screenshot(path=BILDER / "12-verlauf.png")
        browser.close()

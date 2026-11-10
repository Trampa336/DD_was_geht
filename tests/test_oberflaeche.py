"""Rauchtest der Oberfläche (2026-11-10): Seite aus Testdaten bauen, in Chromium öffnen, Feed, Termin-Blatt,
Filter und Suche anfassen. Braucht Node mit dem Paket playwright (npm i -g playwright && npx playwright
install chromium); fehlt es, wird der Test übersprungen. Die Python-Tests prüfen Daten und Scraper,
dieser Test die ~1.100 Zeilen JavaScript in der Vorlage, die sonst niemand ausführt."""
import json
import os
import shutil
import subprocess
from datetime import date, timedelta

import pytest

from ddwg import ausgabe, db
from ddwg.orte import Orte

HIER = os.path.dirname(os.path.abspath(__file__))
SKRIPT = os.path.join(HIER, "oberflaeche_check.mjs")


def _playwright_da():
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-e", "require('playwright')"],
                       cwd=HIER, capture_output=True)
    return r.returncode == 0


def _termine(heute):
    morgen = (heute + timedelta(days=1)).isoformat()
    roh = [
        ("ostpol", "Ostpol", heute.isoformat(), "20:00", "Testkonzert Nachtfalter", "musik", "Lange Beschreibung für die Kachel.", "https://example.org/bild.jpg"),
        ("scheune", "Scheune", heute.isoformat(), "21:00", "Punkabend im Test", "musik", None, None),
        ("ostpol", "Ostpol", morgen, "19:00", "Lesung zur Probe", "kultur", "Ein Abend mit Texten.", None),
        (None, "Irgendwo", morgen, None, "Stadtteilfest Probelauf", "outdoor", None, None),
    ]
    evs = []
    for i, (ort, ort_roh, d, t, titel, kat, b, img) in enumerate(roh):
        evs.append({"uid": f"test{i:02d}", "date": d, "time": t, "title": titel, "ort": ort, "ort_roh": ort_roh,
                    "category": kat, "url": "https://example.org/" + str(i), "image_url": img, "description": b,
                    "price_text": None, "sources": "kulturkalender", "region": "dresden", "laufend": 0})
    return evs


@pytest.mark.skipif(not _playwright_da(), reason="Node mit playwright fehlt")
def test_oberflaeche_feed_blatt_filter_suche(tmp_path):
    heute = date.today()
    orte = Orte.load()
    with db.connect(":memory:") as conn:
        db.replace_events(conn, [(ev, []) for ev in _termine(heute)])
        pfad = ausgabe.schreiben(conn, orte, str(tmp_path / "index.html"), heute)
    r = subprocess.run(["node", SKRIPT, pfad, "nachtfalter"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    aus = json.loads(r.stdout.strip().splitlines()[-1])
    assert "abbruch" not in aus, aus
    assert aus["fehler"] == [], aus["fehler"]
    assert aus["tage"] == 2
    assert aus["termine"] == 4 and aus["kacheln"] == 4
    assert "Testkonzert Nachtfalter" in aus["blattTitel"]
    assert aus["filterTitel"].startswith("Filter")
    assert aus["suchtreffer"] == 1


FEHLER_SKRIPT = """
const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.route(/^https?:/, r => r.abort());
  await p.goto(require("node:url").pathToFileURL(process.argv[1]).href);
  await p.waitForSelector("#fehler", { timeout: 10000 });
  console.log(JSON.stringify({ text: await p.locator("#fehler").textContent() }));
  await b.close();
})();
"""


@pytest.mark.skipif(not _playwright_da(), reason="Node mit playwright fehlt")
def test_oberflaeche_zeigt_hinweis_statt_leerer_seite(tmp_path):
    """Ohne Daten (DATEN = null) stürzt das Skript beim Start ab; der Fehlerfänger im Kopf zeigt einen Hinweis."""
    with open(ausgabe.VORLAGE_PATH, encoding="utf-8") as fh:
        html = fh.read().replace("/*__SCHRIFT__*/", "")
    pfad = tmp_path / "kaputt.html"
    pfad.write_text(html, encoding="utf-8")
    r = subprocess.run(["node", "-e", FEHLER_SKRIPT, str(pfad)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "Neu laden" in json.loads(r.stdout.strip().splitlines()[-1])["text"]

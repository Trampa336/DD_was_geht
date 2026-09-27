"""Ostpol-Scraper ohne Netz, mit einem gekürzten Ausschnitt der echten Seite (27.09.2026)."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg.quellen import ostpol  # noqa: E402

BEISPIEL = """
<div class="termin">
<table><tbody><tr><td width="66" valign="top"><span class="datum">Di.</span> <span class="datum">29</span> <span class="datum">09</span></td><td class="terminbox"><div class="presented_by">Beatpol präsentiert:</div><div class="headline">KLEZ.E</div><div class="description"><div class="xdj266r">
	<span dir="auto">KLEZ.E (D) im Ostpol<br class="html-br">
	29.09.2026<br class="html-br">
	Einlass: 19.00 Uhr<br class="html-br">
	Start: 20.00 Uhr</span></div></div></td></tr></tbody></table>
<table><tbody><tr><td width="66" valign="top"><span class="datum">Mi.</span> <span class="datum">07</span> <span class="datum">10</span></td><td class="terminbox"><div class="headline">Freundeskreis freies Musizieren - Jamsession</div><div class="description"><p>
	<span dir="auto"><img alt="🔥" src="https://static.xx.fbcdn.net/images/emoji.php/v9/t50/1/16/1f525.png" width="16">Jamsession im Ostpol<br>Einlass: 20 Uhr<br>Beginn: 21 Uhr</span></p></div><div class="cost">++FreiSchau++</div></td></tr></tbody></table>
<table><tbody><tr><td width="66" valign="top"><span class="datum">Mo.</span> <span class="datum">12</span> <span class="datum">10</span></td><td class="terminbox"><div class="headline">Queer Monday</div><div class="description"></div></td></tr></tbody></table>
<table><tbody><tr><td width="66" valign="top"><span class="datum">Do.</span> <span class="datum">01</span> <span class="datum">10</span></td><td class="terminbox"><div class="presented_by">Schoisaal Dresden präsentiert:</div><div class="headline">Heckspoiler – „Bock auf Stress“ Tour<br>
+ Special Guest: DIE FINGERNÄGEL</div><div class="description"><span>Einlass: 19:00 Uhr - Start: 20:00 Uhr</span></div></td></tr></tbody></table>
</div>
"""

BEZUG = date(2026, 9, 27)


def _events():
    return {e["title"]: e for e in ostpol._parse(BEISPIEL, BEZUG)}


def test_alle_termine_mit_datum():
    ev = _events()
    assert len(ev) == 4
    assert ev["KLEZ.E"]["date"] == "2026-09-29"
    assert ev["Queer Monday"]["date"] == "2026-10-12"
    assert all(e["venue"] == "Ostpol" and e["source"] == "ostpol" for e in ev.values())


def test_zeit_beginn_vor_einlass_und_keine_geratene():
    ev = _events()
    assert ev["KLEZ.E"]["time"] == "20:00"
    assert ev["Freundeskreis freies Musizieren - Jamsession"]["time"] == "21:00"
    assert ev["Queer Monday"]["time"] is None
    assert ostpol._zeit("Einlass 20 Uhr / Beginn 21 Uhr") == "21:00"
    assert ostpol._zeit("Einlass 19 Uhr") == "19:00"
    assert ostpol._zeit("seit Beginn der 90er Jahre aktiv") is None


def test_titel_einzeilig_beschreibung_mit_veranstalter():
    ev = _events()
    titel = "Heckspoiler – „Bock auf Stress“ Tour + Special Guest: DIE FINGERNÄGEL"
    assert titel in ev
    assert ev[titel]["description"].startswith("Schoisaal Dresden präsentiert:")
    assert ev["Queer Monday"]["description"] is None
    assert ev["Freundeskreis freies Musizieren - Jamsession"]["price_text"] == "++FreiSchau++"


def test_jahreswechsel():
    html = BEISPIEL.replace('<span class="datum">29</span> <span class="datum">09</span>',
                            '<span class="datum">05</span> <span class="datum">01</span>')
    ev = {e["title"]: e for e in ostpol._parse(html, date(2026, 12, 20))}
    assert ev["KLEZ.E"]["date"] == "2027-01-05"


def test_konzerttour_ist_keine_fuehrung():
    ev = _events()
    assert ev["Heckspoiler – „Bock auf Stress“ Tour + Special Guest: DIE FINGERNÄGEL"]["category"] != "fuehrungen"

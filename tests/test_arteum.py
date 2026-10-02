"""Arteum-Scraper ohne Netz, Galerie-JSON gekürzt aus der echten Seite (02.10.2026)."""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg.quellen import arteum  # noqa: E402


def eintrag(titel, text, url, medium):
    return {"itemId": titel, "metaData": {"title": titel, "description": text,
            "link": {"type": "wix", "data": {"url": url, "type": "ExternalLink"}},
            "name": medium}, "mediaUrl": medium}


ITEMS = [
    eintrag("BieberFieber", "📆  Freitag 02.10.\n🕑 ab 22 Uhr\nP18",
            "https://partysdresden.ticket.io/twsPFqKy/", "01abe7_d2fc579b2bbe4e67859299d8ce546244~mv2.jpg"),
    eintrag("Tropo Heats Nights", "📆  Samstag 03.10.\n🕑 ab 22:30 Uhr\nP18",
            "https://dresdenvibes.stgdts.com/events/tropo-heats-nights-arteum-dresden-20261003-50KQo/checkout/products",
            "01abe7_adcc2445a0c048da828e114ee8f2dbcf~mv2.png"),
    eintrag("Disney Chanel Throwback Party", "📆 Freitag 11.09.\n🕑 ab 22 Uhr\nP18",
            "https://loud-events.stgdts.com/events/disney", "01abe7_9268097d825545b9b6c990b0e3b9fa70~mv2.jpeg"),
    eintrag("BOVSKI", "📆  Samstag 06.02.\n🕑 ab 22 Uhr\nP18",
            "https://loud-events.stgdts.com/events/bovski", "01abe7_225ae29804d845ca9e1d20dc6dc8f185~mv2.webp"),
    eintrag("P16 Partys", "2026", "https://whatsapp.com/channel/x", "01abe7_b20764cb848342f08ebbbefc0f1463d8~mv2.png"),
]
WARMUP = {"appsWarmupData": {"14271d6f-ba62-d045-549b-ab972ae1f70e": {
    "comp-mqs4ehek_appSettings": {"pageId": "d34uk"},
    "comp-mqs4ehek_galleryData": {"items": ITEMS, "totalItemsCount": len(ITEMS)}}}}
SEITE = ('<html><body><div data-hook="item-title"><span>BieberFieber</span></div>'
         '<script type="application/json" id="wix-warmup-data">'
         + json.dumps(WARMUP, ensure_ascii=False) + "</script></body></html>")
BEZUG = date(2026, 10, 2)


def test_parse():
    ev = {e["title"]: e for e in arteum._parse(SEITE, BEZUG)}
    assert "P16 Partys" not in ev  # ohne Datum
    bf = ev["BieberFieber"]
    assert bf["date"] == "2026-10-02" and bf["time"] == "22:00" and bf["venue"] == "Arteum"
    assert bf["url"] == "https://partysdresden.ticket.io/twsPFqKy/"
    assert bf["image_url"] == ("https://static.wixstatic.com/media/01abe7_d2fc579b2bbe4e67859299d8ce546244~mv2.jpg"
                               "/v1/fit/w_600,h_600,q_80/01abe7_d2fc579b2bbe4e67859299d8ce546244~mv2.jpg")
    assert bf["description"] is None and bf["category"] == "musik"
    assert ev["Tropo Heats Nights"]["time"] == "22:30"
    assert ev["Disney Chanel Throwback Party"]["date"] == "2026-09-11"  # alter Eintrag
    assert ev["BOVSKI"]["date"] == "2027-02-06"  # Jahreswechsel, Samstag passt


def test_wochentag_entscheidet_jahr():
    # 01.04. liegt vom 02.10.2026 aus gut ein halbes Jahr zurück -> Standard 2027.
    # Mittwoch 01.04. gibt es aber nur 2026: dann gilt der Wochentag.
    assert arteum._datum("Mittwoch 01.04.", BEZUG) == date(2026, 4, 1)
    assert arteum._datum("01.04.", BEZUG) == date(2027, 4, 1)


def test_ohne_json_leer():
    assert arteum._parse("<html><body>nichts</body></html>", BEZUG) == []


def test_scrape_range(monkeypatch):
    monkeypatch.setattr(arteum.base, "fetch_html", lambda url, **kw: SEITE)
    ev = arteum.scrape_range(BEZUG, date(2026, 11, 2))
    assert [e["title"] for e in ev] == ["BieberFieber", "Tropo Heats Nights"]

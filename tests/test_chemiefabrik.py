"""Chemiefabrik-Scraper ohne Netz, mit Ausschnitten der echten Seiten (27.09.2026)."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg import normalize  # noqa: E402
from ddwg.quellen import chemiefabrik  # noqa: E402

UEBERSICHT = """
<div class="events">
<a class="event" href="/gigs/15076/"> <div class="img"> <img src="/veranstaltungsbild/15076/?v=abc" alt="Flyer POINTS OF CONCEPTION"> </div> <div class="info"> <div class="date"> Do, 01.10.26 <span class="time">19:00 Uhr</span> </div> <div class="headlines"> <div class="item">"The Light Inside Tour"</div> </div> <div class="artists"> <div class="item"> <span class="artist-name">POINTS OF CONCEPTION</span> <span class="artist-info">Metalcore / AUT</span></div> </div> </div> </a>
<a class="event" href="/gigs/15088/"> <div class="img"> <img src="/veranstaltungsbild/15088/?v=def" alt="Flyer HOLY WAVE"> </div> <div class="info"> <div class="date"> Fr, 02.10.26 <span class="time">20:00 Uhr</span> </div> <div class="headlines"> </div> <div class="artists"> <div class="item"> <span class="artist-name">HOLY WAVE</span> <span class="artist-info">Neo-Psych from Austin, Texas / USA</span></div><div class="item"> <span class="artist-name">THE ROARING 420s</span> <span class="artist-info">Surf, Rock, 60`s Prepunk / Dresden</span></div><div class="item"> <span class="artist-name">OH NICO</span> <span class="artist-info">Garagepop / Dresden</span></div> </div> </div> </a>
<a class="event" href="/gigs/10161/"> <div class="img"> <img src="/img/demnaechst.png" alt="Infos folgen …"> </div> <div class="info"> <div class="date"> Sa, 28.11.26 </div> <div class="headlines"> <div class="item">Infos folgen …</div><div class="item">Veganer Wintermarkt</div> </div> <div class="artists"> </div> </div> </a>
</div>
"""

DETAIL = """
<div class="event">
 <div class="col"><div class="date">Fr, 02.10.26</div><div class="time">Einlass: 20:00 Uhr<br>Beginn: 21:00 Uhr</div></div>
 <div class="col"><div class="headlines"></div>
  <div class="artists"><div class="item"><span class="artist"><a href="#">HOLY WAVE</a></span> <span class="genre">Neo-Psych from Austin, Texas</span> <span class="herkunft">/ USA</span></div></div>
  <div class="infos"><p>HOLY WAVE kommen aus Austin, Texas.</p></div>
  <div class="praesentatoren">präsentiert von: It's a Gas! Records, Chemiefabrik</div>
 </div>
 <div class="col"><div class="vvk">Vorverkauf: 23,00€ <span class="vvk-gebuehr">zzgl. Vorverkaufs-Gebühren</span> <a class="vvk-stelle">TixforGigs</a></div><div class="ak">Abendkasse: 28,00€</div></div>
</div>
"""


def test_uebersicht_titel_bild_und_platzhalter():
    t = {x["title"]: x for x in chemiefabrik._parse_uebersicht(UEBERSICHT)}
    assert set(t) == {"POINTS OF CONCEPTION", "HOLY WAVE + THE ROARING 420s + OH NICO", "Veganer Wintermarkt"}
    holy = t["HOLY WAVE + THE ROARING 420s + OH NICO"]
    assert holy["date"] == date(2026, 10, 2) and holy["time"] == "20:00"
    assert holy["url"] == "https://www.chemiefabrik.info/gigs/15088/"
    assert holy["image_url"].startswith("https://www.chemiefabrik.info/veranstaltungsbild/15088/")
    assert t["Veganer Wintermarkt"]["image_url"] is None
    assert t["Veganer Wintermarkt"]["time"] is None
    assert t["POINTS OF CONCEPTION"]["kopf"] == ['"The Light Inside Tour"']


def test_detail_beginn_preis_beschreibung():
    zeit, infos, preis, praes = chemiefabrik._parse_detail(DETAIL)
    assert zeit == "21:00"
    assert infos == "HOLY WAVE kommen aus Austin, Texas."
    assert preis == "Vorverkauf 23,00€ · Abendkasse 28,00€"
    assert praes.startswith("präsentiert von:")


def test_scrape_range_mit_detail_und_zeitraum(monkeypatch):
    seiten = {chemiefabrik.URL: UEBERSICHT}
    monkeypatch.setattr(chemiefabrik.base, "fetch_html", lambda url, **kw: seiten.get(url, DETAIL))
    monkeypatch.setattr(chemiefabrik, "DETAIL_DELAY_SECONDS", 0)
    ev = {e["title"]: e for e in chemiefabrik.scrape_range(date(2026, 9, 27), date(2026, 10, 28))}
    assert "Veganer Wintermarkt" not in ev
    holy = ev["HOLY WAVE + THE ROARING 420s + OH NICO"]
    assert holy["time"] == "21:00" and holy["venue"] == "Chemiefabrik"
    assert "HOLY WAVE kommen aus Austin" in holy["description"]


def test_detailfehler_behaelt_termin(monkeypatch):
    def fetch(url, **kw):
        if url == chemiefabrik.URL:
            return UEBERSICHT
        raise RuntimeError("weg")
    monkeypatch.setattr(chemiefabrik.base, "fetch_html", fetch)
    monkeypatch.setattr(chemiefabrik, "DETAIL_DELAY_SECONDS", 0)
    ev = {e["title"]: e for e in chemiefabrik.scrape_range(date(2026, 9, 27), date(2026, 10, 28))}
    assert ev["POINTS OF CONCEPTION"]["time"] == "19:00"


def test_konzerttour_in_chemiefabrik_und_beatpol_ist_keine_fuehrung():
    assert normalize.classify_category(None, "The Light Inside Tour", "Chemiefabrik") != "fuehrungen"
    assert normalize.classify_category(None, "SOLE TOUR", "Beatpol") != "fuehrungen"
    assert normalize.classify_category(None, "Elbschlösser-Tour", "Schloss Albrechtsberg") == "fuehrungen"

"""Scraper für das Arteum (arteum.de), Partykeller am Waldschlösschen.

Seit 2026-10-02 (Davids Wunsch). Normaler Ort, kein Herz-Ort: eher
Partyhaus (Halloween-Partys, Hardtekk, P16-Partys) als Subkultur. Gegen die
Live-Seite geprüft am 02.10.2026, im Browser, weil Cowork die Seite sperrt.

Die Seite ist mit Wix gebaut. Die Termine stehen auf /partys als Bilder-
Galerie. Sichtbar sind nur die ersten drei, aber Wix legt die ganze Galerie
als JSON in die Seite (für den ersten Aufbau):

    <script type="application/json" id="wix-warmup-data">
      {... "appsWarmupData": {"<app>": {"comp-…_galleryData": {"items": [
        {"metaData": {"title": "BieberFieber",
                      "description": "📆  Freitag 02.10.\\n🕑 ab 22 Uhr\\nP18",
                      "link": {"data": {"url": "https://partysdresden.ticket.io/…"}}},
         "mediaUrl": "01abe7_d2fc…~mv2.jpg"}, …]}}}}
    </script>

Das JSON ist stabiler als die Wix-Klassen im HTML. Je Eintrag gibt es nur
Titel, Tag ohne Jahr, Uhrzeit, Altersgrenze, Bild und Ticket-Link, keine
Beschreibung (nichts erfinden). Einträge ohne Datum ("P16 Partys") fallen weg.

Das Jahr fehlt. Es kommt wie beim Ostpol vom Startdatum des Laufs (mehr als
ein halbes Jahr zurück = nächstes Jahr); passt der Wochentag nur zu einem
anderen Jahr, gilt der Wochentag (das nächstliegende passende Jahr). Alte Einträge bleiben manchmal stehen (am 02.10.
"Freitag 11.09."), die filtert der Zeitraum weg.

Bilder: Wix verkleinert über die Adresse; 600 px, Seitenverhältnis bleibt
(große Bilder lassen das Scrollen am Handy stocken, siehe CLAUDE.md).
"""
import json
import re
from datetime import date, datetime, timedelta

from .. import normalize
from . import base

SOURCE = "arteum"
URL = "https://www.arteum.de/partys"
VENUE = "Arteum"
RAW_CATEGORY = "Party"
BILD = "https://static.wixstatic.com/media/{m}/v1/fit/w_600,h_600,q_80/{m}"

WOCHENTAGE = {"montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
              "freitag": 4, "samstag": 5, "sonntag": 6}
_DATUM_RE = re.compile(r"(?:([A-Za-z]+)\s+)?(\d{1,2})\.(\d{1,2})\.")
_ZEIT_RE = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?\s*Uhr", re.IGNORECASE)


def _galerie_eintraege(daten):
    """Alle Galerie-Einträge aus dem Warmup-JSON, egal wie tief sie stecken."""
    if isinstance(daten, dict):
        for schluessel, wert in daten.items():
            if schluessel.endswith("_galleryData") and isinstance(wert, dict):
                yield from wert.get("items") or []
            else:
                yield from _galerie_eintraege(wert)
    elif isinstance(daten, list):
        for wert in daten:
            yield from _galerie_eintraege(wert)


def _datum(text, bezug):
    m = _DATUM_RE.search(text or "")
    if not m:
        return None
    wochentag = WOCHENTAGE.get((m.group(1) or "").lower())
    tag, monat = int(m.group(2)), int(m.group(3))
    kandidaten = []
    for jahr in (bezug.year - 1, bezug.year, bezug.year + 1):
        try:
            kandidaten.append(date(jahr, monat, tag))
        except ValueError:
            pass
    if not kandidaten:
        return None
    # Standard: das Jahr, das nicht mehr als ein halbes Jahr zurückliegt.
    grenze = bezug - timedelta(days=183)
    standard = min((k for k in kandidaten if k >= grenze), default=kandidaten[-1])
    if wochentag is None or standard.weekday() == wochentag:
        return standard
    passend = [k for k in kandidaten if k.weekday() == wochentag]
    return min(passend, key=lambda k: abs(k - bezug)) if passend else standard


def _zeit(text):
    m = _ZEIT_RE.search(text or "")
    if m and int(m.group(1)) <= 23:
        return f"{int(m.group(1)):02d}:{m.group(2) or '00'}"
    return None


def _parse(html, bezug):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt."""
    soup = base.make_soup(html)
    skript = soup.find("script", id="wix-warmup-data")
    if skript is None:
        return []
    try:
        daten = json.loads(skript.string or skript.get_text())
    except ValueError:
        return []

    events = []
    for item in _galerie_eintraege(daten):
        meta = item.get("metaData") or {}
        titel = " ".join((meta.get("title") or "").split())
        text = meta.get("description") or ""
        tag = _datum(text, bezug)
        if not titel or tag is None:
            continue
        zeit = _zeit(text)
        link = ((meta.get("link") or {}).get("data") or {}).get("url") or URL
        medium = item.get("mediaUrl") or meta.get("name")
        events.append({
            "uid": normalize.make_event_uid(tag.isoformat(), zeit, titel, VENUE),
            "source": SOURCE,
            "date": tag.isoformat(),
            "time": zeit,
            "title": titel,
            "venue": VENUE,
            # Die Seite nennt nur "Partys"; genauer wird es über Titel und Flavour.
            "category": normalize.classify_category(RAW_CATEGORY, titel, VENUE),
            "raw_category": RAW_CATEGORY,
            "url": link,
            "image_url": BILD.format(m=medium) if medium else None,
            "price_text": None,
            "description": None,
            # Mehr gibt die Seite nicht her, es gibt nichts nachzuladen.
            "detail_fetched_at": datetime.utcnow().isoformat(),
        })
    return events


def scrape_range(start_day, end_day):
    """Holt /partys einmal und filtert auf [start_day, end_day]."""
    events = _parse(base.fetch_html(URL), start_day)
    start, end = start_day.isoformat(), end_day.isoformat()
    gesehen, aus = set(), []
    for e in events:
        if start <= e["date"] <= end and e["uid"] not in gesehen:
            gesehen.add(e["uid"])
            aus.append(e)
    return aus

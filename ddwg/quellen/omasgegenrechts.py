"""Scraper für die Termine der OMAS GEGEN RECHTS Dresden.

Die Seite läuft mit WordPress und "The Events Calendar", der einen ICS-Export
anbietet:

    https://www.omasgegenrechts-dresden.de/termine/?ical=1

Gegen den echten Feed geprüft (29.09.2026, im Browser, weil die Seite aus
Cowork heraus gesperrt ist): 10 Termine bis Dezember, Kategorien "Demo",
"Mahnwache" und "Gruppentreffen". Übernommen werden Demos und Mahnwachen
(Davids Entscheidung: Demos sind ausdrücklich erwünscht), die internen
Gruppentreffen nicht.

LOCATION hat die Form "Stadt, Ort, Straße, Stadt, PLZ" ("Dresden, Theaterplatz,
Theaterplatz, Dresden, 01067"). Der Ort ist also der ZWEITE Teil. Früher
standen auch Demos in Erfurt oder Riesa im Kalender - übernommen wird nur
Dresden und das Umland (geo.classify_region auf die Stadt).
"""
import html
from datetime import datetime
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

from .. import geo, normalize
from . import base

SOURCE = "omasgegenrechts"
CALENDAR_URL = "https://www.omasgegenrechts-dresden.de/termine/?ical=1"
BERLIN = ZoneInfo("Europe/Berlin")
STICHWOERTER = ("demo", "mahnwache", "kundgebung")


def _kategorien(component):
    werte = component.get("CATEGORIES")
    if werte is None:
        return ""
    if not isinstance(werte, list):
        werte = [werte]
    teile = []
    for w in werte:
        cats = getattr(w, "cats", None)
        teile.extend(str(c) for c in cats) if cats is not None else teile.append(str(w))
    return ",".join(teile)


def _ort(location):
    """(Ort oder None, passt die Region?) aus 'Stadt, Ort, Straße, ...'."""
    teile = [t.strip() for t in (location or "").split(",") if t.strip()]
    if not teile:
        return None, True
    stadt = teile[0]
    ort = teile[1] if len(teile) > 1 else None
    if stadt.lower() == "dresden":
        return ort, True
    if geo.classify_region(stadt) != geo.REGION_UMLAND:
        return None, False
    return (f"{ort} {stadt}" if ort else stadt), True


def _parse_calendar(ics_bytes, start_day, end_day):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt."""
    calendar = icalendar.Calendar.from_ical(ics_bytes)
    events = []
    for component in recurring_ical_events.of(calendar).between(start_day, end_day):
        titel = html.unescape(str(component.get("SUMMARY") or "")).strip()
        dt_start = component.get("DTSTART")
        if not titel or dt_start is None:
            continue
        kategorien = _kategorien(component)
        if not any(w in kategorien.lower() for w in STICHWOERTER) \
                and normalize.classify_category("", titel) != "demo":
            continue
        ort, passt = _ort(str(component.get("LOCATION") or ""))
        if not passt:
            continue

        wert = dt_start.dt
        if isinstance(wert, datetime):
            lokal = wert.astimezone(BERLIN) if wert.tzinfo else wert
            tag, zeit = lokal.date(), f"{lokal.hour:02d}:{lokal.minute:02d}"
        else:
            tag, zeit = wert, None
        text = html.unescape(str(component.get("DESCRIPTION") or "")).strip() or None
        bild = component.get("ATTACH")
        events.append({
            "uid": normalize.make_event_uid(tag.isoformat(), zeit, titel, ort),
            "source": SOURCE,
            "date": tag.isoformat(),
            "time": zeit,
            "title": titel,
            "venue": ort,
            "category": "demo",
            "raw_category": kategorien or None,
            "url": str(component.get("URL") or "") or "https://www.omasgegenrechts-dresden.de/termine/",
            "image_url": str(bild) if bild else None,
            "price_text": None,
            "description": text,
            "detail_fetched_at": datetime.utcnow().isoformat(),
        })
    return events


def scrape_range(start_day, end_day):
    return _parse_calendar(base.fetch_html(CALENDAR_URL), start_day, end_day)

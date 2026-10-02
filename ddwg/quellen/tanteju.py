"""Scraper für den Liveclub Tante JU (liveclub-dresden.de).

Herz-Ort, eigene Quelle seit 2026-10-02. Der Club bietet alle Termine als
iCal-Feed an ("Google Kalender / ICAL" unter /termine/, WordPress-Plugin
Events Manager):

    https://www.liveclub-dresden.de/events.ics

Gegen den echten Feed geprüft (02.10.2026, im Browser, weil die Seite aus
Cowork heraus gesperrt ist): 38 Termine bis Mai 2027, Zeiten mit
TZID=Europe/Berlin, ohne RRULE, ohne LOCATION. Aufbau je VEVENT:

    URL:https://www.liveclub-dresden.de/konzert/sadsvit/
    SUMMARY:SadSvit
    DTSTART;TZID=Europe/Berlin:20261011T200000
    DESCRIPTION:In diesem Herbst begibt sich SadSvit auf eine große ...
    CATEGORIES:Konzerte            (auch "Highlights,Konzerte")

Vorher kamen 11 von 13 Terminen über die Sammelkalender (02.10. bis 02.11.).
Eigenheiten: "(AUSVERKAUFT!)" steht im Titel, es wandert in den Preis.
"(verlegt ins Puschkin)" verschiebt den Termin an den neuen Ort, siehe
base.verlegt(). Kein Bild im Feed, das kommt vom Kulturkalender.
"""
import html
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

from .. import normalize
from . import base, detail_fetch

SOURCE = "tanteju"
CALENDAR_URL = "https://www.liveclub-dresden.de/events.ics"
URL = "https://www.liveclub-dresden.de/termine/"
VENUE = "Tante JU"
BERLIN = ZoneInfo("Europe/Berlin")
_AUSVERKAUFT_RE = re.compile(r"\s*\(\s*ausverkauft!?\s*\)\s*", re.IGNORECASE)


def _kategorie(component):
    """'Highlights,Konzerte' -> 'Konzert'; 'Highlights' allein sagt nichts."""
    roh = component.get("CATEGORIES")
    werte = []
    for teil in roh if isinstance(roh, list) else [roh]:
        if teil is None:
            continue
        werte += [str(c).strip() for c in getattr(teil, "cats", [teil])]
    werte = [w for w in werte if w and w.lower() != "highlights"]
    if not werte:
        return None
    return "Konzert" if werte[0].lower() == "konzerte" else werte[0]


def _parse_calendar(ics_bytes, start_day, end_day):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt."""
    calendar = icalendar.Calendar.from_ical(ics_bytes)
    events = []
    for component in recurring_ical_events.of(calendar).between(start_day, end_day):
        titel = html.unescape(str(component.get("SUMMARY") or "")).strip()
        dt_start = component.get("DTSTART")
        if not titel or dt_start is None:
            continue
        ausverkauft = bool(_AUSVERKAUFT_RE.search(titel))
        titel = " ".join(_AUSVERKAUFT_RE.sub(" ", titel).split())
        titel, neuer_ort = base.verlegt(titel)
        ort = neuer_ort or VENUE

        wert = dt_start.dt
        if isinstance(wert, datetime):
            lokal = wert.astimezone(BERLIN) if wert.tzinfo else wert
            tag, zeit = lokal.date(), f"{lokal.hour:02d}:{lokal.minute:02d}"
        else:
            tag, zeit = wert, None

        text = html.unescape(str(component.get("DESCRIPTION") or "")).strip() or None
        preis = "ausverkauft" if ausverkauft else detail_fetch.price_from_text(text)
        roh = _kategorie(component)
        events.append({
            "uid": normalize.make_event_uid(tag.isoformat(), zeit, titel, ort),
            "source": SOURCE,
            "date": tag.isoformat(),
            "time": zeit,
            "title": titel,
            "venue": ort,
            "category": normalize.classify_category(roh, titel, ort),
            "raw_category": roh,
            "url": str(component.get("URL") or "") or URL,
            "image_url": None,
            "price_text": preis,
            "description": text,
            "detail_fetched_at": datetime.utcnow().isoformat(),
        })
    return events


def scrape_range(start_day, end_day):
    """Holt den Kalender einmal, recurring_ical_events filtert auf den Zeitraum."""
    return _parse_calendar(base.fetch_html(CALENDAR_URL), start_day, end_day)

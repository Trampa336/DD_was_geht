"""Scraper für den Club Puschkin (clubpuschkin.de).

Herz-Ort, eigene Quelle seit 2026-10-02. Die Seite nutzt das WordPress-Plugin
Events Manager, das alle Termine als iCal-Feed ausgibt (nicht verlinkt, aber
dieselbe Adresse wie bei Tante JU):

    https://www.clubpuschkin.de/events.ics

Gegen den echten Feed geprüft (02.10.2026, im Browser, weil die Seite aus
Cowork heraus gesperrt ist): 13 Termine bis Januar 2027, Zeiten in UTC,
ohne RRULE. Der Feed ist schlicht, je VEVENT nur:

    SUMMARY:VITA &#124\\; Was da los Tour 2026     (HTML-Zeichen im Titel)
    DTSTART:20261016T180000Z
    LOCATION:Club Puschkin
    URL:https://www.clubpuschkin.de/events/vita-was-da-los-tour-2026/

Keine Beschreibung, kein Bild, keine Kategorie: die kommen beim Verschmelzen
vom Kulturkalender und von rauze. Die Quelle sorgt für Vollständigkeit
(vorher 6 von 8 Terminen im Oktober) und den richtigen Beginn.
"(hochverlegt in die Tante JU)" verschiebt den Termin, siehe base.verlegt().
"""
import html
from datetime import datetime
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

from .. import normalize
from . import base

SOURCE = "puschkin"
CALENDAR_URL = "https://www.clubpuschkin.de/events.ics"
URL = "https://www.clubpuschkin.de/veranstaltungen/"
VENUE = "Puschkin"
BERLIN = ZoneInfo("Europe/Berlin")


def _parse_calendar(ics_bytes, start_day, end_day):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt."""
    calendar = icalendar.Calendar.from_ical(ics_bytes)
    events = []
    for component in recurring_ical_events.of(calendar).between(start_day, end_day):
        titel = " ".join(html.unescape(str(component.get("SUMMARY") or "")).split())
        dt_start = component.get("DTSTART")
        if not titel or dt_start is None:
            continue
        titel, neuer_ort = base.verlegt(titel)
        ort = neuer_ort or VENUE

        wert = dt_start.dt
        if isinstance(wert, datetime):
            lokal = wert.astimezone(BERLIN) if wert.tzinfo else wert
            tag, zeit = lokal.date(), f"{lokal.hour:02d}:{lokal.minute:02d}"
        else:
            tag, zeit = wert, None

        events.append({
            "uid": normalize.make_event_uid(tag.isoformat(), zeit, titel, ort),
            "source": SOURCE,
            "date": tag.isoformat(),
            "time": zeit,
            "title": titel,
            "venue": ort,
            "category": normalize.classify_category(None, titel, ort),
            "raw_category": None,
            "url": str(component.get("URL") or "") or URL,
            "image_url": None,
            "price_text": None,
            "description": None,
            "detail_fetched_at": datetime.utcnow().isoformat(),
        })
    return events


def scrape_range(start_day, end_day):
    """Holt den Kalender einmal, recurring_ical_events filtert auf den Zeitraum."""
    return _parse_calendar(base.fetch_html(CALENDAR_URL), start_day, end_day)

"""Scraper für die Scheune (scheune.org).

Die Scheune bietet ihr Programm als ICS-Abo an ("ICS KALENDERABO" im Menü):

    https://scheune.org/shows.ics

Gegen den echten Feed geprüft (27.09.2026, im Browser, weil scheune.org aus
Cowork heraus gesperrt ist): 73 Termine, alle mit Uhrzeit in UTC, ohne RRULE.
Aufbau je VEVENT:

    URL:https://scheune.org/show/5478/skating-polly.html
    SUMMARY:Skating Polly
    DTSTART:20260929T180000Z
    LOCATION:scheune\\, Alaunstrasse  36-40\\, 01099 Dresden
    DESCRIPTION:Konzert\\nEU/UK Tour 2026

Zwei Eigenheiten:

1. **Die erste Beschreibungszeile ist meist die Sparte** ("Konzert", "Party",
   "Literatur", "Live Podcast"). Aber nur, wenn noch eine Zeile folgt: bei
   "Ja zum Alter" steht dort allein der Untertitel ("Internationaler Tag der
   Älteren Menschen"). Einzeilige Beschreibungen gelten deshalb nie als Sparte.
2. **Nicht alles findet in der Scheune statt.** 8 von 73 Terminen liefen im
   Kulturpalast, in der Schauburg, im Parkhotel usw. Der Ort ist dann der Teil
   von LOCATION vor dem ersten Komma und läuft ganz normal über orte.resolve().

Kein Bild im Feed. Das Bild kommt beim Verschmelzen vom Kulturkalender.
"""
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

from .. import normalize
from . import base, detail_fetch

SOURCE = "scheune"
CALENDAR_URL = "https://scheune.org/shows.ics"
VENUE = "Scheune"
BERLIN = ZoneInfo("Europe/Berlin")


def _ort(location):
    """'scheune, Alaunstrasse 36-40, ...' -> 'Scheune'; sonst der Name vor dem Komma."""
    name = (location or "").split(",")[0].strip()
    if not name or name.lower().startswith("scheune"):
        return VENUE
    return name


def _sparte_und_text(description):
    """(Sparte oder None, Beschreibungstext oder None), siehe Modul-Docstring."""
    zeilen = [z.strip() for z in (description or "").splitlines() if z.strip()]
    if len(zeilen) >= 2 and len(zeilen[0]) <= 30:
        return zeilen[0], "\n".join(zeilen[1:])
    return None, "\n".join(zeilen) or None


def _ohne_query(url):
    """Tracking-Anhänge am Link weglassen, der Pfad reicht."""
    if not url:
        return None
    teile = urlsplit(url)
    return urlunsplit((teile.scheme, teile.netloc, teile.path, "", ""))


def _parse_calendar(ics_bytes, start_day, end_day):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt."""
    calendar = icalendar.Calendar.from_ical(ics_bytes)
    events = []
    for component in recurring_ical_events.of(calendar).between(start_day, end_day):
        titel = str(component.get("SUMMARY") or "").strip()
        dt_start = component.get("DTSTART")
        if not titel or dt_start is None:
            continue
        wert = dt_start.dt
        if isinstance(wert, datetime):
            lokal = wert.astimezone(BERLIN)
            tag, zeit = lokal.date(), f"{lokal.hour:02d}:{lokal.minute:02d}"
        else:
            tag, zeit = wert, None

        ort = _ort(str(component.get("LOCATION") or ""))
        sparte, text = _sparte_und_text(str(component.get("DESCRIPTION") or ""))
        beschreibung = "\n".join(t for t in (sparte, text) if t) or None

        events.append({
            "uid": normalize.make_event_uid(tag.isoformat(), zeit, titel, ort),
            "source": SOURCE,
            "date": tag.isoformat(),
            "time": zeit,
            "title": titel,
            "venue": ort,
            "category": normalize.classify_category(sparte, titel, ort),
            "raw_category": sparte,
            "url": _ohne_query(str(component.get("URL") or "")) or "https://scheune.org/",
            "image_url": None,
            "price_text": detail_fetch.price_from_text(text),
            "description": beschreibung,
            "detail_fetched_at": datetime.utcnow().isoformat(),
        })
    return events


def scrape_range(start_day, end_day):
    """Holt den Kalender einmal, recurring_ical_events filtert auf den Zeitraum."""
    return _parse_calendar(base.fetch_html(CALENDAR_URL), start_day, end_day)

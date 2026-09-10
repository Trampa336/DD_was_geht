"""Scraper für das Zentralwerk (zentralwerk.de).

Auch hier kein HTML-Scraper: die eigentliche Terminseite des Hauses zeigt gar
kein Programm, sondern verweist ("INFO zu: unserem Veranstaltungskalender")
auf einen öffentlichen Teamup-Kalender:

    https://ics.teamup.com/feed/ksb8nqdwihhj3mdtdc/2968691.ics

Das ist ein normaler ICS-Feed, allerdings MIT wiederkehrenden Terminen
(RRULE) - der offene Chor läuft z.B. wöchentlich, der Arbeitseinsatz jeden
dritten Samstag. Eine rohe icalendar-Bibliothek liefert nur die VEVENT-
*Vorlagen*, nicht deren tatsächliche Termine im Zeitraum; deshalb übernimmt
`recurring_ical_events` das Auflösen (RRULE, EXDATE, Ausnahmen).

DESCRIPTION hat einen festen Zeilenaufbau (gegen 110 echte Einträge
verifiziert, 03.09.2026):

    Who: <Veranstalter oder Genre-Hinweis, z.B. "Jazzkonzert">
    <Leerzeile>
    <Freitext, 0-mehrere Zeilen>
    <Leerzeile>
    INFO: https://zentralwerk.de/...

"Who:" ist keine sortenreine Rohkategorie wie bei anderen Quellen (mal ein
Genre wie "Jazzkonzert", mal einfach der Veranstalter "Zentralwerk e.V." oder
"Chaos Computer Club Dresden") und wird deshalb bewusst NICHT als raw_category
an normalize.classify_category() gereicht - dieselbe Ortsnamen-Falle wie im
README ("Landesbühnen Sachsen" enthält "bühne"), nur mit Veranstalternamen
statt Ortsnamen: "Chaos Computer Club Dresden" enthält "club" und würde eine
Hacker-Konferenz zu "musik" machen. Gegen die 20 echten Termine im
Kalibrierungslauf (10.09.-10.10.2026) klassifiziert der Titel allein genauso
gut oder besser - "Jazzfanatics (Jazzkonzert)" trifft schon über "jazz" im
Titel. "Who:" bleibt trotzdem nicht verloren: es steht als "Veranstalter:"
in der Beschreibung, nur eben außerhalb der Kategorie-Erkennung. Wichtig
auch für tools/reclassify.py, das raw_category aus der DB erneut durch
classify_category schickt - ein einmal gespeicherter Veranstaltername würde
den Fehler bei jedem Nachklassifizieren wiederholen.

Kein Bild: weder im Feed noch auf den verlinkten Programmseiten steht ein
og:image (gegen mehrere echte Seiten verifiziert) - anders als bei Sektor
Evolution oder GrooveStation lohnt sich hier also kein zusätzlicher
Detail-Request je Termin.
"""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

from .. import normalize
from . import base, detail_fetch

SOURCE = "zentralwerk"
CALENDAR_URL = "https://ics.teamup.com/feed/ksb8nqdwihhj3mdtdc/2968691.ics"
VENUE = "Zentralwerk"
BERLIN = ZoneInfo("Europe/Berlin")

_INFO_URL_RE = re.compile(r"INFO:\s*(\S+)")
_WHO_RE = re.compile(r"^Who:\s*(.+)$")


def _split_description(raw_description):
    """Teilt DESCRIPTION in (Who-Zeile, Freitext, INFO-URL) - siehe
    Modul-Docstring. Fehlt eine "Who:"-Zeile (kommt vor, siehe "Offener Chor"),
    bleibt raw_category leer und der Freitext beginnt gleich mit der ersten
    inhaltlichen Zeile."""
    who = None
    body_lines = []
    for line in (raw_description or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        who_match = _WHO_RE.match(stripped)
        if who_match and who is None and not body_lines:
            who = who_match.group(1).strip()
            continue
        if stripped.lower().startswith("info:"):
            continue
        body_lines.append(stripped)
    info_match = _INFO_URL_RE.search(raw_description or "")
    body = "\n".join(body_lines) or None
    return who, body, (info_match.group(1) if info_match else None)


def _event_date_time(dt_value):
    """RRULE-Vorkommen liefern datetime (Termin mit Uhrzeit) oder date
    (ganztägig, z.B. "Datenspuren 2026"). Beides muss hier ankommen können."""
    if isinstance(dt_value, datetime):
        local = dt_value.astimezone(BERLIN)
        return local.date(), f"{local.hour:02d}:{local.minute:02d}"
    return dt_value, None


def _parse_calendar(ics_bytes, start_day, end_day):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt.
    start_day/end_day gehen direkt an recurring_ical_events - das Auflösen
    der RRULEs passiert nur für den gebrauchten Zeitraum, nicht für den
    gesamten Kalender."""
    calendar = icalendar.Calendar.from_ical(ics_bytes)
    occurrences = recurring_ical_events.of(calendar).between(start_day, end_day)

    events = []
    for component in occurrences:
        title = str(component.get("SUMMARY") or "").strip()
        dt_start = component.get("DTSTART")
        if not title or dt_start is None:
            continue
        day, norm_time = _event_date_time(dt_start.dt)

        who, body, info_url = _split_description(str(component.get("DESCRIPTION") or ""))
        room = str(component.get("LOCATION") or "").strip() or None
        # Bewusst raw_category="" statt who - siehe Modul-Docstring.
        category = normalize.classify_category("", title, VENUE)

        description_parts = []
        if room:
            # Der Raum im Haus (Foyer, Kleiner Saal, Hof, ...) geht sonst
            # verloren - VENUE bleibt bewusst "Zentralwerk" (siehe
            # Modul-Docstring), damit Doppelungen mit anderen Quellen
            # überhaupt erkannt werden können.
            description_parts.append(f"Ort im Haus: {room}")
        if who:
            description_parts.append(f"Veranstalter: {who}")
        if body:
            description_parts.append(body)

        events.append({
            "uid": normalize.make_event_uid(day.isoformat(), norm_time, title, VENUE),
            "source": SOURCE,
            "date": day.isoformat(),
            "time": norm_time,
            "title": title,
            "venue": VENUE,
            "category": category,
            "raw_category": None,
            "url": info_url or "https://zentralwerk.de/programm/",
            "image_url": None,
            "price_text": detail_fetch.price_from_text(body),
            "description": "\n\n".join(description_parts) or None,
            "detail_fetched_at": datetime.utcnow().isoformat(),
        })
    return events


def scrape_range(start_day, end_day):
    """Holt den Kalender einmal und löst RRULEs direkt für [start_day, end_day]
    auf - kein Filtern danach nötig wie bei den übrigen Quellen."""
    return _parse_calendar(base.fetch_html(CALENDAR_URL), start_day, end_day)

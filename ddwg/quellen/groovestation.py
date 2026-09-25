"""Scraper für die GrooveStation (groovestation.de).

Anders als alle bisherigen Quellen kein HTML-Scraper: die Seite veröffentlicht
ihr komplettes Programm als ICS-Kalender unter `/calendar.ics` (verlinkt im
Footer als "→ Kalender (ICS)"). Das ist strukturiert, enthält Startzeit,
Beschreibung, Preis und Genre in einem Request - kein Rätselraten an
Uhrzeit-Textknoten wie bei den HTML-Quellen.

Eine Besonderheit macht die Quelle wertvoller als "nur die GrooveStation
selbst": der Kalender ist der einer Booking-Agentur und listet auch Termine,
die sie an ANDEREN Häusern veranstaltet (LOCATION steht z.B. auch mal
"Tante Ju, Dresden" oder "Filmtheater Schauburg, Dresden") - deshalb wird der
Ort aus LOCATION gelesen statt fest auf "GrooveStation" gesetzt.

DESCRIPTION ist ein fester Zeilenaufbau (gegen mehrere echte Einträge
verifiziert, 09.09.2026):

    <Teaser, 0-2 Zeilen>
    Preis: 13.2 EUR            <- optional, "Eintritt frei" statt Betrag möglich
    Alter: 16                  <- optional
    Genres: Literatur          <- optional, mehrere durch ", " getrennt
    <Leerzeile>
    Tickets & Infos:
    https://www.groovestation.de/event/...
    <weitere Ticketlinks, optional>

Genau dieser Aufbau wird zerlegt statt detail_fetch.price_from_text() zu
bemühen: dessen Preis-Regex verlangt zwei Nachkommastellen und würde "13.2
EUR" (eine Stelle, Punkt statt Komma) verfehlen.

Kein Bild im Feed - das liefert nur die Event-Seite selbst (og:image), daher
ein Detail-Request pro Termin im Zeitraum wie schon bei Sektor Evolution.
"""
import logging
import re
import time as time_module
from datetime import datetime
from zoneinfo import ZoneInfo

import icalendar

from .. import normalize
from . import base

logger = logging.getLogger("dd-was-geht.groovestation")

SOURCE = "groovestation"
CALENDAR_URL = "https://www.groovestation.de/calendar.ics"
BERLIN = ZoneInfo("Europe/Berlin")

# Deckel und Drosselung für die Bild-Requests je Event-Seite - dieselbe
# Überlegung wie bei sektor.MAX_DETAIL_FETCHES: 31 Tage Vorlauf liefern hier
# meist 20-30 Termine, der Deckel greift nur, falls die Quelle das Programm
# stark ausweitet.
MAX_DETAIL_FETCHES = 60
DETAIL_DELAY_SECONDS = 0.5

_META_LINE_RE = re.compile(r"^(Preis|Alter|Genres):\s*(.*)$")


def _split_description(raw_description):
    """Teilt DESCRIPTION in (Teaser, {preis, genres}) - siehe Modul-Docstring.

    Die Zeilen "Tickets & Infos:" und alles danach sind reiner Linkspam (die
    URL steht ohnehin schon in url); sie enden die Beschreibung.
    """
    meta = {}
    teaser_lines = []
    for line in (raw_description or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("tickets & infos"):
            break
        match = _META_LINE_RE.match(stripped)
        if match:
            meta[match.group(1).lower()] = match.group(2).strip()
            continue
        teaser_lines.append(stripped)
    return "\n".join(teaser_lines) or None, meta


def _venue_from_location(location):
    """"GrooveStation, Dresden" -> "GrooveStation". Ohne Ortsangabe (kommt in
    der Praxis nicht vor) bleibt der Name der Agentur selbst als Rückfall."""
    first = (location or "").split(",")[0].strip()
    return first or "GrooveStation"


def _raw_category(genres):
    """Die Quelle liefert Musikgenres ("Hip-Hop", "Techno", "Black Metal", ...)
    statt einer Rohkategorie, wie sie normalize.RAW_CATEGORY_MAP kennt - jedes
    Genre einzeln dort einzutragen wäre endlos. Da praktisch jeder Termin ohne
    Genre-Angabe eine Bar-Institution ist (Kickermontag, Billard & Bar,
    GrooveQuiz) und praktisch jeder MIT Angabe ein Konzert oder eine Party,
    reicht eine grobe Weiche: nur "Literatur"/"Poetry" (Lesebühne, Poetry
    Slam) läuft unter kultur, der Rest unter musik. Ohne Genre-Angabe bleibt
    raw_category leer und normalize._classify_by_keywords() entscheidet über
    den Titel (trifft dort nichts, ist "sonstiges" - passend für Kickermontag)."""
    slug = normalize.slugify(genres or "")
    if not slug:
        return None
    if "literatur" in slug or "poetry" in slug or "lesung" in slug:
        return "Lesung"
    return "Konzert"


def _local_time(dt_start):
    """DTSTART steht als UTC-Zeitstempel im Feed; Startzeit in Lokalzeit."""
    if dt_start.tzinfo is None:
        return None
    local = dt_start.astimezone(BERLIN)
    return f"{local.hour:02d}:{local.minute:02d}"


def _parse_calendar(ics_text):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt.

    Gibt Roh-Einträge zurück, noch ohne Bild - das holt scrape_range() pro
    Termin im Zeitraum nach (siehe Modul-Docstring).
    """
    calendar = icalendar.Calendar.from_ical(ics_text)
    entries = []
    for component in calendar.walk("VEVENT"):
        title = str(component.get("SUMMARY") or "").strip()
        dt_start = component.get("DTSTART")
        if not title or dt_start is None:
            continue
        dt_start = dt_start.dt
        # DTSTART kann auch ein reines datum (ganztägig) sein - dann gibt es
        # keine Uhrzeit und astimezone() waere ein Fehler.
        if isinstance(dt_start, datetime):
            day, norm_time = dt_start.astimezone(BERLIN).date(), _local_time(dt_start)
        else:
            day, norm_time = dt_start, None

        teaser, meta = _split_description(str(component.get("DESCRIPTION") or ""))
        venue = _venue_from_location(str(component.get("LOCATION") or ""))
        raw_category = _raw_category(meta.get("genres"))
        url = str(component.get("URL") or "") or None

        entries.append({
            "date": day.isoformat(),
            "time": norm_time,
            "title": title,
            "venue": venue,
            "raw_category": raw_category,
            "url": url,
            "price_text": meta.get("preis"),
            "description": teaser,
        })
    return entries


def _fetch_image(url):
    """og:image der Event-Seite. Wirft nie - ohne Bild bleibt image_url leer."""
    if not url:
        return None
    try:
        soup = base.make_soup(base.fetch_html(url))
        meta = soup.select_one('meta[property="og:image"]')
        return meta["content"] if meta and meta.get("content") else None
    except Exception:
        logger.warning("GrooveStation-Bild nicht ladbar: %s", url)
        return None


def _build_event(entry, image_url):
    return {
        "uid": normalize.make_event_uid(entry["date"], entry["time"], entry["title"], entry["venue"]),
        "source": SOURCE,
        "date": entry["date"],
        "time": entry["time"],
        "title": entry["title"],
        "venue": entry["venue"],
        "category": normalize.classify_category(entry["raw_category"] or "", entry["title"], entry["venue"]),
        "raw_category": entry["raw_category"],
        "url": entry["url"],
        "image_url": image_url,
        "price_text": entry["price_text"],
        "description": entry["description"],
        "detail_fetched_at": datetime.utcnow().isoformat(),
    }


def scrape_range(start_day, end_day, fetch_image=_fetch_image):
    """Holt den Kalender einmal und filtert auf [start_day, end_day].

    fetch_image ist injizierbar, damit Tests ohne Netzwerk auskommen.
    """
    entries = _parse_calendar(base.fetch_html(CALENDAR_URL))
    start, end = start_day.isoformat(), end_day.isoformat()
    entries = sorted(
        (e for e in entries if start <= e["date"] <= end), key=lambda e: (e["date"], e["time"] or "")
    )
    if len(entries) > MAX_DETAIL_FETCHES:
        logger.warning(
            "GrooveStation: %d Termine im Zeitraum, Bilder nur für die ersten %d.",
            len(entries), MAX_DETAIL_FETCHES,
        )

    events = []
    for index, entry in enumerate(entries):
        image_url = fetch_image(entry["url"]) if index < MAX_DETAIL_FETCHES else None
        events.append(_build_event(entry, image_url))
        if index and DETAIL_DELAY_SECONDS:
            time_module.sleep(DETAIL_DELAY_SECONDS)
    return events

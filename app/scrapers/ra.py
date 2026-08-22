"""Quelle: Resident Advisor (ra.co) - Clubkultur/Electronic in Dresden.

Kein HTML-Scraper. ra.co baut seine Seiten im Browser zusammen und schiebt
jeden normalen Seitenabruf durch einen Bot-Schutz (DataDome): ein GET auf
https://ra.co/events/de/dresden antwortet mit HTTP 403 und einer
"Please enable JS"-Seite, egal mit welchem User-Agent. Die GraphQL-
Schnittstelle, aus der sich die Seite selbst bedient, ist dagegen offen und
liefert die Daten direkt strukturiert - inklusive Preis, Beschreibung, Flyer
und Lineup. Deshalb wird hier bewusst die API statt der Seite gelesen.

Gegen die Live-API verifiziert (21.08.2026):
    POST https://ra.co/graphql
    Dresden = areas.eq 150  (GET_AREAS liefert die vollständige Liste, siehe
    README, Abschnitt "Resident Advisor als Quelle")
    - Ein Request deckt einen ganzen Zeitraum ab (Filter listingDate gte/lte),
      nicht Tag für Tag wie bei den HTML-Quellen.
    - `content` (Beschreibung) und `cost` (Preis) kommen bereits in der Liste
      mit; ein Detail-Nachladen wie beim Kulturkalender entfällt.
    - Ein User-Agent MUSS gesetzt sein: ohne UA antwortet auch /graphql mit 403.
      Referer/Origin sind nicht nötig.
"""
import json
import logging
import re
import time
from datetime import datetime

import requests

from .. import config, normalize
from . import base

logger = logging.getLogger("dd-was-geht.scrapers.ra")

SOURCE = "ra"
GRAPHQL_URL = "https://ra.co/graphql"

# Die Seite selbst holt 20er-Seiten; 100 ist erlaubt und spart Requests.
PAGE_SIZE = 100
# Notbremse gegen eine kaputte Pagination (Dresden liefert real ~20 Events
# pro Monat, ein Monat passt also längst in eine Seite).
MAX_PAGES = 10
REQUEST_DELAY_SECONDS = 1.2

# Ohne User-Agent: 403. Bewusst derselbe ehrliche UA wie bei den HTML-Quellen
# (base.HEADERS), statt einen Browser vorzutäuschen.
HEADERS = dict(base.HEADERS, **{"Content-Type": "application/json"})

EVENT_LISTINGS_QUERY = """
query GET_EVENT_LISTINGS($filters: FilterInputDtoInput, $pageSize: Int, $page: Int) {
  eventListings(filters: $filters, pageSize: $pageSize, page: $page) {
    data {
      id
      listingDate
      event {
        id
        date
        startTime
        endTime
        title
        contentUrl
        content
        cost
        images { filename type }
        venue { id name area { id name } }
        artists { name }
      }
    }
    totalResults
  }
}
"""

# Orte, die RA vergibt, wenn der Veranstalter (noch) keinen nennt.
_UNKNOWN_VENUES = {"tba", "tbc", "secret-location", "unknown"}

# "15-20" oder "10 - 15" nennt RA ohne Währung; ohne das € liest sich das
# Preis-Badge im Web-UI wie eine Uhrzeit. Reine Textangaben ("Free entry",
# "VVK 18 €") bleiben unangetastet.
_BARE_AMOUNT_RE = re.compile(r"^[\d]+(?:[.,]\d+)?(?:\s*[-–]\s*[\d]+(?:[.,]\d+)?)?$")


def _price_text(cost):
    cost = (cost or "").strip()
    if not cost:
        return None
    if _BARE_AMOUNT_RE.match(cost):
        return f"{cost} €"
    return cost


def _venue_name(event):
    venue = event.get("venue") or {}
    name = (venue.get("name") or "").strip()
    if not name or normalize.slugify(name) in _UNKNOWN_VENUES:
        return None
    return name


def _image_url(event):
    images = event.get("images") or []
    for image in images:
        if (image.get("type") or "").upper() == "FLYERFRONT" and image.get("filename"):
            return image["filename"]
    for image in images:
        if image.get("filename"):
            return image["filename"]
    return None


def _description(event):
    """Beschreibungstext, ergänzt um das Lineup - auf RA steckt die eigentliche
    Information oft im Lineup und nicht im Fließtext ("Join us for a night...")."""
    parts = []
    content = (event.get("content") or "").strip()
    if content:
        parts.append(content)
    artists = [a.get("name") for a in (event.get("artists") or []) if a.get("name")]
    if artists:
        parts.append("Line-up: " + ", ".join(artists))
    return "\n\n".join(parts) or None


def _start_time(event):
    """RA liefert startTime als lokale Zeit ohne Zeitzone
    ('2026-08-22T23:00:00.000'). Für Events nach Mitternacht steht in
    listingDate weiterhin der Partytag - genau das, was wir als date wollen."""
    raw = event.get("startTime") or ""
    match = re.search(r"T(\d{2}:\d{2})", raw)
    if match:
        return match.group(1)
    return None


def _event_from_listing(listing):
    event = listing.get("event") or {}
    title = (event.get("title") or "").strip()
    if not title:
        return None

    day = (listing.get("listingDate") or event.get("date") or "")[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        return None

    venue = _venue_name(event)
    norm_time = _start_time(event)
    # "Club" ist in normalize.RAW_CATEGORY_MAP hinterlegt und landet damit in
    # musik. Der Sport-Vorabcheck in classify_category() greift trotzdem noch,
    # falls RA doch mal etwas anderes listet.
    raw_category = "Club"
    category = normalize.classify_category(raw_category, title, venue)

    content_url = event.get("contentUrl") or ""
    url = f"https://ra.co{content_url}" if content_url.startswith("/") else (content_url or None)

    return {
        "uid": normalize.make_event_uid(day, norm_time, title, venue or ""),
        "source": SOURCE,
        "date": day,
        "time": norm_time,
        "title": title,
        "venue": venue,
        "category": category,
        "raw_category": raw_category,
        "url": url,
        "image_url": _image_url(event),
        "price_text": _price_text(event.get("cost")),
        "description": _description(event),
        # Beschreibung und Preis stehen schon in der Liste - es gibt nichts
        # nachzuladen (siehe scrapers/detail_fetch.py).
        "detail_fetched_at": datetime.utcnow().isoformat(),
    }


def parse_listings(payload):
    """payload: die geparste GraphQL-Antwort. Gibt normalisierte Event-dicts
    zurück (als eigene Funktion, damit tests_smoke.py sie ohne Netzwerk prüft)."""
    listings = (
        (payload or {}).get("data", {}).get("eventListings", {}).get("data") or []
    )
    events = []
    for listing in listings:
        parsed = _event_from_listing(listing)
        if parsed:
            events.append(parsed)
    return events


def _post(variables, timeout=20, retries=2):
    body = json.dumps({
        "operationName": "GET_EVENT_LISTINGS",
        "variables": variables,
        "query": EVENT_LISTINGS_QUERY,
    })
    last_error = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(GRAPHQL_URL, headers=HEADERS, data=body, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("errors"):
                raise RuntimeError(f"GraphQL-Fehler: {payload['errors']}")
            return payload
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"ra.co/graphql nicht erreichbar: {last_error}")


def _filters(start_day, end_day, area_id):
    return {
        "areas": {"eq": area_id},
        "listingDate": {
            "gte": f"{start_day.isoformat()}T00:00:00.000Z",
            "lte": f"{end_day.isoformat()}T00:00:00.000Z",
        },
    }


def scrape_range(start_day, end_day, area_id=None):
    """start_day/end_day: datetime.date. Ein Request pro Ergebnisseite (nicht
    pro Tag). Fehler werden geloggt, aber nicht geworfen - eine kaputte Quelle
    darf den restlichen Lauf nicht stoppen."""
    area_id = config.RA_AREA_ID if area_id is None else area_id
    filters = _filters(start_day, end_day, area_id)

    all_events = []
    for page in range(1, MAX_PAGES + 1):
        try:
            payload = _post({"filters": filters, "pageSize": PAGE_SIZE, "page": page})
        except RuntimeError as exc:
            logger.warning("[ra] Seite %d konnte nicht geladen werden: %s", page, exc)
            break

        events = parse_listings(payload)
        all_events.extend(events)

        listings = payload["data"]["eventListings"]
        total = listings.get("totalResults") or 0
        if len(listings.get("data") or []) < PAGE_SIZE or page * PAGE_SIZE >= total:
            break
        time.sleep(REQUEST_DELAY_SECONDS)

    return all_events

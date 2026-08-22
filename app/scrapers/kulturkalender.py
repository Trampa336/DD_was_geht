"""Scraper für kulturkalender-dresden.de.

Bekanntes, verlässliches URL-Muster: /heute/{YYYY-MM-DD} zeigt alle Events für
genau diesen Tag, über alle Kategorien hinweg (bestätigt für mehrere Testdaten
im August 2026). Für "diese Woche" / "diesen Monat" wird daher Tag für Tag
abgefragt statt eine (nicht auffindbare) Bereichs-URL zu nutzen.
"""
import time
from datetime import timedelta

from .. import normalize
from . import base

# Kleine Pause zwischen Anfragen - für einen Monat sind das bis zu 31 Requests
# an dieselbe Seite; niemand hat etwas davon, wenn wir sie im Sekundentakt
# bombardieren.
REQUEST_DELAY_SECONDS = 1.2

SOURCE = "kulturkalender"
BASE_URL = "https://www.kulturkalender-dresden.de/heute/{date}"

CATEGORY_HINTS = [
    "Musik", "Bühne", "Ausstellungen", "Ausstellung", "Festival", "Lesung",
    "Vortrag", "Gespräch", "Führungen", "Führung", "Entdeckungen",
    "Kinder", "Familie",
]


def _guess_raw_category(container):
    """Stichwortsuche bewusst OHNE die Linktexte - dort stehen die Ortsnamen,
    die häufig selbst Genre-Wörter enthalten ("Landesbühnen Sachsen",
    "Jazzclub Tonne"). Siehe base.text_excluding_links."""
    lowered = base.text_excluding_links(container).lower()
    for hint in CATEGORY_HINTS:
        if hint.lower() in lowered:
            return hint
    return None


SITE_ROOT = "https://www.kulturkalender-dresden.de"


def _extract_permalink(container, fallback_url):
    """Die Überschrift verlinkt auf die eigene Seite des Events
    (/veranstaltung/{slug}). Ohne sie stünde in url nur die Tagesübersicht -
    die zeigt morgen schon andere Veranstaltungen."""
    link = container.select_one("h3.title-event a[href]") or container.select_one("h3 a[href]")
    if not (link and link.get("href")):
        return fallback_url
    href = link["href"].strip()
    if href.startswith("http"):
        return href
    return SITE_ROOT + ("" if href.startswith("/") else "/") + href


def _extract_image(container):
    """Das Cover liegt nicht im gefundenen Block selbst (.component-card), sondern
    daneben im umgebenden <section class="component-event">. Deshalb gezielt
    genau bis zu diesem Vorfahren hochlaufen - weiter oben stünden schon die
    Bilder der Nachbar-Events."""
    img = container.select_one(".wrapper-event-media img") or container.select_one(".list-media img")
    if img is None:
        section = container.find_parent("section", class_="component-event")
        if section is not None:
            img = section.select_one(".wrapper-event-media img") or section.select_one(".list-media img")
    if img is None:
        return None
    srcset = img.get("srcset")
    if srcset:
        # srcset ist nach Breite absteigend sortiert; der erste Eintrag ist die
        # größte Variante und damit die brauchbarste fürs Cover.
        first = srcset.split(",")[0].strip().split(" ")[0]
        if first:
            return first
    return img.get("src")


def scrape_date(day):
    """day: datetime.date. Gibt eine Liste normalisierter Event-dicts zurück."""
    url = BASE_URL.format(date=day.isoformat())
    html = base.fetch_html(url)
    soup = base.make_soup(html)

    events = []
    for time_text, container in base.find_event_blocks(soup):
        title = base.extract_title(container)
        if not title:
            continue
        venue = base.extract_venue(container)
        raw_category = _guess_raw_category(container)
        category = normalize.classify_category(raw_category or "", title, venue)
        norm_time = normalize.normalize_time(time_text)
        uid = normalize.make_event_uid(day.isoformat(), norm_time, title, venue or "")

        events.append({
            "uid": uid,
            "source": SOURCE,
            "date": day.isoformat(),
            "time": norm_time,
            "title": title,
            "venue": venue,
            "category": category,
            "raw_category": raw_category,
            "url": _extract_permalink(container, url),
            "image_url": _extract_image(container),
            # Preis und Beschreibung stehen NICHT in der Tagesliste - die holt
            # scrapers.detail_fetch bei Bedarf nach (siehe web.api_event_details).
        })
    return events


def scrape_range(start_day, end_day):
    all_events = []
    current = start_day
    while current <= end_day:
        try:
            all_events.extend(scrape_date(current))
        except Exception as exc:  # eine schlechte Antwort soll nicht den ganzen Lauf stoppen
            print(f"[kulturkalender] Fehler beim Laden von {current}: {exc}")
        time.sleep(REQUEST_DELAY_SECONDS)
        current += timedelta(days=1)
    return all_events

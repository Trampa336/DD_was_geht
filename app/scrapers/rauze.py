"""Scraper für rauze.de (Partys, Konzerte, Kunst in Dresden).

Ergänzt kulturkalender-dresden.de vor allem um Nightlife/Club-Events, die dort
kaum vertreten sind - Ostpol, objekt klein a, GrooveStation, Sektor Evolution,
Chemiefabrik, Scheune usw.

URL-Muster (gegen die Live-Seite verifiziert):
    https://www.rauze.de/?date=YYYY-MM-DD

Getestet für nahe und weit entfernte Tage (z.B. 2026-08-22 und 2026-09-05),
liefert jeweils zuverlässig genau den angefragten Tag. Die Startseite ohne
Parameter zeigt den heutigen Tag; wir benutzen trotzdem einheitlich die
?date=-Form, damit es nur einen Codepfad gibt.

Kategorien, die Rauze tatsächlich vergibt (verifiziert):
    Konzert, Party, Kunst, Festival, Film, Sonstiges, Außerhalb
"Außerhalb" ist dabei eine Ortsangabe (Veranstaltung im Umland), kein Genre -
solche Events werden bewusst über die Titel-Schlüsselwörter klassifiziert.
"""
from datetime import datetime

from .. import normalize
from . import base

SOURCE = "rauze"
DATE_URL_TEMPLATE = "https://www.rauze.de/?date={date}"

# Nur echte Genre-Kategorien. "Sonstiges" und "Außerhalb" fehlen hier absichtlich:
# beide sagen nichts über die Art der Veranstaltung aus, deshalb sollen sie in die
# Schlüsselwort-Klassifizierung durchfallen (ein als "Außerhalb" gelistetes Rave
# soll als Musik erkannt werden, nicht als "Weiteres").
CATEGORY_HINTS = [
    "Konzert", "Party", "Kunst", "Festival", "Film",
    "Theater", "Lesung", "Gespräch", "Diskussion",
]


def _guess_raw_category(container):
    """Kategorie in zwei Stufen: erst die von Rauze gerenderte Klammerform
    '( Konzert )', sonst Stichwortsuche - beides bewusst OHNE die Linktexte,
    da dort die Ortsnamen stehen (siehe base.text_excluding_links)."""
    parenthesized = base.extract_parenthesized_category(container)
    if parenthesized:
        for hint in CATEGORY_HINTS:
            if hint.lower() == parenthesized.lower():
                return hint
        # Klammerinhalt erkannt, aber kein Genre (z.B. "Sonstiges", "Außerhalb")
        # -> bewusst None, damit über den Titel klassifiziert wird.
        return None

    lowered = base.text_excluding_links(container).lower()
    for hint in CATEGORY_HINTS:
        if hint.lower() in lowered:
            return hint
    return None


def _extract_price(container):
    """Rauze liefert den Preis als Klartext, z.B. "Eintritt frei", "VVK 32,04",
    "ab 5,-" oder "ausverkauft" - bewusst unverändert übernommen, statt zu
    versuchen, diese sehr freie Schreibweise zu normalisieren."""
    el = container.select_one(".details li.price")
    if el is None:
        return None
    return el.get_text(" ", strip=True) or None


def _extract_image(container):
    bg = base.extract_bg_image_url(container.select_one(".preview .bg_image"))
    if bg:
        return bg
    img = container.select_one(".details .images img")
    return img.get("src") if img else None


def _extract_description(container):
    paragraphs = container.select(".details .description > div")
    text = "\n\n".join(
        p.get_text(" ", strip=True) for p in paragraphs if p.get_text(strip=True)
    )
    return text or None


def _extract_permalink(container, fallback_url):
    """Der Teilen-Link enthält die saubere Event-URL (z.B. /cats-dogs). Ohne ihn
    stünde in url nur die Tagesübersicht, die morgen schon etwas anderes zeigt."""
    link = container.select_one(".details .social li.share a[href]")
    if link and link.get("href"):
        return link["href"]
    return fallback_url


def _parse(html, day, source_url):
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
            "url": _extract_permalink(container, source_url),
            "image_url": _extract_image(container),
            "price_text": _extract_price(container),
            "description": _extract_description(container),
            # Rauze blendet den kompletten Detailinhalt schon in der Tagesliste
            # mit ein (nur per JS zugeklappt) - es gibt also nichts nachzuladen.
            "detail_fetched_at": datetime.utcnow().isoformat(),
        })
    return events


def scrape_date(day):
    """day: datetime.date. Gibt eine Liste normalisierter Event-dicts zurück."""
    return base.fetch_day(DATE_URL_TEMPLATE.format(date=day.isoformat()), day, _parse)


def scrape_range(start_day, end_day):
    return base.scrape_days(start_day, end_day, scrape_date, SOURCE)

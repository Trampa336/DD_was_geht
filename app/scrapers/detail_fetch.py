"""Detailinhalte einzelner Events bei Bedarf nachladen.

Anders als die Tageslisten wird das hier NICHT im Hintergrund-Scrape gemacht,
sondern erst wenn jemand im Web-UI auf "Details" klickt (siehe
web.api_event_details). Ergebnis wandert in die DB und wird ab dann von dort
bedient - pro Event fällt also höchstens ein zusätzlicher Request an, und nur
für Events, die wirklich jemand aufmacht.

Betrifft in der Praxis nur den Kulturkalender: Rauze blendet den kompletten
Detailinhalt schon in der Tagesliste mit ein (nur per JS zugeklappt), diese
Events sind deshalb bereits beim Scrapen vollständig.

Grundhaltung wie bei den Scrapern: nie hart an einer Struktur hängen, im
Zweifel lieber "nichts gefunden" liefern als eine Exception - ein Ausfall der
Quellseite darf den Klick im Browser nicht in einen Fehler verwandeln.
"""
import re

from . import base

FALLBACK_DESCRIPTION = "Keine weitere Beschreibung verfügbar."

# Bewusst kurz und ohne Retry: Das hier passiert, während ein Mensch im Browser
# auf den Popup wartet. Lieber ohne Beschreibung anzeigen als sekundenlang
# hängen.
DETAIL_TIMEOUT_SECONDS = 8

# Preisangaben stehen beim Kulturkalender nirgends strukturiert, sondern
# mitten im Fließtext ("Eintritt: 11€-18€", "Eintritt frei", "ab 8 Euro").
# Diese Muster holen die gängigen Schreibweisen heraus; findet keins etwas,
# bleibt price_text schlicht leer.
# Reihenfolge ist wichtig: Ein konkreter Betrag schlägt "Eintritt frei".
# Sonst käme bei "Eintritt: 11€-18€ (unter 18 Jahren Eintritt frei)" das
# irreführende "Eintritt frei" heraus, obwohl der Abend 11-18€ kostet.
_PRICE_PATTERNS = [
    re.compile(
        r"((?:ab\s*)?\d{1,3}(?:[.,]\d{2})?\s*(?:Euro|EUR|€)"
        r"(?:\s*(?:[-–—]|bis)\s*\d{1,3}(?:[.,]\d{2})?\s*(?:Euro|EUR|€)?)?)",
        re.I,
    ),
    re.compile(r"(Eintritt\s*(?:ist\s*)?frei)", re.I),
    re.compile(r"(kostenlos)", re.I),
    re.compile(r"Eintritt[:\s]+([^.\n;(]{1,40})", re.I),
]


def _clean(text):
    return re.sub(r"\s+", " ", text or "").strip() or None


def _first_text(soup, selectors, min_length=0):
    for selector in selectors:
        for el in soup.select(selector):
            text = el.get_text(" ", strip=True)
            if text and len(text) >= min_length:
                return _clean(text)
    return None


def _first_image(soup, selectors):
    for selector in selectors:
        el = soup.select_one(selector)
        if el is None:
            continue
        srcset = el.get("srcset")
        if srcset:
            first = srcset.split(",")[0].strip().split(" ")[0]
            if first:
                return first
        if el.get("src"):
            return el["src"]
        bg = base.extract_bg_image_url(el)
        if bg:
            return bg
    return None


def price_from_text(text):
    if not text:
        return None
    for pattern in _PRICE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        value = _clean(match.group(1))
        if value:
            return value
    return None


def _parse_kulturkalender_detail(soup):
    """Gegen echte Detailseiten verifiziert. Es gibt zwei Layouts: meist steht
    der Text in <div class="box-content"> direkt unter <main>, manche Seiten
    klappen ihn stattdessen in ein Akkordeon (.box-accordion). Die Mindestlänge
    sortiert die zweite, immer vorhandene .box-content ("Veranstaltung teilen")
    aus, die sonst als Beschreibung durchginge."""
    description = _first_text(
        soup,
        ["main > .box-content", ".box-accordion", ".box-content"],
        min_length=40,
    )
    image_url = _first_image(soup, [".wrapper-event-media img", ".list-media img", "main img"])
    return {
        "description": description or FALLBACK_DESCRIPTION,
        "price_text": price_from_text(description),
        "image_url": image_url,
    }


def _parse_rauze_detail(soup):
    """Sicherheitsnetz - normalerweise nie erreicht, weil Rauze-Events bereits
    beim Scrapen vollständig sind und deshalb nie hier landen."""
    description = _first_text(soup, [".details .description", ".description"])
    return {
        "description": description or FALLBACK_DESCRIPTION,
        "price_text": _first_text(soup, [".details li.price", "li.price"]),
        "image_url": _first_image(soup, [".details .images img", ".preview .bg_image"]),
    }


def _parse_generic_detail(soup):
    """Für alles andere (Events, die auf beliebige Seiten zeigen):
    nur das, was praktisch jede Seite mitliefert."""
    description = None
    for selector in ['meta[property="og:description"]', 'meta[name="description"]']:
        meta = soup.select_one(selector)
        if meta and meta.get("content"):
            description = _clean(meta["content"])
            break
    image = soup.select_one('meta[property="og:image"]')
    return {
        "description": description or FALLBACK_DESCRIPTION,
        "price_text": price_from_text(description),
        "image_url": image["content"] if image and image.get("content") else None,
    }


def _parse_sektor_detail(soup):
    """Delegiert an den Sektor-Scraper.

    Das Markup dieser Quelle steht dort schon beschrieben, und der
    Hintergrund-Scrape braucht dieselbe Funktion (er holt die Detailseite
    sofort mit, weil erst sie die Uhrzeit nennt - siehe sektor.parse_detail).
    Der Import steht bewusst in der Funktion: sektor.py importiert dieses Modul
    seinerseits fuer price_from_text, ein Import auf Modulebene waere ein Zirkel.
    """
    from . import sektor
    return sektor.parse_detail(soup)


_PARSERS = {
    "kulturkalender": _parse_kulturkalender_detail,
    "rauze": _parse_rauze_detail,
    "sektor": _parse_sektor_detail,
}

_EMPTY = {"ok": False, "description": None, "price_text": None, "image_url": None}


def fetch_detail(event, fetch_html=base.fetch_html):
    """Holt genau EIN Event von seiner eigenen Seite nach.

    fetch_html ist injizierbar, damit Tests ohne Netzwerk auskommen.
    Wirft nie - im Fehlerfall kommt ok=False zurück und der Aufrufer zeigt
    einfach das, was ohnehin schon bekannt ist."""
    url = event.get("url")
    if not url:
        return dict(_EMPTY)

    try:
        html = fetch_html(url, timeout=DETAIL_TIMEOUT_SECONDS, retries=0)
        soup = base.make_soup(html)
        result = _PARSERS.get(event.get("source"), _parse_generic_detail)(soup)
    except Exception:
        return dict(_EMPTY)

    result["ok"] = True
    return result

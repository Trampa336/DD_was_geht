"""Standorte der Venues ernten: Adresse + Koordinaten fuer die Kartenansicht.

Hintergrund: die Karte scheiterte bisher an der Annahme, es gaebe keine
Adressdaten. Die stammt aus der EVENT-Detailseite des Kulturkalenders - dort
enthaelt <address> tatsaechlich nur den Venue-Namen (siehe app/geo.py). Die
KK-VENUE-Seite ist eine andere Seite und traegt sehr wohl eine Postanschrift:

    <div class="box-location-description">
        <p> Riesaer Str. 32<br> 01127  Dresden<br> <a href="tel:...">...

Gemessen an den 25 Venues mit den meisten kommenden Events: 24/25 (96%)
liefern eine PLZ, dahinter 1534 von 1588 Events. Der eine Ausreisser ist
"Terrassenufer Dresden" - ein Treffpunkt am Elbufer ohne Hausnummer, also
ehrliches Fehlen und kein Parsefehler.

Zwei Wege zu den Koordinaten, in dieser Reihenfolge:

  1. AUS DER SEITE.  Manche KK-Venue-Seiten binden einen Google-Maps-Link mit
     fertigen Koordinaten ein (.../maps/search/?api=1&query=51.054684,13.735276).
     Die sind exakt und kosten keinen zusaetzlichen Request. Sie stehen aber
     nicht auf jeder Seite (Semperoper ja, Zentralwerk nein).
  2. GEOCODING.  Fehlt der Link, geht die Adresse an Nominatim (OSM). Ein
     Request je Venue, Ergebnis wandert in die DB und wird nie erneut geholt.

Beides wird gecacht (data/venue_cache/kk_pages/, geocode.json), damit ein
zweiter Lauf und jede Handpruefung ohne neue Requests auskommen.

Tempo: base.REQUEST_DELAY_SECONDS (1,2 s) zwischen allen KK-Requests, fuer
Nominatim 1,1 s - deren Nutzungsbedingungen verlangen hoechstens 1 req/s.

Aufruf:
    ../.venv/bin/python tools/fetch_venue_locations.py <db> [--limit N] [--apply]
    (ohne --apply: nur Bericht, nichts geschrieben)
"""
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import venue_slug  # noqa: E402
from app.scrapers import base  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "venue_cache"
PAGE_DIR = CACHE_DIR / "kk_pages"
GEOCODE_CACHE = CACHE_DIR / "geocode.json"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
NOMINATIM_DELAY = 1.1
# Nominatim verlangt eine identifizierbare Anwendung mit Kontakt.
NOMINATIM_HEADERS = {"User-Agent": base.HEADERS["User-Agent"]}

_BLOCK_RE = re.compile(r'<div class="box-location-description">(.*?)</div>', re.S)
_PLZ_RE = re.compile(r"\b(\d{5})\s+(.+)")
_COORD_RE = re.compile(
    r"(?:google\.[a-z.]+/maps[^\"']*?query=|openstreetmap\.org[^\"']*?mlat=)"
    r"(-?\d{1,2}\.\d{3,})[,&][^0-9-]{0,8}(-?\d{1,3}\.\d{3,})"
)
# Dresden und Umgebung grob eingegrenzt. Ein Geocoder, der "Hauptstrasse"
# ohne Ort bekommt, landet gern in Hamburg - so ein Treffer waere auf der
# Karte ein sichtbarer Fehler und faellt hier vorher raus.
BBOX = (50.5, 52.0, 12.5, 15.2)  # lat_min, lat_max, lon_min, lon_max


def in_bbox(lat, lon):
    return BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]


def parse_location(html):
    """KK-Venue-HTML -> (street, postcode, city, lat, lon). Alles einzeln
    NULL-bar: ein Treffpunkt hat keine Hausnummer, das ist kein Fehler."""
    street = postcode = city = None
    block = _BLOCK_RE.search(html)
    if block:
        text = re.sub(r"<br\s*/?>", "\n", block.group(1))
        text = re.sub(r"<[^>]+>", " ", text)
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.split("\n")]
        lines = [ln for ln in lines if ln]
        for i, line in enumerate(lines):
            m = _PLZ_RE.match(line)
            if m:
                postcode, city = m.group(1), m.group(2).strip()
                # Die Strasse steht unmittelbar ueber der PLZ-Zeile - nur dann,
                # sonst faengt man Telefon- oder Mailzeilen ein.
                if i > 0 and not lines[i - 1].startswith(("tel:", "mailto:")):
                    street = lines[i - 1]
                break
    coords = _COORD_RE.search(html)
    lat = lon = None
    if coords:
        try:
            lat, lon = float(coords.group(1)), float(coords.group(2))
        except ValueError:
            lat = lon = None
        if lat is not None and not in_bbox(lat, lon):
            lat = lon = None
    return street, postcode, city, lat, lon


def clean_venue_name(name):
    """Hausname fuer den Geocoder entrauschen.

    Nominatim kennt "Gemaeldegalerie Alte Meister", nicht aber
    "Gemaeldegalerie Alte Meister im Zwinger Dresden". Weg muessen: Klammer-
    zusaetze, der Traeger hinter " - " (siehe parent_venue_id im Schema), die
    "im <Gebaeude>"-Verortung und das angehaengte "Dresden".
    """
    name = re.sub(r"\([^)]*\)", "", name)
    name = re.split(r"\s+[-\u2013]\s+", name)[0]
    name = re.sub(r"\s+im\s+.*$", "", name)
    name = re.sub(r"\s*\bDresden\b\s*$", "", name)
    return re.sub(r"\s+", " ", name).strip()


def cached_page(slug, url, stats):
    """KK-Seite holen, aber nur einmal je Slug."""
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = PAGE_DIR / f"{slug}.html"
    if path.exists():
        stats["cache_hit"] += 1
        return path.read_text(encoding="utf-8", errors="replace")
    try:
        html = base.fetch_html(url, timeout=25)
    except Exception as exc:  # noqa: BLE001 - Bericht statt Abbruch
        stats["fetch_fail"] += 1
        print(f"  FETCH-FAIL {slug}: {str(exc)[:70]}")
        time.sleep(base.REQUEST_DELAY_SECONDS)
        return None
    path.write_text(html, encoding="utf-8")
    stats["fetched"] += 1
    time.sleep(base.REQUEST_DELAY_SECONDS)
    return html


def load_geocode_cache():
    if GEOCODE_CACHE.exists():
        return json.loads(GEOCODE_CACHE.read_text(encoding="utf-8"))
    return {}


def geocode(query, cache, stats):
    """Adresse -> (lat, lon) via Nominatim. Ein Fehlschlag wird MIT gecacht
    (als null), damit der naechste Lauf ihn nicht erneut anfragt."""
    if query in cache:
        stats["geo_cache_hit"] += 1
        hit = cache[query]
        return (hit["lat"], hit["lon"]) if hit else (None, None)
    url = f"{NOMINATIM}?q={quote(query)}&format=json&limit=1&countrycodes=de"
    try:
        resp = requests.get(url, headers=NOMINATIM_HEADERS, timeout=25)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        stats["geo_fail"] += 1
        print(f"  GEO-FAIL {query[:50]}: {str(exc)[:50]}")
        time.sleep(NOMINATIM_DELAY)
        return None, None
    time.sleep(NOMINATIM_DELAY)
    if not data:
        cache[query] = None
        stats["geo_miss"] += 1
        return None, None
    lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
    if not in_bbox(lat, lon):
        # Treffer ausserhalb der Region ist schlimmer als kein Treffer.
        cache[query] = None
        stats["geo_outside"] += 1
        return None, None
    cache[query] = {"lat": lat, "lon": lon}
    stats["geo_ok"] += 1
    return lat, lon


def kk_urls():
    """KK-Venue-URLs aus den Caches von P4, zweifach nachschlagbar.

    Der Cache ist nach dem ANZEIGENAMEN des Kulturkalenders gekeyt, die DB
    fuehrt einen eigenen gepflegten Namen - und die beiden gehen oefter
    auseinander, als es aussieht: gemessen fanden 460 von 656 Venues ihre URL
    ueber den Namen, weitere 61 (582 Events) erst ueber den Slug. Das sind
    keine fehlenden Seiten, sondern Schreibweisen - "Zentralwerk" gegen
    "Zentralwerk Dresden", "Erlwein Forum" gegen "Ostrapark".

    Deshalb zwei Woerterbuecher: exakt ueber den Namen, danach ueber den
    Slug (normalize.slugify, dieselbe Funktion, die auch die Venue-Identitaet
    bildet). Der erste Treffer je Slug gewinnt.
    """
    urls = {}
    for name in ("kk_venue_urls.json", "kk_venue_urls_ids.json"):
        path = CACHE_DIR / name
        if path.exists():
            urls.update(json.loads(path.read_text(encoding="utf-8")))
    by_slug = {}
    for name, url in urls.items():
        by_slug.setdefault(venue_slug(name), url)
    return urls, by_slug


def targets(con, limit):
    """Venues mit kommenden Events, die meisten zuerst - die Karte lebt von
    den Haeusern, an denen etwas stattfindet, nicht von der Namensliste."""
    rows = con.execute(
        """
        SELECT v.id, v.slug, v.name, count(*) n
        FROM events e JOIN venues v ON v.id = e.venue_id
        WHERE e.duplicate_of IS NULL AND e.date >= date('now')
          AND v.is_meeting_point = 0
        GROUP BY 1, 2, 3 ORDER BY n DESC
        """
    ).fetchall()
    return rows[:limit] if limit else rows


def main():
    args = [a for a in sys.argv[1:]]
    apply = "--apply" in args
    args = [a for a in args if a != "--apply"]
    limit = 0
    for a in list(args):
        if a.startswith("--limit"):
            limit = int(a.split("=", 1)[1]) if "=" in a else 0
            args.remove(a)
    db = args[0] if args else "data/dd-was-geht-v2.db"

    con = sqlite3.connect(db)
    urls, urls_by_slug = kk_urls()
    rows = targets(con, limit)
    cache = load_geocode_cache()
    stats = dict.fromkeys(
        ("cache_hit", "fetched", "fetch_fail", "no_url", "no_block",
         "coord_page", "geo_ok", "geo_miss", "geo_fail", "geo_outside",
         "geo_cache_hit", "no_address", "geo_by_name"), 0
    )
    results = []

    print(f"{len(rows)} Venues mit kommenden Events, {len(urls)} bekannte KK-URLs\n")
    for vid, slug, name, n in rows:
        url = urls.get(name) or urls_by_slug.get(slug)
        if not url:
            stats["no_url"] += 1
            continue
        html = cached_page(slug, url, stats)
        if html is None:
            continue
        street, plz, city, lat, lon = parse_location(html)
        source = None
        if lat is not None:
            source = "kk_page"
            stats["coord_page"] += 1
        elif plz and city:
            # Strasse kann fehlen (Treffpunkt) - dann geocodiert PLZ+Ort
            # immer noch auf Stadtteilebene, was fuer eine Karte reicht.
            query = ", ".join(x for x in (street, f"{plz} {city}") if x)
            lat, lon = geocode(query, cache, stats)
            if lat is None:
                # Zweiter Versuch mit dem Hausnamen. Faengt die Faelle ohne
                # Hausnummer ab ("Semperbau am Zwinger", "Neumarkt"), die der
                # Geocoder als Strasse nicht kennt, als Ort aber sehr wohl.
                lat, lon = geocode(f"{clean_venue_name(name)}, {city}", cache, stats)
                if lat is not None:
                    stats["geo_by_name"] += 1
            if lat is not None:
                source = "nominatim"
        else:
            stats["no_address"] += 1
        if not plz:
            stats["no_block"] += 1
        results.append((vid, slug, name, n, street, plz, city, lat, lon, source))
        GEOCODE_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                                 encoding="utf-8")

    located = [r for r in results if r[8] is not None]
    ev_total = sum(r[3] for r in rows)
    ev_located = sum(r[3] for r in located)
    print("\n--- Ergebnis ---")
    for k, v in stats.items():
        if v:
            print(f"  {k:14s} {v}")
    print(f"\n  Venues mit Koordinaten: {len(located)}/{len(rows)} "
          f"({len(located) / max(len(rows), 1) * 100:.1f}%)")
    print(f"  Events dahinter:        {ev_located}/{ev_total} "
          f"({ev_located / max(ev_total, 1) * 100:.1f}%)")

    if not apply:
        print("\n(ohne --apply nichts geschrieben)")
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    con.executemany(
        """UPDATE venues SET street=?, postcode=?, city=?, lat=?, lon=?,
                            geo_source=?, geo_fetched_at=?
           WHERE id=?""",
        [(r[4], r[5], r[6], r[7], r[8], r[9], now, r[0]) for r in results],
    )
    con.commit()
    print(f"\n{len(results)} Venue-Zeilen aktualisiert.")


if __name__ == "__main__":
    main()

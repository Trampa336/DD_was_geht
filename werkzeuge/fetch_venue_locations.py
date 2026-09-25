"""Standorte der Orte ernten: Adresse + Koordinaten fuer die Kartenansicht.

Umgestellt von der alten v2-Datenbank (venues-Tabelle) auf orte/orte.json
(siehe CLAUDE.md, Abschnitt "Offene Ideen"). Kuratiertes liegt jetzt in der
JSON-Datei, dieses Werkzeug liest und schreibt nur noch dort - genau wie
python -m ddwg herz.

Zwei Wege zu Koordinaten, in dieser Reihenfolge:

  1. ADRESSE SCHON DA, KOORDINATEN FEHLEN. orte.json hat bei manchen Orten
     schon eine Adresse (von Hand oder von einem frueheren Lauf), aber keine
     lat/lon. Die kostet keinen Seitenabruf - direkt geocodieren.
  2. WEDER ADRESSE NOCH KOORDINATEN. Die Kulturkalender-Ortsseite traegt in
     .box-location-description eine Postanschrift, manchmal zusaetzlich
     einen Google-Maps-Link mit fertigen Koordinaten (exakt, kein Request
     noetig). Fehlt der Link, wird die Adresse geocodiert.

Beide Wege respektieren, was schon in orte.json steht: nur leere lat/lon
werden gefuellt, nie ueberschrieben - auch nicht mit einem "besseren" Treffer.
Kuratiertes bleibt Davids.

Ziel-Reihenfolge fuer Weg 2 (KK-Seite noetig, kostet Requests): Orte mit den
meisten anstehenden Events zuerst, aus cache/events.db. Treffpunkte (kein
Haus, z.B. Stadtfuehrungen) werden uebersprungen.

Tempo: ddwg.quellen.base.REQUEST_DELAY_SECONDS (1,2 s) zwischen KK-Requests,
fuer Nominatim 1,1 s - deren Nutzungsbedingungen verlangen hoechstens 1 req/s.
Alles wird gecacht (cache/venue_cache/), ein zweiter Lauf kostet nur fuer
wirklich neue Orte neue Requests.

Hinweis Proxmox-Ordner: cache/events.db oeffnen (ddwg.db.connect) schlaegt
ueber den eingebundenen Geraete-Ordner mit "disk I/O error" fehl (SQLite und
der FUSE-Mount vertragen sich nicht) - lief bislang nur im Cowork-Cloud-
Container zuverlaessig. orte.json hinterher zurueckschreiben ist unkritisch,
das ist nur eine JSON-Datei.

Aufruf:
    python werkzeuge/fetch_venue_locations.py [--limit N] [--apply]
    (ohne --apply: nur Bericht, nichts geschrieben. Default-Limit 120 fuer
    Weg 2, wie der gedeckelte Detailabruf der Pipeline.)
"""
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ddwg import db  # noqa: E402
from ddwg.orte import Orte  # noqa: E402
from ddwg.quellen import base as qbase  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "venue_cache"
PAGE_DIR = CACHE_DIR / "kk_seiten"
GEOCODE_CACHE = CACHE_DIR / "geocode.json"
KK_URLS_CACHE = CACHE_DIR / "kk_venue_urls.json"

KK_DAY_URL = "https://www.kulturkalender-dresden.de/heute/{date}"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
NOMINATIM_DELAY = 1.1
NOMINATIM_HEADERS = {"User-Agent": qbase.HEADERS["User-Agent"]}

_BLOCK_RE = re.compile(r'<div class="box-location-description">(.*?)</div>', re.S)
_PLZ_RE = re.compile(r"\b(\d{5})\s+(.+)")
_COORD_RE = re.compile(
    r"(?:google\.[a-z.]+/maps[^\"']*?query=|openstreetmap\.org[^\"']*?mlat=)"
    r"(-?\d{1,2}\.\d{3,})[,&][^0-9-]{0,8}(-?\d{1,3}\.\d{3,})"
)
# Dresden und Umgebung grob eingegrenzt - ein Treffer ausserhalb ist auf der
# Karte ein sichtbarer Fehler und faellt hier vorher raus.
BBOX = (50.5, 52.0, 12.5, 15.2)


def in_bbox(lat, lon):
    return BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]


def parse_location(html):
    """KK-Ortsseite -> (adresse, plz, ort, lat, lon). Alles einzeln None-bar."""
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
    adresse = ", ".join(p for p in (street, f"{postcode} {city}" if postcode else None) if p) or None
    return adresse, postcode, city, lat, lon


def clean_ort_name(name):
    """Hausname fuer den Geocoder entrauschen (Klammerzusaetze, Traeger nach
    ' - ', 'im <Gebaeude>', angehaengtes 'Dresden' raus)."""
    name = re.sub(r"\([^)]*\)", "", name)
    name = re.split(r"\s+[-–]\s+", name)[0]
    name = re.sub(r"\s+im\s+.*$", "", name)
    name = re.sub(r"\s*\bDresden\b\s*$", "", name)
    return re.sub(r"\s+", " ", name).strip()


def load_geocode_cache():
    if GEOCODE_CACHE.exists():
        return json.loads(GEOCODE_CACHE.read_text(encoding="utf-8"))
    return {}


def save_geocode_cache(cache):
    GEOCODE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    GEOCODE_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


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
    except Exception as exc:  # noqa: BLE001 - Bericht statt Abbruch
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
        cache[query] = None
        stats["geo_outside"] += 1
        return None, None
    cache[query] = {"lat": lat, "lon": lon}
    stats["geo_ok"] += 1
    return lat, lon


def harvest_kk_urls(days):
    """{Roh-Schreibweise: KK-Ortsseiten-URL} aus den <address>-Bloecken der
    Tagesseiten - gemeinsamer Cache mit enrich_venues.py, ein Ort wird nur
    einmal geerntet, egal welches Werkzeug zuerst laeuft."""
    if KK_URLS_CACHE.exists():
        return json.loads(KK_URLS_CACHE.read_text(encoding="utf-8"))
    found = {}
    for day in days:
        url = KK_DAY_URL.format(date=day)
        try:
            html = qbase.fetch_html(url)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{day}] Fehler: {exc}")
            time.sleep(qbase.REQUEST_DELAY_SECONDS)
            continue
        soup = qbase.make_soup(html)
        neu = 0
        for address in soup.find_all("address"):
            link = address.find("a", href=True)
            if not link:
                continue
            text = re.sub(r"\s+", " ", address.get_text(" ", strip=True)).strip()
            if text and text not in found:
                href = link["href"].strip()
                found[text] = href if href.startswith("http") else "https://www.kulturkalender-dresden.de" + href
                neu += 1
        print(f"  [{day}] +{neu} neu (gesamt {len(found)})")
        time.sleep(qbase.REQUEST_DELAY_SECONDS)
    KK_URLS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    KK_URLS_CACHE.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
    return found


def cached_kk_page(slug, url, stats):
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = PAGE_DIR / f"{slug}.html"
    if path.exists():
        stats["cache_hit"] += 1
        return path.read_text(encoding="utf-8", errors="replace")
    try:
        html = qbase.fetch_html(url, timeout=25)
    except Exception as exc:  # noqa: BLE001
        stats["fetch_fail"] += 1
        print(f"  FETCH-FAIL {slug}: {str(exc)[:70]}")
        time.sleep(qbase.REQUEST_DELAY_SECONDS)
        return None
    path.write_text(html, encoding="utf-8")
    stats["fetched"] += 1
    time.sleep(qbase.REQUEST_DELAY_SECONDS)
    return html


def ziel_orte(orte, conn, limit):
    """Orte ohne Adresse UND ohne Koordinaten, meiste anstehende Events
    zuerst. Treffpunkte (kein Haus) werden uebersprungen."""
    rows = conn.execute(
        """SELECT ort, COUNT(*) n FROM events
           WHERE ort IS NOT NULL AND date >= date('now')
           GROUP BY ort ORDER BY n DESC"""
    ).fetchall()
    kandidaten = []
    for row in rows:
        ort = orte.get(row["ort"])
        if ort is None or ort.get("treffpunkt") or ort.get("adresse") or (ort.get("lat") and ort.get("lon")):
            continue
        kandidaten.append((row["ort"], ort, row["n"]))
    return kandidaten[:limit] if limit else kandidaten


def main():
    args = sys.argv[1:]
    apply_ = "--apply" in args
    args = [a for a in args if a != "--apply"]
    limit = 120
    for a in list(args):
        if a.startswith("--limit"):
            limit = int(a.split("=", 1)[1]) if "=" in a else 0

    orte = Orte.load()
    cache = load_geocode_cache()
    stats = defaultdict(int)
    geaendert = []

    # --- Weg 1: Adresse da, Koordinaten fehlen -> direkt geocodieren -------
    weg1 = [(slug, o) for slug, o in orte.items()
            if o.get("adresse") and not (o.get("lat") and o.get("lon"))]
    print(f"Weg 1 (Adresse da, Koordinaten fehlen): {len(weg1)} Orte\n")
    for slug, ort in weg1:
        lat, lon = geocode(ort["adresse"], cache, stats)
        if lat is not None:
            stats["direkt_geocodiert"] += 1
            geaendert.append((slug, {"lat": lat, "lon": lon, "geo_quelle": "nominatim"}))
        save_geocode_cache(cache)

    # --- Weg 2: weder Adresse noch Koordinaten -> KK-Seite, dann geocode ---
    with db.connect() as conn:
        ziele = ziel_orte(orte, conn, limit)
        all_days = [r[0] for r in conn.execute(
            "SELECT DISTINCT date FROM events ORDER BY date").fetchall()] if ziele else []
    print(f"\nWeg 2 (KK-Ortsseite noetig): {len(ziele)} Orte (Limit {limit or 'kein'})\n")

    urls = harvest_kk_urls(all_days) if ziele else {}
    by_slug = {}
    for roh, url in urls.items():
        slug = orte.lookup(roh)
        if slug:
            by_slug.setdefault(slug, url)

    for slug, ort, n in ziele:
        url = by_slug.get(slug)
        if not url:
            stats["no_url"] += 1
            continue
        html = cached_kk_page(slug, url, stats)
        if html is None:
            continue
        adresse, plz, city, lat, lon = parse_location(html)
        felder = {}
        if adresse:
            felder["adresse"] = adresse
        if lat is not None:
            stats["coord_seite"] += 1
            felder["lat"], felder["lon"], felder["geo_quelle"] = lat, lon, "kk_seite"
        elif plz and city:
            query = adresse or f"{plz} {city}"
            lat, lon = geocode(query, cache, stats)
            if lat is None:
                lat, lon = geocode(f"{clean_ort_name(ort['name'])}, {city}", cache, stats)
            if lat is not None:
                felder["lat"], felder["lon"], felder["geo_quelle"] = lat, lon, "nominatim"
        else:
            stats["no_address"] += 1
        if felder:
            geaendert.append((slug, felder))
        save_geocode_cache(cache)

    print("\n--- Ergebnis ---")
    for k, v in sorted(stats.items()):
        if v:
            print(f"  {k:20s} {v}")
    print(f"\n  {len(geaendert)} Orte wuerden Adresse und/oder Koordinaten bekommen.")
    for slug, felder in geaendert[:15]:
        print(f"    {slug}: {felder}")
    if len(geaendert) > 15:
        print(f"    ... und {len(geaendert) - 15} weitere")

    if not apply_:
        print("\n(ohne --apply nichts geschrieben)")
        return

    for slug, felder in geaendert:
        orte.by_slug[slug].update(felder)
    orte.save()
    print(f"\n{len(geaendert)} Orte in orte/orte.json aktualisiert.")


if __name__ == "__main__":
    main()

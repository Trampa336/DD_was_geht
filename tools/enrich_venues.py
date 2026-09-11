"""Venue-Anreicherung fuer Schema v2 (P4): homepage_url + gecachte Metadaten.

Fuellt die in migrations/001_schema_v2.sql bewusst leer gelassenen Spalten
`homepage_url`, `meta_title`, `meta_description`, `og_image_url`,
`meta_fetched_at` und `meta_status`. Damit bekommt eine Venue-Seite im eigenen
UI ein Cover und einen Beschreibungstext, statt den Besucher auf die
Aggregator-Seite des Kulturkalenders weiterzuschicken.

Der Weg zur offiziellen Homepage in drei Schritten:

  1. TAGESSEITE -> KK-VENUE-URL.  Jeder <address>-Block einer Tagesliste
     verlinkt die Kulturkalender-eigene Venue-Seite (/{ort}/{slug}). EINE
     Tagesseite liefert rund 245 verschiedene Venue-Links - deshalb werden
     hier Tagesseiten geerntet und nicht je Venue eine Event-Seite geholt.
     Das sind ~10 Requests statt ~113 fuer dasselbe Ergebnis.

  2. KK-VENUE-SEITE -> HOMEPAGE.  Auf der Venue-Seite steht genau EIN
     echter auswaertiger Link: die offizielle Homepage des Hauses. "Echt"
     heisst: ohne die Social-Buttons des Kulturkalenders selbst, die auf
     jeder Seite stehen (facebook.com/kukadresden, twitter.com/kukadresden) -
     siehe _CHROME_URLS. Ohne diesen Filter saehe jede Venue-Seite nach drei
     auswaertigen Links aus.

  3. HOMEPAGE -> METADATEN.  Genau ein Request je Haus, und daraus nur
     <title>, meta description und og:image.

Das Cover wird NICHT heruntergeladen - gespeichert wird die URL, das Bild
bleibt heissverlinkt. In der DB landet ausserdem nur eine kurze
Zusammenfassung (Titel/Description gekappt), kein Seiteninhalt.

Tempo: base.REQUEST_DELAY_SECONDS (1,2 s) zwischen ALLEN Requests, auch den
auswaertigen. Das ist die bestehende Hoeflichkeitsbremse der Scraper, hier
unveraendert uebernommen.

Aufruf:
    ../.venv/bin/python tools/enrich_venues.py <db> [--limit N] [--apply]
    (ohne --apply: nur Bericht, nichts geschrieben)

Roh-HTML und Zwischenergebnisse landen in data/venue_cache/ (gitignored),
damit ein zweiter Lauf und die Handpruefung keine neuen Requests kosten.
"""
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3  # noqa: E402

from app.scrapers import base  # noqa: E402

KK_HOST = "kulturkalender-dresden.de"
KK_DAY_URL = "https://www.kulturkalender-dresden.de/heute/{date}"

# Die Social-Buttons des Kulturkalenders selbst. Sie stehen im Footer JEDER
# Seite und sind der Grund, warum eine KK-Venue-Seite auf den ersten Blick
# drei auswaertige Links zu haben scheint statt einem.
_CHROME_URLS = (
    "facebook.com/kukadresden",
    "twitter.com/kukadresden",
    "instagram.com/kukadresden",
)

# Auswaertige Ziele, die zwar echte Links sind, aber keine Haus-Homepage:
# Ticketshops, Karten, Mailto. Werden getrennt gezaehlt, damit der Bericht
# sagen kann, WIE die Annahme bricht, wenn sie bricht.
_NON_HOMEPAGE_HOSTS = (
    "reservix.de", "eventim.de", "ticketmaster.de", "etix.com",
    "google.com", "google.de", "openstreetmap.org", "maps.app.goo.gl",
    "paypal.com", "spotify.com",
    # Video-Einbettungen. youtube-nocookie.com ist der Regelfall auf den
    # KK-Venue-Seiten (Slider-Medien, class="link-event-slider-media") und
    # war der erste Grund, warum "nimm den einzigen auswaertigen Link"
    # gescheitert ist.
    "youtube-nocookie.com", "youtube.com", "youtu.be", "vimeo.com",
)
_SOCIAL_HOSTS = ("facebook.com", "instagram.com", "twitter.com", "x.com")

# Nur eine Zusammenfassung in die DB - kein Seiteninhalt.
MAX_TITLE = 200
MAX_DESCRIPTION = 500

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "venue_cache"


def _clean(text, limit=None):
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return None
    return text[:limit] if limit else text


def _sleep():
    time.sleep(base.REQUEST_DELAY_SECONDS)


def _fetch(url, timeout=15):
    """Wie base.fetch_html, gibt aber die Response zurueck - fuer auswaertige
    Seiten brauchen wir die End-URL (Weiterleitungen) und den Content-Type.
    Kein zweiter Versuch: bei 500 fremden Servern ist ein stiller Fehlschlag
    das richtige Ergebnis, kein Nachbohren."""
    resp = requests.get(url, headers=base.HEADERS, timeout=timeout)
    resp.raise_for_status()
    ctype = (resp.headers.get("content-type") or "").lower()
    if "charset" not in ctype and resp.apparent_encoding:
        resp.encoding = resp.apparent_encoding
    return resp


# --- Schritt 1: Tagesseiten ernten -----------------------------------------

def harvest_venue_urls(days, cache_path):
    """{raw_venue_text: kk_venue_url} aus den <address>-Bloecken der Tageslisten."""
    if cache_path.exists():
        return json.loads(cache_path.read_text("utf-8"))

    found = {}
    for day in days:
        url = KK_DAY_URL.format(date=day)
        try:
            html = base.fetch_html(url)
        except Exception as exc:
            print(f"  [{day}] Fehler: {exc}")
            _sleep()
            continue
        soup = base.make_soup(html)
        new = 0
        for address in soup.find_all("address"):
            link = address.find("a", href=True)
            if not link:
                continue
            text = _clean(address.get_text(" ", strip=True))
            if text and text not in found:
                found[text] = urljoin(url, link["href"].strip())
                new += 1
        print(f"  [{day}] +{new} neu (gesamt {len(found)})")
        _sleep()

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(found, ensure_ascii=False, indent=1), "utf-8")
    return found


# --- Schritt 2: KK-Venue-Seite -> Homepage ---------------------------------

_HOMEPAGE_LABELS = ("homepage", "website", "webseite", "web", "internet",
                    "zur website", "zur homepage")


def _is_domain_label(text, href):
    """Traegt der Link seine eigene Domain als Beschriftung?

    DAS ist die eigentliche Regel. Der Kulturkalender rendert das Feld
    "Homepage" einer Venue als Link, dessen TEXT die blanke Domain ist
    ("zentralwerk.de", "www.skd.museum", "www.dom-zu-meissen.de"). Jeder
    andere auswaertige Link der Seite - Video-Einbettungen, Links aus dem
    Beschreibungstext - ist anders beschriftet.

    Ohne diese Regel ist die Zuordnung nicht eindeutig: die Seite der
    Gemaeldegalerie hat vier auswaertige Links (drei YouTube-Einbettungen und
    einen Link "Besondere Oeffnungs- und Schliesszeiten"), und ein simples
    "nimm den ersten" lieferte dort eine youtube-nocookie-URL als Homepage.
    """
    text = (text or "").strip().lower().rstrip("/")
    if not text or " " in text or "." not in text:
        return False
    host = (urlparse(href).netloc or "").lower()
    return text.replace("www.", "") == host.replace("www.", "")


def classify_outbound(soup):
    """Alle auswaertigen Links einer KK-Venue-Seite, nach Art sortiert.

    Gibt (homepage_kandidaten, social, sonstige) zurueck - getrennt, damit der
    Bericht messen kann, ob Annahme A ("genau ein auswaertiger Link, und der
    ist die Homepage") wirklich traegt. `other` enthaelt auch alles, was zwar
    auswaertig ist, aber sicher keine Haus-Homepage sein kann (Einbettungen,
    Ticketshops) - das ist die Differenz zwischen "ein auswaertiger Link" und
    "ein Homepage-Link"."""
    homepage, social, other = [], [], []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith("http"):
            continue
        host = (urlparse(href).netloc or "").lower().replace("www.", "")
        if KK_HOST in host:
            continue
        if any(chrome in href.lower().replace("www.", "") for chrome in _CHROME_URLS):
            continue
        if href in seen:
            continue
        seen.add(href)

        label = a.get_text(" ", strip=True)
        if any(h in host for h in _SOCIAL_HOSTS):
            social.append(href)
        elif any(h in host for h in _NON_HOMEPAGE_HOSTS):
            other.append(href)
        elif _is_domain_label(label, href):
            homepage.append(href)
        elif label.lower() in _HOMEPAGE_LABELS:
            homepage.append(href)
        else:
            other.append(href)
    return homepage, social, other


def extract_kk_cover(soup):
    """Das Haus-Foto von der KK-Venue-Seite.

    Der eigentliche Fund dieses Pakets: die Homepages der Haeuser liefern KEIN
    og:image (gemessen, siehe Bericht) - die KK-Venue-Seite dagegen traegt ganz
    oben einen Medien-Slider, dessen erstes Bild das Haus selbst zeigt. Das
    alt-Attribut ist der Venue-Name samt Copyright ("Schloss Wackerbarth (c)
    Wackerbarth"), es ist also wirklich das Haus und nicht ein Event-Plakat.

    srcset ist nach Breite absteigend sortiert - erster Eintrag = groesste
    Variante (dieselbe Regel wie in scrapers/kulturkalender._extract_image).
    Das Bild wird NICHT heruntergeladen, nur die URL gespeichert.
    """
    img = soup.select_one(".glide__slides img") or soup.select_one("img.media")
    if img is None:
        return None, None
    alt = _clean(img.get("alt"), MAX_TITLE)
    srcset = img.get("srcset")
    if srcset:
        first = srcset.split(",")[0].strip().split(" ")[0]
        if first:
            return first, alt
    return img.get("src"), alt


def resolve_homepage(kk_url):
    """-> dict(status, homepage_url, n_homepage, n_social, n_other)."""
    try:
        resp = _fetch(kk_url)
    except Exception as exc:
        return {"status": f"error:kk:{type(exc).__name__}", "homepage_url": None}
    soup = base.make_soup(resp.text)
    homepage, social, other = classify_outbound(soup)
    cover, cover_alt = extract_kk_cover(soup)
    result = {
        "n_homepage": len(homepage),
        "n_social": len(social),
        "n_other": len(other),
        "all_homepage": homepage,
        "all_social": social,
        "all_other": other,
        "kk_cover_url": cover,
        "kk_cover_alt": cover_alt,
    }
    if homepage:
        result["homepage_url"] = homepage[0]
        result["status"] = "ok" if len(homepage) == 1 else "ok_mehrdeutig"
    elif social:
        # Kein eigener Auftritt, aber eine Facebook-Seite - als Homepage
        # unbrauchbar (kein og:image ohne Login), also nicht eintragen.
        result["homepage_url"] = None
        result["status"] = "nur_social"
    else:
        result["homepage_url"] = None
        result["status"] = "not_found"
    return result


# --- Schritt 3: Homepage -> Metadaten --------------------------------------

def extract_meta(html, final_url):
    soup = base.make_soup(html)

    title = None
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get("content"):
        title = _clean(og_title["content"], MAX_TITLE)
    if not title and soup.title:
        title = _clean(soup.title.get_text(), MAX_TITLE)

    description = None
    for sel in ('meta[property="og:description"]', 'meta[name="description"]'):
        meta = soup.select_one(sel)
        if meta and meta.get("content"):
            description = _clean(meta["content"], MAX_DESCRIPTION)
            if description:
                break

    image = None
    for sel in ('meta[property="og:image"]', 'meta[name="twitter:image"]'):
        meta = soup.select_one(sel)
        if meta and meta.get("content"):
            # Relative og:image kommen vor - gegen die End-URL aufloesen,
            # sonst steht ein unbrauchbares "/img/cover.jpg" in der DB.
            image = urljoin(final_url, _clean(meta["content"]))
            break

    return {"meta_title": title, "meta_description": description,
            "og_image_url": image}


def fetch_meta(homepage_url):
    try:
        resp = _fetch(homepage_url, timeout=12)
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "?"
        return {"status": f"error:http:{code}"}
    except Exception as exc:
        return {"status": f"error:{type(exc).__name__}"}

    ctype = (resp.headers.get("content-type") or "").lower()
    if "html" not in ctype:
        return {"status": f"error:ctype:{ctype.split(';')[0][:20]}"}

    meta = extract_meta(resp.text, resp.url)
    meta["status"] = "ok"
    meta["final_url"] = resp.url
    meta["html_len"] = len(resp.text)
    return meta


# --- Ablauf ----------------------------------------------------------------

def target_venues(conn, limit):
    """Venues nach Eventzahl absteigend - der Kopf des Katalogs zuerst."""
    return conn.execute(
        """SELECT v.id, v.slug, v.name, v.kind, COUNT(e.uid) AS n
           FROM venues v JOIN events e ON e.venue_id = v.id
           GROUP BY v.id ORDER BY n DESC LIMIT ?""", (limit,)).fetchall()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    limit = 120
    for a in sys.argv[1:]:
        if a.startswith("--limit"):
            limit = int(a.split("=", 1)[1])
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)

    conn = sqlite3.connect(args[0])
    conn.row_factory = sqlite3.Row
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Schritt 1
    days = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM events ORDER BY date").fetchall()]
    days = days[::3][:12]          # jeder dritte Tag reicht fuer die Abdeckung
    print(f"Schritt 1: KK-Venue-Links aus {len(days)} Tagesseiten ernten ...")
    venue_urls = harvest_venue_urls(days, CACHE_DIR / "kk_venue_urls.json")
    print(f"-> {len(venue_urls)} Rohstrings mit KK-Venue-Link.\n")

    # Rohstring -> venue_id ueber die Alias-Tabelle (dieselbe Kollaps-Regel
    # wie im Schreibpfad, keine zweite Zuordnung).
    alias = {r["raw_venue"]: r["venue_id"] for r in
             conn.execute("SELECT raw_venue, venue_id FROM venue_aliases")}
    by_venue = {}
    for raw, url in venue_urls.items():
        vid = alias.get(raw)
        if vid is not None:
            by_venue.setdefault(vid, url)

    venues = target_venues(conn, limit)
    print(f"Schritt 2+3: {len(venues)} Venues (Top {limit} nach Eventzahl).")
    matched = [v for v in venues if v["id"] in by_venue]
    print(f"-> {len(matched)} davon haben einen KK-Venue-Link, "
          f"{len(venues) - len(matched)} nicht.\n")

    results_path = CACHE_DIR / "enrichment.json"
    results = json.loads(results_path.read_text("utf-8")) if results_path.exists() else {}

    now = datetime.utcnow().isoformat()
    for i, v in enumerate(venues, 1):
        key = str(v["id"])
        if key in results:
            continue
        kk_url = by_venue.get(v["id"])
        if not kk_url:
            results[key] = {"name": v["name"], "n": v["n"], "kind": v["kind"],
                            "status": "kein_kk_link"}
            continue

        rec = {"name": v["name"], "n": v["n"], "kind": v["kind"], "kk_url": kk_url}
        step2 = resolve_homepage(kk_url)
        _sleep()
        rec.update(step2)

        if step2.get("homepage_url"):
            step3 = fetch_meta(step2["homepage_url"])
            _sleep()
            rec["meta"] = step3
            if step3.get("status") != "ok":
                rec["status"] = step3["status"]
        results[key] = rec
        print(f"  [{i:3}/{len(venues)}] {v['name'][:38]:38} {rec['status']:16} "
              f"{(step2.get('homepage_url') or '-')[:45]}")
        results_path.write_text(json.dumps(results, ensure_ascii=False, indent=1), "utf-8")

    results_path.write_text(json.dumps(results, ensure_ascii=False, indent=1), "utf-8")

    # --- Schreiben ---
    written = 0
    for key, rec in results.items():
        meta = rec.get("meta") or {}
        status = rec.get("status", "error:unbekannt")
        if rec.get("homepage_url") and meta.get("status") == "ok":
            db_status = "ok"
        elif status in ("not_found", "nur_social", "kein_kk_link"):
            db_status = "not_found"
        else:
            db_status = f"error:{status}"[:60]

        # Cover: die KK-Venue-Seite zuerst. Das ist NICHT die urspruenglich
        # geplante Reihenfolge - der Plan war og:image der Haus-Homepage, aber
        # die liefern praktisch nie eins (siehe extract_kk_cover). Das
        # og:image bleibt als zweite Wahl stehen, damit ein Haus, das doch
        # eins hat, sein eigenes Bild zeigt statt des KK-Fotos.
        cover = rec.get("kk_cover_url") or meta.get("og_image_url")

        conn.execute(
            """UPDATE venues SET homepage_url = ?, meta_title = ?,
                   meta_description = ?, og_image_url = ?, meta_fetched_at = ?,
                   meta_status = ? WHERE id = ?""",
            (rec.get("homepage_url"), meta.get("meta_title"),
             meta.get("meta_description"), cover,
             now, db_status, int(key)))
        written += 1

    if apply:
        conn.commit()
        print(f"\n{written} Venue-Zeilen geschrieben und committed.")
    else:
        conn.rollback()
        print(f"\n{written} Zeilen vorbereitet, nichts geschrieben (Probelauf).")
    conn.close()


if __name__ == "__main__":
    main()

"""Homepage, Cover und Kurzbeschreibung fuer Orte - ueber die Kulturkalender-
Ortsseite und die Homepage selbst.

Umgestellt von der alten v2-Datenbank (venues-Tabelle) auf orte/orte.json,
genau wie fetch_venue_locations.py. Fuellt drei Felder, alle nur wenn leer -
Kuratiertes bleibt Davids:

    homepage      die offizielle Seite des Hauses
    cover         ein Foto des Hauses (Medien-Slider der KK-Ortsseite, sonst
                  das og:image der Homepage)
    beschreibung  kurze Zusammenfassung von der Homepage (og:description /
                  meta description) - gescrapter Text, kein Erfinden
                  (CLAUDE.md-Regel "Nichts erfinden")

Der Weg in drei Schritten (unveraendert gegenueber v2):

  1. TAGESSEITE -> KK-ORTSSEITE.  Jeder <address>-Block einer Tagesliste
     verlinkt die Kulturkalender-eigene Ortsseite. Gemeinsamer Cache mit
     fetch_venue_locations.py (cache/venue_cache/kk_venue_urls.json) - ein
     Ort wird nur einmal geerntet, egal welches Werkzeug zuerst laeuft.
  2. KK-ORTSSEITE -> HOMEPAGE.  Genau EIN echter auswaertiger Link zaehlt:
     der, dessen Text die eigene Domain traegt ("zentralwerk.de"). Social-
     Buttons des Kulturkalenders, Ticketshops und Video-Einbettungen fliegen
     raus (siehe classify_outbound).
  3. HOMEPAGE -> METADATEN.  Genau ein Request je Haus: <title>/og:title,
     meta description, og:image.

Cover-Reihenfolge: KK-Ortsseite zuerst (fast immer vorhanden), og:image der
Homepage als zweite Wahl.

Ziel-Reihenfolge: Orte ohne Homepage, meiste anstehende Events zuerst, aus
cache/events.db (Proxmox-Ordner-Hinweis siehe fetch_venue_locations.py).

Tempo: ddwg.quellen.base.REQUEST_DELAY_SECONDS (1,2 s) zwischen ALLEN
Requests, auch den auswaertigen.

Aufruf:
    python werkzeuge/enrich_venues.py [--limit N] [--apply]
    (ohne --apply: nur Bericht, nichts geschrieben. Default-Limit 120.)
"""
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ddwg import db  # noqa: E402
from ddwg.orte import Orte  # noqa: E402
from ddwg.quellen import base as qbase  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "venue_cache"
PAGE_DIR = CACHE_DIR / "kk_seiten"
KK_URLS_CACHE = CACHE_DIR / "kk_venue_urls.json"
KK_DAY_URL = "https://www.kulturkalender-dresden.de/heute/{date}"
KK_HOST = "kulturkalender-dresden.de"

# Die Social-Buttons des Kulturkalenders selbst - stehen im Footer JEDER
# Seite und sind der Grund, warum eine KK-Ortsseite auf den ersten Blick
# drei auswaertige Links zu haben scheint statt einem.
_CHROME_URLS = (
    "facebook.com/kukadresden", "twitter.com/kukadresden", "instagram.com/kukadresden",
)
# Auswaertige Ziele, die zwar echte Links sind, aber keine Haus-Homepage.
_NON_HOMEPAGE_HOSTS = (
    "reservix.de", "eventim.de", "ticketmaster.de", "etix.com",
    "google.com", "google.de", "openstreetmap.org", "maps.app.goo.gl",
    "paypal.com", "spotify.com",
    "youtube-nocookie.com", "youtube.com", "youtu.be", "vimeo.com",
)
_SOCIAL_HOSTS = ("facebook.com", "instagram.com", "twitter.com", "x.com")
_HOMEPAGE_LABELS = ("homepage", "website", "webseite", "web", "internet",
                    "zur website", "zur homepage")

MAX_BESCHREIBUNG = 500


def _clean(text, limit=None):
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return None
    return text[:limit] if limit else text


def _fetch(url, timeout=15):
    resp = requests.get(url, headers=qbase.HEADERS, timeout=timeout)
    resp.raise_for_status()
    ctype = (resp.headers.get("content-type") or "").lower()
    if "charset" not in ctype and resp.apparent_encoding:
        resp.encoding = resp.apparent_encoding
    return resp


def harvest_kk_urls(days):
    """Wie in fetch_venue_locations.py - gemeinsamer Cache, siehe dort."""
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
            text = _clean(address.get_text(" ", strip=True))
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


def _is_domain_label(text, href):
    """Traegt der Link seine eigene Domain als Beschriftung? Das ist die
    eigentliche Regel - siehe Modul-Docstring."""
    text = (text or "").strip().lower().rstrip("/")
    if not text or " " in text or "." not in text:
        return False
    host = (urlparse(href).netloc or "").lower()
    return text.replace("www.", "") == host.replace("www.", "")


def classify_outbound(soup):
    """Alle auswaertigen Links einer KK-Ortsseite, nach Art sortiert:
    (homepage_kandidaten, social, sonstige)."""
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
    """Das Haus-Foto von der KK-Ortsseite: oben ein Medien-Slider, dessen
    erstes Bild das Haus selbst zeigt (nicht heruntergeladen, nur die URL)."""
    img = soup.select_one(".glide__slides img") or soup.select_one("img.media")
    if img is None:
        return None
    srcset = img.get("srcset")
    if srcset:
        first = srcset.split(",")[0].strip().split(" ")[0]
        if first:
            return first
    return img.get("src")


def resolve_homepage(html):
    soup = qbase.make_soup(html)
    homepage, social, other = classify_outbound(soup)
    cover = extract_kk_cover(soup)
    if homepage:
        return homepage[0], cover, "ok" if len(homepage) == 1 else "ok_mehrdeutig"
    if social:
        return None, cover, "nur_social"
    return None, cover, "not_found"


def extract_meta(html, final_url):
    soup = qbase.make_soup(html)
    title = None
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get("content"):
        title = _clean(og_title["content"])
    if not title and soup.title:
        title = _clean(soup.title.get_text())

    beschreibung = None
    for sel in ('meta[property="og:description"]', 'meta[name="description"]'):
        meta = soup.select_one(sel)
        if meta and meta.get("content"):
            beschreibung = _clean(meta["content"], MAX_BESCHREIBUNG)
            if beschreibung:
                break

    bild = None
    for sel in ('meta[property="og:image"]', 'meta[name="twitter:image"]'):
        meta = soup.select_one(sel)
        if meta and meta.get("content"):
            bild = urljoin(final_url, _clean(meta["content"]))
            break

    return title, beschreibung, bild


def fetch_meta(homepage_url, stats):
    try:
        resp = _fetch(homepage_url, timeout=12)
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "?"
        stats[f"meta_fehler_http_{code}"] += 1
        return None, None, None
    except Exception as exc:  # noqa: BLE001
        stats["meta_fehler"] += 1
        print(f"    META-FAIL {homepage_url[:50]}: {str(exc)[:50]}")
        return None, None, None
    ctype = (resp.headers.get("content-type") or "").lower()
    if "html" not in ctype:
        stats["meta_kein_html"] += 1
        return None, None, None
    stats["meta_ok"] += 1
    return extract_meta(resp.text, resp.url)


def ziel_orte(orte, conn, limit):
    """Orte ohne Homepage, meiste anstehende Events zuerst. Treffpunkte
    (kein Haus) werden uebersprungen."""
    rows = conn.execute(
        """SELECT ort, COUNT(*) n FROM events
           WHERE ort IS NOT NULL AND date >= date('now')
           GROUP BY ort ORDER BY n DESC"""
    ).fetchall()
    kandidaten = []
    for row in rows:
        ort = orte.get(row["ort"])
        if ort is None or ort.get("treffpunkt") or ort.get("homepage"):
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
    with db.connect() as conn:
        ziele = ziel_orte(orte, conn, limit)
        all_days = [r[0] for r in conn.execute(
            "SELECT DISTINCT date FROM events ORDER BY date").fetchall()] if ziele else []

    print(f"{len(ziele)} Orte ohne Homepage (Limit {limit or 'kein'})\n")
    urls = harvest_kk_urls(all_days) if ziele else {}
    by_slug = {}
    for roh, url in urls.items():
        slug = orte.lookup(roh)
        if slug:
            by_slug.setdefault(slug, url)

    stats = defaultdict(int)
    geaendert = []
    for slug, ort, n in ziele:
        url = by_slug.get(slug)
        if not url:
            stats["kein_kk_link"] += 1
            continue
        html = cached_kk_page(slug, url, stats)
        if html is None:
            continue
        homepage, cover, status = resolve_homepage(html)
        stats[status] += 1
        felder = {}
        if cover and not ort.get("cover"):
            felder["cover"] = cover
        if homepage:
            felder["homepage"] = homepage
            title, beschreibung, og_bild = fetch_meta(homepage, stats)
            time.sleep(qbase.REQUEST_DELAY_SECONDS)
            if og_bild and "cover" not in felder and not ort.get("cover"):
                felder["cover"] = og_bild
            if beschreibung and not ort.get("beschreibung"):
                felder["beschreibung"] = beschreibung
        if felder:
            geaendert.append((slug, felder))

    print("\n--- Ergebnis ---")
    for k, v in sorted(stats.items()):
        if v:
            print(f"  {k:20s} {v}")
    print(f"\n  {len(geaendert)} Orte wuerden Homepage/Cover/Beschreibung bekommen.")
    for slug, felder in geaendert[:15]:
        kurz = {k: (v[:60] + "..." if isinstance(v, str) and len(v) > 60 else v) for k, v in felder.items()}
        print(f"    {slug}: {kurz}")
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

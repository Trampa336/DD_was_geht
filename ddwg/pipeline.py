"""Der Ablauf: Quellen holen -> listings -> Gruppen -> Events -> Ausgabe.

    scrape()    holt alle (oder ausgewaehlte) Quellen, ordnet jede Zeile einem
                Ort aus orte/orte.json zu, verwirft Region "weiter" und
                ersetzt die listings der Quelle. Danach build() und - fuer die
                Herz-Orte - das Nachladen fehlender Beschreibungen.
    build()     baut die Tabelle events komplett neu aus den listings.

Beides laeuft ohne Server, einmal aufgerufen und fertig (python -m ddwg).
"""
import importlib
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from . import db, dedup, geo, merge, quellen
from .orte import Orte
from .quellen import base, detail_fetch

logger = logging.getLogger("ddwg")

# So viele Tage voraus wird gescrapt.
TAGE_VORAUS = 31

# Ab so vielen verschiedenen Tagen mit demselben Titel gilt ein Eintrag als
# Dauerangebot (Ausstellung, taegliche Fuehrung) und rutscht in der Ausgabe
# nach hinten.
LAUFEND_AB_TAGEN = 7

# Detailseiten nachladen: nur fuer Events an Herz-Orten, nur Kulturkalender
# (dort fehlt die Beschreibung in 98 % der Zeilen - rauze und die Seiten der
# Haeuser liefern sie schon in der Liste mit), hoechstens so viele je Lauf.
DETAIL_MAX_JE_LAUF = 120
DETAIL_HOSTS = ("kulturkalender-dresden.de",)


def _jetzt():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- scrape ----------------------------------------------------------------

def scrape(tage=TAGE_VORAUS, nur=None, details=True, heute=None, orte=None, conn=None):
    heute = heute or date.today()
    ende = heute + timedelta(days=tage)
    orte = orte or Orte.load()
    if conn is None:
        with db.connect() as conn:
            return scrape(tage, nur, details, heute, orte, conn)

    for slug in quellen.slugs():
        if nur and slug not in nur:
            continue
        scrape_quelle(conn, orte, slug, heute, ende)
        conn.commit()

    if orte.neu:
        logger.info("%d neue Orte in orte/orte.json: %s", len(orte.neu), ", ".join(orte.neu[:15])
                    + (" ..." if len(orte.neu) > 15 else ""))
    orte.save()

    anzahl = build(conn, orte, heute)
    if details:
        if details_nachladen(conn, orte, heute):
            anzahl = build(conn, orte, heute)
    return anzahl


def scrape_quelle(conn, orte, slug, heute, ende, module=None):
    """Eine Quelle holen und ihre listings ersetzen.

    Der gefaehrliche Fall ist nicht die Exception, sondern der stille
    Nulltreffer: aendert eine Quelle ihr HTML, parst der Scraper 0 Events und
    meldet keinen Fehler. Nur der Vergleich mit dem letzten erfolgreichen Lauf
    macht daraus ein Signal - so ein Lauf gilt als NICHT erfolgreich, und die
    alten listings bleiben stehen."""
    name = quellen.name(slug)
    started = _jetzt()
    try:
        module = module or importlib.import_module(f".quellen.{slug}", package="ddwg")
        found = module.scrape_range(heute, ende)
    except Exception as exc:
        logger.exception("%s fehlgeschlagen - alte Einträge bleiben stehen.", name)
        db.record_run(conn, slug, started, _jetzt(), ok=False, error=repr(exc))
        return None

    previous = db.last_ok_run(conn, slug)
    if not found and previous and previous["event_count"]:
        error = f"0 Events, zuletzt waren es {previous['event_count']}."
        logger.warning("%s: %s Hat sich das HTML geändert? Alte Einträge bleiben stehen.", name, error)
        db.record_run(conn, slug, started, _jetzt(), ok=False, event_count=0, error=error)
        return None

    rows, dropped = listing_rows(found, orte, heute)
    db.replace_listings(conn, slug, rows)
    db.record_run(conn, slug, started, _jetzt(), ok=True, event_count=len(found), dropped=dropped)
    logger.info("%s: %d Einträge, %d davon 'weiter weg' verworfen.", name, len(found), dropped)
    return len(rows)


def listing_rows(found, orte, heute):
    """Scraper-dicts -> listings-Zeilen. Region "weiter" wird verworfen."""
    scraped_at = _jetzt()
    rows, dropped = [], 0
    for ev in found:
        raw_venue = (ev.get("venue") or "").strip() or None
        ort = orte.resolve(raw_venue, heute)
        region = (orte[ort].get("region") if ort else None) or geo.classify_region(raw_venue)
        if region == geo.REGION_WEITER:
            dropped += 1
            continue
        rows.append({
            "source": ev["source"],
            "uid": ev["uid"],
            "date": ev["date"],
            "time": ev.get("time"),
            "title": ev["title"],
            "ort": ort,
            "ort_roh": raw_venue,
            "category": ev.get("category"),
            "raw_category": ev.get("raw_category"),
            "url": ev.get("url"),
            "image_url": ev.get("image_url"),
            "description": ev.get("description"),
            "price_text": ev.get("price_text"),
            "scraped_at": scraped_at,
        })
    return rows, dropped


# --- build -----------------------------------------------------------------

def build(conn, orte, heute=None):
    """events komplett neu aus den listings ab heute bauen. Gibt die Anzahl zurueck."""
    heute = heute or date.today()
    items = []
    for row in db.listings(conn, heute.isoformat()):
        item = dict(row)
        item["event_uid"] = row["uid"]
        item["uid"] = str(row["id"])
        ort = orte.get(row["ort"]) if row["ort"] else None
        # Der kanonische Name des Ortes, damit die Doppelungs-Erkennung
        # "Bunker Straße E" und "Strasse E (Reithalle, Bunker)" als denselben
        # Ort sieht. Platzhalter-Orte heissen weiter wie ihr Platzhalter und
        # bleiben damit "unbekannt".
        item["venue"] = ort["name"] if ort else row["ort_roh"]
        items.append(item)

    detail = db.details(conn)
    out, seen = [], set()
    for members in dedup.cluster(items):
        ev = merge.merge(members, detail)
        uid, n = ev["uid"], 2
        while uid in seen:
            uid, n = f"{ev['uid']}-{n}", n + 1
        ev["uid"] = uid
        seen.add(uid)
        ort = orte.get(ev["ort"]) if ev["ort"] else None
        ev["region"] = (ort or {}).get("region") or geo.classify_region(ev["ort_roh"])
        out.append((ev, [int(m["uid"]) for m in members]))

    _kategorie_vom_ort(out, orte)
    _laufend(out)
    db.replace_events(conn, out)
    logger.info("%d Einträge -> %d Events.", len(items), len(out))
    return len(out)


def _kategorie_vom_ort(out, orte):
    """Stufe 3 der Kategorie-Vergabe: ein Ort mit gepflegter Art, dessen Events
    sich auf GENAU EINE echte Kategorie einigen, vererbt sie an seine
    'sonstiges'-Events. Ein Ort, der mehrere Dinge macht, vererbt nichts -
    'sonstiges' ist eine ehrliche Antwort, eine geratene Kategorie nicht."""
    seen = defaultdict(set)
    for ev, _ids in out:
        ort = orte.get(ev["ort"]) if ev["ort"] else None
        if ort and ort.get("art") and ev["category"] != "sonstiges":
            seen[ev["ort"]].add(ev["category"])
    for ev, _ids in out:
        cats = seen.get(ev["ort"])
        if ev["category"] == "sonstiges" and cats and len(cats) == 1:
            ev["category"] = next(iter(cats))


def _laufend(out):
    days = defaultdict(set)
    for ev, _ids in out:
        days[(ev["title"], ev["ort"])].add(ev["date"])
    for ev, _ids in out:
        ev["laufend"] = 1 if len(days[(ev["title"], ev["ort"])]) >= LAUFEND_AB_TAGEN else 0


# --- Detailseiten ----------------------------------------------------------

def details_nachladen(conn, orte, heute, fetch=detail_fetch.fetch_detail, limit=DETAIL_MAX_JE_LAUF):
    """Fehlende Beschreibungen fuer Events an Herz-Orten von der Detailseite holen."""
    herz = set(orte.herz_orte())
    if not herz:
        return 0
    known = db.details(conn)
    candidates = [
        ev for ev in db.events(conn, heute.isoformat())
        if ev["ort"] in herz and not ev["description"] and ev["url"]
        and ev["url"] not in known and any(h in ev["url"] for h in DETAIL_HOSTS)
    ][:limit]
    for ev in candidates:
        result = fetch({"url": ev["url"], "source": "kulturkalender"})
        desc = result.get("description")
        if desc == detail_fetch.FALLBACK_DESCRIPTION:
            desc = None
        db.save_detail(conn, ev["url"], desc, result.get("price_text"),
                       result.get("image_url"), _jetzt())
        conn.commit()
        base.time_module.sleep(base.REQUEST_DELAY_SECONDS)
    if candidates:
        logger.info("%d Detailseiten für Herz-Orte nachgeladen.", len(candidates))
    return len(candidates)

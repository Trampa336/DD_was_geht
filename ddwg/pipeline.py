"""Der Ablauf: Quellen holen -> listings -> Gruppen -> Events -> Ausgabe.

    scrape()    holt alle (oder ausgewaehlte) Quellen, verwirft Fuehrungen,
                ordnet jede Zeile einem Ort aus orte/orte.json zu, verwirft
                Region "weiter" und ersetzt die listings der Quelle. Danach
                build() und das Nachladen fehlender Beschreibungen.
    build()     baut die Tabelle events komplett neu aus den listings und
                verwirft dabei Fuehrungen (VERWORFENE_KATEGORIEN) und alles,
                was ddwg/aussortieren.py aussortiert (Hotels, Familie ...).

Beides laeuft ohne Server, einmal aufgerufen und fertig (python -m ddwg).
"""
import importlib
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from . import aussortieren, db, dedup, geo, merge, quellen
from .orte import Orte
from .quellen import base, detail_fetch

logger = logging.getLogger("ddwg")

# Kategorien, die gar nicht erst auf die Seite kommen (Davids Entscheidung vom
# 29.09.2026): Fuehrungen aller Art - Stadt-, Museums-, Schiffs- und
# Familienfuehrungen. Erkannt werden sie weiter (normalize), damit sie sauber
# herausfallen. Zweimal verworfen: schon beim Einlesen (listing_rows), damit
# fuer Fuehrungen keine Treffpunkt-Orte in orte.json entstehen, und noch
# einmal in build() nach der Kategorie-Vergabe ueber den Ort (Stufe 3), sonst
# rutschte eine dort vererbte Fuehrung durch.
VERWORFENE_KATEGORIEN = {"fuehrungen"}

# Kategorien, die ein Ort nie an seine 'sonstiges'-Termine weitergibt (Stufe 3):
# Eine Demo ist ein einzelnes Ereignis, keine Eigenschaft des Platzes.
NICHT_VERERBEN = ("demo",)

# So viele Tage voraus wird gescrapt.
TAGE_VORAUS = 31

# Ab so vielen verschiedenen Tagen mit demselben Titel gilt ein Eintrag als
# Dauerangebot (Ausstellung, taegliche Fuehrung) und rutscht in der Ausgabe
# nach hinten.
LAUFEND_AB_TAGEN = 7

# Detailseiten nachladen: fuer alle Events ohne Beschreibung, nur Kulturkalender
# (dort fehlt die Beschreibung in 98 % der Zeilen - rauze und die Seiten der
# Haeuser liefern sie schon in der Liste mit), naechste Tage zuerst, jede Seite
# nur einmal. Die Ergebnisse bleiben in der Tabelle details; GitHub Actions
# behaelt cache/events.db von Lauf zu Lauf (actions/cache in publish.yml), so
# kommen nach dem ersten Lauf taeglich nur neue Termine dazu. Gemessen am
# 29.09.2026: 2.331 Events mit Kulturkalender-Seite ohne Beschreibung - der
# Deckel liegt knapp darueber, der erste Lauf dauert bei 1,2 s Pause ~45 min.
DETAIL_MAX_JE_LAUF = 2500
# So viele Fehlschlaege in Folge, dann bricht das Nachladen ab: Ist die Seite
# ganz weg, wartete der Lauf sonst 2.500 x 8 s Timeout.
DETAIL_ABBRUCH_NACH_FEHLERN = 20
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
    logger.info("%s: %d Einträge, %d davon verworfen (Führung oder weiter weg).", name, len(found), dropped)
    return len(rows)


def listing_rows(found, orte, heute):
    """Scraper-dicts -> listings-Zeilen. Fuehrungen und Region "weiter" werden
    verworfen, bevor ein neuer Ort entsteht bzw. danach."""
    scraped_at = _jetzt()
    rows, dropped = [], 0
    for ev in found:
        if ev.get("category") in VERWORFENE_KATEGORIEN:
            dropped += 1
            continue
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
    vorher = len(out)
    out = [(ev, ids) for ev, ids in out if ev["category"] not in VERWORFENE_KATEGORIEN]
    fuehrungen = vorher - len(out)
    out, aussortiert = _aussortieren(out, orte)
    _laufend(out)
    db.replace_events(conn, out)
    logger.info("%d Einträge -> %d Events (%d Führungen verworfen, aussortiert: %s).",
                len(items), len(out), fuehrungen,
                ", ".join(f"{g} {n}" for g, n in sorted(aussortiert.items())) or "nichts")
    return len(out)


def _aussortieren(out, orte):
    """Termine, die David nie sehen will (siehe ddwg/aussortieren.py), fliegen
    raus. Gibt (verbliebene, {grund: anzahl}) zurueck."""
    flavours = aussortieren.flavour_von_ort()
    bleibt, zaehler = [], defaultdict(int)
    for ev, ids in out:
        ort = (orte.get(ev["ort"]) if ev["ort"] else None) or {"name": ev.get("ort_roh")}
        grund = aussortieren.grund(ev["title"], ev["category"], ev["ort"], ort, flavours)
        if grund:
            zaehler[grund.split(":")[0]] += 1
        else:
            bleibt.append((ev, ids))
    return bleibt, dict(zaehler)


def _kategorie_vom_ort(out, orte):
    """Stufe 3 der Kategorie-Vergabe: ein Ort mit gepflegter Art, dessen Events
    sich auf GENAU EINE echte Kategorie einigen, vererbt sie an seine
    'sonstiges'-Events. Ein Ort, der mehrere Dinge macht, vererbt nichts -
    'sonstiges' ist eine ehrliche Antwort, eine geratene Kategorie nicht.
    Demos zaehlen dabei nicht (NICHT_VERERBEN): Eine Menschenkette auf dem
    Schlossplatz machte sonst die Schnitzeljagd dort zur Demo (30.09.2026)."""
    seen = defaultdict(set)
    for ev, _ids in out:
        ort = orte.get(ev["ort"]) if ev["ort"] else None
        if ort and ort.get("art") and ev["category"] not in ("sonstiges",) + NICHT_VERERBEN:
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
    """Fehlende Beschreibungen von der Detailseite holen (siehe DETAIL_MAX_JE_LAUF).
    db.events liefert nach Datum sortiert, also kommen die naechsten Tage zuerst.
    Eine Ausstellung steht an vielen Tagen mit derselben Seite - die wird nur
    einmal geholt. Seiten ohne Text bleiben in details (leer) und werden nicht
    erneut abgefragt."""
    known = db.details(conn)
    # Kulturkalender-Seite je Termin, auch wenn der Hauptlink zur Seite des Orts führt
    kk_url = {}
    for uid, url in conn.execute(
            "SELECT el.uid, l.url FROM event_listings el JOIN listings l ON l.id = el.listing_id "
            "WHERE l.url IS NOT NULL"):
        if any(h in url for h in DETAIL_HOSTS):
            kk_url.setdefault(uid, url)
    urls = []
    for ev in db.events(conn, heute.isoformat()):
        # ohne Beschreibung oder nur eine Kurzzeile (seit 02.10.2026)
        if not merge.ist_kurz(ev["description"]):
            continue
        url = ev["url"] if ev["url"] and any(h in ev["url"] for h in DETAIL_HOSTS) else kk_url.get(ev["uid"])
        if url and url not in known and url not in urls:
            urls.append(url)
    candidates = urls[:limit]
    gespeichert = fehler = in_folge = 0
    for url in candidates:
        if in_folge >= DETAIL_ABBRUCH_NACH_FEHLERN:
            logger.warning("Detailseiten: %d Fehlschläge in Folge, Abbruch für diesen Lauf.", in_folge)
            break
        result = fetch({"url": url, "source": "kulturkalender"})
        base.time_module.sleep(base.REQUEST_DELAY_SECONDS)
        if not result.get("ok"):
            fehler += 1   # Netzfehler: nicht merken, der naechste Lauf versucht es wieder
            in_folge += 1
            continue
        in_folge = 0
        desc = result.get("description")
        if desc == detail_fetch.FALLBACK_DESCRIPTION:
            desc = None
        db.save_detail(conn, url, desc, result.get("price_text"),
                       result.get("image_url"), _jetzt())
        conn.commit()
        gespeichert += 1
    if candidates:
        logger.info("Detailseiten: %d gespeichert, %d fehlgeschlagen, %d noch offen.",
                    gespeichert, fehler, len(urls) - gespeichert)
    return gespeichert

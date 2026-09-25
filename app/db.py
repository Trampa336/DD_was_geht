"""SQLite-Zugriff: Schema, Events speichern/lesen, Herzen verbuchen.

Seit P3 (Schema v2, siehe migrations/001_schema_v2.sql + migrations/CUTOVER.md):
Venues und Kategorien sind erstklassige Zeilen statt Freitext-Spalten. Es gibt
KEINE Migration aus v1 - eine neue DB startet leer und wird von den Scrapern
neu gefuellt (siehe CUTOVER.md). Die 10 Scraper selbst liefern unveraendert
Dicts mit Freitext-`venue`/`category`; die Aufloesung passiert ausschliesslich
hier in upsert_events()."""
import hashlib
import json
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from . import config, geo, normalize

logger = logging.getLogger("dd-was-geht.db")

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
SCHEMA_V2_PATH = _MIGRATIONS_DIR / "001_schema_v2.sql"

# P5c: `reactions` ist abgeloest. P3 hatte die Tabelle als Zusatz stehen
# lassen, weil P2s DDL sie bewusst weglaesst ("wird von Herzen abgeloest",
# Abschnitt 6) die Herzen aber noch nicht gebaut waren - ein Loeschen haette
# David's 👍/👎 ersatzlos entfernt. Der Ersatz existiert jetzt (hearts +
# /api/herz + scoring.apply_heart), also faellt der Zusatz weg: eine neue DB
# bekommt `reactions` gar nicht erst, eine bestehende raeumt _retire_reactions()
# auf.

# Spalten, die P5c an `hearts` nachruestet, falls die DB noch auf dem Stand von
# P2/P3 ist. Gleiches Muster wie tools/load_enrichment.py._ensure_columns():
# idempotent ueber PRAGMA table_info, weil Schema v2 laut CUTOVER.md keinen
# Migrationsweg kennt. Beide mit DEFAULT, sonst lehnt SQLite ADD COLUMN NOT
# NULL ab.
# Spalten fuer die Kartenansicht (migrations/002_venue_geo.sql). Dasselbe
# idempotente Muster wie HEARTS_ADDED_COLUMNS unten: Schema v2 kennt laut
# CUTOVER.md keinen Migrationsweg, eine bestehende DB bekommt die Spalten
# deshalb hier nachgezogen statt ueber ein ALTER-Geruest. Alle NULL-bar -
# "kein Standort bekannt" ist eine gueltige Antwort, siehe venues_geo().
VENUES_GEO_COLUMNS = {
    "street": "TEXT",
    "postcode": "TEXT",
    "city": "TEXT",
    "lat": "REAL",
    "lon": "REAL",
    "geo_source": "TEXT",
    "geo_fetched_at": "TEXT",
}

HEARTS_ADDED_COLUMNS = {
    "run_key": "TEXT NOT NULL DEFAULT ''",
    "member_uids": "TEXT",
}


def _connect():
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Seit das Web-UI schon während des ersten Scrapes bedient wird (main.py),
    # lesen und schreiben zwei Threads gleichzeitig. Im WAL-Modus blockieren
    # Leser den Schreiber nicht und umgekehrt; die Wartezeit ist nur noch für
    # den seltenen Fall zweier Schreiber nötig. Die Einstellung hängt an der
    # Datei, das PRAGMA hier ist also nur die Absicherung.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Kein _migrate_schema()/ALTER-Geruest mehr: das war v1s inkrementeller Weg,
# nachtraeglich hinzugekommene Spalten auf einer alten DB nachzuziehen. Schema
# v2 kennt laut CUTOVER.md KEINE Migration - eine neue DB wird einmalig aus
# migrations/001_schema_v2.sql angelegt und danach nicht mehr per ALTER
# veraendert. init_db() ist deshalb idempotent ueber "Tabelle events existiert
# schon?" statt ueber einzelne Spalten.
def init_db():
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        ).fetchone()
        if not exists:
            conn.executescript(SCHEMA_V2_PATH.read_text(encoding="utf-8"))
        _ensure_hearts_schema(conn)
        _ensure_venue_geo_schema(conn)
        _retire_reactions(conn)
        _seed_tags(conn)


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _ensure_hearts_schema(conn):
    """run_key/member_uids nachruesten, falls die DB aelter als P5c ist.

    Der UNIQUE-Index auf run_key ist die eigentliche Identitaet eines Herzens:
    ein Herz gilt der ganzen Serie (Entscheidung #26), nicht der einzelnen
    Zeigung - hearts.event_uid ist nur der Anker, auf den es gerade zeigt."""
    have = {row["name"] for row in conn.execute("PRAGMA table_info(hearts)")}
    for name, ddl in HEARTS_ADDED_COLUMNS.items():
        if name not in have:
            conn.execute(f"ALTER TABLE hearts ADD COLUMN {name} {ddl}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_hearts_run ON hearts(run_key)")


def _ensure_venue_geo_schema(conn):
    """Adresse und Koordinaten an `venues` nachruesten (Kartenansicht).

    Der CHECK auf geo_source aus migrations/002_venue_geo.sql laesst sich per
    ALTER TABLE nicht nachtragen - SQLite kann einer bestehenden Tabelle keine
    Bedingung hinzufuegen. Geschrieben wird die Spalte ausschliesslich von
    tools/fetch_venue_locations.py, und dort steht der erlaubte Wertebereich
    ('kk_page' | 'nominatim'); eine frisch aus der Migration angelegte DB
    traegt den CHECK ohnehin."""
    have = {row["name"] for row in conn.execute("PRAGMA table_info(venues)")}
    for name, ddl in VENUES_GEO_COLUMNS.items():
        if name not in have:
            conn.execute(f"ALTER TABLE venues ADD COLUMN {name} {ddl}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_venues_geo "
                 "ON venues(lat, lon) WHERE lat IS NOT NULL")


def _retire_reactions(conn):
    """Die abgeloeste 👍/👎-Tabelle wegraeumen - aber NUR, wenn sie leer ist.

    P2s Messung und der Stand beider Datenbanken sagen 0 Zeilen; faende dieser
    Lauf trotzdem welche, waere das eine Ueberraschung, und eine Ueberraschung
    loescht man nicht weg. Dann bleibt die Tabelle liegen und meldet sich im
    Log, statt Davids Bewertungen still zu entsorgen."""
    if not _table_exists(conn, "reactions"):
        return
    count = conn.execute("SELECT count(*) FROM reactions").fetchone()[0]
    if count:
        logger.warning(
            "Tabelle reactions hat %d Zeile(n) und wurde deshalb NICHT "
            "geloescht - sie wird seit P5c von nichts mehr gelesen (Herzen "
            "haben sie abgeloest). Inhalt pruefen, dann von Hand entfernen.",
            count,
        )
        return
    conn.execute("DROP TABLE reactions")
    logger.info("Tabelle reactions entfernt (leer, seit P5c durch hearts abgeloest).")


# P4e: die fuenf Start-Tags (Begruendung + Liste in normalize.TAG_LABELS,
# NICHT hier verdoppelt). INSERT OR IGNORE, damit ein spaeter von Hand
# ergaenzter Tag bei jedem init_db()-Lauf stehen bleibt - dieselbe Vorsicht
# wie venue_aliases.origin='manuell'.
def _seed_tags(conn):
    for slug, label in normalize.TAG_LABELS.items():
        conn.execute("INSERT OR IGNORE INTO tags (slug, label) VALUES (?, ?)", (slug, label))


# --- Venue-Aufloesung (P3, siehe migrations/001_schema_v2.sql §1) ----------
# Roh-Venue-String -> venue_id. Die Scraper liefern weiter Freitext; hier wird
# er aufgeloest. Ein neuer, unbekannter String legt automatisch Venue + Alias
# an (origin='auto'). Stellt sich spaeter heraus, dass zwei Strings dieselbe
# Venue meinen, zeigt man den Alias auf die andere venue_id um - ohne Deploy.

# Woerter, die beim Kollaps-Schluessel (venues.slug) verschwinden. Das ist P2s
# gemessene Normalisierung (siehe DDL-Kommentar §1): Kleinschreibung, Umlaute,
# Klammerzusaetze und "Dresden"/"e.V."/"GmbH" raus - das und NICHT MEHR, sonst
# kollabieren echte, verschiedene Venues (P2s Messung: 744 -> 710, 4,7%).
_VENUE_PAREN_RE = re.compile(r"\([^)]*\)")
_VENUE_DROP_WORDS = {"dresden", "e", "v", "gmbh"}


def venue_slug(raw_venue):
    """Kollaps-Schluessel fuer Venue-Aufloesung. Oeffentlich, damit die
    einmalige Venue-Vorbefuellung (siehe CUTOVER.md §3) exakt dieselbe Regel
    benutzt wie der laufende Schreibpfad - sonst legt ein spaeterer Scrape eine
    zweite Venue fuer eine schon zusammengelegte Schreibweise an."""
    if not raw_venue:
        return ""
    text = _VENUE_PAREN_RE.sub(" ", raw_venue)
    slug = normalize.slugify(text)
    parts = [p for p in slug.split("-") if p and p not in _VENUE_DROP_WORDS]
    return "-".join(parts) or slug


def resolve_venue(conn, raw_venue, now):
    """raw_venue -> venue_id, oder None wenn raw_venue leer ist.

    Reihenfolge: (1) exakt dieser Rohstring schon als Alias bekannt? Deckt
    sowohl 'auto' als auch von Hand zusammengelegte ('manuell') Aliase ab.
    (2) sein Kollaps-Schluessel trifft eine schon existierende Venue (eine
    andere Schreibweise wurde schon aufgeloest)? Dann wird nur ein Alias
    ergaenzt, keine zweite Venue angelegt. (3) sonst: neue Venue + Alias."""
    if not raw_venue:
        return None
    existing = conn.execute(
        "SELECT venue_id FROM venue_aliases WHERE raw_venue = ?", (raw_venue,)
    ).fetchone()
    if existing:
        conn.execute("UPDATE venues SET last_seen = ? WHERE id = ?",
                     (now, existing["venue_id"]))
        return existing["venue_id"]

    slug = venue_slug(raw_venue)
    venue = conn.execute("SELECT id FROM venues WHERE slug = ?", (slug,)).fetchone()
    if venue:
        venue_id = venue["id"]
        conn.execute("UPDATE venues SET last_seen = ? WHERE id = ?", (now, venue_id))
    else:
        cur = conn.execute(
            """INSERT INTO venues (slug, name, region, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?)""",
            (slug, raw_venue, geo.classify_region(raw_venue), now, now),
        )
        venue_id = cur.lastrowid

    conn.execute(
        """INSERT INTO venue_aliases (raw_venue, venue_id, origin, first_seen)
           VALUES (?, ?, 'auto', ?)
           ON CONFLICT(raw_venue) DO NOTHING""",
        (raw_venue, venue_id, now),
    )
    return venue_id


# --- Stufe 3 der Kategorie-Vergabe: venues.kind (P4e) -----------------------
# Reihenfolge (siehe normalize.classify_category-Docstring fuer Stufe 1+2):
#   1. raw_category (normalize.RAW_CATEGORY_MAP)
#   2. Titel-Stichwort (normalize.KEYWORD_CATEGORY_MAP + Tour-Erkennung)
#   3. venues.kind - NUR wenn die Venue selbst zuverlaessig genau EINE echte
#      Kategorie zeigt (David: "guess from the venue only where the venue
#      does one thing")
#   4. sonstiges
#
# Lebt bewusst hier und nicht in normalize.py: normalize.classify_category()
# wird unveraendert von allen 10 Scrapern aufgerufen, BEVOR venue_id ueberhaupt
# aufgeloest ist (die Scraper liefern nur Freitext-venue). Stufe 3 braucht
# venue_id -> venues.kind -> die bisherige Kategorie-Historie DIESER Venue -
# das ist ausschliesslich hier verfuegbar (in upsert_events, nach
# resolve_venue) und in tools/reclassify.py (das venue_id schon aus den
# gespeicherten Zeilen hat). normalize.classify_category()s Signatur bleibt
# fuer die Scraper unveraendert; Stufe 3 wird von den ZWEI Aufrufern, die
# venue_id haben, als Fallback NACH classify_category angewendet.
#
# Bewusst KEIN statisches kind->Kategorie-Woerterbuch: die kind-Werte streuen
# selbst zu stark, um pauschal zu gelten (gemessen, P4e 2026-09-11, ueber ALLE
# Venues eines kind hinweg): "museum" 316 fuehrungen vs. 280 kultur ueber alle
# Museums-Venues, "theater" und "buehne" beide mehrheitlich noch sonstiges.
# Ein Mehrheits-Label pro kind waere fuer einen erheblichen Teil der
# einzelnen Haeuser falsch. Die empirische Mehrheitskategorie JE VENUE trifft
# das genauer - und faellt automatisch weg, sobald eine Venue mehr als eine
# echte (nicht-sonstiges) Kategorie zeigt ("macht mehrere Dinge", siehe
# Docstring unten).
def venue_category_hints(conn):
    """venue_id -> category_slug, nur fuer Venues mit kuratiertem kind
    (kind != 'sonstiges', siehe migrations/001_schema_v2.sql §1), deren
    BISHERIGE Events (aus Stufe 1+2, category_slug != 'sonstiges') sich auf
    GENAU EINE echte Kategorie einigen. Eine Venue mit zwei oder mehr
    verschiedenen echten Kategorien ("macht mehrere Dinge") taucht hier
    absichtlich NICHT auf und bleibt sonstiges - siehe P4e-Messung: von 76
    kuratierten Venues sind nur 17 so einheitlich, 55 sind Mehrfach-Kategorie
    und 4 haben noch keine einzige echte Kategorie als Beleg.
    """
    rows = conn.execute(
        """SELECT e.venue_id AS venue_id, e.category_slug AS category_slug, COUNT(*) AS n
           FROM events e JOIN venues v ON e.venue_id = v.id
           WHERE v.kind != 'sonstiges'
           GROUP BY e.venue_id, e.category_slug"""
    ).fetchall()
    by_venue = {}
    for row in rows:
        by_venue.setdefault(row["venue_id"], {})[row["category_slug"]] = row["n"]
    hints = {}
    for venue_id, cats in by_venue.items():
        real = [c for c in cats if c != "sonstiges"]
        if len(real) == 1:
            hints[venue_id] = real[0]
    return hints


def identity_key(source, url, date):
    """sha1(source|url|date) - der Wiederanknuepfungs-Griff fuer Herzen, siehe
    DDL §3. BEWUSST NICHT die uid: identity_key ist keine Identitaet, sondern
    die Menge der Kandidaten, falls eine uid durch eine Quellen-Redaktion
    wegbricht."""
    basis = f"{source}|{url or ''}|{date}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def _record_source(conn, event_uid, source, now):
    """Hält fest, dass diese Quelle diesen Eintrag geliefert hat."""
    conn.execute(
        """INSERT INTO event_sources (event_uid, source, first_seen, last_seen)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(event_uid, source) DO UPDATE SET last_seen = excluded.last_seen""",
        (event_uid, source, now, now),
    )


def _source_rank(source):
    """Rang einer Quelle nach config.SOURCE_PRIORITY - je kleiner, desto besser.

    SOURCE_PRIORITY ist eine flache Liste, jede Quelle kommt genau einmal vor,
    also ist list.index() bereits eine eindeutige Totalordnung: zwei
    verschiedene Quellen können nie denselben Rang haben. Gemeinsam genutzt
    von _keeps_own_url (Link-Ownership) und upsert_events (events.source-
    Zuordnung, P3b-2) - eine dritte Kopie dieses Closures wäre der Fehler,
    den P3b-2 explizit vermeiden sollte.
    """
    priority = config.SOURCE_PRIORITY
    return priority.index(source) if source in priority else len(priority)


def _keeps_own_url(conn, event_uid, source):
    """Darf diese Quelle den bereits gespeicherten Link überschreiben?

    Hintergrund: liefern zwei Quellen Datum, Zeit, Titel und Ort identisch,
    fallen sie über dieselbe uid in EINE Zeile (siehe event_sources). Ohne
    Regel gewönne schlicht, wer im Scrape-Lauf zuletzt dran war - der
    Newsletter verlinkte dann mal ra.co, mal das Haus selbst, je nach
    Reihenfolge in scheduler.run_scrape().

    Maßgeblich ist stattdessen dieselbe Rangfolge, die auch über sichtbare und
    ausgeblendete Doppelungen entscheidet: config.SOURCE_PRIORITY. Nur die
    bestplatzierte Quelle, die diesen Eintrag geliefert hat, schreibt den Link.
    Ein leerer Link darf weiterhin von jeder Quelle gefüllt werden - das
    entscheidet der Aufrufer.
    """
    return _source_rank(source) <= min(
        (_source_rank(s) for s in sources_for_event(conn, event_uid)),
        default=_source_rank(source),
    )


def _best_source(conn, event_uid):
    """Die bestplatzierte Quelle unter allen, die diesen Eintrag je geliefert
    haben (event_sources) - das, was events.source eigentlich zeigen sollte.

    _source_rank ist eine Totalordnung (jede Quelle hat einen eindeutigen
    Index in SOURCE_PRIORITY), also ist min() hier bereits deterministisch:
    zwei Quellen können nicht denselben Rang teilen. min() mit key bricht
    Gleichstand ohnehin über den ersten Treffer in Auflistungsreihenfolge -
    sources_for_event sortiert nach first_seen, also stabil pro Zeile."""
    return min(sources_for_event(conn, event_uid), key=_source_rank)


def upsert_events(conn, events):
    """events: Liste von dicts mit uid/source/date/time/title/venue/category/raw_category/url.
    Gibt die Anzahl neu eingefügter (bisher unbekannter) Events zurück.

    P3/Schema v2: venue_id-Aufloesung, identity_key und category_slug-FK werden
    NUR beim INSERT gesetzt - wie category in v1 bleiben sie fuer immer stehen,
    sobald eine Zeile einmal existiert (siehe tools/reclassify.py fuer
    nachtraegliches Neueinordnen). Ein erneuter Scrape aktualisiert wie bisher
    nur last_seen/source/Detail-Felder."""
    now = datetime.utcnow().isoformat()
    # Einmal pro Lauf statt pro Event: welche category_slug-Werte die FK
    # ueberhaupt zulaesst. Ein Scraper-Bucket, der (noch) nicht in `categories`
    # steht, faellt auf 'sonstiges' - das darf die Transaktion nie killen
    # (CUTOVER.md §4.3).
    valid_categories = {row["slug"] for row in conn.execute("SELECT slug FROM categories")}
    # Stufe 3 (venue_category_hints, siehe Kommentar dort) einmal pro Lauf
    # berechnen statt pro Event - dieselbe Begruendung wie bei valid_categories.
    venue_hints = venue_category_hints(conn)
    new_count = 0
    for e in events:
        existing = conn.execute(
            "SELECT uid, url FROM events WHERE uid = ?", (e["uid"],)
        ).fetchone()
        if not existing:
            # Insert VOR _record_source: event_sources.event_uid traegt seit
            # Schema v2 eine FK auf events(uid) (v1 hatte keine) - die Zeile,
            # auf die verwiesen wird, muss also zuerst existieren.
            new_count += 1
            venue_id = resolve_venue(conn, e.get("venue"), now)
            ikey = identity_key(e["source"], e.get("url"), e["date"])
            category_slug = e["category"] if e["category"] in valid_categories else "sonstiges"
            # Stufe 3: raw_category und Titel-Stichwort (in e["category"],
            # von normalize.classify_category() in den Scrapern berechnet)
            # hatten keinen Treffer - letzter Versuch ueber die Venue, siehe
            # venue_category_hints() oben.
            if category_slug == "sonstiges" and venue_id in venue_hints:
                category_slug = venue_hints[venue_id]
            conn.execute(
                """INSERT INTO events
                   (uid, identity_key, source, date, time, title, venue_id, raw_venue,
                    category_slug, raw_category, url, image_url, price_text, description,
                    detail_fetched_at, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["uid"], ikey, e["source"], e["date"], e.get("time"), e["title"],
                    venue_id, e.get("venue"), category_slug, e.get("raw_category"),
                    e.get("url"), e.get("image_url"), e.get("price_text"),
                    e.get("description"), e.get("detail_fetched_at"), now, now,
                ),
            )
            # Tags (Kontext, siehe normalize.derive_tags) - wie category_slug
            # NUR beim Insert gesetzt, nicht bei jedem erneuten Scrape neu
            # berechnet (dieselbe Begruendung wie oben: eine Regeländerung
            # gilt erst nach tools/tag_events.py). Insert NACH der events-Zeile,
            # event_tags.event_uid traegt eine FK darauf.
            venue_row = (
                conn.execute("SELECT name, kind FROM venues WHERE id = ?", (venue_id,)).fetchone()
                if venue_id else None
            )
            tags = normalize.derive_tags(
                e["title"],
                venue_row["name"] if venue_row else e.get("venue"),
                venue_row["kind"] if venue_row else None,
            )
            for tag_slug in tags:
                conn.execute(
                    """INSERT INTO event_tags (event_uid, tag_slug) VALUES (?, ?)
                       ON CONFLICT(event_uid, tag_slug) DO NOTHING""",
                    (e["uid"], tag_slug),
                )
            _record_source(conn, e["uid"], e["source"], now)
            continue

        # Bestehende Zeile: _record_source() zuerst, damit die aktuelle Quelle
        # schon in event_sources steht, wenn _keeps_own_url/_best_source gleich
        # darauf ueber ALLE Melder werten (P3b-2) - unveraendert aus v1.
        _record_source(conn, e["uid"], e["source"], now)
        # Der Link einer besser platzierten Quelle bleibt stehen (siehe
        # _keeps_own_url); ist noch gar keiner da, füllt ihn jede Quelle.
        url = e.get("url")
        if url and existing["url"] and not _keeps_own_url(conn, e["uid"], e["source"]):
            url = None
        best_source = _best_source(conn, e["uid"])
        # COALESCE: Ein normaler Kulturkalender-Lauf liefert für die
        # Detail-Felder None - das darf einen bereits nachgeladenen Detail-
        # Cache nicht wieder ausnullen. Rauze liefert sie bei jedem Lauf
        # frisch mit und überschreibt damit bewusst (z.B. "ausverkauft").
        conn.execute(
            """UPDATE events SET last_seen = ?, source = ?,
                 url = COALESCE(?, url),
                 image_url = COALESCE(?, image_url),
                 price_text = COALESCE(?, price_text),
                 description = COALESCE(?, description),
                 detail_fetched_at = COALESCE(?, detail_fetched_at)
               WHERE uid = ?""",
            (
                now, best_source, url, e.get("image_url"), e.get("price_text"),
                e.get("description"), e.get("detail_fetched_at"), e["uid"],
            ),
        )
    return new_count


# --- Kategorien/Tags fuer die Suchliste (P5b) -------------------------------
# Beide sind seit P2 echte Tabellen (migrations/001_schema_v2.sql §2), aber bis
# P5b las die Web-Oberflaeche Kategorien aus dem seit P2 nicht mehr gepflegten
# config.CATEGORY_LABELS - der 'nightlife'-Slug (P2 in der Tabelle angelegt)
# fehlte dort komplett, siehe Bericht zu P5b.

def list_categories(conn):
    """Kategorien fuer die Chip-Zeile, sortiert nach sort_order. Ersetzt
    config.CATEGORY_LABELS als Quelle fuer die Web-Oberflaeche - die Tabelle
    ist die eigentliche Wahrheit (default_visible/sort_order), config.py kannte
    sie nie vollstaendig."""
    rows = conn.execute(
        "SELECT slug, label, default_visible, sort_order FROM categories "
        "ORDER BY sort_order, slug"
    ).fetchall()
    return [dict(row) for row in rows]


def list_tags(conn):
    """Tags fuer den Filter, in derselben Reihenfolge wie normalize.TAG_LABELS
    (die Seed-Reihenfolge) - eine SELECT ohne ORDER BY liefert das meistens
    auch, ist aber nicht garantiert."""
    order = list(normalize.TAG_LABELS)
    rows = [dict(row) for row in conn.execute("SELECT slug, label FROM tags").fetchall()]
    rows.sort(key=lambda r: order.index(r["slug"]) if r["slug"] in order else len(order))
    return rows


def tags_for_events(conn, uids):
    """event_uid -> sortierte Liste von Tag-Slugs, fuer mehrere Events auf
    einmal (eine Anfrage statt einer pro Event, siehe feed.build_events)."""
    uids = list(uids)
    if not uids:
        return {}
    placeholders = ",".join("?" for _ in uids)
    rows = conn.execute(
        f"SELECT event_uid, tag_slug FROM event_tags WHERE event_uid IN ({placeholders})",
        uids,
    ).fetchall()
    order = list(normalize.TAG_LABELS)
    by_uid = {}
    for row in rows:
        by_uid.setdefault(row["event_uid"], []).append(row["tag_slug"])
    for tags in by_uid.values():
        tags.sort(key=lambda t: order.index(t) if t in order else len(order))
    return by_uid


# --- Venues: Lesezugriffe fuer die Venue-Seiten (P5b) -----------------------

def get_venue_by_slug(conn, slug):
    row = conn.execute("SELECT * FROM venues WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def venue_upcoming_events(conn, venue_id, today):
    """Gewinnende Events einer Venue ab heute, chronologisch - das ist, was die
    Venue-Seite als 'anstehende Termine' zeigt."""
    rows = conn.execute(
        """SELECT * FROM events WHERE venue_id = ? AND duplicate_of IS NULL
             AND date >= ? ORDER BY date ASC, time ASC""",
        (venue_id, today),
    ).fetchall()
    return [dict(row) for row in rows]


def venue_last_past_event(conn, venue_id, today):
    """Der juengste vergangene Auftritt einer Venue, oder None. Nur fuer die
    Leerseite gebraucht (keine anstehenden Termine bekannt) - dort ist "zuletzt
    X am Y" ehrlicher als eine leere Flaeche."""
    row = conn.execute(
        """SELECT * FROM events WHERE venue_id = ? AND duplicate_of IS NULL
             AND date < ? ORDER BY date DESC, time DESC LIMIT 1""",
        (venue_id, today),
    ).fetchone()
    return dict(row) if row else None


def list_venues(conn, today):
    """Alle Venues plus Anzahl anstehender Termine, fuer /orte und den
    statischen Export.

    is_meeting_point-Zeilen fehlen ABSICHTLICH (siehe migrations/001_schema_v2.sql
    §1): 'Dresden City', 'Terrassenufer Dresden', 'Theaterplatz Dresden' sind
    Treffpunkte fuer Stadtrundfahrten, keine Spielstaetten - "sie bekommen keine
    Venue-Seite und sollen aus 'Orte in Dresden' heraus" steht so im Schema-
    Kommentar. Gemessen (P5b): 3 Venues, aber 201 anstehende Gewinner-Events
    haengen an ihnen - diese Events bekommen deshalb KEINEN Venue-Link, nur den
    Quellen-Link (siehe feed.build_events/events_for_range)."""
    rows = conn.execute(
        """SELECT v.*,
             (SELECT COUNT(*) FROM events e WHERE e.venue_id = v.id
                AND e.duplicate_of IS NULL AND e.date >= ?) AS upcoming_count
           FROM venues v
           WHERE v.is_meeting_point = 0
           ORDER BY v.name COLLATE NOCASE""",
        (today,),
    ).fetchall()
    return [dict(row) for row in rows]


def category_filter(category):
    """Normalisiert den Kategorie-Filter auf eine Liste von Keys.
    Akzeptiert None, "alle", einen einzelnen Key, "musik,kultur" oder eine
    Liste - so bleibt der alte Einzel-Aufruf gültig, während das Web-UI
    mehrere Kategorien gleichzeitig auswählen kann. Leere Liste = kein Filter."""
    if not category:
        return []
    if isinstance(category, str):
        category = category.split(",")
    return [c.strip() for c in category if c.strip() and c.strip() != "alle"]


# Ab so vielen verschiedenen Terminen gilt eine Reihe als Dauerangebot:
# Ausstellungen, Werksführungen, Stadtrundfahrten, der Hop-on-Hop-off-Bus. In
# der Live-Datenbank gehören 49% aller Zeilen zu solchen Reihen (2097 von 4297),
# und an einem einzelnen Tag sind es rund 70 von 150 Einträgen. Sie sind nicht
# falsch, aber sie sind etwas anderes als "was ist heute Abend los" - im Web
# werden sie deshalb eigens eingefärbt (siehe .ongoing in index.html).
ONGOING_MIN_DAYS = 7


def _ongoing_titles(conn):
    """Titel, die auf mindestens ONGOING_MIN_DAYS verschiedenen Tagen laufen.

    Bewusst über den GESAMTEN Bestand gezählt, nicht nur über den angezeigten
    Zeitraum: eine Ausstellung, die 32 Tage läuft, ist auch dann ein
    Dauerangebot, wenn man gerade nur den heutigen Tag ansieht.
    """
    rows = conn.execute(
        "SELECT title FROM events GROUP BY title HAVING COUNT(DISTINCT date) >= ?",
        (ONGOING_MIN_DAYS,),
    ).fetchall()
    return {row["title"] for row in rows}


def events_for_range(conn, start_date, end_date, category=None, exclude_categories=None,
                     include_duplicates=False, exclude_far=False):
    """Liefert standardmäßig nur die "gewinnenden" Einträge: als Doppelung
    verbuchte Zeilen (duplicate_of gesetzt, siehe app/dedup.py) bleiben in der
    DB, werden aber nicht ausgeliefert.

    exclude_far=True wirft zusätzlich alles raus, was weder in Dresden noch im
    Speckgürtel liegt (siehe app/geo.py) - so filtert die Web-Startansicht. Mit
    dem Schalter "Umgebung einschließen" bekommt sie dagegen alles und blendet
    im Browser aus, was gerade nicht gezeigt werden soll (siehe
    app/templates/index.html)."""
    # category/venue als Aliase: category_slug/raw_venue heissen seit Schema v2
    # anders in der Tabelle, aber jeder Aufrufer (feed.py, scoring.py, dedup.py,
    # Templates) erwartet weiter event["category"]/event["venue"] - das ist die
    # ganze Grenze, die P3s Umbau nach aussen unsichtbar macht.
    #
    # venue_slug/venue_is_meeting_point (P5b): der Griff auf die Venue-Seite
    # bzw. die Absage daran, siehe list_venues()-Docstring.
    query = ("SELECT e.*, e.category_slug AS category, e.raw_venue AS venue, "
             "v.region AS region, v.slug AS venue_slug, "
             "v.is_meeting_point AS venue_is_meeting_point "
             "FROM events e LEFT JOIN venues v ON v.id = e.venue_id "
             "WHERE e.date >= ? AND e.date <= ?")
    if not include_duplicates:
        query += " AND e.duplicate_of IS NULL"
    params = [start_date, end_date]
    categories = category_filter(category)
    if categories:
        placeholders = ",".join("?" for _ in categories)
        query += f" AND e.category_slug IN ({placeholders})"
        params.extend(categories)
    if exclude_categories:
        placeholders = ",".join("?" for _ in exclude_categories)
        query += f" AND e.category_slug NOT IN ({placeholders})"
        params.extend(exclude_categories)
    query += " ORDER BY e.date ASC, e.time ASC"
    events = [dict(row) for row in conn.execute(query, params).fetchall()]
    # Zusatzfeld fürs Web.
    ongoing = _ongoing_titles(conn)
    for event in events:
        event["ongoing"] = event["title"] in ongoing
        # Region kommt jetzt aus venues.region (JOIN oben, einmal pro Venue
        # berechnet statt einmal pro Event - siehe DDL §1). Nur wenn ein Event
        # gar keine Venue hat (venue_id NULL), faellt es auf die alte
        # Pro-Event-Berechnung zurueck.
        if event.get("region") is None:
            event["region"] = geo.classify_region(event.get("venue"))
        # Treffpunkte (siehe list_venues()-Docstring) bekommen keine Venue-Seite -
        # das Flag selbst verlaesst diese Funktion nicht, nur sein Effekt.
        if event.pop("venue_is_meeting_point", None):
            event["venue_slug"] = None
    if exclude_far:
        events = [e for e in events if e["region"] != geo.REGION_WEITER]
    return events


def save_event_detail(conn, uid, image_url=None, price_text=None, description=None):
    """Speichert das Ergebnis eines Detail-Nachladens (siehe scrapers.detail_fetch).
    description wird bewusst auch dann gesetzt, wenn nichts gefunden wurde - sonst
    sähe das Event für immer wie "noch nie geladen" aus und würde jedes Mal neu
    abgefragt."""
    conn.execute(
        """UPDATE events SET
             image_url = COALESCE(?, image_url),
             price_text = COALESCE(?, price_text),
             description = ?,
             detail_fetched_at = ?
           WHERE uid = ?""",
        (image_url, price_text, description, datetime.utcnow().isoformat(), uid),
    )


# --- Doppelungen zwischen Quellen (siehe app/dedup.py) ---------------------

def link_duplicate(conn, duplicate_uid, canonical_uid, score=None, matched_on=None):
    """Verbucht duplicate_uid als Doppelung von canonical_uid. first_seen der
    Buchung bleibt beim erneuten Verbuchen erhalten - so ist ablesbar, seit wann
    eine Doppelung besteht."""
    now = datetime.utcnow().isoformat()
    sources = conn.execute(
        "SELECT uid, source FROM events WHERE uid IN (?, ?)",
        (duplicate_uid, canonical_uid),
    ).fetchall()
    by_uid = {row["uid"]: row["source"] for row in sources}

    conn.execute("UPDATE events SET duplicate_of = ? WHERE uid = ?",
                 (canonical_uid, duplicate_uid))
    conn.execute(
        """INSERT INTO event_duplicates
             (duplicate_uid, canonical_uid, duplicate_source, canonical_source,
              match_score, matched_on, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(duplicate_uid) DO UPDATE SET
             canonical_uid = excluded.canonical_uid,
             canonical_source = excluded.canonical_source,
             match_score = excluded.match_score,
             matched_on = excluded.matched_on,
             last_seen = excluded.last_seen""",
        (
            duplicate_uid, canonical_uid, by_uid.get(duplicate_uid),
            by_uid.get(canonical_uid), score, matched_on, now, now,
        ),
    )


def unlink_duplicate(conn, duplicate_uid):
    """Hebt eine Verknüpfung wieder auf - z.B. wenn eine Quelle ihren Titel so
    geändert hat, dass die Einträge nicht mehr zusammenpassen."""
    conn.execute("UPDATE events SET duplicate_of = NULL WHERE uid = ?", (duplicate_uid,))
    conn.execute("DELETE FROM event_duplicates WHERE duplicate_uid = ?", (duplicate_uid,))


# Felder, die der gewinnende Eintrag aus seinem Duplikat übernehmen darf.
_FILLABLE_COLUMNS = ("image_url", "price_text", "description", "url")


def fill_missing_from_duplicate(conn, canonical_uid, duplicate_uid):
    """Füllt beim Gewinner nur die LEEREN Felder aus dem Duplikat auf
    (Rauze nennt z.B. keinen Preis, RA schon). Vorhandene Werte werden nie
    überschrieben. Gibt die Namen der tatsächlich gefüllten Spalten zurück."""
    rows = conn.execute(
        "SELECT * FROM events WHERE uid IN (?, ?)", (canonical_uid, duplicate_uid)
    ).fetchall()
    by_uid = {row["uid"]: dict(row) for row in rows}
    canonical, duplicate = by_uid.get(canonical_uid), by_uid.get(duplicate_uid)
    if not canonical or not duplicate:
        return []

    updates = {}
    for column in _FILLABLE_COLUMNS:
        if not (canonical.get(column) or "").strip() and (duplicate.get(column) or "").strip():
            updates[column] = duplicate[column]

    # Wird eine Beschreibung übernommen, muss auch detail_fetched_at gesetzt
    # werden: sonst hält das Detail-Popup das Event für "nie geladen", holt es
    # von der Quellseite nach und überschreibt die übernommene Beschreibung
    # wieder mit Leer (siehe save_event_detail).
    if "description" in updates and not canonical.get("detail_fetched_at"):
        updates["detail_fetched_at"] = (
            duplicate.get("detail_fetched_at") or datetime.utcnow().isoformat()
        )

    if not updates:
        return []
    assignments = ", ".join(f"{column} = ?" for column in updates)
    conn.execute(
        f"UPDATE events SET {assignments} WHERE uid = ?",
        (*updates.values(), canonical_uid),
    )
    return list(updates)


def set_venue(conn, uid, venue):
    """Ort eines Eintrags setzen. Genutzt von dedup._upgrade_placeholder_venue(),
    wenn der Gewinner nur einen Platzhalter ("Location siehe Beschreibung") hat
    und das Duplikat den echten Ort kennt. Loest den neuen Rohstring wie beim
    Insert ueber venue_aliases auf, damit venue_id nicht stehenbleibt."""
    now = datetime.utcnow().isoformat()
    venue_id = resolve_venue(conn, venue, now)
    conn.execute("UPDATE events SET raw_venue = ?, venue_id = ? WHERE uid = ?",
                 (venue, venue_id, uid))


def sources_for_event(conn, event_uid):
    rows = conn.execute(
        "SELECT source FROM event_sources WHERE event_uid = ? ORDER BY first_seen",
        (event_uid,),
    ).fetchall()
    return [row["source"] for row in rows]


def shared_uid_events(conn, start_date, end_date):
    """Einträge, die mehr als eine Quelle identisch geliefert hat - die
    Doppelungen, die schon über die uid zusammenfallen (siehe event_sources)."""
    rows = conn.execute(
        """SELECT e.uid, e.date, e.time, e.title, e.raw_venue AS venue,
                  GROUP_CONCAT(s.source, ',') AS sources, COUNT(*) AS n
           FROM events e JOIN event_sources s ON s.event_uid = e.uid
           WHERE e.date >= ? AND e.date <= ?
           GROUP BY e.uid HAVING n > 1
           ORDER BY e.date ASC, e.time ASC""",
        (start_date, end_date),
    ).fetchall()
    return [dict(row) for row in rows]


def duplicates_for_range(conn, start_date, end_date):
    """Verbuchte Doppelungen im Zeitraum, aufbereitet für tools/show_duplicates.py."""
    rows = conn.execute(
        """SELECT d.duplicate_uid, d.canonical_uid, d.duplicate_source,
                  d.canonical_source, d.match_score, d.matched_on, d.first_seen,
                  dup.title AS duplicate_title, dup.raw_venue AS duplicate_venue,
                  dup.date AS date, dup.time AS duplicate_time,
                  can.title AS canonical_title, can.raw_venue AS canonical_venue,
                  can.time AS canonical_time
           FROM event_duplicates d
           JOIN events dup ON dup.uid = d.duplicate_uid
           JOIN events can ON can.uid = d.canonical_uid
           WHERE dup.date >= ? AND dup.date <= ?
           ORDER BY dup.date ASC, dup.time ASC""",
        (start_date, end_date),
    ).fetchall()
    return [dict(row) for row in rows]


def duplicate_counts(conn):
    """Wie viele Doppelungen je Quellen-Paar verbucht sind."""
    rows = conn.execute(
        """SELECT duplicate_source, canonical_source, COUNT(*) AS n
           FROM event_duplicates
           GROUP BY duplicate_source, canonical_source
           ORDER BY n DESC"""
    ).fetchall()
    return [dict(row) for row in rows]


# --- Zustand der Scraper (siehe app/scheduler.py) --------------------------

def record_scrape_run(conn, source, started_at, finished_at, ok, event_count=None,
                      error=None):
    """Verbucht den Lauf EINER Quelle. ok=0 heißt nicht nur "Exception": auch
    ein Nulltreffer trotz früher gefüllter Quelle gilt als nicht erfolgreich,
    damit last_successful_run() dann sichtbar veraltet."""
    conn.execute(
        """INSERT INTO scrape_runs (source, started_at, finished_at, ok, event_count, error)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (source, started_at, finished_at, 1 if ok else 0, event_count, error),
    )


def last_successful_run(conn, source):
    row = conn.execute(
        """SELECT * FROM scrape_runs WHERE source = ? AND ok = 1
           ORDER BY started_at DESC, id DESC LIMIT 1""",
        (source,),
    ).fetchone()
    return dict(row) if row else None


def last_successful_scrape(conn):
    """Zeitpunkt des jüngsten erfolgreichen Laufs, egal welcher Quelle.
    Grundlage für die Startentscheidung in main.py."""
    row = conn.execute(
        "SELECT MAX(finished_at) AS finished_at FROM scrape_runs WHERE ok = 1"
    ).fetchone()
    return row["finished_at"] if row else None


def _last_run(conn, source):
    row = conn.execute(
        "SELECT * FROM scrape_runs WHERE source = ? ORDER BY started_at DESC, id DESC LIMIT 1",
        (source,),
    ).fetchone()
    return dict(row) if row else None


def scrape_health(conn):
    """Je Quelle der jüngste und der jüngste erfolgreiche Lauf.

    Beides, weil erst der Abstand zwischen ihnen die Lage beschreibt: scheitert
    eine Quelle seit Tagen, steht der letzte Erfolg mit Datum und Anzahl daneben
    und zeigt, wie alt die ausgelieferten Daten dieser Quelle inzwischen sind.

    Es wird über config.SOURCES iteriert und nicht über die Tabelle: eine Quelle,
    die noch nie gelaufen ist, muss auftauchen - genau das ist ja der Ausfall,
    den man sehen will.
    """
    health = {}
    for source in config.SOURCES:
        label = config.SOURCE_LABELS[source]
        latest = _last_run(conn, source)
        success = last_successful_run(conn, source)
        health[source] = {
            "label": label,
            "last_run": latest["started_at"] if latest else None,
            "ok": bool(latest["ok"]) if latest else False,
            "last_success": success["finished_at"] if success else None,
            "event_count": success["event_count"] if success else None,
            "error": latest["error"] if latest else None,
        }
    return health


# --- Verwaiste Events -------------------------------------------------------
# uid = sha1(date|time|title|venue) (siehe normalize.make_event_uid). Korrigiert
# eine Quelle nachtraeglich die Startzeit eines Events, aendert das die uid -
# es entsteht eine ZWEITE Zeile statt die erste zu aktualisieren. Die alte
# Zeile bleibt liegen: last_seen wird nie wieder aktualisiert, aber bislang
# liest das niemand, und ein DELETE existiert nirgends im Code. Diese Funktion
# macht das sichtbar (dry_run=True, Default) - das Loeschen selbst kommt erst
# in einem zweiten, separaten Commit, nachdem ein Dry-Run-Lauf beobachtet wurde.

# Wie viel Zeit die gezaehlten Laeufe mindestens abdecken muessen. Die reine
# Anzahl reicht als Schwelle nicht: Laeufe haeufen sich (Deploys, manuelle
# Testlaeufe), und drei davon koennen innerhalb weniger Stunden liegen. Die
# Schwelle waere dann rein rechnerisch erfuellt, obwohl gar kein Tag beobachtet
# wurde - ein Zukunfts-Event flaege raus, weil zufaellig dreimal kurz
# hintereinander gescrapt wurde.
#
# 12 Stunden und nicht mehr, weil drei aufeinanderfolgende Laeufe des
# */6h-Rhythmus exakt diese Spanne ergeben: der Normalbetrieb soll die Schwelle
# gerade erfuellen, die Haeufung nicht.
MIN_CUTOFF_SPAN = timedelta(hours=12)


def _successful_run_cutoff(conn, source, threshold_runs, min_span=MIN_CUTOFF_SPAN):
    """Startzeitpunkt des Laufs, ab dem ein Event als verwaist gilt: Alles, was
    seitdem nicht mehr aktualisiert wurde, hat mindestens threshold_runs Laeufe
    am Stueck verpasst UND dabei mindestens min_span an Zeit - nicht nur einen
    einzelnen Lauf, der auch mal ein Netzwerk-Hakler sein koennte, und nicht nur
    eine Handvoll Laeufe, die zufaellig dicht beieinander lagen.

    Beide Bedingungen zusammen, deshalb wird das Fenster so weit aufgezogen, bis
    sie beide gelten. Genau die N juengsten Laeufe zu pruefen und bei zu kurzer
    Spanne aufzugeben, saesse dauerhaft auf der Kante: drei Laeufe des
    */6h-Rhythmus ergeben exakt 12 Stunden, ein um Sekunden verspaeteter Lauf
    liesse die Erkennung also staendig kippen und wieder anspringen. Das
    Aufweiten schiebt den Cutoff nur nach hinten - es markiert damit immer
    weniger, nie mehr.

    None, wenn die Historie fuer beides nicht reicht: ohne sie liesse sich ein
    echtes Verwaisen nicht von "die Quelle laeuft erst seit kurzem"
    unterscheiden - dann wird nichts markiert, statt zu raten.
    """
    rows = conn.execute(
        """SELECT started_at FROM scrape_runs WHERE source = ? AND ok = 1
           ORDER BY started_at DESC, id DESC""",
        (source,),
    ).fetchall()
    if len(rows) < threshold_runs:
        return None
    newest = datetime.fromisoformat(rows[0]["started_at"])
    for row in rows[threshold_runs - 1:]:
        if newest - datetime.fromisoformat(row["started_at"]) >= min_span:
            return row["started_at"]
    return None


def _healthy_sources(conn, threshold_runs):
    """Quellen, deren Zustand ueberhaupt eine Aussage ueber Verwaisen zulaesst,
    je mit ihrem Cutoff.

    Zwei Bedingungen, beide aus der alten Fassung uebernommen, nur nicht mehr
    pro Event-Zeile ausgewertet:
    - der LETZTE Lauf war ok. Eine gerade ausgefallene Quelle darf nichts als
      verwaist erklaeren, sie liefert ja nur voruebergehend nichts.
    - _successful_run_cutoff() liefert einen Zeitpunkt. Fehlt die Historie
      (Zeilen ODER Zeitspanne), laesst sich "verwaist" nicht von "laeuft erst
      seit kurzem" unterscheiden - dann urteilt diese Quelle gar nicht.
    """
    healthy = {}
    for source in config.SOURCES:
        latest = _last_run(conn, source)
        if not latest or not latest["ok"]:
            continue
        cutoff = _successful_run_cutoff(conn, source, threshold_runs)
        if cutoff is None:
            continue
        healthy[source] = cutoff
    return healthy


def find_orphaned_events(conn, today, threshold_runs=3):
    """Zukuenftige Events, die KEINE der aktuell urteilsfaehigen Quellen mehr
    liefert.

    Maßgeblich ist event_sources, nicht events.source. Grund (P3, P3b): in
    events.source steht, wer die Zeile ZUERST angelegt hat, nicht wer sie
    zuletzt gemeldet hat - liefert ein Aggregator ein Event vor dem Haus, traegt
    die Zeile fuer immer den Aggregator, obwohl das Haus sie jeden Lauf frisch
    meldet. Solange die Verwaisungs-Erkennung nach events.source gruppierte,
    entschied also eine reine Anzeige-Spalte mit, was geloescht wird. Genau
    diese Kopplung loest diese Funktion auf: events.source ist wieder nur
    Beschriftung und erreicht keinen loeschenden Pfad mehr (siehe §4.7 des
    Plans).

    Eine Zukunfts-Zeile gilt als verwaist, wenn ALLE aktuell urteilsfaehigen
    Quellen, die sie je geliefert haben, sie seit ihrem jeweiligen Cutoff nicht
    mehr gemeldet haben - gemessen an event_sources.last_seen, das pro Quelle
    gefuehrt wird, waehrend events.last_seen nur die jeweils letzte beliebige
    Quelle festhaelt.

    ZWEI Nicht-Leerheits-Schutzklauseln, beide zwingend, weil "alle X sind
    veraltet" ueber einer LEEREN Menge X wahr ist und die Zeile sonst
    klaglos zum Loeschen freigeben wuerde:
    - Zeilen ohne jeden event_sources-Eintrag werden nie markiert. Auf der
      Live-DB gibt es davon aktuell keine einzige (5789/5789 haben Eintraege,
      geprueft 2026-09-10) - upsert_events ruft _record_source() bedingungslos
      als erstes auf, und init_db() traegt Altbestand nach. Die Klausel steht
      trotzdem hier: sie kostet nichts und faengt jeden kuenftigen Schreibpfad
      ab, der die Tabelle vergisst.
    - Zeilen, deren saemtliche Quellen gerade NICHT urteilsfaehig sind, werden
      ebenfalls nie markiert. Das ist der Fall "Aggregator ausgefallen" bei
      Zeilen, die nur dieser Aggregator liefert: niemand kann sagen, ob das
      Event weg ist oder nur die Quelle. Die alte Fassung fing das ueber ihre
      Schleife ueber Quellen mit ab; ohne diese Klausel waere die neue Fassung
      an dieser Stelle SCHAERFER als die alte (gemessen: 9 statt 0, siehe
      Bericht zu P3b-1).

    Nur date >= today: vergangene Events sind historischer Bestand und durch
    Re-Scraping nicht wiederherstellbar - die werden hier nie angefasst.

    Gibt ein dict zurueck: Schluessel ist die aus event_sources abgeleitete
    Quellen-Signatur der Zeile ("sektor+kulturkalender"), Wert die Liste der
    Event-Zeilen. Der Schluessel dient nur dem Log; er kommt bewusst NICHT aus
    events.source.
    """
    healthy = _healthy_sources(conn, threshold_runs)
    if not healthy:
        return {}

    rows = conn.execute(
        """SELECT e.uid, e.title, e.date, e.time, e.raw_venue AS venue, e.last_seen,
                  s.source AS es_source, s.last_seen AS es_last_seen
             FROM events e
             JOIN event_sources s ON s.event_uid = e.uid
            WHERE e.date >= ?
            ORDER BY e.date, e.time, e.uid""",
        (today,),
    ).fetchall()

    per_event = {}
    order = []
    for row in rows:
        if row["uid"] not in per_event:
            per_event[row["uid"]] = {"row": row, "sources": {}}
            order.append(row["uid"])
        per_event[row["uid"]]["sources"][row["es_source"]] = row["es_last_seen"]

    result = {}
    for uid in order:
        entry = per_event[uid]
        sources = entry["sources"]
        judging = {s: ls for s, ls in sources.items() if s in healthy}
        if not judging:
            # Schutzklausel 2 (und, ueber den JOIN, auch 1).
            continue
        if not all(last_seen < healthy[s] for s, last_seen in judging.items()):
            continue
        row = entry["row"]
        signature = "+".join(sorted(sources))
        result.setdefault(signature, []).append({
            "uid": uid, "title": row["title"], "date": row["date"],
            "time": row["time"], "venue": row["venue"],
            "last_seen": row["last_seen"], "sources": signature,
        })
    return result


def _delete_orphaned_event(conn, source, row):
    """AKTUELL NICHT AUFGERUFEN - siehe ORPHAN_DELETION_DISABLED weiter unten.
    Bewusst stehengelassen, weil P3b-3 sie wieder scharf schaltet.

    Loescht EINE verwaiste Zeile - mit den drei Schutzklauseln, die der
    Dry-Run nicht brauchte, weil er nie wirklich loeschte.

    - Eine Zeile, an der ein Herz haengt, wird NIE geloescht: data/ enthaelt die
      einzige Kopie der Herzen, und die kuratierte Seite liest sie ueber die
      lebende Event-Zeile - eine geloeschte Zeile liesse einen Eintrag der
      kuratierten Seite kommentarlos verschwinden. (Seit P5c Herzen statt
      Reaktionen; der Schnappschuss im Herzen faengt den Verlust zwar ab, aber
      "faengt es ab" ist kein Grund, ihn auszuloesen.)
    - Ist die Zeile CANONICAL einer Doppelung, werden ihre Duplikate zuerst
      entkoppelt (unlink_duplicate): sonst zeigt deren duplicate_of ins Leere
      und ein echtes, weiterhin gescraptes Event bliebe fuer immer ausgeblendet.
    - Ist die Zeile selbst als Duplikat verbucht, wird diese Buchung mitgeloescht
      - sonst zeigt sie auf eine nicht mehr existierende Zeile.

    Gibt True zurueck, wenn tatsaechlich geloescht wurde.
    """
    uid = row["uid"]
    if heart_for_uid(conn, uid) is not None:
        logger.warning(
            "Verwaistes Event NICHT geloescht (haengt an einem Herz): %s \"%s\" (%s, %s)",
            uid, row["title"], row["date"], source,
        )
        return False

    for dup in conn.execute(
        "SELECT duplicate_uid FROM event_duplicates WHERE canonical_uid = ?", (uid,)
    ).fetchall():
        unlink_duplicate(conn, dup["duplicate_uid"])
    conn.execute("DELETE FROM event_duplicates WHERE duplicate_uid = ?", (uid,))
    conn.execute("DELETE FROM event_sources WHERE event_uid = ?", (uid,))
    conn.execute("DELETE FROM events WHERE uid = ?", (uid,))
    logger.warning(
        "Verwaistes Event geloescht: %s \"%s\" (%s, %s)",
        uid, row["title"], row["date"], source,
    )
    return True


# ===========================================================================
# ABSICHT, KEIN BUG: Loeschen ist bewusst abgeschaltet (Packet P3b-1).
# ---------------------------------------------------------------------------
# expire_orphaned_events() MELDET ab hier nur noch, was es loeschen wuerde, und
# loescht nichts - auch nicht mit dry_run=False. Das ist eine Produkt-
# entscheidung von David, keine Notloesung und kein vergessener Schalter:
#
#   Der Erkennungs-Pfad (find_orphaned_events) ist gerade von events.source auf
#   event_sources umgestellt worden, also KORREKTER geworden. Eine Aenderung,
#   die einen loeschenden Pfad korrekter macht, und eine Aenderung, die ihn
#   scharf schaltet, sind zwei verschiedene Aenderungen; dazwischen gehoert eine
#   Messung. Erschwerend: laut Plan-§7 hat dieser Loeschpfad in der Produktion
#   noch nie gefeuert - das naechste Deploy (PD) waere zugleich das erste Mal
#   ueberhaupt UND das erste Mal mit der neuen, breiteren Erkennung, und 45
#   Minuten spaeter veroeffentlicht ein Cron das Ergebnis oeffentlich.
#
# Deshalb: erst mitschreiben, was geloescht WUERDE, dann anhand echter Laeufe
# urteilen. Das Log dieser Funktion ist die vollstaendige Eingabe fuer Packet
# P3b-3, das den Schalter wieder entfernt.
#
# ZUM SCHARFSCHALTEN (nur in P3b-3, nach >= 3 beobachteten Laeufen auf CT103):
# die Konstante unten auf False setzen und diesen Block loeschen.
# NICHT vorher, und nicht "weil dry_run=False uebergeben wird".
# ===========================================================================
ORPHAN_DELETION_DISABLED = True


def expire_orphaned_events(conn, today, threshold_runs=3, dry_run=True):
    """Meldet verwaiste Zukunfts-Events (siehe find_orphaned_events).

    Loescht derzeit NICHTS, unabhaengig von dry_run - siehe der Block ueber
    ORPHAN_DELETION_DISABLED. Der Parameter dry_run bleibt in der Signatur
    erhalten, damit die Aufrufer (scheduler.run_scrape) unveraendert bleiben und
    P3b-3 nur die Konstante entfernen muss.

    Geloggt wird pro Quellen-Signatur die Anzahl mit ein paar Beispieltiteln und
    zusaetzlich je Zeile eine eigene Zeile mit uid, Titel, Datum und den Quellen,
    die sie je geliefert haben - das ist die Eingabe fuer P3b-3.
    """
    orphaned = find_orphaned_events(conn, today, threshold_runs)
    total = sum(len(rows) for rows in orphaned.values())
    if not total:
        logger.info(
            "Verwaiste Events: keine gefunden (Schwelle %d Laeufe, Loeschen "
            "abgeschaltet).", threshold_runs,
        )
        return orphaned

    for signature, rows in orphaned.items():
        samples = ", ".join(f'"{r["title"]}"' for r in rows[:3])
        logger.warning(
            "WUERDE LOESCHEN - verwaiste Events aus %s: %d seit %d "
            "erfolgreichen Laeufen von keiner urteilsfaehigen Quelle mehr "
            "geliefert. Beispiele: %s",
            signature, len(rows), threshold_runs, samples,
        )
        for row in rows:
            logger.warning(
                "WUERDE LOESCHEN: %s \"%s\" (%s %s, %s) - Quellen: %s, "
                "zuletzt gesehen %s",
                row["uid"], row["title"], row["date"], row["time"] or "",
                row["venue"], row["sources"], row["last_seen"],
            )

    logger.warning(
        "WUERDE LOESCHEN insgesamt: %d Event(s) ueber %d Quellen-Signatur(en). "
        "Es wurde NICHTS geloescht - Loeschen ist seit P3b-1 bewusst "
        "abgeschaltet (ORPHAN_DELETION_DISABLED), scharf schalten macht P3b-3. "
        "dry_run=%s wird dabei ignoriert.",
        total, len(orphaned), dry_run,
    )
    return orphaned


def get_weight(conn, key):
    row = conn.execute("SELECT likes, skips FROM weights WHERE key = ?", (key,)).fetchone()
    return (row["likes"], row["skips"]) if row else (0, 0)


def bump_weight(conn, key, like_delta=0, skip_delta=0):
    conn.execute(
        """INSERT INTO weights (key, likes, skips) VALUES (?, MAX(?, 0), MAX(?, 0))
           ON CONFLICT(key) DO UPDATE SET
             likes = MAX(likes + ?, 0),
             skips = MAX(skips + ?, 0)""",
        (key, like_delta, skip_delta, like_delta, skip_delta),
    )


# ===========================================================================
# HERZEN (P5c) - Davids redaktionelle Auswahl
# ===========================================================================
#
# DIE EINE REGEL, an der dieses Paket haengt: `link_status = 'ok'` heisst NICHT
# "die Zeile existiert noch", sondern "die Zeile ist eine GEWINNER-Zeile"
# (duplicate_of IS NULL). Nur die zeigt die Liste - events_for_range() haengt
# genau dieses AND an. Eine lebende Zeile mit gesetztem duplicate_of ist in
# jeder Ansicht unsichtbar; ein Herz darauf wuerde sich selbst als 'ok' melden
# und waere trotzdem von der kuratierten Seite verschwunden.
#
# Das ist derselbe Fehler wie zweimal zuvor in diesem Projekt (venues.
# meta_status in P5v, P5ws Doppelungs-Fund): ein Status-Feld, das GESETZT ist,
# ist nicht dieselbe Tatsache wie die Bedingung, die sein Leser wirklich
# braucht. Deshalb gibt es hier genau EINE Stelle, die den Status bestimmt -
# _resolve_heart() - und sowohl der Schreibweg (set_heart) als auch der
# Reparaturlauf nach jedem Scrape (relink_hearts) gehen durch sie.
#
# dedup.link_duplicates() laeuft nach JEDEM Scrape ueber heute..+31 Tage und
# schiebt Zeilen zwischen Gewinner und Doppelung hin und her. Ein Beispiel aus
# dem Bestand (Stand 12.09.2026): 15a4e9d368071799 ("S.Y.N.T.H.E.T.I.C
# S.I.G.N.A.L.S", Kulturkalender, raw_venue "Ostpol Dresden") ist seit P5w
# Doppelung von e5b0aa6df8071ec8 (Rauze, raw_venue "Ostpol"). Die beiden
# Schreibweisen ergeben VERSCHIEDENE Serien-Schluessel - ein Herz auf der
# Kulturkalender-Zeile ist also ueber den Schluessel allein NICHT zu retten.
# Es wird ueber die Doppelungs-Buchung weitergezogen und uebernimmt dabei den
# Schluessel des Gewinners. Genau dafuer ist _canonical_uid() da.

_HEART_EVENT_SELECT = (
    "SELECT e.*, e.category_slug AS category, e.raw_venue AS venue, "
    "v.slug AS venue_slug, v.is_meeting_point AS venue_is_meeting_point "
    "FROM events e LEFT JOIN venues v ON v.id = e.venue_id "
)


def _public_event(row):
    """Dieselbe Nachbereitung wie in events_for_range(): Treffpunkte bekommen
    keine Venue-Seite, das Flag selbst verlaesst die Funktion nicht."""
    event = dict(row)
    if event.pop("venue_is_meeting_point", None):
        event["venue_slug"] = None
    return event


def event_for_uid(conn, uid):
    """Eine einzelne Zeigung mit denselben Feldern, die auch die Liste sieht."""
    row = conn.execute(_HEART_EVENT_SELECT + "WHERE e.uid = ?", (uid,)).fetchone()
    return _public_event(row) if row else None


def run_members(conn, run_key, winners_only=True):
    """Alle Zeigungen EINER Serie, chronologisch.

    Der Serien-Schluessel traegt den Tag an erster Stelle, also reicht ein
    Tages-Query plus Nachfiltern in Python - der Schluessel selbst ist in SQL
    nicht ausdrueckbar (normalize.run_slug). Pro Tag sind das rund 110 Zeilen.

    winners_only=True ist der Normalfall UND der Punkt der ganzen Uebung: was
    die Liste nicht zeigt, ist auch kein Mitglied einer geherzten Serie."""
    day = run_key.split("|", 1)[0]
    query = _HEART_EVENT_SELECT + "WHERE e.date = ?"
    if winners_only:
        query += " AND e.duplicate_of IS NULL"
    members = [
        _public_event(row) for row in conn.execute(query, (day,)).fetchall()
        if normalize.run_key_for_event(_public_event(row)) == run_key
    ]
    members.sort(key=lambda e: (e["time"] or "99:99", e["uid"]))
    return members


def _canonical_uid(conn, uid):
    """Folgt der Doppelungs-Kette bis zu der Zeile, die die Liste zeigt.

    Zuerst events.duplicate_of; ist die Zeile selbst verschwunden, sagt
    event_duplicates noch, worauf sie zuletzt zeigte (die Buchung bleibt auch
    ohne die Zeile stehen). Gibt None zurueck, wenn am Ende keine lebende
    Gewinner-Zeile steht."""
    seen = set()
    while uid and uid not in seen:
        seen.add(uid)
        row = conn.execute(
            "SELECT duplicate_of FROM events WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            booking = conn.execute(
                "SELECT canonical_uid FROM event_duplicates WHERE duplicate_uid = ?",
                (uid,)).fetchone()
            if booking is None:
                return None
            uid = booking["canonical_uid"]
            continue
        if row["duplicate_of"] is None:
            return uid
        uid = row["duplicate_of"]
    return None


def _winner_by_identity(conn, identity_key, run_date):
    """Letzter Rettungsanker: dieselbe Zeigung unter neuer uid. identity_key ist
    sha1("<source>|<url>|<date>") und bewusst nicht eindeutig (Serien teilen
    sich eine Seite), deshalb zaehlt zusaetzlich der Tag."""
    rows = conn.execute(
        _HEART_EVENT_SELECT
        + "WHERE e.identity_key = ? AND e.date = ? AND e.duplicate_of IS NULL "
          "ORDER BY e.time IS NULL, e.time, e.uid",
        (identity_key, run_date),
    ).fetchall()
    return _public_event(rows[0]) if rows else None


def _resolve_heart(conn, heart):
    """Bestimmt Anker, Serien-Schluessel, Mitglieder und link_status EINES
    Herzens - die einzige Stelle, die das tut.

    Reihenfolge, von "nichts passiert" bis "nichts mehr da":
      1. Die Serie hat Gewinner-Zeilen und der Anker ist eine davon -> 'ok'.
      2. Die Serie hat Gewinner-Zeilen, aber der Anker ist keine mehr (seine
         Zeigung ist weggefallen oder zur Doppelung geworden) -> auf die
         frueheste Gewinner-Zeigung umhaengen, 'neu_verknuepft'.
      3. Keine Gewinner-Zeile unter dem Schluessel: der Doppelungs-Buchung von
         Anker und Ex-Mitgliedern folgen. Fuehrt sie auf eine Gewinner-Zeile,
         zieht das Herz MITSAMT Schluessel dorthin um ("Ostpol Dresden" ->
         "Ostpol") -> 'neu_verknuepft'.
      4. Noch nicht am Ende: identity_key + Tag -> 'neu_verknuepft'.
      5. Nichts davon -> 'verwaist'. Das Herz bleibt stehen und lebt vom
         Schnappschuss; die kuratierte Seite markiert es.

    Gibt (event_uid, run_key, members, link_status, relinked_from) zurueck.
    """
    old_uid = heart["event_uid"]
    key = heart["run_key"]
    members = run_members(conn, key)

    if members:
        if any(m["uid"] == old_uid for m in members):
            return old_uid, key, members, "ok", heart.get("relinked_from")
        return members[0]["uid"], key, members, "neu_verknuepft", old_uid

    candidates = [old_uid] + [u for u in _member_uids(heart) if u != old_uid]
    for uid in candidates:
        canonical = _canonical_uid(conn, uid)
        if not canonical:
            continue
        winner = event_for_uid(conn, canonical)
        if winner is None or winner["duplicate_of"] is not None:
            continue
        new_key = normalize.run_key_for_event(winner)
        return (winner["uid"], new_key, run_members(conn, new_key) or [winner],
                "neu_verknuepft", old_uid)

    fallback = _winner_by_identity(conn, heart["identity_key"], key.split("|", 1)[0])
    if fallback is not None:
        new_key = normalize.run_key_for_event(fallback)
        return (fallback["uid"], new_key, run_members(conn, new_key) or [fallback],
                "neu_verknuepft", old_uid)

    return old_uid, key, [], "verwaist", heart.get("relinked_from")


def _member_uids(heart):
    try:
        return json.loads(heart.get("member_uids") or "[]")
    except ValueError:
        return []


def _write_heart(conn, heart, resolved, note=None, created_at=None):
    """Schreibt ein aufgeloestes Herz. Der Schnappschuss wird dabei aus der
    lebenden Ankerzeile aufgefrischt, solange es eine gibt - ein Schnappschuss
    soll den LETZTEN bekannten guten Stand halten, nicht den ersten."""
    uid, key, members, status, relinked_from = resolved
    anchor = next((m for m in members if m["uid"] == uid), None)
    if anchor is None:
        anchor = event_for_uid(conn, uid)
    now = datetime.utcnow().isoformat()
    snap = {
        "identity_key": (anchor or {}).get("identity_key") or heart["identity_key"],
        "snap_title": (anchor or {}).get("title") or heart["snap_title"],
        "snap_date": (anchor or {}).get("date") or heart["snap_date"],
        "snap_time": (anchor or {}).get("time") if anchor else heart.get("snap_time"),
        "snap_venue": (anchor or {}).get("venue") if anchor else heart.get("snap_venue"),
        "snap_url": (anchor or {}).get("url") if anchor else heart.get("snap_url"),
        "snap_source": (anchor or {}).get("source") if anchor else heart.get("snap_source"),
    }
    # Bei 'verwaist' gibt es keine lebenden Mitglieder mehr - dann bleibt die
    # ALTE Liste stehen. Sie mit [] zu ueberschreiben waere der stille Verlust
    # der Kandidaten, ueber die ein spaeterer Lauf das Herz wieder anknuepfen
    # koennte (_resolve_heart, Schritt 3).
    member_uids = json.dumps([m["uid"] for m in members]) if members \
        else (heart.get("member_uids") or json.dumps([]))
    conn.execute(
        """INSERT INTO hearts (event_uid, run_key, identity_key, snap_title,
                               snap_date, snap_time, snap_venue, snap_url,
                               snap_source, member_uids, note, sort_order,
                               link_status, relinked_from, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(run_key) DO UPDATE SET
             event_uid = excluded.event_uid, identity_key = excluded.identity_key,
             snap_title = excluded.snap_title, snap_date = excluded.snap_date,
             snap_time = excluded.snap_time, snap_venue = excluded.snap_venue,
             snap_url = excluded.snap_url, snap_source = excluded.snap_source,
             member_uids = excluded.member_uids, note = excluded.note,
             link_status = excluded.link_status,
             relinked_from = excluded.relinked_from,
             updated_at = excluded.updated_at""",
        (uid, key, snap["identity_key"], snap["snap_title"], snap["snap_date"],
         snap["snap_time"], snap["snap_venue"], snap["snap_url"], snap["snap_source"],
         member_uids,
         heart.get("note") if note is None else note,
         heart.get("sort_order") or 0, status, relinked_from,
         created_at or heart.get("created_at") or now, now),
    )


def get_heart(conn, run_key):
    row = conn.execute("SELECT * FROM hearts WHERE run_key = ?", (run_key,)).fetchone()
    return dict(row) if row else None


def heart_for_uid(conn, uid):
    """Das Herz, an dem diese Zeigung haengt - als Anker ODER als Mitglied der
    Serie. Der Loesch-Schutz in _delete_orphaned_event() braucht die zweite
    Haelfte: geherzt ist die Serie, nicht nur ihre frueheste Zeigung."""
    row = conn.execute("SELECT * FROM hearts WHERE event_uid = ?", (uid,)).fetchone()
    if row:
        return dict(row)
    for candidate in conn.execute("SELECT * FROM hearts").fetchall():
        heart = dict(candidate)
        if uid in _member_uids(heart):
            return heart
    return None


def set_heart(conn, uid, note=None):
    """Herzt die SERIE, zu der diese Zeigung gehoert (Entscheidung #26).

    Zeigt die uid auf eine ausgeblendete Doppelung, gilt das Herz dem Eintrag,
    den die Liste an ihrer Stelle zeigt - sonst legte ein Klick ein Herz an,
    das von Anfang an unsichtbar ist.

    Gibt (herz, neu) zurueck - (None, False), wenn die uid unbekannt ist. Das
    Flag ist nicht Kosmetik: zwei Zeigungen derselben Serie sind zwei Zeilen mit
    demselben Schluessel (eine Doppelvorstellung faellt unter RUN_MIN_SIZE und
    bleibt ungefaltet). Ohne das Flag zaehlte der zweite Klick ein zweites Mal
    in die Gewichte, obwohl sich am Herzen nichts aendert."""
    event = event_for_uid(conn, uid)
    if event is None:
        return None, False
    if event["duplicate_of"] is not None:
        canonical = _canonical_uid(conn, uid)
        event = event_for_uid(conn, canonical) if canonical else event

    key = normalize.run_key_for_event(event)
    seed = {
        "event_uid": event["uid"], "run_key": key,
        "identity_key": event["identity_key"], "snap_title": event["title"],
        "snap_date": event["date"], "snap_time": event.get("time"),
        "snap_venue": event.get("venue"), "snap_url": event.get("url"),
        "snap_source": event.get("source"), "member_uids": None,
        "note": note, "sort_order": 0, "relinked_from": None,
        "created_at": None,
    }
    existing = get_heart(conn, key)
    if existing:
        seed = dict(existing, note=existing.get("note") if note is None else note)
    _write_heart(conn, seed, _resolve_heart(conn, seed), note=note)
    return get_heart(conn, key), existing is None


def remove_heart(conn, run_key):
    cursor = conn.execute("DELETE FROM hearts WHERE run_key = ?", (run_key,))
    return cursor.rowcount > 0


def hearted_run_keys(conn):
    """Die Schluessel aller Herzen - das ist alles, was die Liste im Browser
    braucht, um eine Zeile als geherzt zu zeichnen (eine Abfrage statt einer
    pro Event)."""
    return [row["run_key"] for row in
            conn.execute("SELECT run_key FROM hearts ORDER BY run_key").fetchall()]


def list_hearts(conn):
    """Die kuratierte Seite: je Herz die LEBENDEN Zeilen der Serie, und nur
    wenn es keine mehr gibt, der Schnappschuss."""
    out = []
    rows = conn.execute(
        "SELECT * FROM hearts ORDER BY snap_date ASC, sort_order ASC, "
        "snap_time IS NULL, snap_time ASC").fetchall()
    for row in rows:
        heart = dict(row)
        members = run_members(conn, heart["run_key"])
        first = members[0] if members else None
        out.append({
            "run_key": heart["run_key"],
            "uid": heart["event_uid"],
            "status": heart["link_status"],
            "note": heart["note"],
            "live": bool(members),
            "count": len(members),
            "date": first["date"] if first else heart["snap_date"],
            "times": [m["time"] for m in members] if members else [heart["snap_time"]],
            "title": first["title"] if first else heart["snap_title"],
            "venue": first["venue"] if first else heart["snap_venue"],
            "venue_slug": first.get("venue_slug") if first else None,
            "url": (first.get("url") if first else heart["snap_url"]),
            "image_url": first.get("image_url") if first else None,
            "category": first.get("category") if first else None,
            "source": first.get("source") if first else heart["snap_source"],
        })
    return out


def relink_hearts(conn):
    """Nach JEDEM Scrape (und nach dedup.link_duplicates, nicht davor): jedes
    Herz wieder auf eine Zeile ziehen, die die Liste auch zeigt.

    Gibt {'ok': n, 'neu_verknuepft': n, 'verwaist': n} zurueck."""
    summary = {"ok": 0, "neu_verknuepft": 0, "verwaist": 0}
    for row in conn.execute("SELECT * FROM hearts").fetchall():
        heart = dict(row)
        resolved = _resolve_heart(conn, heart)
        new_uid, new_key, _members, status, _from = resolved
        if new_key != heart["run_key"]:
            # Der Schluessel selbst wandert (Doppelung mit anderer Ortsschreib-
            # weise). Die alte Zeile muss weg, bevor der UNIQUE-Index auf
            # run_key zuschlaegt.
            conn.execute("DELETE FROM hearts WHERE run_key = ?", (heart["run_key"],))
        _write_heart(conn, heart, resolved)
        summary[status] += 1
        if status != "ok":
            logger.warning(
                "Herz %s: %s (Anker %s -> %s, Schluessel %s -> %s)",
                heart["snap_title"], status, heart["event_uid"], new_uid,
                heart["run_key"], new_key,
            )
    if summary["ok"] or summary["neu_verknuepft"] or summary["verwaist"]:
        logger.info("Herzen geprueft: %d ok, %d neu verknuepft, %d verwaist.",
                    summary["ok"], summary["neu_verknuepft"], summary["verwaist"])
    return summary


def venues_geo(conn):
    """Alle verorteten Venues als Nachschlagewerk fuer die Kartenansicht.

    Schmal gehalten, weil die Datei bei jedem Kartenaufruf ueber die Leitung
    geht und sich fast nie aendert: Name, Koordinaten, Region, Art. Alles
    andere (Cover, Beschreibung, Telefon) steht auf der Ortsseite, die von der
    Nadel aus einen Klick entfernt ist.

    Kurze Schluessel (n/r/k statt name/region/kind) - bei ~460 Orten macht das
    im Export rund ein Viertel der Dateigroesse aus.

    Treffpunkte fehlen hier wie ueberall (siehe list_venues), Venues ohne
    Koordinaten ebenso: NULL heisst "kein Standort bekannt" und ist eine
    gueltige Antwort, keine Luecke zum Auffuellen (siehe
    migrations/002_venue_geo.sql).
    """
    rows = conn.execute(
        "SELECT slug, name, lat, lon, region, kind FROM venues "
        "WHERE lat IS NOT NULL AND lon IS NOT NULL AND is_meeting_point = 0"
    ).fetchall()
    return {
        r["slug"]: {"n": r["name"], "lat": r["lat"], "lon": r["lon"],
                    "r": r["region"], "k": r["kind"]}
        for r in rows
    }

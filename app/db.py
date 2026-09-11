"""SQLite-Zugriff: Schema, Events speichern/lesen, Reaktionen verbuchen.

Seit P3 (Schema v2, siehe migrations/001_schema_v2.sql + migrations/CUTOVER.md):
Venues und Kategorien sind erstklassige Zeilen statt Freitext-Spalten. Es gibt
KEINE Migration aus v1 - eine neue DB startet leer und wird von den Scrapern
neu gefuellt (siehe CUTOVER.md). Die 10 Scraper selbst liefern unveraendert
Dicts mit Freitext-`venue`/`category`; die Aufloesung passiert ausschliesslich
hier in upsert_events()."""
import hashlib
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

# P3-Zusatz, NICHT Teil von migrations/001_schema_v2.sql: P2s Entwurf laesst
# `reactions` bewusst weg ("wird von Herzen abgeloest", siehe DDL Abschnitt 6),
# aber die Herzen-Funktion (kuratierte Auswahl, Wiederanknuepfung ueber
# identity_key) ist in diesem Paket nicht gebaut - nur die Tabelle `hearts`
# steht schon in der DDL. Ohne `reactions` waeren David's 👍/👎 ersatzlos weg,
# bevor ein Ersatz existiert (scoring.apply_reaction, /api/feedback,
# tests_smoke.py haengen aktiv daran). Deshalb bleibt reactions als
# Zusatztabelle bestehen, bis ein spaeteres Paket sie wirklich durch Herzen
# ersetzt - siehe Bericht zu P3.
REACTIONS_ADDENDUM = """
CREATE TABLE IF NOT EXISTS reactions (
    event_uid TEXT PRIMARY KEY,
    reaction TEXT NOT NULL CHECK(reaction IN ('like', 'skip')),
    created_at TEXT NOT NULL
);
"""


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
        conn.executescript(REACTIONS_ADDENDUM)
        _seed_tags(conn)


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
    query = ("SELECT e.*, e.category_slug AS category, e.raw_venue AS venue, "
             "v.region AS region "
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

    - Eine Zeile mit Reaktion wird NIE geloescht: data/ enthaelt die einzige
      Kopie der Reaktionen, und liked_events() verbindet reactions -> events -
      eine geloeschte Zeile liesse einen Favoriten kommentarlos verschwinden.
    - Ist die Zeile CANONICAL einer Doppelung, werden ihre Duplikate zuerst
      entkoppelt (unlink_duplicate): sonst zeigt deren duplicate_of ins Leere
      und ein echtes, weiterhin gescraptes Event bliebe fuer immer ausgeblendet.
    - Ist die Zeile selbst als Duplikat verbucht, wird diese Buchung mitgeloescht
      - sonst zeigt sie auf eine nicht mehr existierende Zeile.

    Gibt True zurueck, wenn tatsaechlich geloescht wurde.
    """
    uid = row["uid"]
    if get_reaction(conn, uid) is not None:
        logger.warning(
            "Verwaistes Event NICHT geloescht (hat eine Reaktion): %s \"%s\" (%s, %s)",
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


def get_reaction(conn, event_uid):
    row = conn.execute(
        "SELECT reaction FROM reactions WHERE event_uid = ?", (event_uid,)
    ).fetchone()
    return row["reaction"] if row else None


def set_reaction(conn, event_uid, reaction):
    conn.execute(
        """INSERT INTO reactions (event_uid, reaction, created_at) VALUES (?, ?, ?)
           ON CONFLICT(event_uid) DO UPDATE SET reaction = excluded.reaction,
                                                  created_at = excluded.created_at""",
        (event_uid, reaction, datetime.utcnow().isoformat()),
    )


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


def liked_events(conn, limit=30):
    # Wurde die als Doppelung ausgeblendete Version geliket, erscheint hier der
    # Eintrag, der sie ersetzt (COALESCE auf duplicate_of) - sonst würde ein
    # Favorit ohne Vorwarnung aus der Liste verschwinden. GROUP BY, damit ein
    # beidseitig gelikter Doppeleintrag nur einmal auftaucht.
    rows = conn.execute(
        """SELECT c.* FROM reactions r
           JOIN events e ON e.uid = r.event_uid
           JOIN events c ON c.uid = COALESCE(e.duplicate_of, e.uid)
           WHERE r.reaction = 'like'
           GROUP BY c.uid
           ORDER BY MAX(r.created_at) DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]

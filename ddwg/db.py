"""Die Event-Datenbank - ein Wegwerf-Cache.

Alles Kuratierte steht in orte/orte.json (ddwg/orte.py). Diese Datenbank haelt
nur, was sich aus den Quellen jederzeit neu holen laesst. Wer sie loescht,
verliert nichts ausser dem letzten Scrape; `python -m ddwg scrape` baut sie neu.

Vier Tabellen, in einer Richtung:

    listings        eine Zeile je Quelle und Termin, so wie die Quelle ihn
                    liefert. Je Quelle wird bei jedem ERFOLGREICHEN Lauf alles
                    ersetzt; ein fehlgeschlagener Lauf laesst die alten Zeilen
                    stehen (lieber ein Tag alt als leer).
    events          ein realer Termin, aus einer Gruppe von listings
                    verschmolzen (ddwg/merge.py). Wird nach jedem Scrape
                    KOMPLETT neu gebaut - es gibt kein duplicate_of und kein
                    "Gewinner"-Praedikat, das eine Abfrage kennen muesste.
    event_listings  welche listings in welchem Event stecken (Nachvollziehbarkeit).
    scrape_runs     je Quelle und Lauf: ok, Anzahl, Fehler. Der einzige Weg,
                    einen kaputten Selektor von einem ruhigen Tag zu
                    unterscheiden (siehe pipeline.scrape_quelle).
    details         nachgeladene Detailseiten (Beschreibung/Preis/Bild) je URL.
                    Ueberlebt den Neuaufbau von events, damit keine Seite
                    zweimal geholt wird.
"""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get(
    "DDWG_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache", "events.db"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id           INTEGER PRIMARY KEY,
    source       TEXT NOT NULL,
    uid          TEXT NOT NULL,
    date         TEXT NOT NULL,
    time         TEXT,
    title        TEXT NOT NULL,
    ort          TEXT,
    ort_roh      TEXT,
    category     TEXT,
    raw_category TEXT,
    url          TEXT,
    image_url    TEXT,
    description  TEXT,
    price_text   TEXT,
    scraped_at   TEXT NOT NULL,
    UNIQUE (source, uid)
);
CREATE INDEX IF NOT EXISTS idx_listings_date ON listings(date);

CREATE TABLE IF NOT EXISTS events (
    uid          TEXT PRIMARY KEY,
    date         TEXT NOT NULL,
    time         TEXT,
    title        TEXT NOT NULL,
    ort          TEXT,
    ort_roh      TEXT,
    category     TEXT NOT NULL,
    url          TEXT,
    image_url    TEXT,
    description  TEXT,
    price_text   TEXT,
    sources      TEXT NOT NULL,
    region       TEXT NOT NULL,
    laufend      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);
CREATE INDEX IF NOT EXISTS idx_events_ort ON events(ort);

CREATE TABLE IF NOT EXISTS event_listings (
    uid        TEXT NOT NULL,
    listing_id INTEGER NOT NULL,
    PRIMARY KEY (uid, listing_id)
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    ok          INTEGER NOT NULL,
    event_count INTEGER,
    dropped     INTEGER,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS details (
    url         TEXT PRIMARY KEY,
    description TEXT,
    price_text  TEXT,
    image_url   TEXT,
    fetched_at  TEXT NOT NULL
);
"""

LISTING_FIELDS = (
    "source", "uid", "date", "time", "title", "ort", "ort_roh", "category",
    "raw_category", "url", "image_url", "description", "price_text", "scraped_at",
)
EVENT_FIELDS = (
    "uid", "date", "time", "title", "ort", "ort_roh", "category", "url",
    "image_url", "description", "price_text", "sources", "region", "laufend",
)


@contextmanager
def connect(path=None):
    path = path or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --- listings ----------------------------------------------------------------

def replace_listings(conn, source, rows):
    """Alle Zeilen einer Quelle durch `rows` ersetzen (dicts mit LISTING_FIELDS).
    Doppelte (source, uid) innerhalb eines Laufs: die erste gewinnt."""
    conn.execute("DELETE FROM listings WHERE source = ?", (source,))
    placeholders = ",".join("?" for _ in LISTING_FIELDS)
    conn.executemany(
        f"INSERT OR IGNORE INTO listings ({','.join(LISTING_FIELDS)}) VALUES ({placeholders})",
        [tuple(row.get(f) for f in LISTING_FIELDS) for row in rows],
    )


def listings(conn, start_date=None):
    query = "SELECT * FROM listings"
    params = ()
    if start_date:
        query += " WHERE date >= ?"
        params = (start_date,)
    return [dict(r) for r in conn.execute(query + " ORDER BY date, time, id", params)]


# --- events ------------------------------------------------------------------

def replace_events(conn, events):
    """events: [(event_dict, [listing_ids])]. Ersetzt Tabelle events komplett."""
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM event_listings")
    placeholders = ",".join("?" for _ in EVENT_FIELDS)
    conn.executemany(
        f"INSERT INTO events ({','.join(EVENT_FIELDS)}) VALUES ({placeholders})",
        [tuple(ev.get(f) for f in EVENT_FIELDS) for ev, _ids in events],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO event_listings (uid, listing_id) VALUES (?, ?)",
        [(ev["uid"], lid) for ev, ids in events for lid in ids],
    )


def events(conn, start_date=None, end_date=None):
    query = "SELECT * FROM events WHERE 1=1"
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " ORDER BY date, COALESCE(time, '99:99'), title"
    return [dict(r) for r in conn.execute(query, params)]


# --- details -----------------------------------------------------------------

def details(conn):
    return {r["url"]: dict(r) for r in conn.execute("SELECT * FROM details")}


def save_detail(conn, url, description, price_text, image_url, fetched_at):
    conn.execute(
        """INSERT INTO details (url, description, price_text, image_url, fetched_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(url) DO UPDATE SET description = excluded.description,
               price_text = excluded.price_text, image_url = excluded.image_url,
               fetched_at = excluded.fetched_at""",
        (url, description, price_text, image_url, fetched_at),
    )


# --- scrape_runs -------------------------------------------------------------

def record_run(conn, source, started_at, finished_at, ok, event_count=None,
               dropped=None, error=None):
    conn.execute(
        """INSERT INTO scrape_runs (source, started_at, finished_at, ok, event_count, dropped, error)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (source, started_at, finished_at, 1 if ok else 0, event_count, dropped, error),
    )


def last_ok_run(conn, source):
    row = conn.execute(
        "SELECT * FROM scrape_runs WHERE source = ? AND ok = 1 ORDER BY id DESC LIMIT 1",
        (source,),
    ).fetchone()
    return dict(row) if row else None


def last_runs(conn):
    """Je Quelle der letzte Lauf (egal ob ok) plus der letzte erfolgreiche."""
    out = {}
    for row in conn.execute("SELECT * FROM scrape_runs ORDER BY id"):
        out.setdefault(row["source"], {})["letzter"] = dict(row)
        if row["ok"]:
            out[row["source"]]["letzter_ok"] = dict(row)
    return out

"""SQLite-Zugriff: Schema, Events speichern/lesen, Reaktionen verbuchen."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from . import config, geo

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    uid TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT,
    title TEXT NOT NULL,
    venue TEXT,
    category TEXT NOT NULL,
    raw_category TEXT,
    url TEXT,
    image_url TEXT,
    price_text TEXT,
    description TEXT,
    detail_fetched_at TEXT,
    -- Gesetzt, wenn dieser Eintrag dieselbe Veranstaltung meint wie ein
    -- anderer aus einer Quelle mit höherer Priorität (siehe app/dedup.py).
    -- Solche Zeilen bleiben erhalten, werden aber nicht mehr ausgeliefert.
    duplicate_of TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reactions (
    event_uid TEXT PRIMARY KEY,
    reaction TEXT NOT NULL CHECK(reaction IN ('like', 'skip')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weights (
    key TEXT PRIMARY KEY,
    likes INTEGER NOT NULL DEFAULT 0,
    skips INTEGER NOT NULL DEFAULT 0
);

-- Welche Quellen denselben Eintrag geliefert haben. Nötig, weil die zweite,
-- ältere Art von Doppelung sonst unsichtbar bleibt: schreiben zwei Quellen
-- Datum, Zeit, Titel und Ort identisch, erzeugt normalize.make_event_uid()
-- dieselbe uid, und die zweite Lieferung aktualisiert stillschweigend die
-- erste Zeile (in events.source steht dann nur, wer zuerst da war).
CREATE TABLE IF NOT EXISTS event_sources (
    event_uid TEXT NOT NULL,
    source TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (event_uid, source)
);

-- Buchführung über erkannte Doppelungen zwischen Quellen: welcher Eintrag
-- wurde zugunsten welches anderen ausgeblendet, wie sicher und seit wann.
CREATE TABLE IF NOT EXISTS event_duplicates (
    duplicate_uid TEXT PRIMARY KEY,
    canonical_uid TEXT NOT NULL,
    duplicate_source TEXT,
    canonical_source TEXT,
    match_score REAL,
    matched_on TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

"""

# Die Indizes stehen bewusst NICHT im selben Skript wie die Tabellen: der Index
# auf events(duplicate_of) zeigt auf eine Spalte, die in Bestandsdatenbanken
# erst _migrate_schema() anlegt. Zusammen ausgeführt bricht executescript() auf
# jeder Datenbank ab, die vor der Doppelungs-Erkennung entstanden ist - und
# damit schon init_db() beim Containerstart. Deshalb: erst Tabellen, dann
# Migration, dann Indizes (siehe init_db).
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);
CREATE INDEX IF NOT EXISTS idx_events_duplicate_of ON events(duplicate_of);
CREATE INDEX IF NOT EXISTS idx_event_duplicates_canonical
    ON event_duplicates(canonical_uid);
CREATE INDEX IF NOT EXISTS idx_event_sources_uid ON event_sources(event_uid);
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


# Spalten, die nach dem ersten Release dazugekommen sind. SQLite kennt kein
# "ADD COLUMN IF NOT EXISTS", deshalb wird vor jedem ALTER geprüft.
_ADDED_EVENT_COLUMNS = {
    "image_url": "TEXT",
    "price_text": "TEXT",
    "description": "TEXT",
    "detail_fetched_at": "TEXT",
    "duplicate_of": "TEXT",
}


def _migrate_schema(conn):
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(events)")}
    for column, coltype in _ADDED_EVENT_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE events ADD COLUMN {column} {coltype}")


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate_schema(conn)
        conn.executescript(INDEXES)
        # Bestandsdaten nachtragen, damit event_sources auch für Events gefüllt
        # ist, die vor dieser Tabelle angelegt wurden.
        conn.execute(
            """INSERT OR IGNORE INTO event_sources (event_uid, source, first_seen, last_seen)
               SELECT uid, source, first_seen, last_seen FROM events"""
        )


def _record_source(conn, event_uid, source, now):
    """Hält fest, dass diese Quelle diesen Eintrag geliefert hat."""
    conn.execute(
        """INSERT INTO event_sources (event_uid, source, first_seen, last_seen)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(event_uid, source) DO UPDATE SET last_seen = excluded.last_seen""",
        (event_uid, source, now, now),
    )


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
    priority = config.SOURCE_PRIORITY

    def rank(name):
        return priority.index(name) if name in priority else len(priority)

    return rank(source) <= min(
        (rank(s) for s in sources_for_event(conn, event_uid)), default=rank(source)
    )


def upsert_events(conn, events):
    """events: Liste von dicts mit uid/source/date/time/title/venue/category/raw_category/url.
    Gibt die Anzahl neu eingefügter (bisher unbekannter) Events zurück."""
    now = datetime.utcnow().isoformat()
    new_count = 0
    for e in events:
        _record_source(conn, e["uid"], e["source"], now)
        existing = conn.execute(
            "SELECT uid, url FROM events WHERE uid = ?", (e["uid"],)
        ).fetchone()
        if existing:
            # Der Link einer besser platzierten Quelle bleibt stehen (siehe
            # _keeps_own_url); ist noch gar keiner da, füllt ihn jede Quelle.
            url = e.get("url")
            if url and existing["url"] and not _keeps_own_url(conn, e["uid"], e["source"]):
                url = None
            # COALESCE: Ein normaler Kulturkalender-Lauf liefert für die
            # Detail-Felder None - das darf einen bereits nachgeladenen Detail-
            # Cache nicht wieder ausnullen. Rauze liefert sie bei jedem Lauf
            # frisch mit und überschreibt damit bewusst (z.B. "ausverkauft").
            conn.execute(
                """UPDATE events SET last_seen = ?,
                     url = COALESCE(?, url),
                     image_url = COALESCE(?, image_url),
                     price_text = COALESCE(?, price_text),
                     description = COALESCE(?, description),
                     detail_fetched_at = COALESCE(?, detail_fetched_at)
                   WHERE uid = ?""",
                (
                    now, url, e.get("image_url"), e.get("price_text"),
                    e.get("description"), e.get("detail_fetched_at"), e["uid"],
                ),
            )
        else:
            new_count += 1
            conn.execute(
                """INSERT INTO events
                   (uid, source, date, time, title, venue, category, raw_category, url,
                    image_url, price_text, description, detail_fetched_at, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["uid"], e["source"], e["date"], e.get("time"), e["title"],
                    e.get("venue"), e["category"], e.get("raw_category"),
                    e.get("url"), e.get("image_url"), e.get("price_text"),
                    e.get("description"), e.get("detail_fetched_at"), now, now,
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
    query = "SELECT * FROM events WHERE date >= ? AND date <= ?"
    if not include_duplicates:
        query += " AND duplicate_of IS NULL"
    params = [start_date, end_date]
    categories = category_filter(category)
    if categories:
        placeholders = ",".join("?" for _ in categories)
        query += f" AND category IN ({placeholders})"
        params.extend(categories)
    if exclude_categories:
        placeholders = ",".join("?" for _ in exclude_categories)
        query += f" AND category NOT IN ({placeholders})"
        params.extend(exclude_categories)
    query += " ORDER BY date ASC, time ASC"
    events = [dict(row) for row in conn.execute(query, params).fetchall()]
    # Zusatzfeld fürs Web.
    ongoing = _ongoing_titles(conn)
    for event in events:
        event["ongoing"] = event["title"] in ongoing
        # Ortszuordnung wie ongoing bewusst beim Lesen und nicht als Spalte:
        # die Listen in app/geo.py wachsen weiter, und eine gespeicherte
        # Zuordnung müsste nach jeder Ergänzung nachgezogen werden.
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
    und das Duplikat den echten Ort kennt."""
    conn.execute("UPDATE events SET venue = ? WHERE uid = ?", (venue, uid))


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
        """SELECT e.uid, e.date, e.time, e.title, e.venue,
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
                  dup.title AS duplicate_title, dup.venue AS duplicate_venue,
                  dup.date AS date, dup.time AS duplicate_time,
                  can.title AS canonical_title, can.venue AS canonical_venue,
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

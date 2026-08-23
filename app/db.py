"""SQLite-Zugriff: Schema, Events speichern/lesen, Reaktionen verbuchen."""
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from . import config, geo

logger = logging.getLogger("dd-was-geht.db")

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

-- Ein Lauf je Quelle und Scrape. Ohne diese Buchführung sieht eine Quelle, die
-- nach einer HTML-Änderung 0 Events liefert, exakt aus wie ein ruhiger Tag:
-- die Liste ist kürzer, aber nichts sagt, dass etwas kaputt ist. Erst der
-- Vergleich mit dem letzten ERFOLGREICHEN Lauf macht daraus ein Signal
-- (siehe scheduler.run_scrape und /api/health).
CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    ok INTEGER NOT NULL DEFAULT 0,
    event_count INTEGER,
    error TEXT
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
CREATE INDEX IF NOT EXISTS idx_scrape_runs_source ON scrape_runs(source, started_at);
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

    Es wird über SOURCE_LABELS iteriert und nicht über die Tabelle: eine Quelle,
    die noch nie gelaufen ist, muss auftauchen - genau das ist ja der Ausfall,
    den man sehen will.
    """
    health = {}
    for source, label in config.SOURCE_LABELS.items():
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


def find_orphaned_events(conn, today, threshold_runs=3):
    """Zukuenftige Events je Quelle, die ihre eigene Quelle seit threshold_runs
    erfolgreichen Laeufen nicht mehr geliefert hat.

    Zwei Schutzklauseln, beide zwingend:
    - Nur date >= today: vergangene Events sind historischer Bestand und durch
      Re-Scraping nicht wiederherstellbar - die werden hier nie angefasst.
    - Nur Quellen, deren LETZTER Lauf laut scrape_runs ok=1 war: sonst wuerde
      ein Quellen-Ausfall (der Fall, den scrape_runs erst sichtbar macht) die
      komplette Zukunft dieser Quelle als "verwaist" markieren, obwohl sie nur
      gerade nicht erreichbar ist.

    Gibt ein dict source -> Liste von Event-Zeilen zurueck (nur Quellen mit
    Treffern).
    """
    result = {}
    for source in config.SOURCE_LABELS:
        latest = _last_run(conn, source)
        if not latest or not latest["ok"]:
            continue
        cutoff = _successful_run_cutoff(conn, source, threshold_runs)
        if cutoff is None:
            continue
        rows = conn.execute(
            """SELECT uid, title, date, time, venue, last_seen FROM events
               WHERE source = ? AND date >= ? AND last_seen < ?
               ORDER BY date, time""",
            (source, today, cutoff),
        ).fetchall()
        if rows:
            result[source] = [dict(r) for r in rows]
    return result


def _delete_orphaned_event(conn, source, row):
    """Loescht EINE verwaiste Zeile - mit den drei Schutzklauseln, die der
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


def expire_orphaned_events(conn, today, threshold_runs=3, dry_run=True):
    """Meldet verwaiste Zukunfts-Events (siehe find_orphaned_events) und
    loescht sie, sofern dry_run=False - mit Anzahl und ein paar Beispieltiteln
    je Quelle im Log, dazu je geloeschter (oder uebersprungener) Zeile eine
    eigene Zeile mit ihrer uid, dem einzigen Weg, eine Loeschung nachzuvollziehen.
    """
    orphaned = find_orphaned_events(conn, today, threshold_runs)
    total = sum(len(rows) for rows in orphaned.values())
    if not total:
        logger.info("Verwaiste Events: keine gefunden (Schwelle %d Laeufe).", threshold_runs)
        return orphaned

    for source, rows in orphaned.items():
        label = config.SOURCE_LABELS.get(source, source)
        samples = ", ".join(f'"{r["title"]}"' for r in rows[:3])
        logger.warning(
            "Verwaiste Events bei %s: %d seit %d erfolgreichen Laeufen nicht "
            "mehr gesehen. Beispiele: %s",
            label, len(rows), threshold_runs, samples,
        )
    logger.warning(
        "Verwaiste Events insgesamt: %d ueber %d Quelle(n). dry_run=%s.",
        total, len(orphaned), dry_run,
    )

    if not dry_run:
        for source, rows in orphaned.items():
            for row in rows:
                _delete_orphaned_event(conn, source, row)

    return orphaned

    if not dry_run:
        raise NotImplementedError(
            "Scharf schalten folgt in einem eigenen zweiten Commit, erst nach "
            "einem beobachteten Dry-Run-Lauf (siehe Kommentar bei expire_orphaned_events)."
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

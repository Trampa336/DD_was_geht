"""Einmalige Venue-Vorbefuellung fuer Schema v2 (siehe migrations/CUTOVER.md §3).

Zieht die Rohstrings der Gewinner-Zukunftsevents aus einer eingefrorenen v1-DB,
legt daraus venues + venue_aliases in einer (leeren) Schema-v2-DB an und setzt
region ueber das bestehende app/geo.py sowie kind fuer die Top-N Venues nach
Eventzahl.

Muss VOR dem ersten Scrape gegen die Ziel-DB laufen, sonst legt der erste
Scrape-Lauf die Venues in zufaelliger Reihenfolge an (CUTOVER.md §3).

Wiederverwendet ganz bewusst db.resolve_venue()/db.venue_slug() - dieselbe
Funktion, die auch der laufende Schreibpfad fuer unbekannte Rohstrings
benutzt. Zwei getrennte Implementierungen derselben Kollaps-Regel wuerden
frueher oder spaeter auseinanderlaufen (eine Schreibweise, die die Seeding-
Regel zusammenlegt, die Laufzeit-Regel aber nicht, legt eine zweite Venue an).

Aufruf:
    ../.venv/bin/python tools/seed_venues.py <frozen_v1.db> <target_v2.db> [--apply]
    (ohne --apply: nur Bericht, nichts geschrieben)
"""
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, geo, normalize  # noqa: E402

# Top-N nach Eventzahl bekommen ein kuratiertes `kind` - siehe DDL §1: 634 von
# 1179 Fuehrungen stecken in 6 Venues, die Top-120 tragen den Grossteil des
# Katalogs. Alles danach bleibt bewusst 'sonstiges' (P2s "langer Schwanz").
TOP_N_FOR_KIND = 120

# Explizite Treffer zuerst - fuer die Haeuser, die P2 namentlich in der DDL
# nennt, und fuer is_meeting_point (Stadtrundfahrt-Treffpunkte, keine echten
# Spielstaetten). Schluessel ist der db.venue_slug()-Kollapsschluessel.
EXPLICIT_KIND = {
    "hochstift-meissen": "kirche",              # Dom zu Meissen
    # venue_slug() entfernt Klammerzusaetze VOR dem Slugifizieren (DDL §1) -
    # "Schloss Wackerbarth (Sächs. Staatsweingut)" wird also "schloss-
    # wackerbarth", nicht "...-saechs-staatsweingut". Dieselbe Regel gilt fuer
    # jeden Rohstring hier - Schluessel sind IMMER der Slug OHNE Klammerinhalt.
    "schloss-wackerbarth": "weingut",
    "erlebniswelt-meissen": "museum",
    "terrassenufer": "treffpunkt",
    "frauenkirche": "kirche",
    # "Dresden City" verliert "dresden" ueber _VENUE_DROP_WORDS - Slug ist "city".
    "city": "treffpunkt",
    "theaterplatz": "treffpunkt",
    "zwinger": "museum",
    "comoedie": "theater",
    "st-pauli-ruine": "buehne",
    "riesa-efau": "galerie",
}
EXPLICIT_MEETING_POINT = {"terrassenufer", "city", "theaterplatz"}

# Bekannte Musik-/Nightlife-Haeuser aus app/registry.py (eigene Quelle oder
# EXTRA_VENUE_ALIASES-Ziel) - diese sind sicher 'club', keine Heuristik noetig.
_KNOWN_CLUB_WORDS = (
    "sektor-evolution", "conni", "der-lude", "strasse-e", "groovestation",
    "zentralwerk", "objekt-klein-a", "chemiefabrik", "beatpol",
    "kraftwerk-mitte", "tante-ju", "puschkin", "cafe-zeitlos", "cafe-saite",
    "blaue-fabrik", "ostpol", "biergarten", "trinitatis",
)

_KEYWORD_KIND = (
    # Reihenfolge zaehlt: erster Treffer gewinnt.
    (("museum", "sammlung", "ausstellungshaus", "schloss", "gedenkstaette"), "museum"),
    (("kirche", "dom", "kloster", "kathedrale", "kapelle", "kreuzkirche"), "kirche"),
    (("kino", "filmnaechte", "lichtspiel", "kristallpalast", "rundkino",
      "programmkino"), "kino"),
    (("theater", "oper", "schauspiel", "kabarett"), "theater"),
    (("kulturpalast", "kulturhaus", "buehne", "saal", "halle"), "buehne"),
    (("galerie", "kunstverein", "kunsthaus"), "galerie"),
    (("weingut", "weinberg", "winzer", "weinkeller"), "weingut"),
    (_KNOWN_CLUB_WORDS, "club"),
    (("park", "garten"), "park"),
)


def guess_kind(slug):
    if slug in EXPLICIT_KIND:
        return EXPLICIT_KIND[slug]
    # normalize._FILM_VENUE_RE ist die bereits kuratierte, kurze Liste
    # Dresdner Kino-Spielstaetten (siehe normalize._is_film_venue) -
    # wiederverwendet statt ein zweites Mal von Hand aufgezaehlt.
    if normalize._FILM_VENUE_RE.search(slug):
        return "kino"
    for words, kind in _KEYWORD_KIND:
        if any(w in slug for w in words):
            return kind
    return "sonstiges"


def load_raw_venues(source_db_path):
    """[(raw_venue, count), ...], absteigend - Gewinner-Zukunftsevents wie in
    P2s Messung (migrations/001_schema_v2.sql §1: 744 Strings)."""
    conn = sqlite3.connect(f"file:{source_db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    today = date.today().isoformat()
    rows = conn.execute(
        """SELECT venue, COUNT(*) AS c FROM events
           WHERE duplicate_of IS NULL AND date >= ? AND venue IS NOT NULL AND venue != ''
           GROUP BY venue ORDER BY c DESC""",
        (today,),
    ).fetchall()
    conn.close()
    return [(r["venue"], r["c"]) for r in rows]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    if len(args) != 2:
        print(__doc__)
        sys.exit(1)
    source_path, target_path = args

    raw_venues = load_raw_venues(source_path)
    print(f"{len(raw_venues)} Rohstrings aus {source_path} gezogen "
          f"({sum(c for _, c in raw_venues)} Events).")

    target = sqlite3.connect(target_path)
    target.row_factory = sqlite3.Row
    target.execute("PRAGMA foreign_keys = ON")

    existing_venues = target.execute("SELECT COUNT(*) AS c FROM venues").fetchone()["c"]
    if existing_venues:
        print(f"ABBRUCH: {target_path} hat bereits {existing_venues} Venues - "
              "Vorbefuellung ist nur fuer eine leere DB gedacht (siehe CUTOVER.md §3).")
        sys.exit(1)

    now = datetime.utcnow().isoformat()
    slug_counts = defaultdict(int)
    for raw, count in raw_venues:
        venue_id = db.resolve_venue(target, raw, now)
        slug = target.execute("SELECT slug FROM venues WHERE id = ?", (venue_id,)).fetchone()["slug"]
        slug_counts[slug] += count

    venue_count = target.execute("SELECT COUNT(*) AS c FROM venues").fetchone()["c"]
    alias_count = target.execute("SELECT COUNT(*) AS c FROM venue_aliases").fetchone()["c"]
    print(f"-> {venue_count} venues, {alias_count} venue_aliases "
          f"(Kollaps: {len(raw_venues)} Rohstrings -> {venue_count} Venues).")

    # Top-N nach Eventzahl bekommen ein kuratiertes kind + is_meeting_point.
    top = sorted(slug_counts.items(), key=lambda kv: -kv[1])[:TOP_N_FOR_KIND]
    print(f"\nTop {len(top)} nach Eventzahl - kuratiertes kind:")
    kind_counts = defaultdict(int)
    for slug, count in top:
        kind = guess_kind(slug)
        is_meeting_point = 1 if slug in EXPLICIT_MEETING_POINT else 0
        kind_counts[kind] += 1
        target.execute(
            "UPDATE venues SET kind = ?, is_meeting_point = ? WHERE slug = ?",
            (kind, is_meeting_point, slug),
        )
    for kind, n in sorted(kind_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:12} {n}")

    if apply:
        target.commit()
        print(f"\n{venue_count} Venues geschrieben und committed.")
    else:
        target.rollback()
        print("\nNichts geschrieben (Probelauf). Mit --apply committen.")
    target.close()


if __name__ == "__main__":
    main()

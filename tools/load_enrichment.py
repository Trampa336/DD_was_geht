"""Uebertraegt data/venue_cache/enrichment.json in die Tabelle `venues` (P4c).

Warum getrennt von tools/enrich_venues.py: der Sweep holt und schreibt in
einem Rutsch. Der Cache liegt aber schon auf der Platte, und was fehlt, ist
allein das Schreiben - ohne einen einzigen neuen Request. Dieses Skript holt
NICHTS. Es ist damit auch nach einem abgebrochenen Sweep gefahrlos wiederhol-
bar.

ZUORDNUNG. Die Schluessel in enrichment.json sind `venues.id` als String -
NICHT der slug (target_venues() in enrich_venues.py selektiert v.id). Weil
zwischen Sweep und Ladelauf neu geseedet worden sein kann und `id` ein
AUTOINCREMENT ist, wird jede Zuordnung zusaetzlich ueber den gespeicherten
`name` gegengeprueft. Bei Abweichung wird die Zeile NICHT geschrieben,
sondern gemeldet.

IDEMPOTENZ. Geschrieben wird nur, wenn sich die Nutzlast gegenueber der
DB-Zeile tatsaechlich unterscheidet. Ein zweiter Lauf ohne neue Cache-Daten
fasst keine Zeile an und laesst insbesondere `meta_fetched_at` stehen. Damit
darf dieses Skript nach dem Rest-Sweep einfach erneut laufen.

`kind` wird NICHT angefasst. Der Cache traegt zwar ein vom Werkzeug
erschlossenes `kind`, aber die kuratierte Einstufung aus P3 ist die bessere
Quelle; die Abweichung ist eine Messgroesse (tools/kind_disagreement.py),
kein Schreibgrund.

COVER. Reihenfolge kk_cover_url -> og:image der Homepage. Gemessen in
tools/og_image_audit.py: von 34 og:image-Treffern sind nur 13 als Cover
brauchbar (Rest Logos, Favicons, CMS-Standardbilder, tote Links), waehrend
der KK-Medienslider fuer 104 von 104 Venues mit KK-Seite ein eigenes,
haustypisches Foto liefert. NICHT umkehren - siehe venues.cover_source unten.

ZWEI ABGELEITETE SPALTEN (P5a, ohne einen einzigen neuen Request):
  - homepage_root: scheme://netloc von homepage_url. 45 von 123 gespeicherten
    Homepages sind keine Site-Wurzeln, sondern /veranstaltungen/, /programm/,
    /spielplan/ - der Pfad, den die Venue selbst beim Kulturkalender
    hinterlegt hat. Ein "Homepage"-Knopf soll auf der echten Startseite
    landen; homepage_url bleibt daneben stehen fuer alles, was den vollen Pfad
    braucht.
  - cover_source: welche der beiden Quellen og_image_url tatsaechlich
    geliefert hat ('kulturkalender' | 'homepage' | NULL) - og_image_url
    selbst haelt nur das Ergebnis des Fallbacks, nicht die Herkunft.
Beide Spalten werden bei --apply automatisch angelegt, falls sie in der
Ziel-DB noch fehlen (ALTER TABLE, idempotent).

Aufruf:
    ../.venv/bin/python tools/load_enrichment.py <db> [--apply]
    (ohne --apply: nur Bericht, nichts geschrieben)
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

CACHE = Path(__file__).resolve().parent.parent / "data" / "venue_cache" / "enrichment.json"

# Felder, die dieses Skript verwaltet - und nur diese.
FIELDS = ("homepage_url", "homepage_root", "meta_title", "meta_description",
          "og_image_url", "cover_source", "meta_status")

# Spalten, die dieses Skript bei --apply selbst nachruestet, falls die
# Ziel-DB noch auf dem Stand vor P5a ist (ALTER TABLE, idempotent - siehe
# migrations/001_schema_v2.sql fuer die Spalten einer frischen Installation).
_NEW_COLUMNS = {
    "homepage_root": "TEXT",
    "cover_source": "TEXT CHECK (cover_source IN ('kulturkalender', 'homepage') OR cover_source IS NULL)",
}


def _ensure_columns(conn):
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(venues)")}
    for name, ddl in _NEW_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE venues ADD COLUMN {name} {ddl}")


def _homepage_root(homepage_url):
    """scheme://netloc, oder None ohne homepage_url. Reine Stringzerlegung
    einer schon gespeicherten URL - kein Request, kein neuer Fetch."""
    if not homepage_url:
        return None
    parts = urlsplit(homepage_url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def payload(rec):
    """Cache-Datensatz -> die sieben Spaltenwerte. Ohne meta_fetched_at, das
    haengt davon ab, OB geschrieben wird."""
    meta = rec.get("meta") or {}
    status = rec.get("status", "error:unbekannt")

    if rec.get("homepage_url") and meta.get("status") == "ok":
        db_status = "ok"
    elif status in ("not_found", "nur_social", "kein_kk_link"):
        # Kein eigener Auftritt auffindbar. Als 'not_found' markieren, damit
        # ein spaeterer Lauf diese Venues nicht endlos neu versucht.
        db_status = "not_found"
    else:
        db_status = f"error:{status}"[:60]

    kk_cover = rec.get("kk_cover_url")
    homepage_og = meta.get("og_image_url")
    # Dieselbe Reihenfolge wie og_image_url unten - NICHT umkehren (siehe
    # Docstring: eine Umkehr wuerde sofort kaputte Bilder zeigen).
    if kk_cover:
        cover_source = "kulturkalender"
    elif homepage_og:
        cover_source = "homepage"
    else:
        cover_source = None

    return {
        "homepage_url": rec.get("homepage_url"),
        "homepage_root": _homepage_root(rec.get("homepage_url")),
        "meta_title": meta.get("meta_title"),
        "meta_description": meta.get("meta_description"),
        "og_image_url": kk_cover or homepage_og,
        "cover_source": cover_source,
        "meta_status": db_status,
    }


def load(conn, recs, apply):
    # Idempotent, und lebt in derselben Transaktion wie der Rest: bleibt ein
    # Probelauf (kein --apply), macht main()s conn.rollback() auch die neuen
    # Spalten wieder rueckgaengig - "nichts geschrieben" bleibt wahr.
    _ensure_columns(conn)

    rows = {r["id"]: r for r in conn.execute(
        "SELECT id, name, " + ", ".join(FIELDS) + " FROM venues")}

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    stats = {"matched": 0, "no_row": [], "name_mismatch": [],
             "written": 0, "unchanged": 0}

    for key, rec in recs.items():
        try:
            vid = int(key)
        except ValueError:
            stats["no_row"].append((key, rec.get("name"), "kein numerischer Schluessel"))
            continue

        row = rows.get(vid)
        if row is None:
            stats["no_row"].append((key, rec.get("name"), "keine venues-Zeile"))
            continue
        if row["name"] != rec.get("name"):
            # id zeigt inzwischen auf ein anderes Haus - nicht schreiben.
            stats["name_mismatch"].append((vid, rec.get("name"), row["name"]))
            continue

        stats["matched"] += 1
        new = payload(rec)
        if all(row[f] == new[f] for f in FIELDS):
            stats["unchanged"] += 1
            continue

        if apply:
            conn.execute(
                "UPDATE venues SET " + ", ".join(f"{f} = ?" for f in FIELDS)
                + ", meta_fetched_at = ? WHERE id = ?",
                tuple(new[f] for f in FIELDS) + (now, vid))
        stats["written"] += 1

    return stats


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    db = args[0] if args else "data/dd-was-geht-v2.db"

    recs = json.loads(CACHE.read_text("utf-8"))
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    # Explizit noetig: sqlite3 haengt DDL (ALTER TABLE) NICHT automatisch in
    # eine Transaktion wie INSERT/UPDATE - ohne dieses BEGIN wuerde
    # _ensure_columns() sofort committen, und ein Probelauf ohne --apply
    # haette trotzdem die Tabelle veraendert.
    conn.execute("BEGIN")

    print(f"{len(recs)} Datensaetze im Cache.")
    stats = load(conn, recs, apply)

    print(f"  zugeordnet (id + Name geprueft): {stats['matched']}")
    print(f"  ohne venues-Zeile:               {len(stats['no_row'])}")
    for key, name, why in stats["no_row"]:
        print(f"      {key} {name!r}: {why}")
    print(f"  Name passt nicht zur id:         {len(stats['name_mismatch'])}")
    for vid, cached, dbname in stats["name_mismatch"]:
        print(f"      id={vid} Cache={cached!r} DB={dbname!r} - NICHT geschrieben")
    print(f"  geaendert:                       {stats['written']}")
    print(f"  schon aktuell (nichts getan):    {stats['unchanged']}")

    if apply:
        conn.commit()
        print("\ncommitted.")
    else:
        conn.rollback()
        print("\nProbelauf - nichts geschrieben.")

    for label, sql in (
            ("homepage_url gefuellt", "homepage_url IS NOT NULL"),
            ("og_image_url gefuellt", "og_image_url IS NOT NULL"),
            ("meta_status = 'ok'", "meta_status = 'ok'"),
            ("meta_status gefuellt", "meta_status IS NOT NULL")):
        n = conn.execute(f"SELECT COUNT(*) FROM venues WHERE {sql}").fetchone()[0]
        print(f"  {label:24} {n}")
    conn.close()


if __name__ == "__main__":
    main()

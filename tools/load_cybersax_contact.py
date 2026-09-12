#!/usr/bin/env python3
"""Uebertraegt Adresse/Telefon/Oeffnungszeiten aus data/venue_cache/
cybersax_enrichment.json in `venues` (Paket P5v).

WARUM DIESES SKRIPT NICHTS HOLT. Die zu pruefende Annahme dieses Pakets war:
"die Werte stehen schon im Cache und koennen ohne einen einzigen neuen
Request geparst werden." Das ist verifiziert - siehe cs_sections in
data/venue_cache/cybersax_enrichment.json (74 Eintraege, von
tools/enrich_venues_cybersax.py geschrieben): 56/74 haben eine nichtleere
'Adresse', 22/74 ein 'Telefon:' im Kontakt-Block, 8/74 Oeffnungszeiten. Der
Cache liegt schon auf der Platte - dieses Skript holt NICHTS, genau wie
tools/load_enrichment.py fuer die Homepage-Metadaten. Das Parsen selbst steht
in tools/enrich_venues_cybersax.extract_contact() (dort auch der Beleg fuer
diese vier Zahlen, gegen die echten 74 Cache-Eintraege gemessen).

DATUM DER OEFFNUNGSZEITEN. contact_fetched_at wird NICHT auf "jetzt" gesetzt,
sondern auf das Datum aus venues.meta_fetched_at derselben Zeile - das ist
der tatsaechliche Zeitpunkt, an dem diese cybersax-Adressseite geholt wurde
(tools/enrich_venues_cybersax.write() setzt beide im selben Lauf). "Jetzt"
waere falsch: dieses Skript kann Tage oder Wochen nach dem eigentlichen Fetch
laufen, und genau das Datum soll dem Leser sagen, wie alt die
Oeffnungszeiten sind (siehe Bericht zu P5v).

SPALTEN, DIE DIESES SKRIPT SELBST NACHRUESTET (ALTER TABLE, idempotent -
dasselbe Muster wie tools/load_enrichment.py._ensure_columns, siehe dort
fuer die Begruendung): address, phone, opening_hours, contact_fetched_at.
Eine frische DB hat sie laut migrations/001_schema_v2.sql schon.

Aufruf:
    ../.venv/bin/python tools/load_cybersax_contact.py <db> [--apply]
    (ohne --apply: nur Bericht, nichts geschrieben)
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.enrich_venues_cybersax import RESULTS_CACHE, extract_contact  # noqa: E402

# Spalten, die dieses Skript bei --apply selbst nachruestet, falls die
# Ziel-DB noch auf dem Stand vor P5v ist (siehe migrations/001_schema_v2.sql
# fuer die Spalten einer frischen Installation).
_NEW_COLUMNS = {
    "address": "TEXT",
    "phone": "TEXT",
    "opening_hours": "TEXT",
    "contact_fetched_at": "TEXT",
}

FIELDS = ("address", "phone", "opening_hours")


def _ensure_columns(conn):
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(venues)")}
    for name, ddl in _NEW_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE venues ADD COLUMN {name} {ddl}")


def load(conn, results, apply):
    _ensure_columns(conn)

    rows = {r["id"]: r for r in conn.execute(
        "SELECT id, name, meta_fetched_at, " + ", ".join(FIELDS) + " FROM venues")}

    stats = {"matched": 0, "no_row": [], "name_mismatch": [],
             "no_contact_data": 0, "written": 0, "unchanged": 0}

    for key, rec in results.items():
        try:
            vid = int(key)
        except ValueError:
            stats["no_row"].append((key, rec.get("name"), "kein numerischer Schluessel"))
            continue

        row = rows.get(vid)
        if row is None:
            stats["no_row"].append((key, rec.get("name"), "keine venues-Zeile"))
            continue
        # Gegenprobe ueber den Namen wie in enrich_venues_cybersax.write():
        # venues.id ist AUTOINCREMENT, zwischen Sweep und Laden kann neu
        # geseedet worden sein.
        if row["name"] != rec.get("name"):
            stats["name_mismatch"].append((vid, rec.get("name"), row["name"]))
            continue

        stats["matched"] += 1
        new = extract_contact(rec.get("cs_sections"), rec.get("cs_name") or rec.get("name"))
        if not (new["address"] or new["phone"] or new["opening_hours"]):
            stats["no_contact_data"] += 1
            continue

        if all(row[f] == new[f] for f in FIELDS):
            stats["unchanged"] += 1
            continue

        # Datum der Quelle, nicht der Laufzeit dieses Skripts (siehe Docstring).
        fetched_at = (row["meta_fetched_at"] or "")[:10] or None
        if apply:
            conn.execute(
                "UPDATE venues SET " + ", ".join(f"{f} = ?" for f in FIELDS)
                + ", contact_fetched_at = ? WHERE id = ?",
                tuple(new[f] for f in FIELDS) + (fetched_at, vid))
        stats["written"] += 1

    return stats


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)

    results = json.loads(RESULTS_CACHE.read_text("utf-8"))
    conn = sqlite3.connect(args[0])
    conn.row_factory = sqlite3.Row
    # Wie in tools/load_enrichment.py: sqlite3 haengt ALTER TABLE NICHT
    # automatisch in eine Transaktion - ohne dieses BEGIN wuerde
    # _ensure_columns() sofort committen, auch in einem Probelauf.
    conn.execute("BEGIN")

    print(f"{len(results)} Cache-Eintraege (data/venue_cache/{RESULTS_CACHE.name}).")
    stats = load(conn, results, apply)

    print(f"  zugeordnet (id + Name geprueft): {stats['matched']}")
    print(f"  ohne venues-Zeile:               {len(stats['no_row'])}")
    for key, name, why in stats["no_row"]:
        print(f"      {key} {name!r}: {why}")
    print(f"  Name passt nicht zur id:         {len(stats['name_mismatch'])}")
    for vid, cached, dbname in stats["name_mismatch"]:
        print(f"      id={vid} Cache={cached!r} DB={dbname!r} - NICHT geschrieben")
    print(f"  ohne jedes Kontaktfeld:          {stats['no_contact_data']}")
    print(f"  geaendert:                       {stats['written']}")
    print(f"  schon aktuell (nichts getan):    {stats['unchanged']}")

    if apply:
        conn.commit()
        print("\ncommitted.")
        # Erst NACH dem commit abfragbar: im Probelauf nimmt conn.rollback()
        # auch das ALTER TABLE aus _ensure_columns() wieder zurueck, die
        # Spalten gaebe es dann in DIESER Verbindung nicht mehr.
        for label, sql in (
                ("address gefuellt", "address IS NOT NULL"),
                ("phone gefuellt", "phone IS NOT NULL"),
                ("opening_hours gefuellt", "opening_hours IS NOT NULL"),
                ("contact_fetched_at gefuellt", "contact_fetched_at IS NOT NULL")):
            n = conn.execute(f"SELECT COUNT(*) FROM venues WHERE {sql}").fetchone()[0]
            print(f"  {label:28} {n}")
    else:
        conn.rollback()
        print("\nProbelauf - nichts geschrieben.")
    conn.close()


if __name__ == "__main__":
    main()

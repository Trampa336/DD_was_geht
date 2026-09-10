#!/usr/bin/env python3
"""Einmaliger Backfill: events.source auf die bestplatzierte Quelle ziehen.

Hintergrund (P3, P3b-2): events.source wurde bisher nur beim ersten INSERT
gesetzt und nie revidiert, wenn eine bessere Quelle (event_sources) denselben
Eintrag später auch lieferte. app/db.py:upsert_events schreibt das ab jetzt
für neue Läufe richtig fort (siehe db._best_source) - dieses Skript korrigiert
den Bestand ein einziges Mal.

Bewusst KEIN init_db()-Nebeneffekt, sondern ein tools/-Skript: das Umschreiben
von events.source auf dem Bestand soll gesehen und bestätigt werden, nicht
beim nächsten Container-Start unbemerkt laufen.

Sicherheitsnetz: --dry-run (Standard) zeigt nur, was sich ändern würde.
--apply schreibt tatsächlich. Vor --apply auf der echten DB: Backup ziehen
(siehe app/backup.py) - dieses Skript prüft das nicht selbst.

    python3 tools/backfill_source.py               # dry-run, zeigt Diff
    python3 tools/backfill_source.py --apply        # schreibt

Im Container:
    docker compose exec dd-was-geht python3 tools/backfill_source.py --apply
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db


def plan_backfill(conn):
    """Liefert [(uid, alte_source, neue_source), ...] für jede Zeile, deren
    events.source von der bestplatzierten event_sources-Quelle abweicht."""
    rows = conn.execute("SELECT uid, source FROM events").fetchall()
    changes = []
    for row in rows:
        best = db._best_source(conn, row["uid"])
        if best != row["source"]:
            changes.append((row["uid"], row["source"], best))
    return changes


def apply_backfill(conn, changes):
    for uid, _old, new in changes:
        conn.execute("UPDATE events SET source = ? WHERE uid = ?", (new, uid))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                         help="tatsächlich schreiben (Standard: nur anzeigen)")
    args = parser.parse_args()

    with db.get_conn() as conn:
        changes = plan_backfill(conn)
        print(f"{len(changes)} von {conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]} "
              f"Zeilen betroffen.")
        for uid, old, new in changes[:20]:
            print(f"  {uid}: {old} -> {new}")
        if len(changes) > 20:
            print(f"  ... und {len(changes) - 20} weitere")

        if not args.apply:
            print("\nDry-run - nichts geschrieben. --apply zum Anwenden.")
            return

        apply_backfill(conn, changes)
        print(f"\n{len(changes)} Zeile(n) aktualisiert.")


if __name__ == "__main__":
    main()

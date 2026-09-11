"""Vergibt Kontext-Tags an alle bereits gespeicherten Events (Tag-Backfill).

Dasselbe Problem wie bei tools/reclassify.py: db.upsert_events() setzt Tags
(wie category_slug) NUR beim Insert - eine spaetere Regeländerung in
normalize.derive_tags() gilt sonst nur fuer ab dann neu eingefuegte Events.

Kategorie = WAS ein Event IST, Tag = KONTEXT (siehe normalize.py-Modul-
kommentar "Tags (Kontext, nicht Kategorie)" fuer die fuenf Start-Tags und
ihre Begruendung). Ein Event kann mehrere Tags tragen oder keinen - anders
als category_slug ist das kein Ersatz, sondern eine Ergaenzung.

Aufruf:
    ../.venv/bin/python tools/tag_events.py            # zeigt nur, was sich ändern würde
    ../.venv/bin/python tools/tag_events.py --apply    # schreibt die Änderungen
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, normalize  # noqa: E402


def main():
    apply = "--apply" in sys.argv

    with db.get_conn() as conn:
        db._seed_tags(conn)  # idempotent, siehe db.init_db()

        rows = conn.execute(
            """SELECT e.uid, e.title, v.name AS venue_name, v.kind AS venue_kind
               FROM events e LEFT JOIN venues v ON e.venue_id = v.id"""
        ).fetchall()

        existing_tags = {
            row["event_uid"]: set()
            for row in conn.execute("SELECT DISTINCT event_uid FROM event_tags")
        }
        for row in conn.execute("SELECT event_uid, tag_slug FROM event_tags"):
            existing_tags.setdefault(row["event_uid"], set()).add(row["tag_slug"])

        additions = []  # (uid, tag_slug)
        for row in rows:
            wanted = set(normalize.derive_tags(row["title"], row["venue_name"], row["venue_kind"]))
            have = existing_tags.get(row["uid"], set())
            for tag_slug in wanted - have:
                additions.append((row["uid"], tag_slug))

        if apply:
            for uid, tag_slug in additions:
                conn.execute(
                    """INSERT INTO event_tags (event_uid, tag_slug) VALUES (?, ?)
                       ON CONFLICT(event_uid, tag_slug) DO NOTHING""",
                    (uid, tag_slug),
                )

    print(f"{len(rows)} Events geprüft, {len(additions)} neue Tag-Zuordnungen.\n")

    by_tag = Counter(tag_slug for _, tag_slug in additions)
    for tag_slug, count in by_tag.most_common():
        print(f"  +{tag_slug:10} {count}")

    if apply:
        print(f"\n{len(additions)} Tag-Zuordnungen geschrieben.")
    elif additions:
        print("\nNichts geschrieben. Mit --apply übernehmen.")


if __name__ == "__main__":
    main()

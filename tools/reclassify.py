"""Ordnet alle bereits gespeicherten Events neu ein (Kategorie-Backfill).

Nötig, weil `db.upsert_events()` bei einem erneuten Scrape bewusst nur
last_seen und die Detail-Felder aktualisiert - die Kategorie eines einmal
gespeicherten Events bleibt für immer stehen. Ändert man also die Regeln in
`app/normalize.py` (neue Bucket-Aufteilung, neue Schlüsselwörter), gelten die
neuen Regeln sonst nur für ab dann neu eingefügte Events.

Dieses Skript rechnet `category` für alle Zeilen aus raw_category + title neu
aus - genau so, wie es die Scraper beim Insert tun. Gefahrlos wiederholbar.

Aufruf:
    python3 tools/reclassify.py            # zeigt nur, was sich ändern würde
    python3 tools/reclassify.py --apply    # schreibt die Änderungen
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, normalize  # noqa: E402


def main():
    apply = "--apply" in sys.argv

    changes = []
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT uid, title, raw_venue, raw_category, category_slug FROM events"
        ).fetchall()

        for row in rows:
            new_category = normalize.classify_category(
                row["raw_category"] or "", row["title"], row["raw_venue"]
            )
            if new_category != row["category_slug"]:
                changes.append((row["uid"], row["title"], row["category_slug"], new_category))

        if apply:
            for uid, _, _, new_category in changes:
                conn.execute(
                    "UPDATE events SET category_slug = ? WHERE uid = ?", (new_category, uid)
                )

    print(f"{len(rows)} Events geprüft, {len(changes)} würden sich ändern.\n")

    moves = Counter((old, new) for _, _, old, new in changes)
    for (old, new), count in moves.most_common():
        print(f"  {old:10} -> {new:10}  {count}")

    if changes:
        print("\nBeispiele:")
        for _, title, old, new in changes[:10]:
            print(f"  [{old} -> {new}] {title}")

    if apply:
        print(f"\n{len(changes)} Events aktualisiert.")
    elif changes:
        print("\nNichts geschrieben. Mit --apply übernehmen.")


if __name__ == "__main__":
    main()

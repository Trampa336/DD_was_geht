#!/usr/bin/env python3
"""Zeigt, welche Doppelungen zwischen den Quellen verbucht sind.

Die Erkennung läuft automatisch nach jedem Scrape (app/dedup.py) und blendet
den Eintrag der Quelle mit der niedrigeren Priorität aus. Dieses Tool macht
sichtbar, was da ausgeblendet wurde - zum Nachprüfen, ob die Erkennung nicht
zu großzügig oder zu streng ist.

    python3 tools/show_duplicates.py                  # ab heute, 31 Tage
    python3 tools/show_duplicates.py --tage 7
    python3 tools/show_duplicates.py --von 2026-09-01 --bis 2026-09-30
    python3 tools/show_duplicates.py --neu-berechnen   # Erkennung neu laufen lassen

Im Container:
    docker compose exec dd-was-geht python3 tools/show_duplicates.py
"""
import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, db, dedup  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Verbuchte Doppelungen anzeigen")
    parser.add_argument("--tage", type=int, default=31, help="Zeitraum ab heute (Standard: 31)")
    parser.add_argument("--von", help="Startdatum YYYY-MM-DD (überschreibt --tage)")
    parser.add_argument("--bis", help="Enddatum YYYY-MM-DD")
    parser.add_argument("--neu-berechnen", action="store_true",
                        help="Erkennung für den Zeitraum neu laufen lassen")
    args = parser.parse_args()

    start = args.von or date.today().isoformat()
    end = args.bis or (date.today() + timedelta(days=args.tage)).isoformat()

    db.init_db()
    with db.get_conn() as conn:
        if args.neu_berechnen:
            count = dedup.link_duplicates(conn, start, end)
            print(f"Neu berechnet: {count} Doppelungen im Zeitraum.\n")
        rows = db.duplicates_for_range(conn, start, end)
        counts = db.duplicate_counts(conn)
        shared = db.shared_uid_events(conn, start, end)

    print(f"Quellen-Priorität: {' > '.join(config.SOURCE_PRIORITY)}")
    print(f"Zeitraum: {start} bis {end}\n")

    if not rows:
        print("Keine Doppelungen verbucht.")
    for row in rows:
        score = row["match_score"] or 0.0
        print(f"{row['date']}  {row['canonical_time'] or '--:--'}  "
              f"{row['canonical_title']} — {row['canonical_venue'] or 'Ort unbekannt'}"
              f"   [{row['canonical_source']}]")
        print(f"{' ' * 12}  verdeckt: {row['duplicate_time'] or '--:--'}  "
              f"{row['duplicate_title']} — {row['duplicate_venue'] or 'Ort unbekannt'}"
              f"   [{row['duplicate_source']}]")
        print(f"{' ' * 12}  Treffer über {row['matched_on']}, "
              f"Ähnlichkeit {score:.2f}, verbucht seit {(row['first_seen'] or '')[:10]}\n")

    if counts:
        print("Summe je Quellen-Paar (ausgeblendet <- sichtbar):")
        for entry in counts:
            print(f"  {entry['duplicate_source']} <- {entry['canonical_source']}: {entry['n']}")

    # Zweite Art von Doppelung: beide Quellen schreiben Datum, Zeit, Titel und
    # Ort identisch, damit faellt schon die uid zusammen - es gibt also gar
    # keinen zweiten Eintrag zum Ausblenden. Trotzdem ist es eine Doppelung
    # und gehoert in die Buchfuehrung.
    print(f"\nDeckungsgleich geliefert (gleiche uid, mehrere Quellen): {len(shared)}")
    for row in shared:
        print(f"  {row['date']}  {row['time'] or '--:--'}  {row['title']} — "
              f"{row['venue'] or 'Ort unbekannt'}   [{row['sources']}]")


if __name__ == "__main__":
    main()

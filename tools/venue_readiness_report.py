#!/usr/bin/env python3
"""Misst, ob eine Venue-Seite aus rein vorhandenen Daten "landbar" ist -
die Kernannahme von Paket P5b: "jedes Event fuehrt auf eine Venue-Seite, und
die ist auch ohne neue Anreicherung etwas wert."

Hintergrund: P5b uebergab die Zahl "38% der ~569 nie angereicherten Venues
haben genau ein Event" ungeprueft weiter. Dieses Skript legt die Rechnung
offen, weil in diesem Projekt schon drei Zahlen nicht reproduzierten, deren
Rechenweg nirgends stand (siehe Paket-Bericht). Jede Ausgabezeile hier nennt
ihren Nenner.

Aufruf (read-only, keine Netzwerk-Zugriffe, keine Schreibvorgaenge):
    ../.venv/bin/python tools/venue_readiness_report.py [pfad/zur.db]
"""
import argparse
import os
import sqlite3
import sys


def _pct(n, d):
    return f"{n}/{d} = {n / d:.1%}" if d else f"{n}/0 = n/a"


def report(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    print(f"DB: {db_path}\n")

    # --- 1. Loesen alle Gewinner-Events auf eine Venue auf? --------------
    total_winners = conn.execute(
        "SELECT COUNT(*) FROM events WHERE duplicate_of IS NULL"
    ).fetchone()[0]
    winners_no_venue = conn.execute(
        "SELECT COUNT(*) FROM events WHERE duplicate_of IS NULL AND venue_id IS NULL"
    ).fetchone()[0]
    orphan_refs = conn.execute(
        """SELECT COUNT(*) FROM events e LEFT JOIN venues v ON v.id = e.venue_id
           WHERE e.venue_id IS NOT NULL AND v.id IS NULL"""
    ).fetchone()[0]
    print("=== 1. Aufloesung Event -> Venue (alle Gewinner, nicht nur Zukunft) ===")
    print(f"Gewinner-Events gesamt: {total_winners}")
    print(f"davon ohne venue_id: {_pct(winners_no_venue, total_winners)}")
    print(f"venue_id zeigt auf nichts (Integritaet): {orphan_refs}")

    meeting_point_events = conn.execute(
        """SELECT COUNT(*) FROM events e JOIN venues v ON v.id = e.venue_id
           WHERE v.is_meeting_point = 1 AND e.duplicate_of IS NULL AND e.date >= date('now')"""
    ).fetchone()[0]
    meeting_point_venues = conn.execute(
        "SELECT COUNT(*) FROM venues WHERE is_meeting_point = 1"
    ).fetchone()[0]
    print(f"\nis_meeting_point-Venues (bekommen KEINE Seite, Schema §1): {meeting_point_venues}")
    print("anstehende Gewinner-Events an diesen Venues (bekommen nur den "
          f"Quellen-Link, keinen Venue-Link): {meeting_point_events}")

    # --- 2. Verteilung dessen, was eine Venue-Seite zeigen kann ----------
    rows = conn.execute(
        """SELECT v.id, v.homepage_url, v.og_image_url, v.meta_description, v.meta_status,
                  (SELECT COUNT(*) FROM events e WHERE e.venue_id = v.id
                     AND e.duplicate_of IS NULL AND e.date >= date('now')) AS upcoming
           FROM venues v WHERE v.is_meeting_point = 0"""
    ).fetchall()
    total = len(rows)

    def dist(group, label):
        n = len(group)
        if n == 0:
            print(f"--- {label}: n=0, ueberspringe ---")
            return
        eq1 = sum(1 for r in group if r["upcoming"] == 1)
        eq0 = sum(1 for r in group if r["upcoming"] == 0)
        ge3 = sum(1 for r in group if r["upcoming"] >= 3)
        cover = sum(1 for r in group if r["og_image_url"])
        home = sum(1 for r in group if r["homepage_url"])
        meta = sum(1 for r in group if r["meta_description"])
        print(f"--- {label} (n={n}) ---")
        print(f"  hat Cover:              {_pct(cover, n)}")
        print(f"  hat Homepage:           {_pct(home, n)}")
        print(f"  hat meta_description:   {_pct(meta, n)}")
        print(f"  >=3 anstehende Events:  {_pct(ge3, n)}")
        print(f"  genau 1 anstehendes:    {_pct(eq1, n)}")
        print(f"  0 anstehende Events:    {_pct(eq0, n)}")

    print(f"\n=== 2. Verteilung ueber alle Venues (ohne Treffpunkte, n={total}) ===")
    dist(rows, "ALLE")

    never_attempted = [r for r in rows if r["meta_status"] is None]
    attempted = [r for r in rows if r["meta_status"] is not None]
    print(f"\n=== 3. Aufgeschluesselt nach P4-Anreicherungsversuch ===")
    print("(meta_status IS NULL = nie versucht - die im Paket 'die ~569' genannte "
          "Gruppe; meta_status NOT NULL = versucht, egal mit welchem Ergebnis - "
          "'die 160')")
    dist(never_attempted, "NIE VERSUCHT (meta_status IS NULL)")
    dist(attempted, "VERSUCHT (meta_status NOT NULL)")

    # --- 4. Fallback-Wirkung: Event-Bild als Venue-Cover -----------------
    if never_attempted:
        ids = [r["id"] for r in never_attempted]
        qmarks = ",".join("?" * len(ids))
        with_img = conn.execute(
            f"""SELECT COUNT(DISTINCT venue_id) FROM events
                WHERE venue_id IN ({qmarks}) AND duplicate_of IS NULL
                  AND date >= date('now') AND image_url IS NOT NULL AND image_url <> ''""",
            ids,
        ).fetchone()[0]
        print(f"\n=== 4. Fallback: Event-Bild als Venue-Cover (siehe feed.venue_cover) ===")
        print("von den nie versuchten Venues hat mindestens 1 anstehendes Event "
              f"mit Bild: {_pct(with_img, len(never_attempted))}")

        thin = [r for r in never_attempted if r["upcoming"] == 1]
        if thin:
            tids = [r["id"] for r in thin]
            tq = ",".join("?" * len(tids))
            single_events = conn.execute(
                f"""SELECT venue_id, description, image_url FROM events
                    WHERE venue_id IN ({tq}) AND duplicate_of IS NULL AND date >= date('now')""",
                tids,
            ).fetchall()
            truly_bare = sum(
                1 for e in single_events if not e["description"] and not e["image_url"]
            )
            print(f"\nvon den {len(thin)} nie-versuchten Venues mit GENAU 1 anstehendem "
                  "Event: dessen einziges Event hat weder Bild noch Beschreibung "
                  f"(wirklich karg): {_pct(truly_bare, len(thin))}"
                  f" -- als Anteil aller {total} Venues: {_pct(truly_bare, total)}")

    # --- 5. Score-Konsum (zweiter Check aus dem Paket) -------------------
    reactions = conn.execute(
        "SELECT COUNT(*) FROM reactions"
    ).fetchone()[0] if conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='reactions'"
    ).fetchone() else None
    weights = conn.execute(
        "SELECT COUNT(*) FROM weights"
    ).fetchone()[0] if conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='weights'"
    ).fetchone() else None
    print("\n=== 5. score-Grundlage (reactions/weights) ===")
    print(f"reactions-Zeilen: {reactions}")
    print(f"weights-Zeilen: {weights}")
    print("(0/0 bedeutet: score ist fuer JEDES Event exakt 50.0, siehe scoring.py)")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("db", nargs="?",
                        default=os.path.join(os.path.dirname(os.path.dirname(
                            os.path.abspath(__file__))), "data", "dd-was-geht-v2.db"))
    args = parser.parse_args()
    report(args.db)


if __name__ == "__main__":
    main()

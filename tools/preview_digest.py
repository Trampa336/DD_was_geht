#!/usr/bin/env python3
"""Zeigt den Newsletter, ohne ihn zu verschicken.

Rendert Tages- und Wochendigest mit genau derselben Auswahl- und
Formatierungslogik wie der Telegram-Push (app/scoring.top_picks und
app/bot._event_line) - nur landet das Ergebnis auf der Konsole statt im Chat.
Gedacht zum Nachsehen, WAS morgen früh rausgeht und warum: Reihenfolge,
Datumsspalte, Links, Maskierung von Sonderzeichen.

    python3 tools/preview_digest.py                 # heute + diese Woche
    python3 tools/preview_digest.py --roh           # das gesendete HTML zeigen
    python3 tools/preview_digest.py --tag 2026-09-05

Im Container:
    docker compose exec dd-was-geht python3 tools/preview_digest.py
"""
import argparse
import os
import re
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import bot, config, db, scoring  # noqa: E402
from app.ranges import week_range  # noqa: E402

_TAG_RE = re.compile(r"<[^>]+>")


def _plain(line):
    """Dasselbe wie in Telegram sichtbar: Links werden zu ihrem Text, und die
    Maskierung (&amp; -> &) wird zurückgenommen."""
    text = _TAG_RE.sub("", line)
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        text = text.replace(entity, char)
    return text


def _digest(conn, title, start, end, limit, with_date):
    events = db.events_for_range(
        conn, start.isoformat(), end.isoformat(),
        exclude_categories=config.EXCLUDED_CATEGORIES, exclude_far=True,
    )
    top = scoring.top_picks(conn, events, limit=limit)
    if with_date:
        top = sorted(top, key=lambda e: (e["date"], e["time"] or "99:99"))
    return title, events, top


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Stichtag statt heute (YYYY-MM-DD)")
    parser.add_argument("--roh", action="store_true",
                        help="das tatsächlich gesendete HTML ausgeben")
    args = parser.parse_args()

    today = (datetime.strptime(args.tag, "%Y-%m-%d").date() if args.tag
             else date.today())
    start, end = week_range(today)

    with db.get_conn() as conn:
        blocks = [
            _digest(conn, f"📅 Heute in Dresden – {today.strftime('%d.%m.%Y')}",
                    today, today, config.DAILY_TOP_N, False),
            _digest(conn,
                    f"🗓️ Diese Woche in Dresden "
                    f"({start.strftime('%d.%m.')}–{end.strftime('%d.%m.%Y')})",
                    start, end, config.DAILY_TOP_N * 2, True),
        ]

    for title, events, top in blocks:
        with_date = title.startswith("🗓")
        print(f"\n{title}")
        print(f"   ({len(top)} von {len(events)} Veranstaltungen im Zeitraum, "
              f"ausgeblendet: {', '.join(config.EXCLUDED_CATEGORIES) or 'nichts'})\n")
        if not top:
            print("   Keine Veranstaltungen gefunden.")
            continue
        for event in top:
            line = bot._event_line(event, with_date=with_date)
            # Marker fuer das, was in Telegram als Foto rausgeht (siehe
            # bot._send_event): nur Events, die schon eine image_url haben.
            cover = "\U0001f5bc " if (event.get("image_url") or "").strip() else "  "
            print("   " + cover + (line if args.roh else _plain(line)))
    print()


if __name__ == "__main__":
    main()

"""Schlägt Subreddits vor, die sich zum Beobachten lohnen könnten.

Sucht über die offizielle Reddit-API (zuverlässiger als eine Websuche) und gibt
die Treffer nur aus - eingetragen wird von Hand in config/reddit_subreddits.txt.

Braucht gesetzte REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET in der .env.

Aufruf:
    python3 tools/discover_subreddits.py Dresden "Dresden Techno" "Dresden Party"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sources.reddit import client  # noqa: E402

DEFAULT_QUERIES = ["Dresden", "Dresden Techno", "Dresden Party", "Sachsen"]


def main():
    queries = sys.argv[1:] or DEFAULT_QUERIES
    seen = {}

    for query in queries:
        print(f"Suche nach {query!r} ...")
        try:
            for sub in client.search_subreddits(query):
                seen.setdefault(sub["name"].lower(), sub)
        except Exception as exc:
            print(f"  Fehler: {exc}")

    if not seen:
        print("\nKeine Treffer. Zugangsdaten in .env gesetzt?")
        return

    print(f"\n{len(seen)} Kandidaten (nach Größe sortiert):\n")
    print(f"{'Subreddit':<28} {'Mitglieder':>10}  Beschreibung")
    print("-" * 100)
    for sub in sorted(seen.values(), key=lambda s: -s["subscribers"]):
        print(f"r/{sub['name']:<26} {sub['subscribers']:>10}  {sub['description'][:55]}")

    print(
        "\nPassende Zeilen von Hand in config/reddit_subreddits.txt eintragen "
        "(ein Subreddit pro Zeile, ohne 'r/')."
    )


if __name__ == "__main__":
    main()

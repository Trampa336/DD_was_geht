"""PRAW-Zugriff auf Reddit (nur lesend).

Ohne Benutzername/Passwort läuft PRAW automatisch im read-only-Modus - der
Bot kann also nichts posten oder voten, selbst wenn die Zugangsdaten abhandenkommen.
"""
import logging
import time

from ... import config

logger = logging.getLogger("dd-was-geht.sources.reddit")

RETRIES = 2

_reddit = None


def get_reddit_client():
    """Lazy wie get_bot()/get_llm_client(): Import des Moduls soll ohne
    gesetzte Zugangsdaten funktionieren."""
    global _reddit
    if _reddit is None:
        import praw
        _reddit = praw.Reddit(
            client_id=config.REDDIT_CLIENT_ID,
            client_secret=config.REDDIT_CLIENT_SECRET,
            user_agent=config.REDDIT_USER_AGENT,
        )
    return _reddit


def _to_dict(submission):
    """PRAW-Objekte sind faul (jeder Attributzugriff kann eine Anfrage
    auslösen). Deshalb hier einmal einlesen und als schlichtes dict
    weiterreichen - das macht den Rest der Pipeline ohne Netzwerk testbar."""
    return {
        "id": submission.id,
        "title": submission.title or "",
        "selftext": submission.selftext or "",
        "created_utc": submission.created_utc,
        "permalink": submission.permalink,
        "flair": submission.link_flair_text,
        "subreddit": str(submission.subreddit),
    }


def fetch_new_posts(subreddit_name, limit):
    """Neueste Posts eines Subreddits. Wirft bei dauerhaftem Fehler - der
    Aufrufer fängt das pro Subreddit ab (wie scrape_range in den Scrapern)."""
    import prawcore

    last_error = None
    for attempt in range(RETRIES + 1):
        try:
            subreddit = get_reddit_client().subreddit(subreddit_name)
            return [_to_dict(s) for s in subreddit.new(limit=limit)]
        except prawcore.exceptions.PrawcoreException as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Konnte r/{subreddit_name} nicht laden: {last_error}")


def search_subreddits(query, limit=15):
    """Für tools/discover_subreddits.py: Kandidaten zu einem Stichwort finden."""
    results = []
    for sub in get_reddit_client().subreddits.search(query, limit=limit):
        results.append({
            "name": sub.display_name,
            "title": sub.title,
            "subscribers": sub.subscribers or 0,
            "description": (sub.public_description or "").replace("\n", " ").strip(),
        })
    return results

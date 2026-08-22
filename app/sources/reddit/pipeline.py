"""Ablauf einer Reddit-Runde: holen -> schon gesehen? -> vorfiltern -> LLM ->
in das Event-Format von app/db.py übersetzen -> Fast-Dubletten zusammenfassen.
"""
import difflib
import logging
import re
import time
from datetime import datetime, timedelta, timezone

from ... import config, db, normalize
from .. import common
from . import client as reddit_client
from . import prefilter, subreddits

logger = logging.getLogger("dd-was-geht.sources.reddit")

SOURCE = "reddit"

# Ab dieser Ähnlichkeit gelten zwei Titel am selben Tag/Ort als dasselbe Event.
DUPLICATE_TITLE_RATIO = 0.75

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Beitragstext, der an das LLM geht - lange Threads bringen keinen Mehrwert
# für die Extraktion, kosten aber Tokens.
MAX_TEXT_CHARS = 1500


def _post_text(post):
    body = post.get("selftext") or ""
    text = f"{post['title']}\n{body}".strip()
    return text[:MAX_TEXT_CHARS]


def _reference_date(post):
    created = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc)
    return created.date().isoformat()


def _collect_candidates(names, lookback_hours):
    """Neue Posts aller Subreddits, bereits nach Alter gefiltert."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).timestamp()
    posts = []
    for name in names:
        try:
            fetched = reddit_client.fetch_new_posts(
                name, limit=config.REDDIT_MAX_POSTS_PER_SUBREDDIT
            )
        except Exception as exc:  # ein defektes Subreddit stoppt den Lauf nicht
            logger.warning("[reddit] r/%s übersprungen: %s", name, exc)
            continue
        posts.extend(p for p in fetched if p["created_utc"] >= cutoff)
        time.sleep(config.REDDIT_SUBREDDIT_DELAY_SECONDS)
    return posts


def _to_event(result, post):
    """Ein LLM-Ergebnis in genau das dict übersetzen, das db.upsert_events
    erwartet - dieselben Felder wie bei den beiden HTML-Scrapern."""
    title = (result.get("title") or "").strip()
    date = (result.get("date") or "").strip()
    if not title or not DATE_RE.match(date):
        return None

    venue = (result.get("venue") or "").strip() or None
    raw_category = (result.get("raw_category") or "").strip() or None
    event_time = normalize.normalize_time(result.get("time"))

    return {
        "uid": normalize.make_event_uid(date, event_time, title, venue or ""),
        "source": SOURCE,
        "date": date,
        "time": event_time,
        "title": title,
        "venue": venue,
        "category": normalize.classify_category(raw_category or "", title, venue),
        "raw_category": raw_category,
        "url": f"https://www.reddit.com{post['permalink']}",
        "_created_utc": post["created_utc"],
    }


def _completeness(event):
    return (event["venue"] is not None) + (event["time"] is not None)


def collapse_near_duplicates(events):
    """Crossposts und zwei Leute, die dieselbe Party ankündigen, ergeben über
    das Slug-basierte uid-Schema zwei verschiedene IDs. Deshalb hier zusätzlich
    Titel am selben Tag/Ort vergleichen. Bewusst best-effort, wie die ohnehin
    schon unscharfe quellenübergreifende Dedup-Logik (siehe README)."""
    kept = []
    for event in sorted(events, key=lambda e: (-_completeness(e), e["_created_utc"])):
        slug = normalize.slugify(event["title"])
        venue_slug = normalize.slugify(event["venue"] or "")
        duplicate_of = None
        for other in kept:
            if other["date"] != event["date"]:
                continue
            if normalize.slugify(other["venue"] or "") != venue_slug:
                continue
            ratio = difflib.SequenceMatcher(
                None, normalize.slugify(other["title"]), slug
            ).ratio()
            if ratio >= DUPLICATE_TITLE_RATIO:
                duplicate_of = other
                break
        if duplicate_of is None:
            kept.append(event)
        else:
            # Der zuerst veröffentlichte Post ist die bessere Quellenangabe.
            if event["_created_utc"] < duplicate_of["_created_utc"]:
                duplicate_of["url"] = event["url"]
            logger.info(
                "[reddit] Dublette zusammengefasst: %r ~ %r",
                event["title"], duplicate_of["title"],
            )
    return kept


def poll_recent(lookback_hours=None, fetch=None, extract=None):
    """Gibt eine Liste von Event-dicts zurück (noch nicht gespeichert).
    fetch/extract sind nur für Tests da, damit die Pipeline ohne Netz läuft."""
    lookback_hours = lookback_hours or config.REDDIT_POLL_LOOKBACK_HOURS
    fetch = fetch or _collect_candidates
    extract = extract or common.extract_events

    names = subreddits.load_active_subreddits()
    if not names:
        logger.warning(
            "Keine Subreddits konfiguriert (%s) - Reddit-Quelle bleibt inaktiv.",
            config.REDDIT_SUBREDDITS_FILE,
        )
        return []

    posts = fetch(names, lookback_hours)
    logger.info("[reddit] %d Posts aus %d Subreddits geholt.", len(posts), len(names))

    candidates = []
    with db.get_conn() as conn:
        for post in posts:
            if db.reddit_seen(conn, post["id"]):
                continue
            if not prefilter.looks_event_ish(
                post["title"], post.get("selftext", ""), post.get("flair")
            ):
                db.mark_reddit_seen(conn, post["id"], "skipped_prefilter")
                continue
            candidates.append(post)

    logger.info("[reddit] %d Posts gehen an die Auswertung.", len(candidates))
    if not candidates:
        return []

    by_id = {p["id"]: p for p in candidates}
    events = []
    calls = 0
    for start in range(0, len(candidates), config.REDDIT_LLM_BATCH_SIZE):
        if calls >= config.REDDIT_LLM_MAX_CALLS_PER_RUN:
            logger.warning(
                "[reddit] Obergrenze von %d LLM-Aufrufen erreicht, %d Posts "
                "bleiben für den nächsten Lauf liegen.",
                config.REDDIT_LLM_MAX_CALLS_PER_RUN,
                len(candidates) - start,
            )
            break
        batch = candidates[start:start + config.REDDIT_LLM_BATCH_SIZE]
        try:
            results = extract([
                {
                    "id": p["id"],
                    "text": _post_text(p),
                    "reference_date": _reference_date(p),
                }
                for p in batch
            ])
        except Exception:
            logger.exception("[reddit] LLM-Auswertung fehlgeschlagen, Batch übersprungen.")
            continue
        calls += 1

        with db.get_conn() as conn:
            for result in results:
                post = by_id.get(result.get("id"))
                if post is None:
                    continue
                if not result.get("is_event"):
                    db.mark_reddit_seen(conn, post["id"], "not_event")
                    continue
                if (result.get("confidence") or 0) < config.REDDIT_LLM_CONFIDENCE_THRESHOLD:
                    db.mark_reddit_seen(conn, post["id"], "low_confidence")
                    continue
                event = _to_event(result, post)
                if event is None:
                    db.mark_reddit_seen(conn, post["id"], "unbrauchbar")
                    continue
                db.mark_reddit_seen(conn, post["id"], "event", event["uid"])
                events.append(event)

    events = collapse_near_duplicates(events)
    for event in events:
        event.pop("_created_utc", None)
    logger.info("[reddit] %d Events erkannt (%d LLM-Aufrufe).", len(events), calls)
    return events

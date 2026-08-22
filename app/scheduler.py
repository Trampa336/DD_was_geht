"""APScheduler-Jobs: tägliches Scrapen + Push, wöchentliche Übersicht."""
import asyncio
import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import config, db, dedup
from .bot import send_daily_digest, send_weekly_digest
from .ranges import month_range
from .scrapers import azconni, cybersax, kulturkalender, ra, rauze, sektor

logger = logging.getLogger("dd-was-geht.scheduler")


def run_scrape(days_ahead=31):
    today = date.today()
    end = today + timedelta(days=days_ahead)
    events = []
    events.extend(kulturkalender.scrape_range(today, end))
    events.extend(rauze.scrape_range(today, end))
    if config.RA_ENABLED:
        # Eigener try/except wie bei Reddit: fällt die RA-API aus, sollen die
        # beiden HTML-Quellen trotzdem gespeichert werden.
        try:
            events.extend(ra.scrape_range(today, end))
        except Exception:
            logger.exception("Resident Advisor fehlgeschlagen - Lauf geht weiter.")
    if config.CYBERSAX_ENABLED:
        try:
            events.extend(cybersax.scrape_range(today, end))
        except Exception:
            logger.exception("CyberSAX fehlgeschlagen - Lauf geht weiter.")
    if config.AZCONNI_ENABLED:
        try:
            events.extend(azconni.scrape_range(today, end))
        except Exception:
            logger.exception("AZ Conni fehlgeschlagen - Lauf geht weiter.")
    if config.SEKTOR_ENABLED:
        try:
            events.extend(sektor.scrape_range(today, end))
        except Exception:
            logger.exception("Sektor Evolution fehlgeschlagen - Lauf geht weiter.")

    with db.get_conn() as conn:
        new_count = db.upsert_events(conn, events)
        # Erst nach dem Speichern: die Erkennung vergleicht alle Quellen im
        # Zeitraum miteinander, nicht nur die gerade geholten Einträge.
        duplicate_count = dedup.link_duplicates(conn, today.isoformat(), end.isoformat())
    logger.info(
        "Scrape fertig: %d Events gesehen, %d davon neu, %d Doppelungen ausgeblendet.",
        len(events), new_count, duplicate_count,
    )
    return len(events), new_count


def run_reddit_poll(lookback_hours=None):
    """Reddit wird bewusst nur einmal täglich abgefragt (siehe README):
    die LLM-Auswertung kostet pro Post Geld, und für einen Tagesdigest reicht
    ein Lauf morgens völlig aus."""
    from .sources.reddit import pipeline as reddit_pipeline

    events = reddit_pipeline.poll_recent(lookback_hours)
    if not events:
        return 0, 0
    with db.get_conn() as conn:
        new_count = db.upsert_events(conn, events)
        dates = sorted(e["date"] for e in events if e.get("date"))
        if dates:
            dedup.link_duplicates(conn, dates[0], dates[-1])
    logger.info("Reddit fertig: %d Events gesehen, %d davon neu.", len(events), new_count)
    return len(events), new_count


async def _scrape_job():
    await asyncio.to_thread(run_scrape)


async def _daily_job():
    # Eigener try/except wie bei RA und Reddit, aber um den ganzen Scrape: fällt
    # eine der beiden HTML-Quellen aus (oder die DB ist kurz gesperrt), soll der
    # Push trotzdem rausgehen. Ein Digest aus den Daten des letzten Laufs ist
    # deutlich besser als gar kein Newsletter - vorher hat genau das den
    # Tagesversand still ausfallen lassen.
    try:
        await _scrape_job()
    except Exception:
        logger.exception("Scrape fehlgeschlagen - Push läuft mit den vorhandenen Daten weiter.")
    if config.REDDIT_ENABLED:
        # Eigener try/except: fällt Reddit oder die LLM-API aus, sollen der
        # HTML-Scrape und der Telegram-Push trotzdem durchlaufen.
        try:
            await asyncio.to_thread(run_reddit_poll)
        except Exception:
            logger.exception("Reddit-Durchlauf fehlgeschlagen - Push läuft trotzdem.")
    await send_daily_digest()


async def _weekly_job():
    await send_weekly_digest()


def start_scheduler():
    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)

    scheduler.add_job(
        _daily_job,
        CronTrigger(hour=config.DAILY_SEND_HOUR, minute=config.DAILY_SEND_MINUTE),
        id="daily_scrape_and_push",
    )
    scheduler.add_job(
        _weekly_job,
        CronTrigger(
            day_of_week=config.WEEKLY_SEND_DAY,
            hour=config.WEEKLY_SEND_HOUR,
            minute=config.WEEKLY_SEND_MINUTE,
        ),
        id="weekly_push",
    )
    # Zusätzlicher, häufigerer Hintergrund-Scrape, damit die Web-Oberfläche
    # auch außerhalb des täglichen Pushs halbwegs aktuell bleibt.
    scheduler.add_job(_scrape_job, CronTrigger(hour="*/6", minute=30), id="background_scrape")

    scheduler.start()
    return scheduler

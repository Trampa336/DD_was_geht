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
    # Je Quelle ein eigener try/except: faellt eine aus, werden die anderen
    # trotzdem gespeichert.
    try:
        events.extend(ra.scrape_range(today, end))
    except Exception:
        logger.exception("Resident Advisor fehlgeschlagen - Lauf geht weiter.")
    try:
        events.extend(cybersax.scrape_range(today, end))
    except Exception:
        logger.exception("CyberSAX fehlgeschlagen - Lauf geht weiter.")
    try:
        events.extend(azconni.scrape_range(today, end))
    except Exception:
        logger.exception("AZ Conni fehlgeschlagen - Lauf geht weiter.")
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


async def _scrape_job():
    await asyncio.to_thread(run_scrape)


async def _daily_job():
    # Eigener try/except wie bei RA, aber um den ganzen Scrape: fällt
    # eine der beiden HTML-Quellen aus (oder die DB ist kurz gesperrt), soll der
    # Push trotzdem rausgehen. Ein Digest aus den Daten des letzten Laufs ist
    # deutlich besser als gar kein Newsletter - vorher hat genau das den
    # Tagesversand still ausfallen lassen.
    try:
        await _scrape_job()
    except Exception:
        logger.exception("Scrape fehlgeschlagen - Push läuft mit den vorhandenen Daten weiter.")
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

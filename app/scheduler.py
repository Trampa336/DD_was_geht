"""APScheduler-Jobs: periodischer Hintergrund-Scrape."""
import logging
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import config, db, dedup
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


def start_scheduler():
    scheduler = BackgroundScheduler(timezone=config.TIMEZONE)

    # Haelt die Web-Oberflaeche zwischen den manuellen/Erst-Scrapes aktuell.
    scheduler.add_job(run_scrape, CronTrigger(hour="*/6", minute=30), id="background_scrape")

    scheduler.start()
    return scheduler

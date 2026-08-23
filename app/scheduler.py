"""APScheduler-Jobs: periodischer Hintergrund-Scrape."""
import logging
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import config, db, dedup
from .scrapers import azconni, cybersax, kulturkalender, ra, rauze, sektor

logger = logging.getLogger("dd-was-geht.scheduler")

# Reihenfolge wie gehabt, aber als Liste statt als sechs kopierte try/except-
# Bloecke. Der Grund ist nicht Kuerze: kulturkalender und rauze standen vorher
# ungeschuetzt VOR den Bloecken, obwohl der Kommentar "je Quelle ein eigener
# try/except" versprach. Ausgerechnet kulturkalender liefert rund drei Viertel
# aller Zeilen - eine Exception dort riss den kompletten Lauf mit. Ueber eine
# Liste kann eine neue Quelle gar nicht erst ungeschuetzt dazukommen.
SOURCES = [
    ("kulturkalender", kulturkalender),
    ("rauze", rauze),
    ("ra", ra),
    ("cybersax", cybersax),
    ("azconni", azconni),
    ("sektor", sektor),
]


def run_scrape(days_ahead=31):
    today = date.today()
    end = today + timedelta(days=days_ahead)
    events = []
    for name, module in SOURCES:
        label = config.SOURCE_LABELS.get(name, name)
        try:
            found = module.scrape_range(today, end)
        except Exception:
            logger.exception("%s fehlgeschlagen - Lauf geht weiter.", label)
            continue
        events.extend(found)
        logger.info("%s: %d Events.", label, len(found))

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

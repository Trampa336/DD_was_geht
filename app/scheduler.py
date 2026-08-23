"""APScheduler-Jobs: periodischer Hintergrund-Scrape und taegliche Sicherung."""
import logging
from datetime import date, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import backup, config, db, dedup
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
        started_at = datetime.utcnow().isoformat()
        try:
            found = module.scrape_range(today, end)
        except Exception as exc:
            logger.exception("%s fehlgeschlagen - Lauf geht weiter.", label)
            with db.get_conn() as conn:
                db.record_scrape_run(conn, name, started_at,
                                     datetime.utcnow().isoformat(), ok=False,
                                     error=repr(exc))
            continue

        events.extend(found)
        # Der gefaehrliche Fall ist nicht die Exception, sondern der stille
        # Nulltreffer: aendert eine Quelle ihr HTML, parst der Scraper 0 Events
        # und meldet keinen Fehler - in der Liste sieht das aus wie ein ruhiger
        # Tag. Nur der Vergleich mit dem letzten erfolgreichen Lauf macht daraus
        # ein Signal, deshalb gilt so ein Lauf als nicht erfolgreich.
        error = None
        with db.get_conn() as conn:
            previous = db.last_successful_run(conn, name)
            if not found and previous and previous["event_count"]:
                error = f"0 Events, zuletzt waren es {previous['event_count']}."
                logger.warning("%s: %s Hat sich das HTML geaendert?", label, error)
            else:
                logger.info("%s: %d Events.", label, len(found))
            db.record_scrape_run(conn, name, started_at,
                                 datetime.utcnow().isoformat(), ok=error is None,
                                 event_count=len(found), error=error)

    with db.get_conn() as conn:
        new_count = db.upsert_events(conn, events)
        # Erst nach dem Speichern: die Erkennung vergleicht alle Quellen im
        # Zeitraum miteinander, nicht nur die gerade geholten Einträge.
        duplicate_count = dedup.link_duplicates(conn, today.isoformat(), end.isoformat())
        # Dry-Run: meldet nur, was verwaist waere (siehe db.expire_orphaned_events).
        # Scharf schalten ist ein eigener, spaeterer Commit.
        db.expire_orphaned_events(conn, today.isoformat())
    logger.info(
        "Scrape fertig: %d Events gesehen, %d davon neu, %d Doppelungen ausgeblendet.",
        len(events), new_count, duplicate_count,
    )
    return len(events), new_count


def start_scheduler():
    scheduler = BackgroundScheduler(timezone=config.TIMEZONE)

    # Haelt die Web-Oberflaeche zwischen den manuellen/Erst-Scrapes aktuell.
    scheduler.add_job(run_scrape, CronTrigger(hour="*/6", minute=30), id="background_scrape")

    # Taegliche Sicherung der Datenbank (siehe app/backup.py). 03:45 ist bewusst
    # gewaehlt: die Scrapes laufen zur Minute 30, und um 04:00 startet auf dem
    # Pi der Watchtower-Lauf, der den Container neu bauen kann - ein Snapshot,
    # der da noch laeuft, waere abgeschnitten. Der Viertelstunde davor kommt
    # nichts anderes in die Quere.
    scheduler.add_job(backup.run_backup, CronTrigger(hour=3, minute=45), id="daily_backup")

    scheduler.start()
    return scheduler

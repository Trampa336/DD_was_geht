"""Einstiegspunkt: startet den Scrape-Scheduler und danach das Web-UI im
selben Prozess."""
import logging
from datetime import datetime, timedelta

from app import config, db
from app.scheduler import run_scrape, start_scheduler
from app.web import run_web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("dd-was-geht.main")

# Wie alt der letzte erfolgreiche Lauf sein darf, damit der Start ihn nicht
# wiederholt. Vorher scrapte JEDER Containerstart mehrere Minuten lang alle
# sechs Quellen - zusammen mit "restart: unless-stopped" wird aus einem
# Crash-Loop damit ein Dauerbeschuss fremder Server. Nach einem Neustart ist der
# letzte Erfolg praktisch immer frisch, also scrapt erst der Neustart nach
# Stunden wieder. Den Normalfall deckt ohnehin der */6-Job des Schedulers ab.
STARTUP_SCRAPE_MAX_AGE = timedelta(hours=6)


def main():
    db.init_db()

    with db.get_conn() as conn:
        last_success = db.last_successful_scrape(conn)
    age = None if last_success is None else datetime.utcnow() - datetime.fromisoformat(last_success)

    if age is None or age > STARTUP_SCRAPE_MAX_AGE:
        logger.info("Erster Scrape läuft (kann beim allerersten Start etwas dauern) ...")
        try:
            run_scrape()
        except Exception:
            logger.exception("Erster Scrape fehlgeschlagen - Web startet trotzdem.")
    else:
        logger.info("Start-Scrape übersprungen: letzter Erfolg vor %d Minuten.",
                    age.total_seconds() // 60)

    start_scheduler()
    logger.info("Scheduler gestartet (Hintergrund-Scrape alle 6 Stunden).")

    # Blockiert im Hauptthread - der Scheduler laeuft in eigenen Threads
    # daneben weiter. Es gibt keinen zweiten Dienst mehr, der den Prozess
    # am Leben halten muesste.
    logger.info("Web-UI läuft auf Port %s", config.WEB_PORT)
    run_web()


if __name__ == "__main__":
    main()

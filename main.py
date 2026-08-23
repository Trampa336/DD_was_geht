"""Einstiegspunkt: startet den Scrape-Scheduler und danach das Web-UI im
selben Prozess."""
import logging

from app import config, db
from app.scheduler import run_scrape, start_scheduler
from app.web import run_web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("dd-was-geht.main")


def main():
    db.init_db()

    logger.info("Erster Scrape läuft (kann beim allerersten Start etwas dauern) ...")
    try:
        run_scrape()
    except Exception:
        logger.exception("Erster Scrape fehlgeschlagen - Web startet trotzdem.")

    start_scheduler()
    logger.info("Scheduler gestartet (Hintergrund-Scrape alle 6 Stunden).")

    # Blockiert im Hauptthread - der Scheduler laeuft in eigenen Threads
    # daneben weiter. Es gibt keinen zweiten Dienst mehr, der den Prozess
    # am Leben halten muesste.
    logger.info("Web-UI läuft auf Port %s", config.WEB_PORT)
    run_web()


if __name__ == "__main__":
    main()

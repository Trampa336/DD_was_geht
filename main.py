"""Einstiegspunkt: startet Web-UI (eigener Thread), Scheduler und Telegram-Bot
(asyncio-Hauptschleife) gemeinsam in einem Prozess/Container."""
import asyncio
import logging
import threading

from app import config, db
from app.bot import run_bot
from app.scheduler import run_scrape, start_scheduler
from app.web import run_web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("dd-was-geht.main")


def _check_config():
    missing = []
    if not config.TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not config.TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if config.REDDIT_ENABLED:
        for name in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
                     "REDDIT_USER_AGENT", "ANTHROPIC_API_KEY"):
            if not getattr(config, name):
                missing.append(name)
    if missing:
        raise SystemExit(
            f"Fehlende Konfiguration in .env: {', '.join(missing)}. "
            f"Siehe .env.example."
        )


async def main():
    _check_config()
    db.init_db()

    # Das Web-UI startet VOR dem ersten Scrape. Frueher hing es dahinter, und
    # weil ein Voll-Scrape mehrere Minuten dauert, war die Seite nach jedem
    # Neustart genau so lange tot (Verbindung abgewiesen, nicht mal eine
    # Fehlerseite). Die Datenbank steht zu diesem Zeitpunkt schon, ein leerer
    # oder noch alter Bestand wird also normal ausgeliefert.
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    logger.info("Web-UI läuft auf Port %s", config.WEB_PORT)

    logger.info("Erster Scrape läuft (kann beim allerersten Start etwas dauern) ...")
    try:
        await asyncio.to_thread(run_scrape)
    except Exception:
        logger.exception("Erster Scrape fehlgeschlagen - Bot/Web starten trotzdem.")

    start_scheduler()
    logger.info("Scheduler gestartet (täglich %02d:%02d, wöchentlich Tag %d %02d:%02d).",
                config.DAILY_SEND_HOUR, config.DAILY_SEND_MINUTE,
                config.WEEKLY_SEND_DAY, config.WEEKLY_SEND_HOUR, config.WEEKLY_SEND_MINUTE)

    logger.info("Telegram-Bot startet (Polling) ...")
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())

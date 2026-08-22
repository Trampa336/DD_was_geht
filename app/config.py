"""Zentrale Konfiguration, gelesen aus Umgebungsvariablen (.env)."""
import os
from dotenv import load_dotenv

load_dotenv()


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _float(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

DB_PATH = os.environ.get("DB_PATH", "./data/dd-was-geht.db")

DAILY_SEND_HOUR = _int("DAILY_SEND_HOUR", 8)
DAILY_SEND_MINUTE = _int("DAILY_SEND_MINUTE", 0)

WEEKLY_SEND_DAY = _int("WEEKLY_SEND_DAY", 0)  # 0 = Montag
WEEKLY_SEND_HOUR = _int("WEEKLY_SEND_HOUR", 8)
WEEKLY_SEND_MINUTE = _int("WEEKLY_SEND_MINUTE", 15)

DAILY_TOP_N = _int("DAILY_TOP_N", 6)

# Cover-Bilder im Telegram-Digest: Events, für die schon eine image_url in der
# DB steht, gehen als Foto mit Bildunterschrift raus statt als reiner Text.
# Nachgeladen wird dafür nichts (siehe bot._send_event). Auf "false" verhält
# sich der Newsletter exakt wie vorher.
NEWSLETTER_COVERS = os.environ.get("NEWSLETTER_COVERS", "true").strip().lower() == "true"

WEB_PORT = _int("WEB_PORT", 8080)

# Ab diesem "Für dich"-Score (siehe app/scoring.py) gilt ein Event in der
# Web-Liste als Treffer und wird hervorgehoben. 80 ist der Zielwert - solange
# das Lernmodell wenig Feedback hat, deckelt die Laplace-Glättung die Scores
# aber nach oben: bei 29 Likes / 17 Skips lag das Maximum über alle 5008
# kommenden Events bei 78,6. Deshalb ist der Wert per .env absenkbar.
HIGHLIGHT_SCORE = _int("HIGHLIGHT_SCORE", 80)

# --- Resident Advisor als Quelle (ra.co) -----------------------------------
# Clubkultur/Electronic. Läuft über die öffentliche GraphQL-Schnittstelle von
# ra.co (siehe app/scrapers/ra.py), braucht keinen Schlüssel und ist deshalb
# standardmäßig an.
RA_ENABLED = os.environ.get("RA_ENABLED", "true").strip().lower() == "true"
# Gebiets-ID auf ra.co. 150 = Dresden (gegen die Live-API geprüft; die Liste
# aller Gebiete liefert die GET_AREAS-Abfrage, siehe README).
RA_AREA_ID = _int("RA_AREA_ID", 150)

# --- CyberSAX / SAX-Terminal als Quelle (cybersax.de) -----------------------
# Der Tageskalender des SAX-Stadtmagazins. Einzige Quelle, die die kleinen
# Laeden mit Programm systematisch listet (Blue Note, Cafe Saite, Kafe Zeitlos,
# Der Lude, Downtown, Kleinkunstbuehne Q24 ...). Braucht keinen Schluessel.
# Uebernommen wird bewusst nur ein Teil - siehe cybersax.BIG_VENUE_SLUGS.
CYBERSAX_ENABLED = os.environ.get("CYBERSAX_ENABLED", "true").strip().lower() == "true"

# --- AZ Conni als Quelle (azconni.de) --------------------------------------
# Einzelnes Haus, das in keinem Aggregator auftaucht und deshalb direkt geholt
# wird. Eine Anfrage pro Lauf (eine Uebersichtsseite fuer alle Termine).
AZCONNI_ENABLED = os.environ.get("AZCONNI_ENABLED", "true").strip().lower() == "true"

# --- Sektor Evolution als Quelle (sektor-evolution.de) ---------------------
# Anders als AZ Conni steht dieses Haus durchaus in den Aggregatoren - der Grund
# fuer die eigene Quelle ist der Link: aus rauze/ra kam im Newsletter ein
# ra.co-Permalink, gewuenscht ist die Seite des Ladens selbst. Mit sektor ganz
# vorn in SOURCE_PRIORITY gewinnt bei jeder Doppelung der Eintrag des Hauses.
# Eine Anfrage fuer die Uebersicht plus eine je Termin im Zeitraum (die
# Uebersicht nennt keine Uhrzeit - siehe app/scrapers/sektor.py).
SEKTOR_ENABLED = os.environ.get("SEKTOR_ENABLED", "true").strip().lower() == "true"

# --- Doppelungen zwischen Quellen ------------------------------------------
# Dieselbe Clubnacht steht oft auf rauze.de UND auf ra.co. Erkannte Doppelungen
# werden verbucht (Tabelle event_duplicates) und nur einmal ausgeliefert - die
# Version der Quelle, die hier weiter vorn steht, gewinnt. Quellen, die nicht
# in der Liste stehen, landen automatisch hinten.
#
# Warum diese Reihenfolge: sektor und azconni sind die Quellen der jeweiligen
# Haeuser selbst und damit fuer deren Termine die genauesten - und nur sie
# verlinken auf den Laden statt auf einen Aggregator. rauze und ra liefern
# Event-Permalinks, Bilder und Preise.
#
# cybersax steht ganz hinten, und das ist gemessen, nicht geraten: die Quelle
# hat keine Event-Permalinks, sondern nur die Tagesseite. Stand cybersax vor
# kulturkalender, verdraengte es 40 Eintraege eines Testlaufs und der
# Newsletter verlinkte danach auf eine Tagesliste mit 90 Zeilen statt auf die
# Veranstaltung - fill_missing_from_duplicate() konnte den besseren Link nicht
# nachtragen, weil die Tagesseite das url-Feld ja schon belegt. Der Gewinn
# dieser Quelle ist ihre Abdeckung (Laeden, die sonst niemand listet), nicht
# die Qualitaet der einzelnen Zeile - und Abdeckung braucht keine Prioritaet.
SOURCE_PRIORITY = [
    s.strip() for s in os.environ.get(
        "SOURCE_PRIORITY", "sektor,azconni,rauze,ra,kulturkalender,cybersax,reddit"
    ).split(",") if s.strip()
]
DEDUP_ENABLED = os.environ.get("DEDUP_ENABLED", "true").strip().lower() == "true"

# --- Reddit als zusätzliche Quelle (optional, standardmäßig aus) -----------
# Anders als die beiden HTML-Quellen liefert Reddit keine strukturierten
# Veranstaltungslisten, sondern Fließtext. Deshalb entscheidet ein LLM, ob ein
# Post überhaupt ein Event ankündigt, und zieht Datum/Zeit/Titel/Ort heraus.
REDDIT_ENABLED = os.environ.get("REDDIT_ENABLED", "false").strip().lower() == "true"
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "dd-was-geht/1.0")

REDDIT_SUBREDDITS_FILE = os.environ.get(
    "REDDIT_SUBREDDITS_FILE", "./config/reddit_subreddits.txt"
)
# Kommagetrennte Ergänzung zur Datei - praktisch zum schnellen Ausprobieren,
# ohne die Datei im Container anzufassen.
REDDIT_SUBREDDITS_EXTRA = os.environ.get("REDDIT_SUBREDDITS", "")

REDDIT_MAX_POSTS_PER_SUBREDDIT = _int("REDDIT_MAX_POSTS_PER_SUBREDDIT", 25)
# Etwas mehr als 24h, damit bei einem verspäteten Lauf nichts durchrutscht.
REDDIT_POLL_LOOKBACK_HOURS = _int("REDDIT_POLL_LOOKBACK_HOURS", 30)
REDDIT_SUBREDDIT_DELAY_SECONDS = _int("REDDIT_SUBREDDIT_DELAY_SECONDS", 1)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
REDDIT_LLM_MODEL = os.environ.get("REDDIT_LLM_MODEL", "claude-haiku-4-5")
REDDIT_LLM_BATCH_SIZE = _int("REDDIT_LLM_BATCH_SIZE", 10)
REDDIT_LLM_CONFIDENCE_THRESHOLD = _float("REDDIT_LLM_CONFIDENCE_THRESHOLD", 0.6)
# Harte Obergrenze pro Lauf, damit ein Traffic-Ausreißer in einem Subreddit
# nicht unbemerkt Geld kostet.
REDDIT_LLM_MAX_CALLS_PER_RUN = _int("REDDIT_LLM_MAX_CALLS_PER_RUN", 20)

TIMEZONE = "Europe/Berlin"

# Kategorien, die im Bot/Web-UI als Filter angeboten werden.
CATEGORY_LABELS = {
    "kultur": "Kultur & Bühne",
    "musik": "Musik & Nightlife",
    "familie": "Familie & Kinder",
    "fuehrungen": "Führungen & Touren",
    "outdoor": "Feste & Märkte",
    "sport": "Sport & Bewegung",
    "sonstiges": "Weiteres",
}

# Chip-Beschriftung in der Kategorienzeile des Web-UI: dieselben Schlüssel wie
# oben, aber kurz genug, dass alle Kategorien nebeneinander in eine Zeile passen.
# Die langen Labels bleiben für die Tags an den Event-Zeilen.
CATEGORY_SHORT_LABELS = {
    "kultur": "Kultur",
    "musik": "Musik",
    "familie": "Familie",
    "fuehrungen": "Führungen",
    "outdoor": "Feste",
    "sport": "Sport",
    "sonstiges": "Weiteres",
}

# Quellen, die im Web-UI als Filter angeboten werden. Der Schlüssel ist der
# Wert in events.source, wie ihn die Scraper schreiben.
SOURCE_LABELS = {
    "kulturkalender": "Kulturkalender",
    "rauze": "Rauze",
    "ra": "Resident Advisor",
    "cybersax": "SAX Terminal",
    "azconni": "AZ Conni",
    "sektor": "Sektor Evolution",
    "reddit": "Reddit",
}

# Kategorien, die standardmäßig aus Newsletter (Telegram) und Web-Startansicht
# rausgefiltert werden - im Web-UI aber weiterhin über den Kategorie-Chip
# erreichbar. Kommagetrennt, z.B. "familie,outdoor".
#
# "fuehrungen" steht hier, weil die Kategorie den Digest sonst dominiert: sie
# ist mit Abstand die größte (gemessen am 22.08.2026 rund 1160 von 5500
# Einträgen, davon ~970 allein über das Stichwort "Führung"). Das sind
# überwiegend täglich wiederkehrende Standardtouren - im Web über den eigenen
# Chip gewollt, im täglichen Newsletter nur Rauschen.
EXCLUDED_CATEGORIES = [
    c.strip() for c in os.environ.get(
        "EXCLUDED_CATEGORIES", "familie,fuehrungen").split(",")
    if c.strip()
]

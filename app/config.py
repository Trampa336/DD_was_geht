"""Zentrale Konfiguration.

Oben steht, was per `.env` eingestellt wird: Pfad, Port und der Highlight-Wert.
Alles darunter sind feste Konstanten - Werte, die zwar Entscheidungen sind,
aber im Betrieb nie umgestellt wurden. Wer eine davon ändern will, ändert sie
hier und deployt neu, statt eine Umgebungsvariable zu setzen, die nirgends
gesetzt ist.
"""
import os
from dotenv import load_dotenv

from . import registry

load_dotenv()


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# --- Aus der .env ----------------------------------------------------------

DB_PATH = os.environ.get("DB_PATH", "./data/dd-was-geht.db")

WEB_PORT = _int("WEB_PORT", 8080)

# Ab diesem "Für dich"-Score (siehe app/scoring.py) gilt ein Event in der
# Web-Liste als Treffer und wird hervorgehoben. 80 ist der Zielwert - solange
# das Lernmodell wenig Feedback hat, deckelt die Laplace-Glättung die Scores
# aber nach oben: bei 29 Likes / 17 Skips lag das Maximum über alle 5008
# kommenden Events bei 78,6. Deshalb ist der Wert per .env absenkbar.
HIGHLIGHT_SCORE = _int("HIGHLIGHT_SCORE", 80)


# --- Feste Konstanten ------------------------------------------------------

TIMEZONE = "Europe/Berlin"

# --- Sicherung der Datenbank -----------------------------------------------
# Wie viele Tages-Snapshots in data/backups/ stehen bleiben (app/backup.py).
# 14 Tage sind der Abstand, in dem ein stiller Schaden - eine missglueckte
# Migration, ein verunglueckter Dedup-Lauf - erfahrungsgemaess auffaellt.
# Bei rund 4,5 MB je Snapshot kostet das etwa 63 MB Platte.
BACKUP_KEEP = 14

# Gebiets-ID auf ra.co für die Resident-Advisor-Quelle (app/scrapers/ra.py).
# 150 = Dresden, gegen die Live-API geprüft; die Liste aller Gebiete liefert
# die GET_AREAS-Abfrage, siehe README.
RA_AREA_ID = 150

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
# Die Reihenfolge selbst ist tragend, nicht nur die Menge: db._source_rank ist
# ein list.index(), und db._best_source und db._keeps_own_url kommen genau
# deshalb ohne Gleichstands-Regel aus. Eine stille Umsortierung schriebe
# events.source und events.url um - also wird sie in tests_smoke.py gegen die
# frueher hier stehende Literal-Liste geprueft, nicht nur begutachtet.
SOURCE_PRIORITY = registry.priority_order()

# Kategorien, die im Web-UI als Filter angeboten werden.
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

# SOURCE_LABELS hatte zwei Aufgaben, die nur zufaellig dieselbe Liste waren:
# "alle Quellen, die es gibt" (Vollstaendigkeit in /api/health und in der
# Verwaisungs-Erkennung) und "die Chips in der Quellen-Zeile des Web-UI".
# Solange jede Quelle ihren eigenen Chip hat, sind beide gleich; sobald viele
# Haeuser dazukommen, ist das nicht mehr gewollt. Deshalb stehen sie jetzt
# getrennt - heute mit identischem Inhalt.

# Alle Quellen-Slugs, in Scrape-Reihenfolge. Vollstaendigkeitsliste.
SOURCES = registry.live_slugs()

# Slug -> Beschriftung, fuer /api/health und die Protokollzeilen des Scrapers.
SOURCE_LABELS = registry.labels()

# Chip-Beschriftung in der Quellen-Zeile des Web-UI. Der Schlüssel ist der
# Wert in events.source, wie ihn die Scraper schreiben.
SOURCE_GROUP_LABELS = registry.labels()

# Kategorien, die standardmäßig aus der Web-Startansicht rausgefiltert werden -
# im Web-UI aber weiterhin über den Kategorie-Chip erreichbar.
#
# "fuehrungen" steht hier, weil die Kategorie den Digest sonst dominiert: sie
# ist mit Abstand die größte (gemessen am 22.08.2026 rund 1160 von 5500
# Einträgen, davon ~970 allein über das Stichwort "Führung"). Das sind
# überwiegend täglich wiederkehrende Standardtouren - im Web über den eigenen
# Chip gewollt, im täglichen Newsletter nur Rauschen.
EXCLUDED_CATEGORIES = ["familie", "fuehrungen"]

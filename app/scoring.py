"""Lern-Logik: aus Davids Herzen lernen, welche Kategorien/Orte/Schlüsselwörter
er mag, und daraus einen 0-100 'Für dich'-Score pro Event berechnen.

Kein LLM, keine externe API - eine simple, nachvollziehbare Laplace-geglättete
Like-Rate pro Feature (Kategorie, Ort, Schlagwort), gemittelt über alle
Features eines Events. Ohne jede Historie ergibt das neutral 50/100 für alle
Events; jedes Herz verschiebt die betroffenen Features nach oben.

WAS SICH MIT P5c GEÄNDERT HAT - und was das für den Score bedeutet:
Gefüttert wurde dieses Modell bis P5c aus 👍/👎 (Tabelle `reactions`), also aus
einem ZWEISEITIGEN Signal. Herzen sind einseitig: es gibt kein Gegenstück zum
Daumen runter, `weights.skips` bleibt deshalb dauerhaft 0. Damit liegt die
Laplace-Rate (likes+1)/(likes+skips+2) immer in [0,5 ; 1) - der Score kann
ab jetzt nur noch von 50 nach OBEN wandern, nie darunter.

Das ist keine Ungenauigkeit, sondern eine Folge der Produktentscheidung (#3:
"ein Herz statt Daumen hoch UND runter"), und sie hat genau eine Konsequenz im
UI: der Filter "Wenig relevant" (Score < 40) war damit unerreichbar geworden
und ist in P5c entfernt worden, statt als toter Schalter stehen zu bleiben.
Die beiden anderen Verbraucher des Scores - die Top-Treffer-Marke an der Zeile
(config.HIGHLIGHT_SCORE) und die Sortierung von /api/fuer-dich - passen
dagegen zu einem rein positiven Signal und bleiben.
"""
from . import db, normalize

FEATURE_WEIGHTS = {
    "category": 1.0,
    "venue": 1.0,
    "keyword": 0.6,
}


# "sonstiges" ist kein Geschmacksmerkmal, sondern das Restfach des Klassifikators:
# dort landet, was keine Regel erkannt hat. Als Lern-Feature ist es schädlich -
# in der Live-Datenbank stand category:sonstiges bei 0 Likes / 4 Skips, was per
# Laplace-Glättung ALLE 1734 Einträge dieses Buckets dauerhaft auf ~29-41%
# gedrückt hat, darunter reichlich nur falsch einsortierte Veranstaltungen.
# Vier Klicks dürfen nicht 40% des Katalogs stummschalten.
NEUTRAL_CATEGORIES = {"sonstiges"}


def _feature_keys(event):
    keys = []
    if event.get("category") and event["category"] not in NEUTRAL_CATEGORIES:
        keys.append(("category", f"category:{event['category']}", FEATURE_WEIGHTS["category"]))
    if event.get("venue"):
        keys.append(("venue", f"venue:{normalize.slugify(event['venue'])}", FEATURE_WEIGHTS["venue"]))
    for kw in normalize.extract_keywords(event.get("title", "")):
        keys.append(("keyword", f"keyword:{kw}", FEATURE_WEIGHTS["keyword"]))
    return keys


def score_event(conn, event):
    """0-100: 50 = neutral/unbekannt, >50 = passt vermutlich, <50 eher nicht."""
    keys = _feature_keys(event)
    if not keys:
        return 50.0
    total_weight = 0.0
    weighted_sum = 0.0
    for _, key, weight in keys:
        likes, skips = db.get_weight(conn, key)
        rate = (likes + 1) / (likes + skips + 2)  # Laplace-Glättung, 0.5 ohne Daten
        weighted_sum += rate * weight
        total_weight += weight
    return round(100 * weighted_sum / total_weight, 1)


def score_events(conn, events):
    for e in events:
        e["score"] = score_event(conn, e)
    return events


def apply_heart(conn, event, on):
    """Verbucht ein gesetztes (on=True) oder entferntes Herz in den Gewichten.

    EINMAL PRO SERIE, nicht einmal pro Zeigung: geherzt wird die Serie
    (Entscheidung #26), und die Frauenkirche fuehrt dieselbe Tour 5-8 mal am
    Tag. Wuerde jede Zeigung zaehlen, haette ein einziger Klick auf eine
    Domfuehrung achtmal so viel Gewicht wie ein Klick auf ein Konzert - das
    Lernmodell saehe eine Vorliebe, die nur die Taktung der Quelle ist.
    Gezaehlt wird deshalb der Anker der Serie.

    Rueckgaengig machen ist dasselbe mit like_delta=-1; db.bump_weight()
    klemmt bei 0 ab, ein doppeltes Entherzen kann die Gewichte also nicht
    negativ ziehen."""
    delta = 1 if on else -1
    for _, key, _ in _feature_keys(event):
        db.bump_weight(conn, key, like_delta=delta)
    return True


def top_picks(conn, events, limit=6):
    scored = score_events(conn, list(events))
    scored.sort(key=lambda e: e["score"], reverse=True)
    return scored[:limit]

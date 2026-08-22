"""Lern-Logik: aus 👍/👎-Reaktionen lernen, welche Kategorien/Orte/Schlüsselwörter
David mag, und daraus einen 0-100 'Für dich'-Score pro Event berechnen.

Kein LLM, keine externe API - eine simple, nachvollziehbare Laplace-geglättete
Like-Rate pro Feature (Kategorie, Ort, Schlagwort), gemittelt über alle
Features eines Events. Ohne jede Historie ergibt das neutral 50/100 für alle
Events; jedes Feedback verschiebt die betroffenen Features Richtung 0 oder 100.
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


def apply_reaction(conn, event, reaction):
    """reaction: 'like' oder 'skip'. Idempotent - wiederholtes Klicken derselben
    Reaktion verändert nichts weiter; ein Wechsel (z.B. skip -> like) macht die
    alte Gewichtung rückgängig, bevor die neue angewendet wird."""
    previous = db.get_reaction(conn, event["uid"])
    if previous == reaction:
        return False

    keys = _feature_keys(event)

    if previous == "like":
        for _, key, _ in keys:
            db.bump_weight(conn, key, like_delta=-1)
    elif previous == "skip":
        for _, key, _ in keys:
            db.bump_weight(conn, key, skip_delta=-1)

    if reaction == "like":
        for _, key, _ in keys:
            db.bump_weight(conn, key, like_delta=1)
    elif reaction == "skip":
        for _, key, _ in keys:
            db.bump_weight(conn, key, skip_delta=1)

    db.set_reaction(conn, event["uid"], reaction)
    return True


def top_picks(conn, events, limit=6):
    scored = score_events(conn, list(events))
    scored.sort(key=lambda e: e["score"], reverse=True)
    return scored[:limit]

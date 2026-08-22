"""Die ausgelieferte Event-Liste - einmal gebaut, zweimal benutzt.

Das Web-UI (app/web.py) und der statische Export (tools/export_static.py)
zeigen dieselbe Liste: Zeitraum aus der DB holen, mit dem persoenlichen Score
versehen (app/scoring.py), sortieren, ausliefern. Frueher stand dieser Ablauf
zweimal im Code und musste per Hand synchron gehalten werden. Hier steht er
einmal; was die beiden Ausgaben wirklich unterscheidet, sind die Parameter von
build_events() - und dort steht auch, warum sie sich unterscheiden.
"""
from collections import OrderedDict

from . import db, scoring

# Felder, die das Frontend tatsaechlich anfasst. Alles andere (first_seen,
# raw_category, detail_fetched_at ...) ist Innenleben und bleibt auf dem Pi.
EVENT_FIELDS = (
    "uid", "title", "date", "time", "venue", "category", "source", "url",
    "image_url", "price_text", "description",
)


def slim_event(event):
    """Ein Event so, wie es die Tagesdatei des statischen Exports braucht.
    Leere Felder fliegen raus - das spart rund ein Zehntel Datenmenge, und das
    Frontend behandelt fehlende Felder ohnehin schon als leer."""
    out = OrderedDict()
    for field in EVENT_FIELDS:
        value = event.get(field)
        if value not in (None, ""):
            out[field] = value
    if event.get("ongoing"):
        out["ongoing"] = True
    # Nur "weiter" wird mitgeschrieben (siehe app/geo.py): Dresden ist der
    # Normalfall und braucht in jeder Zeile kein eigenes Feld, und das Umland
    # verhaelt sich im Frontend genau wie Dresden.
    if event.get("region") == "weiter":
        out["region"] = "weiter"
    # Der Score aus dem persoenlichen Lernmodell (app/scoring.py). Bewertet wird
    # nur auf dem Pi; die oeffentliche Kopie zeigt das Ergebnis mit, damit dort
    # dieselbe Empfehlungszeile und derselbe "wenig relevant"-Filter funktionieren
    # wie im Heimnetz.
    out["score"] = round(event.get("score", 50.0), 1)
    return out


def build_events(conn, start, end, categories=None, exclude_categories=None,
                 with_reactions=False, slim=False):
    """Die Events von start bis end (beides date-Objekte, beide Tage inklusive),
    bewertet und nach Datum/Uhrzeit sortiert. Events ohne Uhrzeit stehen am Ende
    ihres Tages.

    categories: nur diese Kategorie-Keys, leer/None = alle. Das Web-UI reicht
        hier die angeklickten Chips durch, der Export nichts.

    exclude_categories: diese Kategorie-Keys weglassen (config.EXCLUDED_CATEGORIES).
        Das Web-UI filtert damit seine Startansicht "Alle"; wer eine Kategorie
        bewusst anklickt, bekommt sie auch dann, wenn sie ausgeschlossen ist.
        Der statische Export filtert hier bewusst NICHT: EXCLUDED_CATEGORIES ist
        ja nur die Startansicht und ueber die Chips wieder erreichbar - das
        entscheidet dort der Browser, der die Tagesdateien komplett bekommt.

    with_reactions: je Event das gespeicherte 👍/👎 mitgeben. Nur das Web-UI
        braucht das - bewertet wird ausschliesslich im Heimnetz, die
        oeffentliche Kopie hat keine Bewerten-Buttons (siehe
        tools/export_static.py).

    slim: die Events auf die Felder eindampfen, die das Frontend anfasst
        (siehe slim_event). Der Export tut das, weil die Tagesdateien viermal
        taeglich nach Git wandern; das Web-UI liefert die vollen Zeilen aus.
    """
    events = db.events_for_range(conn, start.isoformat(), end.isoformat(),
                                 categories, exclude_categories=exclude_categories)
    events = scoring.score_events(conn, events)
    if with_reactions:
        for event in events:
            event["reaction"] = db.get_reaction(conn, event["uid"])
    events.sort(key=lambda e: (e["date"], e["time"] or "99:99"))
    if slim:
        events = [slim_event(event) for event in events]
    return events

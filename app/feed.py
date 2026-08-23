"""Die ausgelieferte Event-Liste fuers Web-UI (app/web.py): Zeitraum aus der
DB holen, mit dem persoenlichen Score versehen (app/scoring.py), sortieren,
ausliefern.
"""
from . import db, scoring


def build_events(conn, start, end, categories=None, exclude_categories=None,
                 with_reactions=False):
    """Die Events von start bis end (beides date-Objekte, beide Tage inklusive),
    bewertet und nach Datum/Uhrzeit sortiert. Events ohne Uhrzeit stehen am Ende
    ihres Tages.

    categories: nur diese Kategorie-Keys, leer/None = alle. Das Web-UI reicht
        hier die angeklickten Chips durch.

    exclude_categories: diese Kategorie-Keys weglassen (config.EXCLUDED_CATEGORIES).
        Das Web-UI filtert damit seine Startansicht "Alle"; wer eine Kategorie
        bewusst anklickt, bekommt sie auch dann, wenn sie ausgeschlossen ist.

    with_reactions: je Event das gespeicherte 👍/👎 mitgeben.
    """
    events = db.events_for_range(conn, start.isoformat(), end.isoformat(),
                                 categories, exclude_categories=exclude_categories)
    events = scoring.score_events(conn, events)
    if with_reactions:
        for event in events:
            event["reaction"] = db.get_reaction(conn, event["uid"])
    events.sort(key=lambda e: (e["date"], e["time"] or "99:99"))
    return events

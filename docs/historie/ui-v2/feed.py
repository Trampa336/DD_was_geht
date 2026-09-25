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
# venue_slug (P5b): der Griff auf die Venue-Seite, siehe db.list_venues().
EVENT_FIELDS = (
    "uid", "title", "date", "time", "venue", "category", "source", "url",
    "image_url", "price_text", "description", "venue_slug",
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
    if event.get("tags"):
        out["tags"] = event["tags"]
    # P5b: der neue Regions-Schalter (Standard: nur Dresden) muss 'umland' UND
    # 'weiter' vom Normalfall unterscheiden koennen - vorher (nur "weiter"
    # wurde mitgeschrieben) sah eine Umland-Zeile in der Exportdatei genauso
    # aus wie Dresden, weil der alte Schalter "Umgebung einschliessen" beide
    # ohnehin immer zeigte (siehe app/geo.py, Bericht zu P5b).
    if event.get("region") not in (None, "dresden"):
        out["region"] = event["region"]
    # Der Score aus dem persoenlichen Lernmodell (app/scoring.py). Geherzt wird
    # nur auf dem Pi; die oeffentliche Kopie zeigt das Ergebnis mit, damit dort
    # dieselbe Empfehlungszeile und dieselbe Top-Treffer-Marke funktionieren wie
    # im Heimnetz. Seit P5c wird der Score aus den Herzen gefuettert statt aus
    # 👍/👎 - er bleibt 50.0, solange David noch nichts geherzt hat, und kann
    # danach nur noch steigen (einseitiges Signal, siehe scoring.py).
    out["score"] = round(event.get("score", 50.0), 1)
    return out


def venue_cover(venue, events):
    """Cover-URL fuer eine Venue-Seite.

    Reihenfolge (P5a, NICHT umkehren - siehe migrations/001_schema_v2.sql §1):
    venues.og_image_url zuerst (das ist bereits das Ergebnis des kk_cover_url-
    vor-Homepage-og:image-Fallbacks aus tools/load_enrichment.py). Fehlt sie,
    das Bild des naechsten anstehenden Events, falls die Quelle eins
    mitgeliefert hat. Erst wenn auch das fehlt, bleibt die Flaeche leer
    (Platzhalter im Template).

    Wie viel dieser Fallback traegt, misst tools/venue_readiness_report.py,
    Abschnitt 4 - hier steht bewusst KEINE Zahl mehr: die alte Fassung nannte
    "569 nie angefragte Venues, davon 67,7% mit Event-Bild", und beide Werte
    reproduzierten spaeter nicht mehr, weil jeder Anreicherungslauf Venues aus
    der Gruppe herausnimmt - P5t verschob 74 Venues von "nie versucht" nach
    'not_found', womit aus 569 495 wurden und aus 67,7% 77,8% (385/495, Stand
    12.09.2026). Der Bericht rechnet die Quote bei jedem Lauf neu und nennt
    dabei seinen Nenner."""
    if venue.get("og_image_url"):
        return venue["og_image_url"]
    for event in events:
        if event.get("image_url"):
            return event["image_url"]
    return None


def build_events(conn, start, end, categories=None, exclude_categories=None,
                 slim=False):
    """Die Events von start bis end (beides date-Objekte, beide Tage inklusive),
    bewertet und nach Datum/Uhrzeit sortiert. Events ohne Uhrzeit stehen am Ende
    ihres Tages.

    categories: nur diese Kategorie-Keys, leer/None = alle. Das Web-UI reicht
        hier die angeklickten Chips durch, der Export nichts.

    exclude_categories: diese Kategorie-Keys weglassen (Kategorien mit
        default_visible=0, siehe db.list_categories/web._default_hidden seit
        P5b - vorher config.EXCLUDED_CATEGORIES). Das Web-UI filtert damit
        seine Startansicht "Alle"; wer eine Kategorie bewusst anklickt, bekommt
        sie auch dann, wenn sie default_visible=0 hat. Der statische Export
        filtert hier bewusst NICHT: das ist ja nur die Startansicht und ueber
        die Chips wieder erreichbar - das entscheidet dort der Browser, der
        die Tagesdateien komplett bekommt.

    Ein frueherer Parameter with_reactions haengte je Event das gespeicherte
    👍/👎 an. Er ist mit P5c ersatzlos weg: ein Herz haengt nicht an der
    einzelnen Zeigung, sondern an der Serie (Entscheidung #26), deshalb holt
    sich die Liste im Browser die Herzen als EINE Schluesselliste ueber
    /api/herzen statt als Feld an jedem einzelnen Event.

    slim: die Events auf die Felder eindampfen, die das Frontend anfasst
        (siehe slim_event). Der Export tut das, weil die Tagesdateien viermal
        taeglich nach Git wandern; das Web-UI liefert die vollen Zeilen aus.
    """
    events = db.events_for_range(conn, start.isoformat(), end.isoformat(),
                                 categories, exclude_categories=exclude_categories)
    events = scoring.score_events(conn, events)
    # Tags (P5b): eine Anfrage fuer alle Events des Zeitraums statt einer pro
    # Event - dieselbe Begruendung wie bei venue_category_hints in db.py.
    tag_map = db.tags_for_events(conn, [e["uid"] for e in events])
    for event in events:
        event["tags"] = tag_map.get(event["uid"], [])
    events.sort(key=lambda e: (e["date"], e["time"] or "99:99"))
    if slim:
        events = [slim_event(event) for event in events]
    return events

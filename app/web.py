"""Personalisierte Web-Oberfläche (Flask) - dieselbe Optik wie der Artifact-
Prototyp 'DD was geht', aber live aus der SQLite-Datenbank statt mit
Beispieldaten, plus 'Für dich'-Bereich und Like/Skip direkt im Browser.

Die Seite selbst ist app/templates/index.html (nur noch Markup); Stylesheet und
Skripte liegen daneben in app/static/ und werden von Flask ausgeliefert."""
import hashlib
import os
from datetime import date

from flask import Flask, abort, jsonify, render_template, request

from . import config, db, feed, scoring
from .ranges import day_range, week_range
from .scrapers import detail_fetch

app = Flask(__name__)


@app.template_filter("de_date")
def de_date(iso):
    """'2026-09-20' -> '20.09.2026', fuer die Venue-Seite (P5b). Genutzt vom
    Flask-Template UND vom statischen Export - beide rendern app/templates/
    venue.html ueber dieselbe Flask-App-Instanz (tools/export_static.py
    importiert web.app), ein Filter reicht also fuer beide Modi."""
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return iso


STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Nur diese Dateien darf die oeffentliche Kopie mitnehmen. rating.js fehlt hier
# mit Absicht: dort gibt es keinen Server, an den eine Bewertung ginge, also
# soll auch der Code dafuer nicht dabei sein (siehe tools/export_static.py).
PUBLIC_ASSETS = ("boot.js", "app.css", "app.js", "background.js", "orte.js",
                  "flatpickr.min.js", "flatpickr.min.css", "flatpickr-de.js")


def asset_version():
    """Kurzer Hash ueber die statischen Dateien, haengt als ?v=... an jedem
    Link. Ohne ihn holte der Browser nach einem Deploy weiter CSS und JS aus
    seinem Cache - die Seite saehe kaputt aus, obwohl auf dem Pi das Richtige
    liegt."""
    digest = hashlib.sha1()
    for name in sorted(os.listdir(STATIC_DIR)):
        with open(os.path.join(STATIC_DIR, name), "rb") as handle:
            digest.update(handle.read())
    return digest.hexdigest()[:8]


ASSET_VERSION = asset_version()


def _requested_day():
    """?date=YYYY-MM-DD aus dem Kalender. Fehlt der Parameter oder ist er
    ungueltig, gilt heute - das deckt sowohl den ersten Seitenaufruf (noch
    keine Auswahl) als auch einen kaputten/manipulierten Wert ab."""
    raw = request.args.get("date")
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return date.today()


def _selected_categories(valid_slugs):
    """Mehrfachauswahl aus ?cat=musik,kultur. Unbekannte Keys fliegen raus,
    "alle" bzw. leer bedeutet: keine Auswahl (= alles, minus den Kategorien mit
    default_visible=0)."""
    raw = request.args.get("cat", "alle")
    return [c for c in db.category_filter(raw) if c in valid_slugs]


def api_urls():
    """URLs, wie sie das Template braucht - hier absolut (Flask liefert unter
    "/" aus, das gilt unabhaengig davon, wie tief eine Route liegt). Der
    statische Export baut sich das Gegenstueck relativ zusammen (siehe
    tools/export_static.py._static_urls), weil GitHub Pages auch aus einem
    Unterverzeichnis des Repos ausgeliefert werden kann (siehe app/templates/
    index.html, aeltere Fassung). EIN Template, ZWEI Aufrufer - das ist der von
    P5a verifizierte Vertrag (tools/export_static.py:160-172)."""
    return {
        "index": "/",
        "venues_index": "/orte",
        "venue": lambda slug: f"/orte/{slug}",
        "asset": lambda name: f"/static/{name}?v={ASSET_VERSION}",
    }


def _default_hidden(categories):
    """Kategorie-Slugs mit default_visible=0 (categories-Tabelle) - was die
    Startansicht ausblendet, bis jemand bewusst einen Kategorie-Chip anklickt.
    Ersetzt seit P5b config.EXCLUDED_CATEGORIES als Quelle (siehe Kommentar
    dort: die Liste und die Tabelle widersprachen sich bei 'familie')."""
    return [c["slug"] for c in categories if not c["default_visible"]]


@app.route("/")
def index():
    # mode="api": die Seite spricht mit dieser Flask-App. Dieselbe Vorlage wird
    # von tools/export_static.py ein zweites Mal mit mode="static" gerendert -
    # das ist die oeffentliche Kopie ohne Server (siehe README).
    with db.get_conn() as conn:
        categories = db.list_categories(conn)
        tags = db.list_tags(conn)
    return render_template("index.html", categories=categories, tags=tags,
                           sources=config.SOURCE_GROUP_LABELS, mode="api",
                           default_hidden=_default_hidden(categories),
                           generated_at="",
                           highlight_score=config.HIGHLIGHT_SCORE,
                           asset_v=ASSET_VERSION, urls=api_urls())


@app.route("/api/events")
def api_events():
    day = _requested_day()
    start, end = day_range(day)

    with db.get_conn() as conn:
        categories = db.list_categories(conn)
        selected = _selected_categories({c["slug"] for c in categories})
        # Nur die Startansicht ("Alle") filtert hart; wer eine Kategorie bewusst
        # anklickt, soll sie auch dann sehen, wenn sie default_visible=0 hat.
        exclude = None if selected else _default_hidden(categories)
        # Dieselbe Liste baut der statische Export (tools/export_static.py) - nur
        # mit anderen Parametern, siehe feed.build_events.
        events = feed.build_events(conn, start, end, categories=selected,
                                   exclude_categories=exclude, with_reactions=True)

    return jsonify({
        "date": day.isoformat(),
        "categories": selected,
        "category": selected[0] if len(selected) == 1 else "alle",
        "events": events,
    })


@app.route("/api/health")
def api_health():
    """Zustand der sechs Scraper: letzter Lauf, letzter Erfolg mit Anzahl,
    letzter Fehlertext.

    Bewusst nur abrufbar und ohne Alarm-Kanal (kein Mail, kein Push, kein
    Webhook): der einzige Push-Weg dieses Dienstes wurde gerade ersatzlos
    entfernt, ein neuer waere derselbe Fehler unter anderem Namen. Log und diese
    Antwort sind das Mass.
    """
    with db.get_conn() as conn:
        return jsonify(db.scrape_health(conn))


@app.route("/api/fuer-dich")
def api_fuer_dich():
    today = date.today()
    _, end = week_range(today)
    with db.get_conn() as conn:
        categories_meta = db.list_categories(conn)
        categories = _selected_categories({c["slug"] for c in categories_meta})
        exclude = None if categories else _default_hidden(categories_meta)
        events = db.events_for_range(conn, today.isoformat(), end.isoformat(), categories, exclude_categories=exclude)
        top = scoring.top_picks(conn, events, limit=8)
        for e in top:
            e["reaction"] = db.get_reaction(conn, e["uid"])
    return jsonify({"categories": categories, "events": top})


# --- Venue-Seiten (P5b) ------------------------------------------------------
# Kernannahme des Pakets: ein Event fuehrt in die App hinein (auf die
# Venue-Seite), nicht raus zum Kulturkalender (decision #4). Siehe
# feed.venue_cover fuer die Cover-Reihenfolge/den Bild-Fallback und
# db.list_venues fuer die Treffpunkt-Ausnahme (keine Seite fuer
# "Dresden City"/"Terrassenufer"/"Theaterplatz").

@app.route("/orte")
def venues_index():
    with db.get_conn() as conn:
        venues = db.list_venues(conn, date.today().isoformat())
    enriched_count = sum(1 for v in venues if v.get("og_image_url"))
    return render_template("venues.html", venues=venues, mode="api",
                           enriched_count=enriched_count,
                           kind_labels=config.VENUE_KIND_LABELS,
                           region_labels=config.REGION_LABELS,
                           asset_v=ASSET_VERSION, urls=api_urls())


@app.route("/orte/<slug>")
def venue_detail(slug):
    today = date.today().isoformat()
    with db.get_conn() as conn:
        venue = db.get_venue_by_slug(conn, slug)
        if venue is None or venue["is_meeting_point"]:
            abort(404)
        events = db.venue_upcoming_events(conn, venue["id"], today)
        last_past = db.venue_last_past_event(conn, venue["id"], today) if not events else None
    cover = feed.venue_cover(venue, events)
    return render_template("venue.html", venue=venue, events=events,
                           last_past=last_past, cover=cover, mode="api",
                           kind_labels=config.VENUE_KIND_LABELS,
                           region_labels=config.REGION_LABELS,
                           asset_v=ASSET_VERSION, urls=api_urls())


def _detail_payload(event, status):
    """Bewusst schmal: Titel/Datum/Ort/Score hat das Frontend schon aus
    /api/events, hier kommt nur dazu, was dort fehlt."""
    return {
        "uid": event["uid"],
        "url": event.get("url"),
        "image_url": event.get("image_url"),
        "price_text": event.get("price_text"),
        "description": event.get("description"),
        "detail_status": status,
    }


@app.route("/api/event/<uid>/details")
def api_event_details(uid):
    """Details fürs Popup. Beim ersten Aufruf werden sie ggf. von der Quellseite
    nachgeladen (siehe scrapers.detail_fetch) und danach aus der DB bedient."""
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM events WHERE uid = ?", (uid,)).fetchone()
    if row is None:
        return jsonify({"error": "unbekanntes Event"}), 404

    event = dict(row)
    if event.get("detail_fetched_at"):
        return jsonify(_detail_payload(event, "cached"))

    # Die Verbindung ist hier bewusst zu: das Nachladen hängt am fremden Server
    # und soll nicht sekundenlang eine SQLite-Verbindung blockieren.
    detail = detail_fetch.fetch_detail(event)
    if not detail["ok"]:
        # detail_fetched_at bleibt leer, damit ein späterer Klick es erneut
        # versucht - die Quellseite war vielleicht nur kurz nicht erreichbar.
        return jsonify(_detail_payload(event, "unavailable"))

    with db.get_conn() as conn:
        db.save_event_detail(
            conn, uid, detail["image_url"], detail["price_text"], detail["description"]
        )
    event["image_url"] = detail["image_url"] or event.get("image_url")
    event["price_text"] = detail["price_text"] or event.get("price_text")
    event["description"] = detail["description"]
    return jsonify(_detail_payload(event, "fetched"))


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    payload = request.get_json(force=True, silent=True) or {}
    uid = payload.get("uid")
    reaction = payload.get("reaction")
    if reaction not in ("like", "skip") or not uid:
        return jsonify({"error": "uid und reaction ('like'|'skip') erforderlich"}), 400

    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM events WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            return jsonify({"error": "unbekanntes Event"}), 404
        event = dict(row)
        scoring.apply_reaction(conn, event, reaction)
        new_score = scoring.score_event(conn, event)

    return jsonify({"ok": True, "uid": uid, "reaction": reaction, "score": new_score})


def run_web():
    app.run(host="0.0.0.0", port=config.WEB_PORT, debug=False, use_reloader=False)

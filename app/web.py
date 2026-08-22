"""Personalisierte Web-Oberfläche (Flask) - dieselbe Optik wie der Artifact-
Prototyp 'DD was geht', aber live aus der SQLite-Datenbank statt mit
Beispieldaten, plus 'Für dich'-Bereich und Like/Skip direkt im Browser."""
from datetime import date

from flask import Flask, jsonify, render_template, request

from . import config, db, feed, scoring
from .ranges import month_range, week_range
from .scrapers import detail_fetch

app = Flask(__name__)

def _range_bounds(range_key):
    today = date.today()
    if range_key == "woche":
        return week_range(today)
    if range_key == "monat":
        return month_range(today)
    return today, today


def _selected_categories():
    """Mehrfachauswahl aus ?cat=musik,kultur. Unbekannte Keys fliegen raus,
    "alle" bzw. leer bedeutet: keine Auswahl (= alles, minus EXCLUDED)."""
    raw = request.args.get("cat", "alle")
    return [c for c in db.category_filter(raw) if c in config.CATEGORY_LABELS]


@app.route("/")
def index():
    # mode="api": die Seite spricht mit dieser Flask-App. Dieselbe Vorlage wird
    # von tools/export_static.py ein zweites Mal mit mode="static" gerendert -
    # das ist die oeffentliche Kopie ohne Server (siehe README).
    return render_template("index.html", categories=config.CATEGORY_LABELS,
                           categories_short=config.CATEGORY_SHORT_LABELS,
                           sources=config.SOURCE_LABELS, mode="api",
                           excluded=[], generated_at="",
                           highlight_score=config.HIGHLIGHT_SCORE)


@app.route("/api/events")
def api_events():
    range_key = request.args.get("range", "heute")
    categories = _selected_categories()
    start, end = _range_bounds(range_key)

    # Nur die Startansicht ("Alle") filtert hart; wer eine Kategorie bewusst
    # anklickt, soll sie auch dann sehen, wenn sie in EXCLUDED_CATEGORIES steht.
    exclude = None if categories else config.EXCLUDED_CATEGORIES
    # Dieselbe Liste baut der statische Export (tools/export_static.py) - nur
    # mit anderen Parametern, siehe feed.build_events.
    with db.get_conn() as conn:
        events = feed.build_events(conn, start, end, categories=categories,
                                   exclude_categories=exclude, with_reactions=True)

    return jsonify({
        "range": range_key,
        "categories": categories,
        "category": categories[0] if len(categories) == 1 else "alle",
        "events": events,
    })


@app.route("/api/fuer-dich")
def api_fuer_dich():
    today = date.today()
    _, end = week_range(today)
    categories = _selected_categories()
    exclude = None if categories else config.EXCLUDED_CATEGORIES
    with db.get_conn() as conn:
        events = db.events_for_range(conn, today.isoformat(), end.isoformat(), categories, exclude_categories=exclude)
        top = scoring.top_picks(conn, events, limit=8)
        for e in top:
            e["reaction"] = db.get_reaction(conn, e["uid"])
    return jsonify({"categories": categories, "events": top})


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

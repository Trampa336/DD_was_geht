"""Personalisierte Web-Oberfläche (Flask) - dieselbe Optik wie der Artifact-
Prototyp 'DD was geht', aber live aus der SQLite-Datenbank statt mit
Beispieldaten, plus 'Für dich'-Bereich und Herzen direkt im Browser.

ZWEI OBERFLÄCHEN AUF EINER DATENBANK (der Grund für den ganzen Umbau):
die durchsuchbare Liste unter "/" und die kuratierte Seite unter "/herzen" -
dort steht ausschließlich, was David selbst geherzt hat.

Geherzt wird NUR hier, im Heimnetz. Die Trennung ist keine Prüfung im Code,
sondern die Bauart - drei Mechanismen, alle drei schon vor P5c in Betrieb und
in tests_smoke.py festgehalten:
  1. die Vorlage bindet herzen.js nur im api-Modus ein ({% if mode != 'static' %}),
  2. PUBLIC_ASSETS unten lässt herzen.js beim Export weg (und der Exporter
     löscht eine Altkopie aktiv wieder),
  3. app.js setzt CAN_HEART = MODE === 'api' und fragt die Herzen gar nicht
     erst ab, wenn die Seite statisch läuft.
Die Schreibroute /api/herz existiert deshalb ausschließlich auf diesem Server;
in der öffentlichen Kopie liegt nicht einmal der Code, der sie aufrufen würde.

Die Seite selbst ist app/templates/index.html (nur noch Markup); Stylesheet und
Skripte liegen daneben in app/static/ und werden von Flask ausgeliefert."""
import hashlib
import os
from datetime import date

from flask import Flask, abort, jsonify, render_template, request

from . import config, db, feed, normalize, scoring
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

# Nur diese Dateien darf die oeffentliche Kopie mitnehmen. herzen.js fehlt hier
# mit Absicht: dort gibt es keinen Server, an den ein Herz ginge, also soll auch
# der Code dafuer nicht dabei sein (siehe tools/export_static.py). Bis P5c stand
# an dieser Stelle rating.js, aus demselben Grund.
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
        "hearts_index": "/herzen",
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
                                   exclude_categories=exclude)

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


# --- Herzen (P5c) ------------------------------------------------------------
# Entscheidung #3: Kuratieren heisst Herzen - EIN positives Signal, kein
# Annehmen/Ablehnen. Das abgeloeste 👍/👎 (/api/feedback, scoring.apply_reaction,
# Tabelle reactions, static/rating.js) ist in diesem Paket vollstaendig
# entfallen; Herzen sind der Ersatz, nicht ein zweites System daneben.
#
# Ein Herz gilt der SERIE, nicht der einzelnen Zeigung (Entscheidung #26): der
# Browser schickt die uid der angeklickten Zeigung, den Serien-Schluessel
# bestimmt der Server (db.set_heart -> normalize.run_key). So gibt es genau
# eine Stelle, die weiss, welche Zeilen zu einer Serie gehoeren - der
# Schreibweg und der Reparaturlauf nach dem Scrape benutzen dieselbe.

@app.route("/api/geherzt")
def api_geherzt():
    """Die Schluessel aller Herzen. Die Liste im Browser markiert damit ihre
    Zeilen - eine Abfrage fuer die ganze Seite, nicht eine je Event.

    Heisst bewusst NICHT /api/herzen: dann waere "/api/herz" ein Praefix
    von beidem, und die Pruefung "keine Schreibroute im statischen Export"
    (tests_smoke.py, decision #8) liesse sich nicht mehr mit einem Griff
    machen. Diese Leseroute darf im Export-Bundle stehen - aufgerufen wird
    sie dort nie (CAN_HEART ist false), genau wie /api/event/<uid>/details
    seit P5b."""
    with db.get_conn() as conn:
        return jsonify({"run_keys": db.hearted_run_keys(conn)})


@app.route("/api/herz", methods=["POST"])
def api_herz():
    payload = request.get_json(force=True, silent=True) or {}
    uid = payload.get("uid")
    an = payload.get("an", True)
    if not uid:
        return jsonify({"error": "uid erforderlich"}), 400

    with db.get_conn() as conn:
        event = db.event_for_uid(conn, uid)
        if event is None:
            return jsonify({"error": "unbekanntes Event"}), 404

        if an:
            heart, neu = db.set_heart(conn, uid)
            anchor = db.event_for_uid(conn, heart["event_uid"]) or event
            # Gewichte einmal je Serie, nicht je Zeigung - siehe
            # scoring.apply_heart - und nur beim ERSTEN Mal: zwei Zeilen
            # derselben Serie (Doppelvorstellung unter RUN_MIN_SIZE) tragen
            # denselben Schluessel, der zweite Klick aendert am Herzen nichts.
            if neu:
                scoring.apply_heart(conn, anchor, True)
            return jsonify({
                "ok": True, "an": True, "run_key": heart["run_key"],
                "uid": heart["event_uid"], "anzahl": len(db.run_members(conn, heart["run_key"])),
                "link_status": heart["link_status"],
                "score": scoring.score_event(conn, anchor),
            })

        run_key = payload.get("run_key") or normalize.run_key_for_event(event)
        heart = db.get_heart(conn, run_key)
        if heart is None:
            return jsonify({"ok": True, "an": False, "run_key": run_key})
        anchor = db.event_for_uid(conn, heart["event_uid"]) or event
        db.remove_heart(conn, run_key)
        scoring.apply_heart(conn, anchor, False)
        return jsonify({"ok": True, "an": False, "run_key": run_key,
                        "score": scoring.score_event(conn, anchor)})


@app.route("/herzen")
def hearts_page():
    """Die kuratierte Seite - die zweite Oberflaeche auf derselben Datenbank.

    Sie startet LEER (Entscheidung #19): keine Vorauswahl, kein Vorschlag, kein
    Seeding. Was hier steht, hat David selbst geherzt.

    Bewusst NICHT im statischen Export (tools/export_static.py exportiert
    index.html und die Venue-Seiten): die kuratierte Auswahl ist bis P6
    ausschliesslich im Heimnetz zu sehen. Ob sie spaeter die oeffentliche Seite
    wird, entscheidet David, nicht dieses Paket."""
    today = date.today().isoformat()
    with db.get_conn() as conn:
        hearts = db.list_hearts(conn)
    upcoming = [h for h in hearts if h["date"] >= today]
    past = [h for h in hearts if h["date"] < today]
    past.reverse()
    return render_template("herzen.html", upcoming=upcoming, past=past,
                           mode="api", asset_v=ASSET_VERSION, urls=api_urls())


def run_web():
    app.run(host="0.0.0.0", port=config.WEB_PORT, debug=False, use_reloader=False)

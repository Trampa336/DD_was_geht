#!/usr/bin/env python3
"""Exportiert den Kalender als statische Seite fuer GitHub Pages.

Damit laesst sich DD was geht mit Freunden teilen, ohne irgendetwas ins Netz zu
oeffnen: der Pi schiebt das Ergebnis in ein oeffentliches Repo, die Freunde lesen
dort. Der Pi selbst bleibt unerreichbar.

Die Rechte-Trennung ist dabei keine Pruefung im Code, sondern die Bauart: auf der
statischen Kopie gibt es keinen Server, an den man schreiben koennte - und seit
dem Umbau zeigt sie auch keine Herz-Knoepfe mehr. Geherzt wird ausschliesslich
unter http://<pi>:1111, also aus dem Heimnetz. Mitexportiert wird nur das Ergebnis:
das Feld "score" je Event, damit die Empfehlungszeile auch oeffentlich etwas zu
zeigen hat.

Seit P6a wird auch die kuratierte Seite exportiert (Entscheidung #27): das
ERGEBNIS der Auswahl ist oeffentlich, der Herz-Knopf selbst nie (Entscheidung #8
unveraendert). Die Vorlage herzen.html traegt dafuer denselben mode-Schalter wie
index.html - im static-Modus ohne Knopf, ohne data-run-key und ohne herzen.js.

Ausgabe (in --out, Standard ./data/site):

    index.html            dieselbe Vorlage wie das Web-UI, nur mit mode="static"
    herzen.html           die kuratierte Seite, read-only (Entscheidung #27)
    orte/index.html       die Orte-Uebersicht
    orte/<slug>.html      eine Seite je Ort
    static/*              Stylesheet und Skripte, dieselben Dateien wie auf dem Pi
                          (ohne herzen.js - siehe web.PUBLIC_ASSETS)
    data/index.json       welche Tage es gibt, mit Version je Tag (Cache-Buster)
    data/days/<tag>.json  die Events eines Tages
    robots.txt            Disallow (die Seite ist "unlisted", nicht geheim)
    .nojekyll             sonst ignoriert GitHub Pages Dateien mit Unterstrich

Warum eine Datei pro Tag und nicht eine grosse: die Seite wird viermal taeglich
neu gepusht. Eine einzelne 2,5-MB-Datei waere jedes Mal ein neuer Blob in der
Git-Historie; so aendern sich nur die Tage, an denen sich wirklich etwas getan
hat, und der Browser laedt fuer "Heute" auch nur einen Tag (~18 KB gzip).

    python3 tools/export_static.py                    # nach ./data/site
    python3 tools/export_static.py --out /tmp/site --days 45

Im Container:
    docker compose exec dd-was-geht python3 tools/export_static.py --out /app/data/site
"""
import argparse
import hashlib
import json
import os
import sys
from collections import OrderedDict
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, db, feed, web  # noqa: E402
from app.web import app as flask_app  # noqa: E402


def _dump(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _static_urls(asset_v, under_orte=False):
    """Gegenstueck zu app/web.py:api_urls() fuer den Export: dort sind alle
    URLs absolut (Flask liefert immer unter "/" aus), hier relativ - GitHub
    Pages kann auch aus einem Unterverzeichnis des Repos ausgeliefert werden
    (aeltere Begruendung in app/templates/index.html). Nur zwei Pfadtiefen
    gibt es: die Wurzel (index.html) und "orte/" (venue.html-Instanzen UND der
    Orte-Index orte/index.html liegen im selben Verzeichnis)."""
    if under_orte:
        return {
            "index": "../index.html",
            "venues_index": "index.html",
            "hearts_index": "../herzen.html",
            "venue": lambda slug: f"{slug}.html",
            "asset": lambda name: f"../static/{name}?v={asset_v}",
        }
    return {
        "index": "index.html",
        "venues_index": "orte/index.html",
        "hearts_index": "herzen.html",
        "venue": lambda slug: f"orte/{slug}.html",
        "asset": lambda name: f"static/{name}?v={asset_v}",
    }


def _write(path, text):
    """Schreibt nur, wenn sich der Inhalt geaendert hat - sonst sieht Git eine
    Aenderung, wo keine ist, und jeder Push traegt unnoetige Blobs nach.

    Verglichen wird BYTEWEISE, nicht im Textmodus (P6a). Im Textmodus macht
    Python beim Lesen aus jedem \\r\\n ein \\n (universal newlines); ein
    gerendertes \\r\\n las sich also immer wieder als "geaendert", obwohl auf
    der Platte Byte fuer Byte dasselbe stand. Real gemessen: genau ein
    Event-Titel aus dem Scrape traegt ein CRLF ("King Of Pop: A Tribute to
    Michael Jackson ... von\\r\\nMichael Jackson"), und orte/boulevardtheater.html
    wurde deshalb bei JEDEM Export neu geschrieben. Git sah davon nie etwas -
    die Zaehlung in der Ausgabe ("venues_written") log aber, und zwar in die
    Richtung, in der man sie am wenigsten hinterfragt."""
    data = text.encode("utf-8")
    try:
        with open(path, "rb") as handle:
            if handle.read() == data:
                return False
    except FileNotFoundError:
        pass
    with open(path, "wb") as handle:
        handle.write(data)
    return True


def _previous_generated_at(index_path, payload):
    """Den Zeitstempel des letzten Exports weiterverwenden, falls sich am Inhalt
    nichts geaendert hat. Gibt None zurueck, wenn es einen neuen braucht."""
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            old = json.load(handle)
    except (OSError, ValueError):
        return None
    stamp = old.pop("generated_at", None)
    return stamp if old == payload else None


def collect(conn, start, end):
    """Events des Zeitraums, nach Tag gruppiert. Dieselbe Liste, die auch das
    Web-UI ausliefert (app/web.py) - gebaut vom selben feed.build_events(). Was
    den Export unterscheidet, steht dort an den Parametern: kein
    Kategorie-Filter, keine Reaktionen, dafuer die schmalen Zeilen fuer die
    Tagesdateien."""
    events = feed.build_events(conn, start, end, slim=True)
    by_day = OrderedDict()
    for event in events:
        by_day.setdefault(event["date"], []).append(event)
    for day in by_day:
        by_day[day].sort(key=lambda e: (e.get("time") or "99:99", e["title"]))
    return by_day


def export(out_dir, days_ahead=45, today=None):
    today = today or date.today()
    end = today + timedelta(days=days_ahead)

    days_dir = os.path.join(out_dir, "data", "days")
    os.makedirs(days_dir, exist_ok=True)

    with db.get_conn() as conn:
        by_day = collect(conn, today, end)
        categories = db.list_categories(conn)
        tags = db.list_tags(conn)
        default_hidden = [c["slug"] for c in categories if not c["default_visible"]]
        # Venue-Seiten (P5b): ungefenstert (nicht auf days_ahead begrenzt wie
        # die Tagesdateien oben) - eine Venue-Seite soll den vollen bekannten
        # Vorlauf zeigen, nicht nur die naechsten 45 Tage.
        # Die kuratierte Seite (Entscheidung #27). Dieselbe Abfrage wie
        # web.hearts_page - eine Quelle, zwei Aufrufer, wie bei index.html.
        hearts = db.list_hearts(conn)
        venues = db.list_venues(conn, today.isoformat())
        venue_events = {}
        venue_last_past = {}
        for v in venues:
            events = db.venue_upcoming_events(conn, v["id"], today.isoformat())
            venue_events[v["slug"]] = events
            venue_last_past[v["slug"]] = (
                None if events else db.venue_last_past_event(conn, v["id"], today.isoformat())
            )

    index_days = []
    written = 0
    for day, events in sorted(by_day.items()):
        text = _dump(events)
        if _write(os.path.join(days_dir, f"{day}.json"), text):
            written += 1
        index_days.append({
            "date": day,
            "count": len(events),
            # Kurzer Inhalts-Hash: solange sich ein Tag nicht aendert, bleibt die
            # URL gleich und der Browser holt ihn nicht neu.
            "v": hashlib.sha1(text.encode("utf-8")).hexdigest()[:8],
        })

    # Tage, die aus dem Zeitfenster gelaufen sind (gestern und frueher), muessen
    # weg - sonst wuechse das Repo immer weiter.
    keep = {f"{d['date']}.json" for d in index_days}
    removed = 0
    for name in os.listdir(days_dir):
        if name.endswith(".json") and name not in keep:
            os.remove(os.path.join(days_dir, name))
            removed += 1

    index_path = os.path.join(out_dir, "data", "index.json")
    index_payload = {
        "days": index_days,
        # categories/sources/excluded: app.js liest sie aus data/index.json
        # nie (nur idx.days, siehe staticIndex()/staticEvents()) - die
        # eigentliche Quelle ist das inline window.DD-Objekt in index.html.
        # Bleiben trotzdem hier, konsistent mit der categories-Tabelle
        # (P5b), statt sie in einem separaten Aufraeum-Schritt zu entfernen.
        "categories": {c["slug"]: c["label"] for c in categories},
        "sources": config.SOURCE_GROUP_LABELS,
        "excluded": default_hidden,
    }
    # generated_at wird nur hochgezaehlt, wenn sich am Bestand wirklich etwas
    # geaendert hat. Sonst waere jeder Lauf ein Commit: der Zeitstempel steckt
    # auch in der Fussnote der Seite, index.json UND index.html (rund 90 KB)
    # bekaemen also viermal taeglich einen neuen Blob, obwohl kein einziges
    # Event dazugekommen ist.
    generated_at = _previous_generated_at(index_path, index_payload)
    if generated_at is None:
        generated_at = datetime.now().replace(microsecond=0).isoformat()
    _write(index_path, _dump(dict(index_payload, generated_at=generated_at)))

    # Stylesheet und Skripte sind dieselben Dateien, die auch der Pi ausliefert -
    # nur herzen.js bleibt zurueck (web.PUBLIC_ASSETS). Die Vorlage verlinkt sie
    # relativ ("static/app.css"), das passt unter Flask wie unter GitHub Pages,
    # auch wenn die Seite dort in einem Unterverzeichnis liegt.
    static_out = os.path.join(out_dir, "static")
    os.makedirs(static_out, exist_ok=True)
    for name in web.PUBLIC_ASSETS:
        with open(os.path.join(web.STATIC_DIR, name), "r", encoding="utf-8") as handle:
            _write(os.path.join(static_out, name), handle.read())
    # Ein herzen.js (oder ein rating.js aus einem Export vor P5c) muss weg, sonst
    # laege der Code fuer den Schreibweg weiter im oeffentlichen Repo.
    for name in os.listdir(static_out):
        if name not in web.PUBLIC_ASSETS:
            os.remove(os.path.join(static_out, name))

    asset_v = web.asset_version()

    # Dieselbe Vorlage wie die Flask-Seite, nur im anderen Modus - deshalb gibt
    # es kein zweites Frontend, das mit der Zeit auseinanderlaeuft (von P5a
    # verifiziert, tools/export_static.py:160-172 - diese Stelle hier).
    with flask_app.test_request_context("/"):
        html = flask_app.jinja_env.get_template("index.html").render(
            categories=categories,
            tags=tags,
            sources=config.SOURCE_GROUP_LABELS,
            mode="static",
            default_hidden=default_hidden,
            highlight_score=config.HIGHLIGHT_SCORE,
            generated_at=generated_at,
            generated_at_label=datetime.fromisoformat(generated_at).strftime("%d.%m.%Y, %H:%M"),
            asset_v=asset_v,
            urls=_static_urls(asset_v),
        )
    _write(os.path.join(out_dir, "index.html"), html)

    # --- Die kuratierte Seite (P6a, Entscheidung #27) ------------------------
    # Oeffentlich ist das ERGEBNIS der Auswahl, nie der Weg dorthin: dieselbe
    # Vorlage wie unter Flask, nur mode="static" - damit faellt der Herz-Knopf
    # weg (samt data-run-key/data-uid) und herzen.js wird gar nicht erst
    # verlinkt. Der Exporter kopiert es ohnehin nicht mit (web.PUBLIC_ASSETS).
    # Entscheidung #8 bleibt damit woertlich erfuellt: in der oeffentlichen
    # Kopie liegt nicht einmal der Code, der /api/herz aufrufen wuerde.
    hearts_today = today.isoformat()
    hearts_upcoming = [h for h in hearts if h["date"] >= hearts_today]
    hearts_past = [h for h in hearts if h["date"] < hearts_today]
    hearts_past.reverse()
    with flask_app.test_request_context("/"):
        hearts_html = flask_app.jinja_env.get_template("herzen.html").render(
            upcoming=hearts_upcoming, past=hearts_past, mode="static",
            asset_v=asset_v,
            generated_at_label=datetime.fromisoformat(generated_at).strftime("%d.%m.%Y, %H:%M"),
            urls=_static_urls(asset_v),
        )
    _write(os.path.join(out_dir, "herzen.html"), hearts_html)

    # --- Venue-Seiten (P5b) --------------------------------------------------
    # Kernannahme des Pakets: ein Event fuehrt auf eine Venue-Seite INNERHALB
    # der App, nicht zum Kulturkalender (decision #4) - das muss auch in der
    # oeffentlichen, statischen Kopie gelten, nicht nur im Flask-Modus.
    orte_dir = os.path.join(out_dir, "orte")
    os.makedirs(orte_dir, exist_ok=True)
    venue_urls = _static_urls(asset_v, under_orte=True)
    venues_written = 0
    for v in venues:
        events = venue_events[v["slug"]]
        cover = feed.venue_cover(v, events)
        with flask_app.test_request_context("/"):
            venue_html = flask_app.jinja_env.get_template("venue.html").render(
                venue=v, events=events, last_past=venue_last_past[v["slug"]],
                cover=cover, mode="static", kind_labels=config.VENUE_KIND_LABELS,
                region_labels=config.REGION_LABELS, urls=venue_urls,
            )
        if _write(os.path.join(orte_dir, f"{v['slug']}.html"), venue_html):
            venues_written += 1

    enriched_count = sum(1 for v in venues if v.get("og_image_url"))
    with flask_app.test_request_context("/"):
        venues_index_html = flask_app.jinja_env.get_template("venues.html").render(
            venues=venues, mode="static", enriched_count=enriched_count,
            kind_labels=config.VENUE_KIND_LABELS, region_labels=config.REGION_LABELS,
            urls=venue_urls,
        )
    _write(os.path.join(orte_dir, "index.html"), venues_index_html)

    # Eine Venue-Zeile verschwindet praktisch nie (venues werden nie geloescht,
    # nur Aliase umgehaengt - siehe migrations/001_schema_v2.sql §1), aber
    # falls doch (manuelles Zusammenlegen, Umbenennen des Slugs), soll keine
    # verwaiste Datei im oeffentlichen Repo liegen bleiben - dieselbe
    # Vorsicht wie bei den Tagesdateien oben.
    keep_venue_files = {f"{v['slug']}.html" for v in venues} | {"index.html"}
    venues_removed = 0
    for name in os.listdir(orte_dir):
        if name.endswith(".html") and name not in keep_venue_files:
            os.remove(os.path.join(orte_dir, name))
            venues_removed += 1

    _write(os.path.join(out_dir, "robots.txt"), "User-agent: *\nDisallow: /\n")
    _write(os.path.join(out_dir, ".nojekyll"), "")

    return {
        "days": len(index_days),
        "events": sum(d["count"] for d in index_days),
        "days_written": written,
        "days_removed": removed,
        "venues": len(venues),
        "venues_written": venues_written,
        "venues_removed": venues_removed,
        "hearts": len(hearts),
        "bytes": sum(
            os.path.getsize(os.path.join(root, name))
            for root, _, names in os.walk(out_dir) for name in names
            if ".git" not in root
        ),
        "generated_at": generated_at,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="./data/site", help="Zielverzeichnis")
    parser.add_argument("--days", type=int, default=45,
                        help="Wie viele Tage ab heute (Standard 45 - die "
                             "Monatsansicht braucht bis zum Monatsende)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    stats = export(args.out, days_ahead=args.days)
    if not args.quiet:
        print(f"{stats['events']} Events an {stats['days']} Tagen nach {args.out} "
              f"({stats['bytes'] / 1024 / 1024:.1f} MB, "
              f"{stats['days_written']} Tagesdateien neu/geaendert, "
              f"{stats['days_removed']} entfernt). "
              f"{stats['venues']} Venue-Seiten ({stats['venues_written']} neu/geaendert, "
              f"{stats['venues_removed']} entfernt). "
              f"Kuratierte Seite: {stats['hearts']} Eintraege.")


if __name__ == "__main__":
    main()

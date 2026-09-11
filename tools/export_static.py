#!/usr/bin/env python3
"""Exportiert den Kalender als statische Seite fuer GitHub Pages.

Damit laesst sich DD was geht mit Freunden teilen, ohne irgendetwas ins Netz zu
oeffnen: der Pi schiebt das Ergebnis in ein oeffentliches Repo, die Freunde lesen
dort. Der Pi selbst bleibt unerreichbar.

Die Rechte-Trennung ist dabei keine Pruefung im Code, sondern die Bauart: auf der
statischen Kopie gibt es keinen Server, an den man schreiben koennte - und seit
dem Umbau zeigt sie auch keine Bewerten-Buttons mehr. Bewertet wird ausschliesslich
unter http://<pi>:1111, also aus dem Heimnetz. Mitexportiert wird nur das Ergebnis:
das Feld "score" je Event, damit die Empfehlungszeile auch oeffentlich etwas zu
zeigen hat.

Ausgabe (in --out, Standard ./data/site):

    index.html            dieselbe Vorlage wie das Web-UI, nur mit mode="static"
    static/*              Stylesheet und Skripte, dieselben Dateien wie auf dem Pi
                          (ohne rating.js - siehe web.PUBLIC_ASSETS)
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


def _write(path, text):
    """Schreibt nur, wenn sich der Inhalt geaendert hat - sonst sieht Git eine
    Aenderung, wo keine ist, und jeder Push traegt unnoetige Blobs nach."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as handle:
            if handle.read() == text:
                return False
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
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
        "categories": config.CATEGORY_LABELS,
        "sources": config.SOURCE_GROUP_LABELS,
        "excluded": config.EXCLUDED_CATEGORIES,
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
    # nur rating.js bleibt zurueck (web.PUBLIC_ASSETS). Die Vorlage verlinkt sie
    # relativ ("static/app.css"), das passt unter Flask wie unter GitHub Pages,
    # auch wenn die Seite dort in einem Unterverzeichnis liegt.
    static_out = os.path.join(out_dir, "static")
    os.makedirs(static_out, exist_ok=True)
    for name in web.PUBLIC_ASSETS:
        with open(os.path.join(web.STATIC_DIR, name), "r", encoding="utf-8") as handle:
            _write(os.path.join(static_out, name), handle.read())
    # Ein rating.js aus einem aelteren Export muss weg, sonst laege der Code fuer
    # das Bewerten weiter im oeffentlichen Repo.
    for name in os.listdir(static_out):
        if name not in web.PUBLIC_ASSETS:
            os.remove(os.path.join(static_out, name))

    # Dieselbe Vorlage wie die Flask-Seite, nur im anderen Modus - deshalb gibt
    # es kein zweites Frontend, das mit der Zeit auseinanderlaeuft.
    with flask_app.test_request_context("/"):
        html = flask_app.jinja_env.get_template("index.html").render(
            categories=config.CATEGORY_LABELS,
            categories_short=config.CATEGORY_SHORT_LABELS,
            sources=config.SOURCE_GROUP_LABELS,
            mode="static",
            excluded=config.EXCLUDED_CATEGORIES,
            highlight_score=config.HIGHLIGHT_SCORE,
            generated_at=generated_at,
            generated_at_label=datetime.fromisoformat(generated_at).strftime("%d.%m.%Y, %H:%M"),
            asset_v=web.asset_version(),
        )
    _write(os.path.join(out_dir, "index.html"), html)

    _write(os.path.join(out_dir, "robots.txt"), "User-agent: *\nDisallow: /\n")
    _write(os.path.join(out_dir, ".nojekyll"), "")

    return {
        "days": len(index_days),
        "events": sum(d["count"] for d in index_days),
        "days_written": written,
        "days_removed": removed,
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
              f"{stats['days_removed']} entfernt).")


if __name__ == "__main__":
    main()

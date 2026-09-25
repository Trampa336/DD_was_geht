"""Debug-Helfer zur Kalibrierung der Scraper (siehe README, 'Scraper kalibrieren').

Läuft NUR auf einer Maschine mit echtem Internetzugang (also auf dem Pi, nicht
in der Umgebung, in der dieses Projekt geschrieben wurde). Lädt eine URL
herunter, speichert das rohe HTML zur Ansicht und zeigt, welche Event-Blöcke
die aktuelle Heuristik (find_event_blocks) darin erkennt.

Aufruf:
    python3 tools/inspect_source.py https://www.kulturkalender-dresden.de/heute
    python3 tools/inspect_source.py https://www.rauze.de/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scrapers import base  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print("Nutzung: python3 tools/inspect_source.py <URL>")
        raise SystemExit(1)

    url = sys.argv[1]
    print(f"Lade {url} ...")
    html = base.fetch_html(url)

    out_path = Path("data/last_fetch.html")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Rohes HTML gespeichert unter {out_path} (im Browser oder Editor ansehen).\n")

    soup = base.make_soup(html)
    blocks = base.find_event_blocks(soup)
    print(f"Heuristik hat {len(blocks)} mögliche Event-Blöcke gefunden:\n")

    for i, (time_text, container) in enumerate(blocks[:15]):
        title = base.extract_title(container)
        venue = base.extract_venue(container)
        print(f"{i+1:>2}. Zeit={time_text!r}  Titel={title!r}  Ort={venue!r}")
        if not title:
            print("      ^ Keine Überschrift (h1-h4) in der Nähe gefunden - "
                  "das ist ein Kandidat zum Nachjustieren, siehe README.")

    if not blocks:
        print("Keine Blöcke gefunden. Öffne data/last_fetch.html und sieh dir an, "
              "wie Uhrzeiten dort im Markup stehen (evtl. anderes Zeitformat, "
              "oder Inhalte werden erst per JavaScript nachgeladen).")


if __name__ == "__main__":
    main()

"""Scraper für den Der Lude (derlude.de).

Der Laden pflegt kein eigenes Terminsystem, sondern nur seine Facebook-Seite;
die Startseite bindet deren Events über das WordPress-Plugin "Custom Facebook
Feed Pro" ein (Klassenpräfix "cff-"). Das Plugin ruft selbst regelmäßig die
Facebook-Graph-API auf und rendert das Ergebnis serverseitig in die Seite -
für uns heißt das: ein einziger Request auf derlude.de liefert bereits
vollständige Event-Blöcke, ganz ohne Facebook selbst anzufragen (das würde an
deren Bot-Schutz scheitern, siehe README-Abschnitt zu Resident Advisor).

Markup je Event (gegen die Live-Seite verifiziert, 09.09.2026):

    <div class="cff-item cff-event ... cff-upcoming-event ..."
         data-cff-timestamp="1788379200" id="cff_2676382112817710">
      <div class="cff-media-wrap">
        <a class="cff-photo" href="https://facebook.com/events/2676382112817710">
          <img class="cff-feed-image" data-orig-source="https://scontent...jpg" ...>
        </a>
      </div>
      <p class="cff-event-title"><a href="...">Ludenkaraoke - mit DJ Baroness</a></p>
      <p class="cff-date"><span class="cff-start-date">02.09.26</span></p>
      <p class="cff-location"><b class="cff-event-place">Der Lude</b></p>
      <p class="cff-desc"><span class="cff-desc-text">Klar doch, los trau dich ...</span></p>
    </div>

`data-cff-timestamp` ist die zuverlässigste Angabe - ein Unix-Zeitstempel in
UTC, während `cff-start-date` nur das Datum ohne Uhrzeit im zweistelligen
Jahresformat zeigt. Das echte `<img src>` ist wegen Lazy-Loading nur ein
Platzhalter-SVG; das tatsächliche Bild steht im Facebook-CDN-Link unter
`data-orig-source`.

Zwei Einschränkungen, beide hingenommen statt umgangen:

1. **"Mehr Events laden" wird nicht nachgeladen.** Der Button lädt über
   admin-ajax.php + einen von der Seite selbst gecachten Facebook-Token
   weitere, ältere/zusätzliche Termine nach - das nachzubauen wäre fragiler
   als der Rest dieses Scrapers. Die serverseitig gerenderten ~15-20 Einträge
   decken in der Praxis rund 3-4 Wochen ab (verifiziert: 09.09.-30.09.2026),
   für die restliche Zeit des 31-Tage-Fensters bleibt die Quelle stumm - wie
   bei jeder Quelle hier gilt: leer ist kein Fehler, nur eine Lücke.
2. **Der Feed zeigt auch schon vergangene Termine.** Das Plugin cached länger
   als es aktualisiert; scrape_range() filtert deshalb wie überall lokal auf
   [start_day, end_day] statt der Quelle zu vertrauen.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .. import normalize
from . import base

SOURCE = "derlude"
URL = "https://derlude.de/"
VENUE = "Der Lude"
BERLIN = ZoneInfo("Europe/Berlin")

# Der Laden ist eine Bar mit Karaoke-/Tanzabenden - keine Rohkategorie im
# Markup, aber "Party" reicht über normalize.RAW_CATEGORY_MAP für "musik".
RAW_CATEGORY = "Party"


def _extract_image(item):
    img = item.select_one(".cff-photo img.cff-feed-image")
    if img is None:
        return None
    orig = img.get("data-orig-source")
    if orig:
        return orig
    return None


def _parse(html):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt."""
    soup = base.make_soup(html)
    events = []

    for item in soup.select(".cff-item.cff-event"):
        timestamp = item.get("data-cff-timestamp")
        title_link = item.select_one(".cff-event-title a")
        if not timestamp or title_link is None:
            continue
        title = title_link.get_text(" ", strip=True)
        if not title:
            continue

        local = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).astimezone(BERLIN)
        day = local.date()
        norm_time = f"{local.hour:02d}:{local.minute:02d}"

        # .cff-event-place wird bewusst NICHT gelesen: Facebook trägt dort mal
        # den Seitennamen ein ("Der Lude"), mal die volle Adresse ("Görlitzer
        # Str. 3, 01099 Dresden-Neustadt, Germany") - real bei "Swipe the
        # Night" beobachtet. Der Feed gehört ohnehin zu genau einem Haus (die
        # Startseite bindet nur die eigene Facebook-Seite ein), der Ort ist
        # also immer VENUE, ganz wie bei AZ Conni und Sektor Evolution.
        venue = VENUE

        desc_el = item.select_one(".cff-desc-text")
        description = desc_el.get_text(" ", strip=True) if desc_el else None

        url = title_link.get("href") or URL

        events.append({
            "uid": normalize.make_event_uid(day.isoformat(), norm_time, title, venue),
            "source": SOURCE,
            "date": day.isoformat(),
            "time": norm_time,
            "title": title,
            "venue": venue,
            "category": normalize.classify_category(RAW_CATEGORY, title, venue),
            "raw_category": RAW_CATEGORY,
            "url": url,
            "image_url": _extract_image(item),
            "price_text": None,
            "description": description,
            # Der Feed liefert Bild und Beschreibung schon beim Scrapen mit -
            # es gibt nichts nachzuladen.
            "detail_fetched_at": datetime.utcnow().isoformat(),
        })
    return events


def scrape_range(start_day, end_day):
    """Holt die Startseite einmal und filtert auf [start_day, end_day]."""
    events = _parse(base.fetch_html(URL))
    start, end = start_day.isoformat(), end_day.isoformat()
    return [e for e in events if start <= e["date"] <= end]

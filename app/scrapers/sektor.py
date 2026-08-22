"""Scraper für das Sektor Evolution (sektor-evolution.de).

Warum eine eigene Quelle für ein einzelnes Haus - zum zweiten Mal nach dem AZ
Conni, diesmal aber aus einem anderen Grund: das Sektor Evolution *steht* in
den Aggregatoren (rauze.de, ra.co), nur zeigte der Link im Newsletter dann eben
auf ra.co statt auf den Laden selbst. Mit dieser Quelle ganz vorn in
config.SOURCE_PRIORITY gewinnt bei jeder Doppelung der Eintrag des Hauses, und
der Link ist der echte Event-Permalink (…/event/…). Was RA oder Rauze zusätzlich
wissen (Preis, Cover), trägt db.fill_missing_from_duplicate() weiterhin nach.

Wie beim AZ Conni gibt es eine einzige Übersichtsseite mit allen Terminen
(https://www.sektor-evolution.de/dates/, Vergangenheit und Zukunft in einer
Liste, keine Blätterfunktion) - ein Request holt alles, gefiltert wird lokal.

Markup der Übersicht (gegen die Live-Seite verifiziert, WordPress-Theme "angio"):

    <div class="mod mod-event-1 mod-event-list ...">
      <article class="... angio_event_type-future-events">
        <a class="mod__click ..." href="https://www.sektor-evolution.de/event/werkhain-2/">
          <div class="mod__event-date">
            <span class="mod__event-day">22</span>
            <span class="mod__event-month">Aug.</span>
            <span class="mod__event-year">2026</span>
          </div>
          <h2 class="mod__event-name">Pangaea invites </h2>
          <div class="mod__event-location">SektorEvolution</div>
        </a>
      </article>
    </div>

Zwei Eigenheiten, die einen zweiten Request je Termin nötig machen:

1. **Die Übersicht nennt keine Uhrzeit.** Die steht nur auf der Detailseite,
   und zwar im 12-Stunden-Format ("11:00 PM") - siehe _parse_time(). Ohne sie
   stünde die Clubnacht ohne Anfangszeit im Newsletter, und schlimmer: die uid
   aus normalize.make_event_uid() rechnet die Zeit mit ein, das Event würde
   also beim Nachtragen der Zeit zu einer zweiten Zeile.
2. **Preis und Beschreibung** stehen ebenfalls nur auf der Detailseite.

Deshalb holt scrape_range() für jeden Termin *im Zeitraum* die Detailseite mit
(bei 31 Tagen Vorlauf rund zehn Requests pro Lauf, gedrosselt und gedeckelt).
Schlägt einer davon fehl, bleibt der Termin trotzdem erhalten - nur eben ohne
Uhrzeit.
"""
import logging
import re
import time as time_module
from datetime import date, datetime

from .. import normalize
from . import base, detail_fetch

logger = logging.getLogger("dd-was-geht.sektor")

SOURCE = "sektor"
VENUE = "Sektor Evolution"
DATES_URL = "https://www.sektor-evolution.de/dates/"

# Die Quelle listet ausschließlich Clubnächte des eigenen Hauses. "Club" ist in
# normalize.RAW_CATEGORY_MAP hinterlegt und landet damit in musik - dieselbe
# Vorgabe, die auch der RA-Scraper für dieselben Abende setzt.
RAW_CATEGORY = "Club"

# Deckel und Drosselung für die Detailseiten. 60 liegt weit über dem, was ein
# 31-Tage-Fenster liefert (~10), und verhindert nur, dass ein Umbau der Quelle
# den Lauf in hunderte Requests laufen lässt.
MAX_DETAIL_FETCHES = 60
DETAIL_DELAY_SECONDS = 0.5

MONTHS = {
    "jan": 1, "feb": 2, "mae": 3, "mar": 3, "apr": 4, "mai": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dez": 12,
}

# "11:00 PM" - die Detailseite gibt die Zeit englisch im 12-Stunden-Format aus.
# normalize.normalize_time() würde daraus stumm "11:00" machen (also 23 Uhr als
# 11 Uhr morgens), deshalb wird dieses Format hier zuerst geprüft.
_TIME_12H_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*([AP])\.?M\.?\s*$", re.I)

# Das Haus schreibt sich selbst mal "SektorEvolution", mal "Sektor Evolution",
# und einmal steht dort ein Tippfehler ("Sektor Evolutin"). Alles davon meint
# denselben Laden und wird auf die Schreibweise von VENUE vereinheitlicht -
# sonst zerfiele der Ortsschlüssel in dedup.py in mehrere Varianten.
_VENUE_SELF_RE = re.compile(r"^sektor\s*evoluti", re.I)


def _venue_name(text):
    """Ortsname aus der Übersicht. Bei den seltenen Abenden über mehrere Läden
    ("SektorEvolution, objekt klein a, Circie, Club Paula") zählt der erste -
    das ist der Ort, an dem dieses Haus stattfindet, und nur der taugt als
    Vergleichsschlüssel für die Doppelungserkennung."""
    first = (text or "").split(",")[0].strip()
    return VENUE if not first or _VENUE_SELF_RE.match(first) else first


def _parse_date(day_text, month_text, year_text):
    """Datum aus den drei Spans der Übersicht. Anders als beim AZ Conni nennt
    die Quelle das Jahr, es muss also nichts geraten werden."""
    month = MONTHS.get(normalize.slugify(month_text or "").replace("-", "")[:3])
    if not month:
        return None
    try:
        return date(int(year_text), month, int(day_text))
    except (TypeError, ValueError):  # z.B. 30. Februar
        return None


def _parse_time(text):
    """"11:00 PM" -> "23:00". Alles andere geht an normalize.normalize_time()."""
    match = _TIME_12H_RE.match(text or "")
    if not match:
        return normalize.normalize_time(text)
    hour = int(match.group(1)) % 12  # 12 AM = 0 Uhr, 12 PM = 12 Uhr
    if match.group(3).upper() == "P":
        hour += 12
    return f"{hour:02d}:{match.group(2)}"


def _parse_list(html):
    """Reine Parse-Funktion für die Übersichtsseite (ohne Netzzugriff).

    Gibt Roh-Einträge zurück (Datum/Titel/Ort/Link), noch keine fertigen
    Events: die uid darf erst gebildet werden, wenn die Uhrzeit von der
    Detailseite bekannt ist (siehe Modul-Docstring, Punkt 1).
    """
    soup = base.make_soup(html)
    entries = []

    for block in soup.select(".mod-event-list"):
        link = block.find("a", href=True)
        title_el = block.select_one(".mod__event-name")
        day_el = block.select_one(".mod__event-day")
        month_el = block.select_one(".mod__event-month")
        year_el = block.select_one(".mod__event-year")
        if not (link and title_el and day_el and month_el and year_el):
            continue

        title = title_el.get_text(" ", strip=True)
        day = _parse_date(
            day_el.get_text(strip=True),
            month_el.get_text(strip=True),
            year_el.get_text(strip=True),
        )
        if not title or day is None:
            continue

        location_el = block.select_one(".mod__event-location")
        entries.append({
            "date": day.isoformat(),
            "title": title,
            "venue": _venue_name(location_el.get_text(" ", strip=True) if location_el else None),
            "url": link["href"],
        })
    return entries


def _detail_description(soup):
    """Beschreibungstext der Detailseite, Zeilenumbrüche erhalten.

    Das Line-up steht dort als eine Folge von <br>-getrennten Namen; würde man
    sie wie sonst mit Leerzeichen zusammenziehen, entstünde eine unlesbare
    Wortschlange. Eingebettete Ticket-Widgets (pretix) fliegen raus - sie
    liefern nur ihren Noscript-Hinweis als Text.
    """
    block = soup.select_one(".event__text")
    if block is None:
        return None
    clone = base.make_soup(str(block))
    for tag in clone.find_all(["script", "style", "link", "noscript", "pretix-widget"]):
        tag.decompose()
    for br in clone.find_all("br"):
        br.replace_with("\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in clone.get_text("\n").splitlines()]
    return "\n".join(line for line in lines if line) or None


def _detail_field(soup, name):
    """Ein Wert aus der Tabelle rechts neben dem Cover ("Date", "Time", "Venue")."""
    for item in soup.select(".details-list li"):
        label = item.select_one(".details-list__name")
        value = item.select_one(".details-list__data")
        if label is None or value is None:
            continue
        if label.get_text(strip=True).lower() == name.lower():
            return value.get_text(" ", strip=True)
    return None


def parse_detail(soup):
    """Detailseite eines Termins auswerten.

    Bewusst öffentlich: dieselbe Funktion bedient den Hintergrund-Scrape und
    das Detail-Popup im Web-UI (registriert in detail_fetch._PARSERS). Deshalb
    hat das Ergebnis auch dessen Form - description fällt auf
    detail_fetch.FALLBACK_DESCRIPTION zurück. Das zusätzliche Feld "time" ist
    das, was nur diese Quelle hier nachliefert.
    """
    description = _detail_description(soup)
    image = soup.select_one(".event-cover__thumb img[src]")
    return {
        "description": description or detail_fetch.FALLBACK_DESCRIPTION,
        # Preise stehen nirgends strukturiert, sondern im Fließtext
        # ("Tickets: 5 € …") - dieselbe Lage wie beim Kulturkalender.
        "price_text": detail_fetch.price_from_text(description),
        "image_url": image["src"] if image else None,
        "time": _parse_time(_detail_field(soup, "Time")),
    }


def _build_event(entry, detail=None):
    """Roh-Eintrag der Übersicht + (optional) Detailseite -> fertiges Event."""
    detail = detail or {}
    norm_time = detail.get("time")
    description = detail.get("description")
    if description == detail_fetch.FALLBACK_DESCRIPTION:
        description = None

    return {
        "uid": normalize.make_event_uid(
            entry["date"], norm_time, entry["title"], entry["venue"]
        ),
        "source": SOURCE,
        "date": entry["date"],
        "time": norm_time,
        "title": entry["title"],
        "venue": entry["venue"],
        "category": normalize.classify_category(RAW_CATEGORY, entry["title"], entry["venue"]),
        "raw_category": RAW_CATEGORY,
        "url": entry["url"],
        "image_url": detail.get("image_url"),
        "price_text": detail.get("price_text"),
        "description": description,
        # Nur wenn die Detailseite wirklich gelesen wurde, gilt das Event als
        # vollständig - sonst darf detail_fetch.py es später nachholen.
        "detail_fetched_at": datetime.utcnow().isoformat() if detail else None,
    }


def _fetch_detail(url):
    """Detailseite holen. Wirft nie - fällt sie aus, bleibt der Termin ohne
    Uhrzeit stehen, statt den ganzen Lauf mitzureißen."""
    try:
        return parse_detail(base.make_soup(base.fetch_html(url)))
    except Exception:
        logger.warning("Sektor-Detailseite nicht ladbar: %s", url)
        return None


def scrape_range(start_day, end_day, fetch_detail=_fetch_detail):
    """Holt die Übersichtsseite einmal, filtert auf [start_day, end_day] und
    lädt zu jedem verbleibenden Termin die Detailseite nach (Uhrzeit!).

    fetch_detail ist injizierbar, damit Tests ohne Netzwerk auskommen.
    """
    entries = _parse_list(base.fetch_html(DATES_URL))
    start, end = start_day.isoformat(), end_day.isoformat()
    entries = sorted(
        (e for e in entries if start <= e["date"] <= end), key=lambda e: e["date"]
    )
    if len(entries) > MAX_DETAIL_FETCHES:
        logger.warning(
            "Sektor: %d Termine im Zeitraum, Detailseiten nur für die ersten %d.",
            len(entries), MAX_DETAIL_FETCHES,
        )

    events = []
    for index, entry in enumerate(entries):
        detail = fetch_detail(entry["url"]) if index < MAX_DETAIL_FETCHES else None
        events.append(_build_event(entry, detail))
        if index and DETAIL_DELAY_SECONDS:
            time_module.sleep(DETAIL_DELAY_SECONDS)
    return events

"""Scraper für das AZ Conni (azconni.de).

Warum eine eigene Quelle für ein einzelnes Haus: das AZ Conni steht in keinem
der Aggregatoren. Im Kulturkalender taucht es gar nicht auf, auf rauze.de stand
(Stand 22.08.2026) genau ein einziger Termin, und das SAX-Terminal listet es
überhaupt nicht. Wer den Laden im Newsletter haben will, muss ihn direkt holen.

Anders als die anderen Scraper wird hier NICHT Tag für Tag abgefragt: die Quelle
hat eine einzige Übersichtsseite mit allen kommenden Terminen. scrape_range()
lädt sie einmal und filtert auf den Zeitraum.

Markup (gegen die Live-Seite verifiziert):

    <div class="termin overview">
      <span class="time">Donnerstag, 3. September ab 19:00 Uhr</span>
      <span class="categories">Workshop</span>
      <header><a href="https://www.azconni.de/termin-regular/offener-djtreff/">
        Offener DJ*-Treff</a></header>
      <p>Mit dem offenen DJ*-Treff ... &hellip;
         <a class="continue-reading" href="...">[weiterlesen]</a></p>
    </div>

Zwei Eigenheiten, die den Code länger machen als das Markup vermuten lässt:

1. **In der Datumszeile steht kein Jahr.** Siehe _parse_german_date().
2. **Wiederkehrende Termine teilen sich einen Permalink** - beide DJ-Treff-
   Einträge zeigen auf dieselbe URL. Unkritisch, weil normalize.make_event_uid()
   das Datum mit einrechnet, die uid also trotzdem je Termin eine andere ist.
"""
import re
from datetime import date

from .. import normalize
from . import base

SOURCE = "azconni"
VENUE = "AZ Conni"
TERMINE_URL = "https://www.azconni.de/termine/"

MONTHS = {
    "januar": 1, "februar": 2, "maerz": 3, "marz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
}

# "Donnerstag, 3. September ab 19:00 Uhr" -> Tag + Monatsname.
DATE_PATTERN = re.compile(r"(\d{1,2})\.\s*([A-Za-zÄÖÜäöüß]+)")


def _parse_german_date(text, today):
    """Datum aus einer Zeile wie "Donnerstag, 3. September ab 19:00 Uhr".

    Die Quelle nennt kein Jahr. Angenommen wird deshalb das nächste Vorkommen ab
    heute: steht im Dezember ein Januartermin, gehört er ins Folgejahr. Ein paar
    Tage Kulanz nach hinten, damit ein Termin am Tag selbst nicht plötzlich ein
    Jahr in die Zukunft rutscht, wenn der Lauf kurz nach Mitternacht startet.
    """
    match = DATE_PATTERN.search(text or "")
    if not match:
        return None
    day = int(match.group(1))
    month = MONTHS.get(normalize.slugify(match.group(2)).replace("-", ""))
    if not month:
        return None

    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:  # z.B. 30. Februar
            return None
        if (candidate - today).days >= -7:
            return candidate
    return None


def _extract_description(block):
    """Teasertext ohne den angehängten "[weiterlesen]"-Link."""
    paragraphs = []
    for para in block.find_all("p"):
        clone = base.make_soup(str(para))
        for link in clone.find_all("a"):
            link.decompose()
        text = clone.get_text(" ", strip=True)
        # Das Auslassungszeichen vor dem entfernten Link stünde sonst nackt da.
        text = re.sub(r"[\s…]+$", "", text)
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs) or None


def _parse(html, today=None):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt.

    today wird nur für die Jahresermittlung gebraucht (siehe
    _parse_german_date) und ist in den Tests deshalb fest vorgegeben.
    """
    today = today or date.today()
    soup = base.make_soup(html)
    events = []

    for block in soup.find_all("div", class_="termin"):
        time_el = block.find("span", class_="time")
        if time_el is None:
            continue
        time_text = time_el.get_text(" ", strip=True)

        day = _parse_german_date(time_text, today)
        if day is None:
            continue

        link = block.find("header")
        link = link.find("a") if link else None
        title = link.get_text(" ", strip=True) if link else None
        if not title:
            continue

        category_el = block.find("span", class_="categories")
        raw_category = category_el.get_text(" ", strip=True) if category_el else None

        # Die Zeit steckt in derselben Zeile wie das Datum ("... ab 19:00 Uhr");
        # normalize_time() zieht sich die erste HH:MM heraus und gibt None
        # zurück, wenn keine drinsteht (ganztägige Termine).
        norm_time = normalize.normalize_time(time_text)

        events.append({
            "uid": normalize.make_event_uid(day.isoformat(), norm_time, title, VENUE),
            "source": SOURCE,
            "date": day.isoformat(),
            "time": norm_time,
            "title": title,
            "venue": VENUE,
            "category": normalize.classify_category(raw_category or "", title, VENUE),
            "raw_category": raw_category,
            "url": link.get("href") or TERMINE_URL,
            "image_url": None,
            "price_text": None,
            "description": _extract_description(block),
            # Die Übersicht enthält nur den Teaser; die Detailseite hätte mehr.
            # Bewusst nicht gesetzt, damit detail_fetch.py sie nachladen kann.
            "detail_fetched_at": None,
        })
    return events


def scrape_range(start_day, end_day):
    """Holt die Übersichtsseite einmal und filtert auf [start_day, end_day]."""
    html = base.fetch_html(TERMINE_URL)
    events = _parse(html, today=start_day)
    start, end = start_day.isoformat(), end_day.isoformat()
    return [e for e in events if start <= e["date"] <= end]

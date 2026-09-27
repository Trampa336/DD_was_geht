"""Scraper für das Hole of Fame (holeoffame.de).

Die Startseite ist eine Tabelle mit Monatsüberschriften, rund fünf Monate im
Voraus (gemessen 27.09.2026). Gegen die Live-Seite geprüft, im Browser, weil
holeoffame.de aus Cowork heraus nicht getestet werden kann.

    <tr><td colspan="3"><h2 class="title">Oktober</h2></td></tr>
    <tr>
      <td class="date">Do. 15.</td>                       (laufende Woche: nur "Mittwoch")
      <td><span class="type badge">film</span></td>
      <td class="event_title"><a href="/events/politkino-...">PolitKino of Fame #04</a></td>
    </tr>
    <tr class="additional_info"><td></td><td></td>
      <td>Gemeinsam politisches Kino gucken<br> 19:00 Uhr</td></tr>

Detailseite je Termin:

    <div class="s12">
      <div class="col s4">15. Oktober</div>
      <div class="col s4">Begin: 19:00</div>
      <div class="col s4">Eintritt frei, Spende willkommen</div>
    </div>
    <div class="trix-content"> ... Beschreibung ... </div>

Regeln:
- Das Datum kommt aus Monatsüberschrift + Tag. Steht nur ein Wochentag da,
  liefert erst die Detailseite den Tag. Das Jahr kommt vom Laufdatum wie bei
  ostpol.py (mehr als ein halbes Jahr zurück heißt: nächstes Jahr).
- Die Uhrzeit aus der Übersicht hat Vorrang. "Begin: 00:00" auf der
  Detailseite heißt "nicht eingetragen" (gesehen bei SUPERFEST) und zählt nicht.
- Das Etikett ("film", "talk", "workshop") ist die Rohkategorie.
- Ausstellungen ("bis 16. Oktober") sind Dauerangebote und fallen weg. Die
  Vernissage steht als eigener Termin da und bleibt.
Detailseiten nur für Termine im Zeitraum (oder mit unbekanntem Tag),
gedrosselt, höchstens MAX_DETAILS. Fehlt eine, bleibt der Termin, wenn sein
Datum aus der Übersicht bekannt ist.
"""
import logging
import re
import time as time_module
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from .. import normalize
from . import base

logger = logging.getLogger("dd-was-geht.holeoffame")

SOURCE = "holeoffame"
URL = "https://holeoffame.de/"
VENUE = "Hole of Fame"
MAX_DETAILS = 40
DETAIL_DELAY_SECONDS = base.REQUEST_DELAY_SECONDS

MONATE = {m: i for i, m in enumerate(
    ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august",
     "september", "oktober", "november", "dezember"], start=1)}
_TAG = re.compile(r"(\d{1,2})\.")
_TAG_MONAT = re.compile(r"(\d{1,2})\.\s*([A-Za-zäÄ]+)")
_ZEIT = re.compile(r"(\d{1,2})[:.](\d{2})")
_WEG = {"ausstellung"}


def _text(tag):
    if tag is None:
        return ""
    zeilen = (" ".join(z.split()) for z in tag.get_text("\n").split("\n"))
    return "\n".join(z for z in zeilen if z)


def _datum(tag, monat, bezug):
    kandidat = date(bezug.year, monat, tag)
    if kandidat < bezug - timedelta(days=183):
        kandidat = date(bezug.year + 1, monat, tag)
    return kandidat


def _hhmm(text):
    m = _ZEIT.search(text or "")
    if not m or int(m.group(1)) > 23:
        return None
    zeit = f"{int(m.group(1)):02d}:{m.group(2)}"
    return None if zeit == "00:00" else zeit


def _parse_uebersicht(html, bezug):
    """Startseite -> Termine; date ist None, wenn nur ein Wochentag dasteht."""
    soup = base.make_soup(html)
    termine, monat = [], None
    for tr in soup.select("tr"):
        h2 = tr.select_one("h2")
        if h2 is not None:
            monat = MONATE.get(h2.get_text(strip=True).lower())
            continue
        link = tr.select_one("td.event_title a")
        if link is None:
            if "additional_info" in (tr.get("class") or []) and termine:
                zeilen = _text(tr.select("td")[-1]).split("\n")
                zeit = _hhmm(zeilen[-1]) if zeilen and zeilen[-1].endswith("Uhr") else None
                if zeit:
                    zeilen = zeilen[:-1]
                termine[-1]["untertitel"] = "\n".join(z for z in zeilen if z) or None
                termine[-1]["time"] = zeit
            continue
        art = (_text(tr.select_one(".type")) or "").lower() or None
        titel = " ".join(_text(link).split("\n"))
        if not titel:
            continue
        m = _TAG.search(_text(tr.select_one("td.date")))
        tag = None
        if m and monat:
            try:
                tag = _datum(int(m.group(1)), monat, bezug)
            except ValueError:
                tag = None
        termine.append({"date": tag, "time": None, "title": titel, "art": art,
                        "untertitel": None, "url": urljoin(URL, link.get("href") or "")})
    return [t for t in termine if t["art"] not in _WEG]


def _parse_detail(html, bezug):
    """Detailseite -> (Datum oder None, Beginn oder None, Preis, Beschreibung)."""
    soup = base.make_soup(html)
    spalten = [_text(c) for c in soup.select(".s12 .col")]
    tag = zeit = preis = None
    for s in spalten:
        m = _TAG_MONAT.search(s)
        if tag is None and m and m.group(2).lower() in MONATE:
            try:
                tag = _datum(int(m.group(1)), MONATE[m.group(2).lower()], bezug)
            except ValueError:
                pass
        elif s.lower().startswith("begin"):
            zeit = _hhmm(s)
        elif s and not m:
            preis = s
    return tag, zeit, preis, _text(soup.select_one(".trix-content")) or None


def _event(t, detail=None):
    d_tag, d_zeit, preis, text = detail or (None, None, None, None)
    tag = t["date"] or d_tag
    zeit = t["time"] or d_zeit
    beschreibung = "\n".join(x for x in (t["untertitel"], text) if x) or None
    return {
        "uid": normalize.make_event_uid(tag.isoformat(), zeit, t["title"], VENUE),
        "source": SOURCE,
        "date": tag.isoformat(),
        "time": zeit,
        "title": t["title"],
        "venue": VENUE,
        "category": normalize.classify_category(t["art"], t["title"], VENUE),
        "raw_category": t["art"],
        "url": t["url"],
        "image_url": None,
        "price_text": preis,
        "description": beschreibung,
        "detail_fetched_at": datetime.utcnow().isoformat() if detail else None,
    }


def scrape_range(start_day, end_day):
    """Übersicht einmal holen, dann Detailseiten für Termine im Zeitraum."""
    termine = [t for t in _parse_uebersicht(base.fetch_html(URL), start_day)
               if t["date"] is None or start_day <= t["date"] <= end_day]
    events = []
    for i, t in enumerate(termine):
        detail = None
        if i < MAX_DETAILS:
            if i:
                time_module.sleep(DETAIL_DELAY_SECONDS)
            try:
                detail = _parse_detail(base.fetch_html(t["url"]), start_day)
            except Exception as exc:  # ein kaputter Termin darf den Rest nicht kosten
                logger.warning("Hole of Fame: Detailseite %s nicht lesbar: %s", t["url"], exc)
        if (t["date"] or (detail and detail[0])) is None:
            continue
        ev = _event(t, detail)
        if start_day.isoformat() <= ev["date"] <= end_day.isoformat():
            events.append(ev)
    return events

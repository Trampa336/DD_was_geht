"""Scraper für den Ostpol (ost-pol.de).

Der Laden pflegt alle kommenden Termine auf der Startseite, rund fünf Wochen
im Voraus (gemessen 27.09.2026: 31 Termine bis 31.10.). Ein Request reicht,
gefiltert wird lokal wie bei den anderen Orte-Seiten.

Markup je Termin, eine eigene kleine Tabelle (gegen die Live-Seite geprüft,
27.09.2026, im Browser, weil ost-pol.de aus Cowork heraus gesperrt ist):

    <table><tbody><tr>
      <td width="66" valign="top">
        <span class="datum">Di.</span> <span class="datum">29</span> <span class="datum">09</span>
      </td>
      <td class="terminbox">
        <div class="presented_by">Beatpol präsentiert:</div>   (nicht immer da)
        <div class="headline">KLEZ.E</div>
        <div class="description">... Einlass: 19.00 Uhr<br>Start: 20.00 Uhr ...</div>
        <div class="cost">++FreiSchau++</div>                  (selten)
      </td>
    </tr></tbody></table>

Drei Eigenheiten:

1. **Kein Jahr.** Das Datum ist nur Tag und Monat. Das Jahr kommt vom
   Startdatum des Laufs; liegt der Termin damit mehr als ein halbes Jahr in
   der Vergangenheit, gehört er ins nächste Jahr (Dezember → Januar).
2. **Keine eigene Uhrzeit.** Sie steht, wenn überhaupt, im Beschreibungstext
   ("Start: 20.00 Uhr", "Einlass 20 Uhr / Beginn 21 Uhr"). Genommen wird
   Beginn/Start, sonst Einlass, sonst keine Zeit. Nichts wird geraten.
3. **Keine Event-Seiten, keine Bilder.** Link ist die Startseite; Bilder in der
   Beschreibung sind nur Emoji-Grafiken von Facebook und werden ignoriert.
"""
import re
from datetime import date, datetime, timedelta

from .. import normalize
from . import base

SOURCE = "ostpol"
URL = "https://www.ost-pol.de/"
VENUE = "Ostpol"

# "Start: 20.00 Uhr", "Beginn 21 Uhr", "Einlass: 19:00 Uhr". Die Ziffern müssen
# direkt folgen - "Beginn der 90er Jahre" ist keine Uhrzeit.
_ZEIT_RE = r"\s*:?\s*(\d{1,2})(?:[:.](\d{2}))?\s*Uhr"
_BEGINN = re.compile(r"(?:Beginn|Start)" + _ZEIT_RE, re.IGNORECASE)
_EINLASS = re.compile(r"Einlass" + _ZEIT_RE, re.IGNORECASE)


def _zeit(text):
    """Beginn/Start vor Einlass; None, wenn nichts Eindeutiges dasteht."""
    for muster in (_BEGINN, _EINLASS):
        m = muster.search(text or "")
        if m and int(m.group(1)) <= 23:
            return f"{int(m.group(1)):02d}:{m.group(2) or '00'}"
    return None


def _datum(tag, monat, bezug):
    """Tag und Monat ohne Jahr -> date; Jahr aus dem Bezugsdatum (siehe oben)."""
    kandidat = date(bezug.year, monat, tag)
    if kandidat < bezug - timedelta(days=183):
        kandidat = date(bezug.year + 1, monat, tag)
    return kandidat


def _text(tag):
    """Text mit Zeilenumbrüchen, leere Zeilen und Einrückungen entfernt."""
    if tag is None:
        return ""
    zeilen = (" ".join(z.split()) for z in tag.get_text("\n").split("\n"))
    return "\n".join(z for z in zeilen if z)


def _parse(html, bezug):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt."""
    soup = base.make_soup(html)
    events = []
    for box in soup.select("td.terminbox"):
        zeile = box.find_parent("tr")
        teile = [s.get_text(strip=True) for s in zeile.select(".datum")] if zeile else []
        titel = " ".join(_text(box.select_one(".headline")).split("\n"))
        if len(teile) < 3 or not titel:
            continue
        try:
            tag = _datum(int(teile[1]), int(teile[2]), bezug)
        except ValueError:
            continue

        beschreibung_roh = _text(box.select_one(".description"))
        praesentiert = _text(box.select_one(".presented_by"))
        beschreibung = "\n".join(t for t in (praesentiert, beschreibung_roh) if t) or None
        zeit = _zeit(beschreibung_roh)
        preis = _text(box.select_one(".cost")) or None

        events.append({
            "uid": normalize.make_event_uid(tag.isoformat(), zeit, titel, VENUE),
            "source": SOURCE,
            "date": tag.isoformat(),
            "time": zeit,
            "title": titel,
            "venue": VENUE,
            # Die Seite nennt keine Kategorie. Keine erfinden: Titel-Stichwort,
            # dann Art des Ortes, sonst "sonstiges" (siehe CLAUDE.md).
            "category": normalize.classify_category(None, titel, VENUE),
            "raw_category": None,
            "url": URL,
            "image_url": None,
            "price_text": preis,
            "description": beschreibung,
            # Alles steht schon auf der Startseite, es gibt nichts nachzuladen.
            "detail_fetched_at": datetime.utcnow().isoformat(),
        })
    return events


def scrape_range(start_day, end_day):
    """Holt die Startseite einmal und filtert auf [start_day, end_day]."""
    events = _parse(base.fetch_html(URL), start_day)
    start, end = start_day.isoformat(), end_day.isoformat()
    return [e for e in events if start <= e["date"] <= end]

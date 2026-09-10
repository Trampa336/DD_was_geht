"""Scraper für die STRASSE E® (strasse-e.de).

Die Seite selbst ist eine Tabellen-Website aus den frühen 2000ern ohne jede
CSS-Klasse an den Event-Blöcken - aber sie verlinkt einen eigenen RSS-Feed
("STRASSE E® Dates"), der genau das liefert, was auf der Startseite mühsam
aus Schriftgrößen-Spans herausgelesen werden müsste:

    http://www.strasse-e.de/strasse-e.xml

Der Titel jedes Items trägt das Datum bereits maschinenlesbar voran
("2026-09-12, Sa : Black Celebration - Bunker Party auf 3 Floors"), die
Beschreibung ist das Line-up, und der Link zeigt auf `termine.php?id=<N>` -
den echten Permalink des Termins. Verifiziert am 09.09.2026: der Feed listet
konstant die nächsten ~9-15 Termine.

Was im Feed FEHLT und nur auf der `termine.php?id=<N>`-Seite steht:
Uhrzeit und Halle. Die Komplett-Adresse besteht aus zwei Hallen
("BUNKER STRASSE E®", "REITHALLE STRASSE E®") - deren Namen zählen mehr als
das bloße "Straße E", weil Bunker und Reithalle unterschiedliche Kapazitäten
und Programme haben. Markup der Detailseite (gegen mehrere echte Seiten
verifiziert):

    <span style="font-weight:bold">BUNKER STRASSE E&reg;<br>
      <span style="font-size:110%">BLACK CELEBRATION - ...</span><br>
      <span style="font-size:80%">Einlass 22 Uhr<br>...<a href="...">weitere
      Informationen</a></span>
    </span>

Ein Request je Termin im Feed (9-15 pro Lauf, wie bei Sektor Evolution
gedrosselt und gedeckelt) - dafür Halle UND Uhrzeit statt nur die Halle zu
raten.

Kodierung: die Seite liefert ISO-8859-1 (siehe <?xml ... encoding=
"ISO-8859-1"?>), requests dekodiert das nur korrekt, wenn man es nicht dem
falschen Rateverfahren überlässt - siehe fetch_html() unten.
"""
import html
import logging
import re
import time as time_module
from datetime import date, datetime

import requests

from .. import normalize
from . import base

logger = logging.getLogger("dd-was-geht.strassee")

SOURCE = "strassee"
RSS_URL = "http://www.strasse-e.de/strasse-e.xml"
SITE_VENUE = "Straße E"

MAX_DETAIL_FETCHES = 30
DETAIL_DELAY_SECONDS = 0.5

_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)
_TITLE_RE = re.compile(r"<title>\s*(\d{4})-(\d{2})-(\d{2}),\s*\w+\s*:\s*(.+?)\s*</title>", re.S)
_LINK_RE = re.compile(r"<link>\s*(.+?)\s*</link>", re.S)
_DESC_RE = re.compile(r"<description>(.*?)</description>", re.S)

# Detailseite: Halle, Titel und der Rest (Uhrzeit + weiterführender Link) in
# drei aufeinanderfolgenden <span>s desselben umschließenden <span>.
_DETAIL_BLOCK_RE = re.compile(
    r'<span style="font-weight:bold">(.*?)<br>'
    r'<span style="font-size:110%">(.*?)</span><br>'
    r'<span style="font-size:80%">(.*?)</span>',
    re.S,
)
_EINLASS_RE = re.compile(r"Einlass\s*(\d{1,2})(?:[:.](\d{2}))?\s*Uhr", re.I)


def _clean(html_fragment):
    text = re.sub(r"<[^>]+>", " ", html_fragment or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip() or None


def _fix_mojibake(text):
    """Der Feed deklariert ISO-8859-1, mischt an manchen Stellen aber
    UTF-8-kodierte Interpunktion ein (z.B. eine kuratierte Ankuendigung mit
    typografischem Apostroph) - fetch_html() dekodiert dann alles als
    ISO-8859-1 und aus dem Apostroph wird "â" plus zwei unsichtbare
    Kontrollzeichen ("Doesnât Matter"). Reparatur per Rueckkodierungs-Probe:
    kodiert man den (falsch dekodierten) Text nach ISO-8859-1 zurueck, hat
    man wieder die Original-Bytes - lassen die sich als UTF-8 dekodieren,
    war es UTF-8-Interpunktion und das Ergebnis ist korrekt; wirft es,
    handelte es sich um echtes ISO-8859-1 (z.B. "ß", "ü") und der Text
    bleibt unangetastet."""
    if not text:
        return text
    try:
        return text.encode("iso-8859-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _parse_feed(xml_text):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt.

    Bewusst mit Regex statt BeautifulSoup: der Feed ist wohlgeformtes,
    simples RSS ohne Verschachtelung - ein XML-Parser wäre hier nur Ballast,
    und einer für ISO-8859-1 bräuchte ohnehin Sonderbehandlung.
    """
    entries = []
    for raw_item in _ITEM_RE.findall(xml_text):
        title_match = _TITLE_RE.search(raw_item)
        link_match = _LINK_RE.search(raw_item)
        if not (title_match and link_match):
            continue
        year, month, day, title = title_match.groups()
        try:
            event_date = date(int(year), int(month), int(day))
        except ValueError:
            continue
        desc_match = _DESC_RE.search(raw_item)
        entries.append({
            "date": event_date.isoformat(),
            "title": _fix_mojibake(title.strip()),
            "url": link_match.group(1).strip(),
            "description": _fix_mojibake(_clean(desc_match.group(1))) if desc_match else None,
        })
    return entries


def _parse_detail(html_text):
    """Halle + Uhrzeit von termine.php?id=<N>. Gibt (halle, zeit) zurück,
    beides ggf. None, falls die Struktur einmal nicht passt."""
    match = _DETAIL_BLOCK_RE.search(html_text)
    if not match:
        return None, None
    venue = _clean(match.group(1))
    if venue:
        # "BUNKER STRASSE E&reg;" -> "Bunker Straße E". Die Quelle schreibt
        # den Hallennamen komplett in Grossbuchstaben und meidet das Eszett
        # (ASCII-Notation aus den fruehen 2000ern) - fuer den Ortsschluessel
        # der Doppelungs-Erkennung ist beides egal (normalize.slugify senkt
        # auf Kleinbuchstaben und wandelt "ß" ohnehin zu "ss"), lesbarer ist
        # es trotzdem so.
        venue = venue.replace("®", "").strip().title().replace("Strasse", "Straße")
    info_text = match.group(3)
    einlass = _EINLASS_RE.search(_clean(info_text) or "")
    norm_time = f"{int(einlass.group(1)):02d}:{einlass.group(2) or '00'}" if einlass else None
    return venue or None, norm_time


def _fetch_detail(url):
    """Wirft nie - ohne Detailseite bleiben Halle und Uhrzeit leer.
    Gibt (halle, zeit, erfolgreich?) zurück."""
    try:
        venue, norm_time = _parse_detail(base.fetch_html(url))
        return venue, norm_time, True
    except Exception:
        logger.warning("Straße-E-Detailseite nicht ladbar: %s", url)
        return None, None, False


def fetch_html(url, timeout=15, retries=2):
    """Wie base.fetch_html, aber mit expliziter ISO-8859-1-Dekodierung - ohne
    das rät requests anhand des HTTP-Headers und trifft es nicht immer richtig,
    aus "größer" würde sonst stellenweise Muell."""
    last_error = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=base.HEADERS, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = "iso-8859-1"
            return resp.text
        except requests.RequestException as exc:
            last_error = exc
            time_module.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Konnte {url} nicht laden: {last_error}")


def _build_event(entry, venue, norm_time, detail_ok):
    venue = venue or SITE_VENUE
    return {
        "uid": normalize.make_event_uid(entry["date"], norm_time, entry["title"], venue),
        "source": SOURCE,
        "date": entry["date"],
        "time": norm_time,
        "title": entry["title"],
        "venue": venue,
        # Keine Rohkategorie im Feed - die Location ist durchgehend eine
        # Clubreihe/Konzerthalle, der Titel entscheidet über
        # normalize._classify_by_keywords().
        "category": normalize.classify_category("", entry["title"], venue),
        "raw_category": None,
        "url": entry["url"],
        "image_url": None,
        "price_text": None,
        "description": entry["description"],
        # Nur wenn die Detailseite wirklich gelesen wurde, gilt der Termin
        # als vollständig - sonst darf ein späterer Lauf Halle/Uhrzeit
        # nachtragen (die fehlen sonst z.B. bei "TOWER TRANSMISSIONS", wo die
        # Quelle selbst keine Einlasszeit nennt - das ist trotzdem ein
        # erfolgreicher Abruf, kein Fehlschlag).
        "detail_fetched_at": datetime.utcnow().isoformat() if detail_ok else None,
    }


def scrape_range(start_day, end_day, fetch_detail=_fetch_detail):
    """Holt den RSS-Feed einmal, filtert auf [start_day, end_day] und lädt zu
    jedem verbleibenden Termin die Detailseite nach (Halle, Uhrzeit).

    fetch_detail ist injizierbar, damit Tests ohne Netzwerk auskommen.
    """
    entries = _parse_feed(fetch_html(RSS_URL))
    start, end = start_day.isoformat(), end_day.isoformat()
    entries = sorted(
        (e for e in entries if start <= e["date"] <= end), key=lambda e: e["date"]
    )
    if len(entries) > MAX_DETAIL_FETCHES:
        logger.warning(
            "Straße E: %d Termine im Zeitraum, Details nur für die ersten %d.",
            len(entries), MAX_DETAIL_FETCHES,
        )

    events = []
    for index, entry in enumerate(entries):
        if index < MAX_DETAIL_FETCHES:
            venue, norm_time, detail_ok = fetch_detail(entry["url"])
        else:
            venue, norm_time, detail_ok = None, None, False
        events.append(_build_event(entry, venue, norm_time, detail_ok))
        if index and DETAIL_DELAY_SECONDS:
            time_module.sleep(DETAIL_DELAY_SECONDS)
    return events

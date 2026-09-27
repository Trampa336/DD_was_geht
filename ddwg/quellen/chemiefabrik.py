"""Scraper für die Chemiefabrik (chemiefabrik.info).

Die Startseite listet alle Gigs, rund 16 Monate im Voraus (gemessen
27.09.2026: 67 Termine bis 09.2027). Gegen die Live-Seite geprüft, im
Browser, weil chemiefabrik.info aus Cowork heraus gesperrt ist.

Übersicht, ein Link je Termin:

    <a class="event" href="/gigs/15088/">
      <div class="img"><img src="/veranstaltungsbild/15088/?v=..."></div>
      <div class="info">
        <div class="date">Fr, 02.10.26 <span class="time">20:00 Uhr</span></div>
        <div class="headlines"><div class="item">THRASH TITANS VOL. III</div></div>
        <div class="artists">
          <div class="item"><span class="artist-name">HOLY WAVE</span>
                            <span class="artist-info">Neo-Psych / USA</span></div>
        </div>
      </div>
    </a>

Die Zeit in der Übersicht ist der **Einlass**. Beginn, Beschreibung und Preis
stehen nur auf der Detailseite:

    <div class="time">Einlass: 20:00 Uhr<br>Beginn: 21:00 Uhr</div>
    <div class="infos"> ... </div>
    <div class="praesentatoren">präsentiert von: It's a Gas! Records, Chemiefabrik</div>
    <div class="vvk">Vorverkauf: 23,00€ ...</div>
    <div class="ak">Abendkasse: 28,00€</div>

Deshalb holt scrape_range() die Detailseite für jeden Termin im Zeitraum mit
(gedrosselt, höchstens MAX_DETAILS). Schlägt eine fehl, bleibt der Termin mit
den Angaben aus der Übersicht erhalten.

Titel sind die Bandnamen, mit " + " verbunden. Kopfzeilen wie "+ Wir feiern
25 Jahre an 25 Tagen +" oder "THRASH TITANS VOL. III" kommen in die
Beschreibung. Ohne Bands wird die Kopfzeile zum Titel; der Platzhalter
"Infos folgen …" zählt nie.
"""
import logging
import re
import time as time_module
from datetime import date, datetime
from urllib.parse import urljoin

from .. import normalize
from . import base

logger = logging.getLogger("dd-was-geht.chemiefabrik")

SOURCE = "chemiefabrik"
URL = "https://www.chemiefabrik.info/"
VENUE = "Chemiefabrik"
MAX_DETAILS = 60
DETAIL_DELAY_SECONDS = base.REQUEST_DELAY_SECONDS

_DATUM = re.compile(r"(\d{2})\.(\d{2})\.(\d{2})")
_UHR = r"\s*:?\s*(\d{1,2})[:.](\d{2})"
_BEGINN = re.compile(r"Beginn" + _UHR, re.IGNORECASE)
_EINLASS = re.compile(r"Einlass" + _UHR, re.IGNORECASE)
_ZEIT = re.compile(r"(\d{1,2})[:.](\d{2})")
_PREIS = re.compile(r"(Vorverkauf|Abendkasse):\s*([\d.,]+\s*€)")
_PLATZHALTER = "infos folgen"


def _text(tag):
    if tag is None:
        return ""
    zeilen = (" ".join(z.split()) for z in tag.get_text("\n").split("\n"))
    return "\n".join(z for z in zeilen if z)


def _hhmm(match):
    return f"{int(match.group(1)):02d}:{match.group(2)}" if match else None


def _parse_uebersicht(html):
    """Startseite -> Termine mit Angaben aus der Übersicht (ohne Netz)."""
    soup = base.make_soup(html)
    termine = []
    for a in soup.select("a.event"):
        datum_tag = a.select_one(".date")
        m = _DATUM.search(datum_tag.get_text(" ") if datum_tag else "")
        if not m:
            continue
        try:
            tag = date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        zeit_tag = a.select_one(".date .time")
        kopf = [_text(i) for i in a.select(".headlines .item")]
        kopf = [k for k in kopf if k and not k.lower().startswith(_PLATZHALTER)]
        bands = [_text(b) for b in a.select(".artists .artist-name")]
        bands = [b for b in bands if b]
        titel = " + ".join(bands) or " / ".join(kopf)
        if not titel:
            continue
        img = a.select_one(".img img")
        bild = img.get("src") if img else None
        if bild and "demnaechst" in bild:
            bild = None
        termine.append({
            "date": tag,
            "time": _hhmm(_ZEIT.search(zeit_tag.get_text())) if zeit_tag else None,
            "title": titel,
            "kopf": [k for k in kopf if k != titel],
            "bands": [" ".join(_text(i).split("\n")) for i in a.select(".artists .item")],
            "url": urljoin(URL, a.get("href") or ""),
            "image_url": urljoin(URL, bild) if bild else None,
        })
    return termine


def _parse_detail(html):
    """Detailseite -> (Beginn oder Einlass, Beschreibung, Preis, Veranstalter)."""
    soup = base.make_soup(html)
    zeit_text = _text(soup.select_one(".event .time") or soup.select_one(".time"))
    zeit = _hhmm(_BEGINN.search(zeit_text)) or _hhmm(_EINLASS.search(zeit_text))
    infos = _text(soup.select_one(".infos")) or None
    preise = []
    for sel in (".vvk", ".ak"):
        m = _PREIS.search(_text(soup.select_one(sel)))
        if m:
            preise.append(f"{m.group(1)} {m.group(2).replace(' ', '')}")
    praes = _text(soup.select_one(".praesentatoren")) or None
    return zeit, infos, " · ".join(preise) or None, praes


def _event(t, detail=None):
    zeit, infos, preis, praes = detail or (None, None, None, None)
    zeit = zeit or t["time"]
    teile = t["kopf"] + t["bands"]
    beschreibung = "\n".join(x for x in teile + [infos, praes] if x) or None
    tag = t["date"].isoformat()
    return {
        "uid": normalize.make_event_uid(tag, zeit, t["title"], VENUE),
        "source": SOURCE,
        "date": tag,
        "time": zeit,
        "title": t["title"],
        "venue": VENUE,
        # Keine Kategorie auf der Seite. Titel sind Bandnamen, also meist
        # "sonstiges" - dann greift die Art des Ortes (club), siehe CLAUDE.md.
        "category": normalize.classify_category(None, t["title"], VENUE),
        "raw_category": None,
        "url": t["url"],
        "image_url": t["image_url"],
        "price_text": preis,
        "description": beschreibung,
        "detail_fetched_at": datetime.utcnow().isoformat() if detail else None,
    }


def scrape_range(start_day, end_day):
    """Übersicht einmal holen, dann je Termin im Zeitraum die Detailseite."""
    termine = [t for t in _parse_uebersicht(base.fetch_html(URL)) if start_day <= t["date"] <= end_day]
    events = []
    for i, t in enumerate(termine):
        detail = None
        if i < MAX_DETAILS:
            if i:
                time_module.sleep(DETAIL_DELAY_SECONDS)
            try:
                detail = _parse_detail(base.fetch_html(t["url"]))
            except Exception as exc:  # ein kaputter Termin darf den Rest nicht kosten
                logger.warning("Chemiefabrik: Detailseite %s nicht lesbar: %s", t["url"], exc)
        events.append(_event(t, detail))
    return events

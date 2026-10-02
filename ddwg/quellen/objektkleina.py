"""Scraper für objekt klein a (objektkleina.com).

Herz-Ort seit 2026-09-30, bis 2026-10-02 ohne eigene Quelle (live 2 Termine
aus den Sammelkalendern, auf der eigenen Seite 7 im Oktober). Gegen die
Live-Seite geprüft am 02.10.2026, im Browser, weil Cowork die Seite sperrt.

Die Seite ist WordPress mit einer Seite je Monat. Die Startseite ist immer
der aktuelle Monat, das Menü links nennt alle Monate mit Namen:

    <nav class="off-canvas ..."><ul>
      <li><a href="https://objektkleina.com/">Oktober 2026</a></li>
      <li><a href="https://objektkleina.com/september-2026-2/">September 2026</a></li>
      <li><a href="https://objektkleina.com/juni-2026-2-2/">Juli 2026</a></li>

Die Adressen sind unregelmäßig (Juli steht unter "juni-2026-2-2"), darum
zählt nur der Linktext. Je Termin ein Artikel:

    <article class="child" data-permalink="https://objektkleina.com/oktober-2026/routine/">
      <div class="child__header"><h2>ROUTINE w/ Das Beat &amp; Hyperaktivist</h2></div>
      <img src="https://objektkleina.com/content/uploads/....jpg" ...>
      <div class="child__info">
        <dl><dt>Type:</dt><dd>Club</dd><dt>Date:</dt><dd>03 10 26</dd>
            <dt>Start:</dt><dd>23:00</dd></dl>
        <div class="text text-size--large"> Beschreibung </div>
        <div class="text text-size--small"> 10€ bis 0000 ... Ticket-Link </div>
        <h2>Lineup</h2>
        <div class="text text-size--large"> Das Beat<br>Hyperaktivist ... </div>
      </div>
    </article>

Beschreibung = Text plus "Lineup: …". Platzhalter ("lorem ipsum") fallen weg.
Preis = Zeilen aus dem kleinen Text mit "€" oder "Eintritt".
"""
import re
from datetime import date, datetime

from .. import normalize
from . import base

SOURCE = "objektkleina"
URL = "https://objektkleina.com/"
VENUE = "objekt klein a"

MONATE = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
}
_MONAT_RE = re.compile(r"([A-Za-zÄÖÜäöü]+)\s+(\d{4})")
_DATUM_RE = re.compile(r"(\d{1,2})\D+(\d{1,2})\D+(\d{2,4})")
_ZEIT_RE = re.compile(r"(\d{1,2})[:.](\d{2})")
_PLATZHALTER = ("lorem ipsum",)


def _zeilen(tag):
    """Text mit Zeilenumbrüchen, Leerzeichen (auch &nbsp;) zusammengefasst."""
    if tag is None:
        return []
    # Nur <br> und Absätze trennen Zeilen, Links mitten im Satz nicht
    # ("<a>Bephål</a> ( SAFT )" bleibt eine Zeile).
    for br in tag.find_all("br"):
        br.replace_with("\n")
    for block in tag.find_all(["p", "div", "li"]):
        block.append("\n")
    zeilen = (" ".join(z.split()) for z in tag.get_text("").split("\n"))
    return [z for z in zeilen if z]


def _monatsseiten(html):
    """(jahr, monat) -> URL aus dem Menü der Startseite."""
    soup = base.make_soup(html)
    seiten = {}
    for a in soup.select("nav a[href]"):
        m = _MONAT_RE.search(a.get_text(" ", strip=True))
        if not m:
            continue
        monat = MONATE.get(m.group(1).lower())
        if monat:
            seiten.setdefault((int(m.group(2)), monat), a["href"])
    return seiten


def _datum(text):
    m = _DATUM_RE.search(text or "")
    if not m:
        return None
    tag, monat, jahr = (int(x) for x in m.groups())
    if jahr < 100:
        jahr += 2000
    try:
        return date(jahr, monat, tag)
    except ValueError:
        return None


def _parse(html):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt."""
    soup = base.make_soup(html)
    events = []
    for art in soup.select("article.child"):
        kopf = art.select_one(".child__header h2")
        titel = " ".join(kopf.get_text(" ").split()) if kopf else ""
        info = art.select_one(".child__info")
        if not titel or info is None:
            continue

        felder = {}
        for dt in info.select("dl dt"):
            dd = dt.find_next_sibling("dd")
            if dd is not None:
                felder[dt.get_text(strip=True).rstrip(":").lower()] = " ".join(dd.get_text(" ").split())
        tag = _datum(felder.get("date"))
        if tag is None:
            continue
        m = _ZEIT_RE.search(felder.get("start", ""))
        zeit = f"{int(m.group(1)):02d}:{m.group(2)}" if m and int(m.group(1)) <= 23 else None
        art_roh = felder.get("type") or None

        # Kinder von .child__info der Reihe nach: vor "Lineup" Text und
        # Kleingedrucktes, danach das Lineup.
        text, klein, lineup, nach_lineup = [], [], [], False
        for kind in info.find_all(recursive=False):
            klassen = kind.get("class") or []
            if kind.name == "h2" and "lineup" in kind.get_text(strip=True).lower():
                nach_lineup = True
            elif "text" in klassen:
                zeilen = _zeilen(kind)
                if nach_lineup:
                    lineup += zeilen
                elif "text-size--small" in klassen:
                    klein += zeilen
                else:
                    text += zeilen
        if any(" ".join(text).lower().startswith(p) for p in _PLATZHALTER):
            text = []
        teile = ["\n".join(text)] if text else []
        if lineup:
            teile.append("Lineup: " + ", ".join(lineup))
        beschreibung = "\n\n".join(teile) or None
        preis = " · ".join(z for z in klein if "€" in z or "eintritt" in z.lower()) or None

        img = art.select_one("img[src]")
        bild = img["src"] if img is not None and img["src"].startswith("http") else None

        events.append({
            "uid": normalize.make_event_uid(tag.isoformat(), zeit, titel, VENUE),
            "source": SOURCE,
            "date": tag.isoformat(),
            "time": zeit,
            "title": titel,
            "venue": VENUE,
            "category": normalize.classify_category(art_roh, titel, VENUE),
            "raw_category": art_roh,
            "url": art.get("data-permalink") or URL,
            "image_url": bild,
            "price_text": preis,
            "description": beschreibung,
            # Alles steht schon auf der Monatsseite, es gibt nichts nachzuladen.
            "detail_fetched_at": datetime.utcnow().isoformat(),
        })
    return events


def _monate_im_zeitraum(start_day, end_day):
    jahr, monat = start_day.year, start_day.month
    while (jahr, monat) <= (end_day.year, end_day.month):
        yield jahr, monat
        jahr, monat = (jahr + 1, 1) if monat == 12 else (jahr, monat + 1)


def scrape_range(start_day, end_day):
    """Startseite holen, dann jede Monatsseite im Zeitraum (laut Menü) einmal."""
    start_html = base.fetch_html(URL)
    seiten = _monatsseiten(start_html)
    geholt = {URL: start_html}
    for jm in _monate_im_zeitraum(start_day, end_day):
        url = seiten.get(jm)
        if url and url not in geholt:
            base.time_module.sleep(base.REQUEST_DELAY_SECONDS)
            geholt[url] = base.fetch_html(url)
    start, end = start_day.isoformat(), end_day.isoformat()
    gesehen, events = set(), []
    for html in geholt.values():
        for e in _parse(html):
            if start <= e["date"] <= end and e["uid"] not in gesehen:
                gesehen.add(e["uid"])
                events.append(e)
    return events

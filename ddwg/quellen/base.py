"""Gemeinsame Hilfsfunktionen für die Scraper.

WICHTIG (siehe README, Abschnitt "Scraper kalibrieren"): Die URL-Muster beider
Quellen sind gegen die echten Seiten verifiziert (Kulturkalender:
/heute/{YYYY-MM-DD}, Rauze: /?date={YYYY-MM-DD}) - ebenso die tatsächlich
gelieferten Inhalte, Zeitformate und Kategorienamen. Was NICHT gegen rohes HTML
verifiziert werden konnte, ist die Markup-Struktur (Klassennamen, Verschachtelung),
weil die Entwicklungsumgebung nur gerenderten Text sah. Die Heuristik unten ist
deshalb bewusst strukturunabhängig gebaut. Falls doch etwas hakt, hilft
`tools/inspect_source.py` beim Nachjustieren in wenigen Minuten.

Strategie, die deutlich robuster ist als exakte CSS-Klassen zu raten:
finde alle Textknoten, die wie eine Uhrzeit aussehen (HH:MM), und behandle deren
nächstgelegenen Vorfahren mit einer Überschrift als "ein Event-Block". Das
übersteht Redesigns besser als starre Klassennamen.
"""
import re
import time as time_module
from datetime import timedelta

import requests
from bs4 import BeautifulSoup

# lxml ist schnell, hat aber auf 32-bit-Raspberry-Pi-OS (armv7) oft kein
# fertiges Wheel und müsste dann minutenlang aus dem Quellcode gebaut werden.
# Deshalb: benutzen wenn vorhanden, sonst klaglos auf Pythons eingebauten
# Parser zurückfallen. Für unsere Zwecke ist der Unterschied nicht spürbar.
try:
    import lxml  # noqa: F401
    HTML_PARSER = "lxml"
except ImportError:
    HTML_PARSER = "html.parser"

# Uhrzeit-Textknoten, z.B. "20:00", "18:00-19:30", "18:00–19:30" (En-Dash!),
# "19.30 bis 22.00". Rauze benutzt tatsächlich den En-Dash (–), nicht den
# ASCII-Bindestrich - das war ein echter Fallstrick beim Kalibrieren.
#
# Zwei Varianten: TIME_PATTERN verlangt, dass der GESAMTE Textknoten nur die
# Zeit ist (deckt z.B. "19.30 bis 22.00" als eigener Knoten ab). Real liefert
# Kulturkalender aber Knoten wie "21.08.2026\n     | 08:00" - Datum und Zeit im
# selben <time>-Element. Dafür sucht TIME_EMBEDDED_PATTERN gezielt nur nach der
# Doppelpunkt-Form irgendwo im Text (nie die Punkt-Form - "21.08.2026" enthält
# sonst zufällig punktgetrennte Ziffernpaare wie "08.20", die sich sonst als
# Zeit lesen ließen).
TIME_PATTERN = re.compile(
    r"^\s*\d{1,2}[:.]\d{2}\s*(?:[-–—]|bis)?\s*(?:\d{1,2}[:.]\d{2})?\s*(?:Uhr)?\s*$"
)
TIME_EMBEDDED_PATTERN = re.compile(
    r"\d{1,2}:\d{2}(?:\s*(?:[-–—]|bis)\s*\d{1,2}:\d{2})?(?:\s*Uhr)?"
)


def _extract_time_text(raw_text):
    stripped = raw_text.strip()
    if not stripped:
        return None
    if TIME_PATTERN.match(stripped):
        return stripped
    match = TIME_EMBEDDED_PATTERN.search(stripped)
    return match.group(0) if match else None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DresdenTaktBot/1.0; "
        "+privates, nicht-kommerzielles Projekt)"
    )
}


def fetch_html(url, timeout=15, retries=2):
    last_error = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            last_error = exc
            time_module.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Konnte {url} nicht laden: {last_error}")


# --- Quellen mit einer Seite pro Tag ---------------------------------------
# Kulturkalender, Rauze und CyberSAX haben alle drei eine URL je Tag und keine
# Bereichs-URL. Ihr Ablauf ist deshalb bis auf das Parsen identisch und steht
# hier einmal: Tagesseite holen -> quellen-eigenes _parse() -> nächster Tag.

# Kleine Pause zwischen zwei Tagesabrufen - für einen Monat sind das bis zu 31
# Requests an dieselbe Seite; niemand hat etwas davon, wenn wir sie im
# Sekundentakt bombardieren.
REQUEST_DELAY_SECONDS = 1.2


def fetch_day(url, day, parse):
    """Eine Tagesseite holen und parsen lassen.

    parse(html, day, source_url) -> Liste von Event-dicts. Die URL wird
    mitgegeben, weil die Quellen ohne Event-Permalink sie als url eintragen
    (CyberSAX) bzw. als Rückfallebene brauchen (Rauze, Kulturkalender).
    """
    return parse(fetch_html(url), day, url)


def scrape_days(start_day, end_day, scrape_date, source,
                delay=REQUEST_DELAY_SECONDS):
    """Tag für Tag abfragen und alles einsammeln.

    Ein schlechter Tag (Timeout, Redesign, leere Antwort) darf den Rest des
    Laufs nicht stoppen: der Fehler wird gemeldet, der nächste Tag trotzdem
    geholt.
    """
    all_events = []
    current = start_day
    while current <= end_day:
        try:
            all_events.extend(scrape_date(current))
        except Exception as exc:
            print(f"[{source}] Fehler beim Laden von {current}: {exc}")
        time_module.sleep(delay)
        current += timedelta(days=1)
    return all_events


def _is_event_container(tag):
    """Ein Container gilt als 'ein Event', sobald er entweder eine Überschrift
    (h1-h4, z.B. Kulturkalender) ODER eine Klasse exakt 'event' trägt (z.B.
    Rauze, das gar keine Überschriften-Tags benutzt, sondern <div class="event">)."""
    if tag.find(["h1", "h2", "h3", "h4"]):
        return True
    classes = tag.get("class") or []
    return any(c.lower() == "event" for c in classes)


def find_event_blocks(soup, max_ancestor_hops=6):
    """Findet Kandidaten-Container für einzelne Events, indem von jedem
    Uhrzeit-Textknoten aus nach oben gelaufen wird, bis ein Container gefunden
    wird, der wie ein Event aussieht (siehe _is_event_container)."""
    blocks = []
    seen_ids = set()

    for text_node in soup.find_all(string=True):
        time_text = _extract_time_text(str(text_node))
        if not time_text:
            continue
        node = text_node.parent
        if node is None or node.name in ("script", "style"):
            continue

        container = node
        for _ in range(max_ancestor_hops):
            if _is_event_container(container):
                break
            if container.parent is None:
                break
            container = container.parent

        if id(container) in seen_ids:
            continue
        seen_ids.add(id(container))
        blocks.append((time_text, container))

    return blocks


def extract_title(container):
    heading = container.find(["h1", "h2", "h3", "h4"])
    if heading:
        return heading.get_text(" ", strip=True)
    # Manche Quellen (z.B. Rauze) haben keine Überschriften-Tags, sondern ein
    # Element mit Klasse 'title' (<span class="title">...).
    for el in container.find_all(True):
        classes = el.get("class") or []
        if any(c.lower() == "title" for c in classes):
            text = el.get_text(" ", strip=True)
            if text:
                return text
    return None


def extract_venue(container, exclude_texts=()):
    """Bevorzugt ein semantisches <address>-Element (z.B. Kulturkalender),
    sonst den Text des ersten Links, der nicht offensichtlich ein
    Social-Share-, Ticket- oder Breadcrumb-Link ist."""
    address = container.find("address")
    if address:
        text = address.get_text(" ", strip=True)
        if text:
            return text

    for link in container.find_all("a"):
        href = (link.get("href") or "").lower()
        text = link.get_text(strip=True)
        if not text or text in exclude_texts:
            continue
        if any(skip in href for skip in ("facebook", "twitter", "whatsapp", "mailto", ".ics", "reservix", "eventim")):
            continue
        return text
    return None


def text_excluding_links(container):
    """Text eines Blocks OHNE die Beschriftungen von Links.

    Wichtig für die Kategorie-Erkennung: Ortsnamen stehen als Link im selben
    Block und enthalten oft Genre-Wörter ("Burg Max Jacob *Theater*",
    "Landes*bühnen* Sachsen", "Jazz*club* Tonne"). Würde man sie mitlesen,
    landet ein Rave im Max-Jacob-Theater fälschlich in der Kategorie Bühne.
    """
    clone = BeautifulSoup(str(container), HTML_PARSER)
    for link in clone.find_all("a"):
        link.decompose()
    return clone.get_text(" ", strip=True)


BG_IMAGE_URL_PATTERN = re.compile(r"url\(([^)]+)\)")


def extract_bg_image_url(tag):
    """Liest die Bild-URL aus einem style="background-image: url(...)"-Attribut.
    Rauze rendert Cover-Bilder so statt als <img src>."""
    if tag is None:
        return None
    match = BG_IMAGE_URL_PATTERN.search(tag.get("style") or "")
    return match.group(1).strip("'\" ") if match else None


PAREN_CATEGORY_PATTERN = re.compile(r"\(\s*([A-Za-zÄÖÜäöüß/ -]{3,20}?)\s*\)")


def extract_parenthesized_category(container):
    """Rauze rendert die Kategorie als '( Konzert )' - falls vorhanden, ist das
    die verlässlichste Quelle, deutlich besser als Stichwortsuche im Fließtext."""
    match = PAREN_CATEGORY_PATTERN.search(text_excluding_links(container))
    return match.group(1).strip() if match else None


def make_soup(html):
    return BeautifulSoup(html, HTML_PARSER)

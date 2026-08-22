"""Scraper für das "Terminal" des SAX-Stadtmagazins (cybersax.de).

Ergänzt die anderen Quellen um die kleinen Läden: Bars, Cafés und Kleinbühnen
mit Programm, die weder im Kulturkalender (fast nur institutionelle Veranstalter)
noch auf rauze.de (kuratierte Neustadt-Auswahl) auftauchen - Blue Note,
Café Saite, Kafé Zeitlos, Der Lude, Downtown, Eselnest, Bürgergarten,
Gartenlokal Fortschritt, Blaue Fabrik, Kleinkunstbühne Q24, Hoppes Hoftheater.

URL-Muster (gegen die Live-Seite verifiziert):
    https://www.cybersax.de/terminal/day/YYYY/M/D/
Wichtig: OHNE führende Nullen. /terminal/day/2026/8/29/ liefert Samstag,
den 29. August 2026.

Seitenaufbau (verifiziert): ein <div class="tx-usercybersax-pi2"> pro Tag, darin
eine Tabelle mit drei Zeilenarten in Dokumentreihenfolge:

    <tr><td colspan="3"><h4>Musik</h4></td></tr>        -> Abschnittsüberschrift
    <tr><td class="td1">20:00 Uhr</td>
        <td class="td2"><a ...>Ostpol</a></td>
        <td class="td3">Titel&nbsp;Beschreibung</td></tr> -> ein Event
    <tr><td class="td1">21:00 Uhr</td>
        <td colspan="2" class="td3">...</td></tr>         -> Kinoprogramm

Die Abschnittsüberschriften sind die Rohkategorien der Quelle (verifiziert):
    Aktionen, Bühne, Musik, Tanz / Party, Vortrag / Gespräch,
    Kunst / Ausstellung, Fest, Führungen, Kinder / Familie, Treff,
    Workshops, Literatur, Film
Dazwischen stehen aber auch Festivalnamen im selben <h4> ("Klang&Kruste",
"Herbst- und Weinfest", "Zaunkönig", "Tag des Offenen Denkmals"). Die sind keine
Kategorie, sondern der Name EINER Veranstaltung, deren Line-up in den folgenden
Zeilen steht - siehe _collapse_festival_groups().

Anders als bei rauze.de gibt es hier KEINE Event-Permalinks; die Quelle verlinkt
nur Orte (/terminal/adressen/address/<ort>/). Als url steht deshalb die
Tagesseite drin - die ist wenigstens stabil und zeigt dauerhaft denselben Tag.
Bilder und Preise liefert die Quelle gar nicht.
"""
import time
from datetime import datetime, timedelta

from .. import normalize
from . import base

SOURCE = "cybersax"
DATE_URL_TEMPLATE = "https://www.cybersax.de/terminal/day/{year}/{month}/{day}/"

# Wie bei Rauze: für einen Monat sind das bis zu 31 Anfragen.
REQUEST_DELAY_SECONDS = 1.2

# Die Tagestabelle steht in diesem Container. Alles andere auf der Seite
# (Sidebar, Werbung, Fußzeile) hat mit Terminen nichts zu tun.
TERMINAL_CONTAINER_CLASS = "tx-usercybersax-pi2"

# --- Nur kleine Häuser ------------------------------------------------------
# Das Terminal listet 50-180 Termine pro Tag und damit auch das komplette
# Programm der großen Institutionen - die stehen aber schon vollständig im
# Kulturkalender. Übernommen wird deshalb nur, was dort fehlt: die kleinen
# Läden. Der Filter läuft absichtlich hier im Scraper und nicht erst beim
# Ausspielen, damit die Doppelungen gar nicht erst in der Datenbank landen.
#
# Bewusst eine kurze, ausdrückliche Liste statt einer Rateheuristik (gleiche
# Überlegung wie bei normalize._FILM_VENUE_RE): "groß" ist nichts, was man einem
# Namen ansieht. Verglichen wird gegen normalize.slugify() des Ortsnamens, und
# zwar per Teilstring - "schloss-pillnitz-kunstgewerbemuseum" wird also von
# "schloss-pillnitz" mit erfasst.
#
# Erweitern, wenn ein großes Haus durchrutscht:
#   SELECT venue, count(*) c FROM events WHERE source='cybersax'
#     GROUP BY 1 ORDER BY c DESC LIMIT 40;
# Der Ortsname aus der Ausgabe, durch slugify() geschickt, kommt hier rein.
BIG_VENUE_SLUGS = {
    # Staatliche Bühnen und Orchester
    "semperoper", "staatsoperette", "staatsschauspiel", "kleines-haus",
    # CyberSAX nennt das Haus des Staatsschauspiels nur "Schauspielhaus".
    "schauspielhaus", "landesbuehnen",
    "deutsches-nationaltheater",  # Weimar, taucht im Terminal mit auf
    "philharmonie", "kulturpalast", "tjg", "theater-junge-generation",
    # Große Privatbühnen mit Dauerprogramm
    "boulevardtheater", "theaterkahn", "societaetstheater", "carte-blanche",
    "comoedie", "herkuleskeule",
    # Museen und Sammlungen
    "residenzschloss", "residenzschloss-dresden", "gruenes-gewoelbe",
    "kupferstich-kabinett", "gemaeldegalerie", "albertinum", "zwinger",
    "japanisches-palais", "deutsches-hygiene-museum", "hygiene-museum",
    "verkehrsmuseum", "karl-may-museum", "stadtmuseum", "militaerhistorisches",
    "slub", "landesbibliothek", "technische-sammlungen", "kunstsammlungen",
    "anna-amalia",  # Weimar, taucht im Terminal mit auf
    # Kirchen
    "frauenkirche", "kreuzkirche", "hofkirche", "kathedrale", "dom",
    "annenkirche", "martin-luther-kirche",
    # Schlösser und Burgen (fast durchweg Umland-Ausflugsziele)
    "albrechtsburg", "festung", "schloss-pillnitz", "schloss-uebigau",
    "schloss-klippenstein", "schloss-moritzburg", "schloss-wackerbarth",
    "barockschloss", "burg-stolpen", "grosssedlitz", "schloss-weesenstein",
    "schloss-schoenfeld", "kloster-altzella",
    # Große Open-Air-Bühnen
    "filmnaechte", "freilichtbuehne-junge-garde", "junge-garde", "felsenbuehne",
    "seebuehne", "amphitheater", "konzertplatz-weisser-hirsch",
    "hellerau", "messe-dresden", "rudolf-harbig-stadion",
    # Tourismus-Infrastruktur
    "touristservice", "glaeserne-manufaktur", "erlebniswelt", "yenidze",
}


def _is_big_house(venue):
    """Große Institution, die der Kulturkalender ohnehin vollständig liefert?"""
    slug = normalize.slugify(venue or "")
    if not slug:
        return False
    return any(big in slug for big in BIG_VENUE_SLUGS)


# --- Festival-Überschriften -------------------------------------------------
# Die Abschnittsüberschrift ist meistens eine Rubrik ("Musik", "Bühne"), manchmal
# aber der Name einer einzelnen Veranstaltung, deren Programm in den folgenden
# Zeilen steht. Real am 22.08.2026: unter "Klang&Kruste" standen zehn Zeilen, alle
# im Alaunpark - das ist ein Open Air mit Line-up und keine zehn Veranstaltungen.
#
# Unterschieden wird über eine ausdrückliche Liste der echten Rubriken (gemessen
# über den kompletten Bestand); alles andere gilt als Festivalname. Andersherum
# ginge es nicht - Festivalnamen sind beliebig und nicht zu erraten.
#
# Erweitern, wenn die Quelle eine neue RUBRIK einführt (der Lauf meldet jede
# unbekannte Überschrift auf der Konsole):
#   SELECT raw_category, count(*) c FROM events WHERE source='cybersax'
#     GROUP BY 1 ORDER BY c DESC;
SECTION_HEADINGS = {
    "aktionen", "buehne", "musik", "tanz-party", "vortrag-gespraech",
    "kunst-ausstellung", "fest", "fuehrungen", "kinder-familie", "treff",
    "workshops", "literatur", "film", "markt", "show", "kursstarts",
    "online", "messe",
}

# Ab so vielen Zeilen unter derselben Festival-Überschrift AM SELBEN ORT wird
# zusammengefasst. Zwei reichen: eine einzelne Zeile ist ohnehin schon ein
# Eintrag, und ihr eigener Titel ("Kunst im Schloss und Park") sagt mehr als der
# Festivalname.
MIN_GROUP_SIZE = 2

# Zusammengefasst wird bewusst NICHT über Orte hinweg: das Musikfest Erzgebirge
# listet unter einer Überschrift echte Einzelkonzerte in verschiedenen Kirchen
# der Region, und der "Tag des Offenen Denkmals" jedes Denkmal für sich. Gleiche
# Überschrift + gleicher Ort + gleicher Tag ist dagegen verlässlich EIN Termin.

# Trenner zwischen den Programmpunkten in der Beschreibung des Sammel-Eintrags.
LINEUP_SEPARATOR = " · "


def is_festival_heading(heading):
    """Überschrift ist ein Veranstaltungsname und keine Rubrik?"""
    slug = normalize.slugify(heading or "")
    return bool(slug) and slug not in SECTION_HEADINGS


def _group_category(heading, venue, slots):
    """Kategorie des Sammel-Eintrags.

    Der Festivalname allein sagt selten etwas ("Klang&Kruste", "Zaunkönig"), das
    Programm darunter dagegen schon. Deshalb: erst wie überall den Namen
    einordnen, und nur wenn dabei "sonstiges" herauskommt, die häufigste
    aussagekräftige Kategorie der Einzelzeilen nehmen.
    """
    category = normalize.classify_category(heading, heading, venue)
    if category != "sonstiges":
        return category
    counts = {}
    for slot in slots:
        if slot["category"] != "sonstiges":
            counts[slot["category"]] = counts.get(slot["category"], 0) + 1
    if not counts:
        return "sonstiges"
    # Bei Gleichstand entscheidet der Name der Kategorie, damit dieselbe
    # Tagesseite immer dieselbe Kategorie ergibt.
    return min(counts, key=lambda c: (-counts[c], c))


def _collapse_festival_groups(slots, day, source_url):
    """Erzeugt zu jeder Festival-Gruppe einen zusätzlichen Sammel-Eintrag.

    Die Einzelzeilen bleiben unangetastet in der Rückgabe: ausgeblendet werden
    sie erst in app/dedup.py, und zwar an genau dem Merkmal, das hier gesetzt
    wird - der Sammel-Eintrag trägt die Überschrift der Gruppe als Titel UND als
    raw_category. So bleibt das Line-up in der Datenbank erhalten und die
    Zusammenfassung ist umkehrbar.
    """
    groups = {}
    for slot in slots:
        heading = slot["raw_category"]
        if not is_festival_heading(heading) or not slot["venue"]:
            continue
        groups.setdefault((heading, slot["venue"]), []).append(slot)

    umbrellas = []
    for (heading, venue), members in groups.items():
        if len(members) < MIN_GROUP_SIZE:
            continue
        members = sorted(members, key=lambda s: (s["time"] or "99:99", s["title"]))
        start = members[0]["time"]
        lineup = LINEUP_SEPARATOR.join(
            f"{m['time']} {m['title']}" if m["time"] else m["title"] for m in members
        )
        umbrellas.append({
            "uid": normalize.make_event_uid(day.isoformat(), start, heading, venue),
            "source": SOURCE,
            "date": day.isoformat(),
            "time": start,
            "title": heading,
            "venue": venue,
            "category": _group_category(heading, venue, members),
            # Titel == raw_category ist das Erkennungsmerkmal für dedup.py.
            "raw_category": heading,
            "url": source_url,
            "image_url": None,
            "price_text": None,
            "description": f"Line-up: {lineup}",
            "detail_fetched_at": datetime.utcnow().isoformat(),
        })
        # Jede Zusammenfassung steht im Lauf-Protokoll: nur so faellt auf, wenn
        # die Quelle eine neue RUBRIK einfuehrt, die hier faelschlich als
        # Veranstaltungsname gilt (dann gehoert sie in SECTION_HEADINGS).
        print(f"[cybersax] {day}: '{heading}' als eine Veranstaltung "
              f"zusammengefasst ({len(members)} Zeilen, {venue})")
    return umbrellas


def _clean_title_cell(cell):
    """Gibt (Titel, Beschreibung) aus einer td3-Zelle zurück.

    Aufbau der Zelle (verifiziert): der Titel steht als nackter Text, danach ein
    geschütztes Leerzeichen, ein Info-Button und die Langfassung in einem
    aufklappbaren <div id="infoNNN">:

        Kostenlose Pflanzenausgabe (bis 14.00)&nbsp;<button ...></button>
        <div id="info1656561">Wie schon in den vergangenen zwei Jahren ...</div>

    Von 90 Zeilen eines Tages hatten 25 eine Langfassung - und zwar ausnahmslos
    in dieser Form. Wird das <div> einfach mit weggeworfen, bleibt gar keine
    Beschreibung übrig; wird es dringelassen, klebt sie im Titel. Deshalb: erst
    herausnehmen, dann den Rest als Titel lesen.
    """
    clone = base.make_soup(str(cell))

    description = None
    for info in clone.find_all("div", id=lambda v: bool(v) and v.startswith("info")):
        text = info.get_text(" ", strip=True)
        if text and description is None:
            description = text
        info.decompose()

    for junk in clone.find_all(["button", "script", "style"]):
        junk.decompose()

    text = clone.get_text(" ", strip=False)
    # Rückfallebene, falls die Quelle die Langfassung einmal ohne <div> liefert:
    # dann steht sie direkt hinter dem geschützten Leerzeichen.
    title, separator, trailing = text.partition("\xa0")
    title = " ".join(title.split())
    if description is None and separator:
        description = " ".join(trailing.split()) or None

    return title or None, description


def _parse(html, day, source_url):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt."""
    soup = base.make_soup(html)
    container = soup.find("div", class_=TERMINAL_CONTAINER_CLASS)
    if container is None:
        return []

    events = []
    raw_category = None
    for row in container.find_all("tr"):
        heading = row.find(["h3", "h4"])
        if heading is not None:
            # Abschnittsüberschrift: gilt für alle folgenden Zeilen, bis die
            # nächste kommt.
            raw_category = heading.get_text(" ", strip=True) or None
            continue

        time_cell = row.find("td", class_="td1")
        venue_cell = row.find("td", class_="td2")
        title_cell = row.find("td", class_="td3")
        if time_cell is None or title_cell is None:
            continue
        if venue_cell is None:
            # Kinoprogramm: dort steht der Filmtitel über zwei Spalten und es
            # gibt gar keinen Ort. Ohne Ort greift _is_big_house() nicht - und
            # das Kinoprogramm ist auch nicht der Zweck dieser Quelle.
            continue

        venue = venue_cell.get_text(" ", strip=True) or None
        if _is_big_house(venue):
            continue

        title, description = _clean_title_cell(title_cell)
        if not title:
            continue

        norm_time = normalize.normalize_time(time_cell.get_text(" ", strip=True))
        category = normalize.classify_category(raw_category or "", title, venue)
        uid = normalize.make_event_uid(day.isoformat(), norm_time, title, venue or "")

        events.append({
            "uid": uid,
            "source": SOURCE,
            "date": day.isoformat(),
            "time": norm_time,
            "title": title,
            "venue": venue,
            "category": category,
            "raw_category": raw_category,
            # Kein Event-Permalink vorhanden, siehe Modul-Docstring.
            "url": source_url,
            "image_url": None,
            "price_text": None,
            "description": description,
            # Die Tagesliste enthält bereits alles, was die Quelle hat - es
            # gibt keine Detailseite zum Nachladen.
            "detail_fetched_at": datetime.utcnow().isoformat(),
        })
    return events + _collapse_festival_groups(events, day, source_url)


def scrape_date(day):
    """day: datetime.date. Gibt eine Liste normalisierter Event-dicts zurück."""
    url = DATE_URL_TEMPLATE.format(year=day.year, month=day.month, day=day.day)
    html = base.fetch_html(url)
    return _parse(html, day, url)


def scrape_range(start_day, end_day):
    all_events = []
    current = start_day
    while current <= end_day:
        try:
            all_events.extend(scrape_date(current))
        except Exception as exc:  # ein schlechter Tag soll nicht den Lauf stoppen
            print(f"[cybersax] Fehler beim Laden von {current}: {exc}")
        time.sleep(REQUEST_DELAY_SECONDS)
        current += timedelta(days=1)
    return all_events

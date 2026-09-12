#!/usr/bin/env python3
"""Venue-Anreicherung ueber die Adressseiten von cybersax.de (Paket P5u).

WOFUER. 74 der 726 adressierbaren Venues sind "wirklich karg": kein Cover,
keine Beschreibung, genau ein anstehendes Event, und auch das ohne Bild und
ohne Text. P5t hat gemessen (voller Tages-Zensus, nicht Stichprobe), dass
tools/enrich_venues.py fuer diese 74 strukturell nichts liefern kann: alle 74
stammen ausschliesslich aus der Quelle `cybersax`, und dieser Scraper nimmt
laut app/scrapers/cybersax.py ausdruecklich nur auf, was der Kulturkalender
NICHT fuehrt. Ohne Kulturkalender-Venue-Seite greift der dortige Weg
"Tagesseite -> KK-Venue-Seite -> Homepage" nicht. 0 von 74.

Dieses Werkzeug geht denselben Weg ueber die Adressseiten der Quelle selbst.

GEGEN ECHTE SEITEN VERIFIZIERT (nicht aus einem Docstring uebernommen - der
Docstring von tools/enrich_venues.py behauptet ein Roh-HTML-Cache, den es nie
geschrieben hat):

  1. TAGESSEITE -> ADRESSSEITE. In der Tagestabelle traegt die Ortszelle
     (td.td2) einen Link auf /terminal/adressen/address/<ort>/. Gemessen am
     13.09.2026: 99 von 140 Ortszellen haben so einen Link, der Rest gar
     keinen. Eine Tagesseite liefert also viele Adresslinks auf einmal -
     deshalb wird hier geerntet und nicht je Venue geraten.

  2. ADRESSSEITE -> HOMEPAGE. Der Inhaltsblock ist <div class="user-cybersax">.
     Aufbau (an 13 Seiten geprueft): <h2> Name, danach ein optionaler
     Freitext-<p> ueber das Haus, danach bis zu vier <div class="col-3"> mit
     <h3>-Ueberschriften "Adresse", "Kontakt", "Oeffnungszeiten", "Anfahrt".
     Die Homepage steht als "Web: <a>" im Kontakt-Block - NICHT als einziger
     auswaertiger Link der Seite. Auswaertige Links hat jede Adressseite auch
     ohne Venue-Bezug: die Social-Buttons von cybersax selbst, eine feste
     Reihe bezahlter Werbelinks (motel-one.com, flyer-druck-muenchen.de,
     kunzmanns.de, mvz-marienplatz.de) sowie Google-Maps- und VVO-Links aus
     dem Anfahrt-Block. "Nimm den einzigen auswaertigen Link" haette also auf
     jeder einzelnen Seite ein Werbebanner als Haus-Homepage eingetragen.
     Gelesen wird deshalb ausschliesslich der Kontakt-Block.

  3. HOMEPAGE -> METADATEN. Wie in tools/enrich_venues.py, Schritt 3, und mit
     denselben Funktionen (extract_meta/fetch_meta werden importiert, nicht
     nachgebaut).

WAS DIE ADRESSSEITEN NICHT HABEN: ein Bild. In <div class="user-cybersax">
steht kein einziges <img>. Ein Cover kann also nur vom og:image der
Haus-Homepage kommen - und genau das ist `cover_source = 'homepage'`. Ein
cybersax-eigenes Cover gibt es nicht und wird darum auch nicht behauptet.

STRENGER ALS tools/enrich_venues.py an zwei Stellen, beide absichtlich:

  * homepage_url wird nur gespeichert, wenn die Seite auch wirklich mit 200
    und HTML antwortet. app/templates/venue.html zeigt den "Homepage"-Knopf
    allein an homepage_root - eine gespeicherte tote URL waere ein toter
    Knopf. Ein nicht erreichbares Haus bekommt lieber gar keinen Knopf.
  * og:image wird vor dem Speichern abgeklopft (Status, Content-Type, Groesse,
    Bildmasse aus dem Dateikopf) und bei Logo-/Favicon-Verdacht verworfen.
    Grund: tools/og_image_audit.py hat fuer P4c gemessen, dass von 34
    og:image-Treffern nur 13 als Cover taugten.

BESCHREIBUNGEN. Es wird ausschliesslich gespeichert, was wirklich geholt
wurde: die meta-description der Haus-Homepage, sonst der Freitext der
cybersax-Adressseite, sonst NICHTS. Kein Satz aus Weltwissen, keine Ableitung
aus dem Venue-Namen. Welche der beiden Quellen es war, steht je Datensatz als
`description_source` im Cache.

KIND wird hier NICHT geschrieben. Siehe tools/curate_kind_p5t.py: kind wird
kuratiert, nicht geraten.

CACHE. data/venue_cache/cybersax_*.json - bewusst eigene Dateien.
enrichment.json bleibt unberuehrt, dort stehen diese 74 als 'kein_kk_link'
und tools/enrich_venues.py ueberspringt jeden Schluessel, der schon drin ist.

Tempo: base.REQUEST_DELAY_SECONDS (1,2 s) zwischen allen Requests, auch den
auswaertigen.

Aufruf:
    ../.venv/bin/python tools/enrich_venues_cybersax.py <db> [--apply]
    ../.venv/bin/python tools/enrich_venues_cybersax.py <db> --ids=657,667
    ../.venv/bin/python tools/enrich_venues_cybersax.py <db> --limit=10
    (ohne --apply: nur Bericht, nichts geschrieben)
"""
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlsplit

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scrapers import base  # noqa: E402
from tools.enrich_venues import (  # noqa: E402
    MAX_DESCRIPTION, _clean, _sleep, fetch_meta,
)

CS_HOST = "cybersax.de"
CS_DAY_URL = "https://www.cybersax.de/terminal/day/{year}/{month}/{day}/"
ADDRESS_PATH = "/terminal/adressen/address/"

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "venue_cache"
LINKS_CACHE = CACHE_DIR / "cybersax_address_urls.json"
RESULTS_CACHE = CACHE_DIR / "cybersax_enrichment.json"

# Der Inhaltsblock einer Adressseite. Alles ausserhalb (Kopf, Sidebar,
# Werbeleiste, Fuss) gehoert der Quelle, nicht der Venue.
CONTENT_CLASS = "user-cybersax"

# Ueberschrift des Spaltenblocks, in dem "Web:" steht.
CONTACT_HEADING = "kontakt"

_SOCIAL_HOSTS = ("facebook.com", "instagram.com", "twitter.com", "x.com",
                 "tiktok.com", "youtube.com", "youtu.be", "soundcloud.com",
                 "bandcamp.com", "linktr.ee")

# Ziele, die zwar echte Links sind, aber keine Haus-Homepage: Ticketshops,
# Karten, Mailto-Weiterleitungen. Getrennt gezaehlt, damit der Bericht sagen
# kann, WIE die Annahme bricht, wenn sie bricht.
_NON_HOMEPAGE_HOSTS = ("reservix.de", "eventim.de", "ticketmaster.de",
                       "etix.com", "google.com", "google.de",
                       "openstreetmap.org", "vvo-online.de", "paypal.com")


# --- Schritt 1: Adresslinks aus den Tagesseiten ernten ----------------------

def parse_address_links(html, page_url):
    """{Ortsname: absolute Adressseiten-URL} aus einer cybersax-Tagesseite.

    Reine Parse-Funktion (kein Netzzugriff), damit sie im Smoke-Test gegen ein
    Fixture laufen kann. Der Ortsname ist exakt der Text, den auch
    app/scrapers/cybersax.py als `venue` uebernimmt - nur so trifft die
    Zuordnung ueber venue_aliases.
    """
    soup = base.make_soup(html)
    container = soup.find("div", class_="tx-usercybersax-pi2")
    if container is None:
        return {}
    found = {}
    for cell in container.find_all("td", class_="td2"):
        link = cell.find("a", href=True)
        if not link or ADDRESS_PATH not in link["href"]:
            continue
        name = _clean(cell.get_text(" ", strip=True))
        if name and name not in found:
            found[name] = urljoin(page_url, link["href"].strip())
    return found


def harvest_address_urls(days, cache_path):
    """Erntet die Tagesseiten der uebergebenen Tage. Cache: eigene Datei."""
    if cache_path.exists():
        return json.loads(cache_path.read_text("utf-8"))

    found = {}
    for day in days:
        year, month, dom = (int(x) for x in day.split("-"))
        url = CS_DAY_URL.format(year=year, month=month, day=dom)
        try:
            html = base.fetch_html(url)
        except Exception as exc:
            print(f"  [{day}] Fehler: {exc}")
            _sleep()
            continue
        new = parse_address_links(html, url)
        added = sum(1 for name in new if name not in found)
        found.update({k: v for k, v in new.items() if k not in found})
        print(f"  [{day}] +{added} neu (gesamt {len(found)})")
        _sleep()

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(found, ensure_ascii=False, indent=1), "utf-8")
    return found


# --- Schritt 2: Adressseite lesen ------------------------------------------

def classify_web_url(url):
    """'homepage' | 'social' | 'unbrauchbar' fuer den Link aus dem Kontaktblock.

    Eine Facebook-Seite ist als Homepage unbrauchbar (kein og:image ohne
    Login) - dieselbe Einstufung wie in tools/enrich_venues.py, Status
    'nur_social'.
    """
    host = (urlparse(url).netloc or "").lower().replace("www.", "")
    if not host:
        return "unbrauchbar"
    if any(h in host for h in _SOCIAL_HOSTS):
        return "social"
    if any(h in host for h in _NON_HOMEPAGE_HOSTS) or CS_HOST in host:
        return "unbrauchbar"
    return "homepage"


def parse_address_page(html):
    """Liest den Inhaltsblock einer cybersax-Adressseite aus.

    -> dict(name, description, web_url, sections, n_images). `sections` ist
    {Ueberschrift: Text} der col-3-Bloecke und dient nur dem Bericht -
    Postanschrift und Oeffnungszeiten haben in `venues` keine Spalte.
    """
    soup = base.make_soup(html)
    block = soup.find("div", class_=CONTENT_CLASS)
    if block is None:
        return None

    heading = block.find("h2")
    name = _clean(heading.get_text(" ", strip=True)) if heading else None

    # Freitext: die <p> im Kopfbereich, also VOR dem ersten col-3-Block und
    # ohne die Termin-Tabelle. Meist leer; wenn gefuellt, ist es eine
    # Selbstbeschreibung des Hauses.
    description = None
    head = block.find("div", class_="col-12")
    if head is not None:
        for para in head.find_all("p"):
            text = _clean(para.get_text(" ", strip=True), MAX_DESCRIPTION)
            if text:
                description = text
                break

    sections, web_url = {}, None
    for col in block.find_all("div", class_="col-3"):
        head3 = col.find("h3")
        if head3 is None:
            continue
        label = _clean(head3.get_text(" ", strip=True)) or ""
        body = col.get_text(" ", strip=True)
        if body.startswith(label):
            body = body[len(label):]
        sections[label] = _clean(body) or ""
        if label.lower() != CONTACT_HEADING:
            continue
        for link in col.find_all("a", href=True):
            href = link["href"].strip()
            if href.startswith("http") and CS_HOST not in href:
                web_url = href
                break

    return {"name": name, "description": description, "web_url": web_url,
            "sections": sections, "n_images": len(block.find_all("img"))}


# --- P5v: Adresse/Telefon/Oeffnungszeiten aus denselben Adressseiten -------
#
# P5u hat `sections` nur fuer den Bericht gelesen und nirgends gespeichert
# (Zitat aus parse_address_page oben: "Postanschrift und Oeffnungszeiten
# haben in `venues` keine Spalte"). Das stimmt jetzt nicht mehr, siehe
# migrations/001_schema_v2.sql.
#
# GEPRUEFT AN DEN ECHTEN 74 CACHE-EINTRAEGEN (data/venue_cache/
# cybersax_enrichment.json, Stand 12.09.2026, VOR jedem neuen Request - das
# war genau die zu pruefende Annahme dieses Pakets): 56/74 haben eine
# nichtleere 'Adresse', 22/74 ein 'Telefon:' im Kontakt-Block, 8/74 eine
# nichtleere 'Oeffnungszeiten'. Jede der 22/8 hat auch eine Adresse - 56 ist
# die Vereinigung, nicht die Summe. 'Anfahrt' ist bei allen Faellen nur
# Linktext ("» Stadtplan » Verkehrsverbindung") und wird nie gelesen.
_PHONE_RE = re.compile(r"Telefon:\s*(.+?)(?=\s+(?:Fax|Email|Web):|$)")


def extract_contact(sections, cs_name):
    """cs_sections + der <h2>-Seitenname -> dict(address, phone, opening_hours).

    address: Die Adressseite wiederholt den Hausnamen vor der Strasse (siehe
    CYBERSAX_ADDRESS_FIXTURE: "Testklub Teststrasse 1 01099 Dresden") - bei
    allen 56 gepruesten Faellen identisch mit dem <h2>. Der Name wird nur
    gestrichen, wenn er tatsaechlich am Anfang steht; sonst bleibt der Text
    unangetastet stehen (nichts wird erraten, lieber die Dopplung sichtbar
    als eine falsche Trennstelle).

    phone: aus dem Kontakt-Block, der auch eine Kontaktperson und Fax/Email/
    Web in derselben Zeile tragen kann (echter Fall: "Olaf Doehler Telefon:
    +49 (0) 351/3 17 46-0 Fax: ..."). Nur der Wert hinter 'Telefon:' wird
    uebernommen.

    opening_hours: unveraendert aus 'Oeffnungszeiten' - keine Struktur, kein
    Normalisieren (Bericht zu P5v: das wuerde der Quelle eine Praezision
    unterstellen, die sie nicht hat).
    """
    sections = sections or {}
    address = (sections.get("Adresse") or "").strip() or None
    if address and cs_name and address.startswith(cs_name):
        address = address[len(cs_name):].strip() or None

    phone = None
    kontakt = (sections.get("Kontakt") or "").strip()
    if kontakt:
        match = _PHONE_RE.search(kontakt)
        if match:
            phone = match.group(1).strip() or None

    opening_hours = (sections.get("Öffnungszeiten") or "").strip() or None

    return {"address": address, "phone": phone, "opening_hours": opening_hours}


def fetch_address_page(url):
    try:
        html = base.fetch_html(url)
    except Exception as exc:
        return {"status": f"error:adresse:{type(exc).__name__}"}
    parsed = parse_address_page(html)
    if parsed is None:
        return {"status": "error:adresse:kein_inhaltsblock"}
    parsed["status"] = "ok"
    return parsed


# --- Bildpruefung ----------------------------------------------------------

# Dateinamen, die in P4c durchweg Logos, Favicons oder CMS-Standardbilder
# waren (tools/og_image_audit.py: "logo.png -> 404", "cropped-favicon-...",
# "kupa_default_meta.jpg", "icons/icon-300x300.png").
_LOGO_NAME_RE = re.compile(
    r"(logo|favicon|fav-?image|site-?icon|sprite|platzhalter|placeholder|"
    r"default[-_]?meta|standardbild|icon-\d+x\d+)", re.I)

# Unter dieser Kantenlaenge ist ein quadratisches Bild praktisch immer ein
# Logo (P4c: 298x298, 256x256, 300x300 - alle drei Logos).
MIN_SQUARE_EDGE = 500
MIN_IMAGE_BYTES = 15000

# Ab diesem Seitenverhaeltnis ist es ein Kopfstreifen der Website und kein
# Motiv - dieselbe Kategorie, die tools/og_image_audit.py fuer P4c von Hand
# aussortiert hat ("header_tile.png 1000x256 - Kopfstreifen, kein Motiv").
# In diesem Lauf betrifft es die sechs Stadtteilbibliotheken: alle sechs
# tragen dasselbe 2400x560-Banner von bibo-dresden.de (Haende mit
# aufgeschlagenem Buch vor blauer Flaeche), also weder das jeweilige Haus
# noch ueberhaupt ein Gebaeude - von Hand angesehen, siehe BILD_HANDPRUEFUNG.
MAX_ASPECT = 3.0


def _image_size(data):
    """(Breite, Hoehe) aus den ersten Bytes einer PNG/GIF/JPEG/WEBP-Datei.

    Bewusst von Hand statt mit Pillow: Pillow steht nicht in
    requirements.txt, und fuer die Frage "ist das ein 256x256-Logo?" reichen
    die Kopfdaten. Unbekanntes Format -> (None, None), das ist kein
    Ablehnungsgrund.
    """
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
            return (int.from_bytes(data[16:20], "big"),
                    int.from_bytes(data[20:24], "big"))
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return (int.from_bytes(data[6:8], "little"),
                    int.from_bytes(data[8:10], "little"))
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and data[12:16] == b"VP8X":
            return (int.from_bytes(data[24:27], "little") + 1,
                    int.from_bytes(data[27:30], "little") + 1)
        if data[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    return (int.from_bytes(data[i + 7:i + 9], "big"),
                            int.from_bytes(data[i + 5:i + 7], "big"))
                i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    except Exception:
        return None, None
    return None, None


def bild_verdikt(probe):
    """'brauchbar' oder der Ablehnungsgrund - rein aus den Kopfdaten.

    Getrennt von probe_image, damit eine geaenderte Regel auf den Cache
    angewendet werden kann, ohne ein einziges Bild neu zu holen.
    """
    url = probe.get("url") or ""
    if probe.get("http") is None:
        return probe.get("verdikt", "tot:unbekannt")
    if probe["http"] != 200:
        return f"tot:http{probe['http']}"
    ctype = probe.get("ctype") or ""
    if not ctype.startswith("image/"):
        return f"kein_bild:{ctype[:24]}"
    width, height = probe.get("width"), probe.get("height")
    size = probe.get("bytes")
    if _LOGO_NAME_RE.search(urlparse(url).path):
        return "logo:dateiname"
    if width and height and width == height and width < MIN_SQUARE_EDGE:
        return f"logo:quadratisch_{width}"
    if width and height and width / height >= MAX_ASPECT:
        return f"kopfstreifen:{width}x{height}"
    if size and size < MIN_IMAGE_BYTES:
        return f"zu_klein:{size}b"
    return "brauchbar"


def probe_image(url, read_bytes=65536):
    """Klopft ein og:image ab, ohne es ganz zu laden.

    -> dict(verdikt, http, ctype, bytes, width, height). `verdikt` ist
    'brauchbar' oder der Ablehnungsgrund. Geladen werden nur die ersten
    64 KB - genug fuer die Bildmasse aus dem Dateikopf.
    """
    out = {"url": url}
    try:
        resp = requests.get(url, headers=base.HEADERS, timeout=12, stream=True)
    except Exception as exc:
        out["verdikt"] = f"tot:{type(exc).__name__}"
        return out
    out["http"] = resp.status_code
    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    out["ctype"] = ctype
    if resp.status_code != 200 or not ctype.startswith("image/"):
        resp.close()
        out["verdikt"] = bild_verdikt(out)
        return out
    head = resp.raw.read(read_bytes, decode_content=True) or b""
    declared = resp.headers.get("content-length")
    resp.close()
    out["bytes"] = int(declared) if (declared or "").isdigit() else len(head)
    width, height = _image_size(head)
    out["width"], out["height"] = width, height

    out["verdikt"] = bild_verdikt(out)
    return out


# Handpruefung der Bilder, die probe_image durchgelassen hat: heruntergeladen
# und angesehen. Reine Dokumentation - der Code liest diese Tabelle nicht,
# sie haelt fest, WAS auf dem Bild zu sehen ist, damit die Zahl "4 Cover"
# nachvollziehbar bleibt (P4c-Lehre: von 34 og:image-Treffern taugten 13).
BILD_HANDPRUEFUNG = {
    549: "Innenaufnahme des Saals mit Glastonne und Kronleuchter, 1920x1280 - das Haus selbst",
    558: "Baumhaus-Anlage der Kulturinsel, 2067x1378 - das Haus selbst, aber 6,1 MB PNG (siehe Bericht)",
    587: "Dreiteiliges Titelbild: Grabmal, Kapelle, Friedhofstor - Motiv stimmt, zeigt aber alle drei Friedhoefe des Traegers",
    657: "Clubraum mit Discokugel und vollem Publikum, 574x301 - das Haus selbst",
}


# --- Handpruefung der Texte ------------------------------------------------
#
# JEDER Beschreibungstext muss hier stehen, sonst wird er NICHT gespeichert.
# Das ist Absicht: es geht um oeffentliche Aussagen ueber echte Dresdner
# Laeden, und ein automatisch uebernommener meta-Text ist oft gar keine
# Ortsbeschreibung (CMS-Standardtext, Stichwortliste, Nachrichtenticker).
# Ein spaeterer Lauf ueber andere Venues schreibt deshalb erst dann Texte,
# wenn jemand sie gelesen und hier eingetragen hat.
#
# venue_id -> (Quelle oder None, Begruendung)
#   'homepage_meta'        - meta-description der Haus-Homepage
#   'cybersax_adressseite' - Freitext der cybersax-Adressseite
#   None                   - geprueft und VERWORFEN, die Venue bleibt ohne Text
#
# Gepruefte Kandidaten: 23. Uebernommen: 10. Das Verhaeltnis ist der Grund
# fuer diese Tabelle.
BESCHREIBUNG_PRUEFUNG = {
    443: ("cybersax_adressseite", "'Raum+Verlag für Fotografie, Grafik und Editionen' - beschreibt den Ort"),
    459: ("homepage_meta", "beschreibt das denkmalgeschuetzte Haus, Raeume, Garten am Badesee"),
    486: ("cybersax_adressseite", "erster Absatz ist in sich abgeschlossen und beschreibt die Akademie"),
    494: (None, "Der Freitext beschreibt den STADTTEIL Buehlau, nicht die Kirche; die "
                "weiteren Absaetze der Seite sind Gemeindeleben und Grussworte. Kein "
                "Text ueber den Ort vorhanden."),
    504: ("cybersax_adressseite", "erster Absatz beschreibt die Kirche und ihre Lage, in sich abgeschlossen"),
    510: ("homepage_meta", "durch '|' getrennt und titelartig, benennt aber Ausstellungen, "
                           "Veranstaltungen und Festsaalvermietung des Hauses"),
    530: (None, "beschreibt den Quohrener Leben e.V. und das Dorfleben, nicht das Orthsche Gut"),
    538: (None, "Stichwortliste ohne Satz ('Natukundemuseum, Zoologie, Geologie, ...'), "
                "SEO-Text und kein Beschreibungstext"),
    549: (None, "Werbetext mit Sternchen-Glyphen und Handlungsaufforderung "
                "('Kontaktieren Sie uns!') - keine Ortsbeschreibung"),
    558: ("homepage_meta", "beschreibt den Freizeitpark und die Holzgestaltung vor Ort"),
    559: (None, "beschreibt die WEBSITE, nicht das Haus: 'Die Startseite des Kulturhaus "
                "Torgau. Hier erhalten Sie eine Uebersicht ueber unser Webangebot.'"),
    572: (None, "Der Freitext erzaehlt die Geschichte bis zu den gescheiterten "
                "Wiederaufbauversuchen; dass die Kirche 1994 wiedergeweiht wurde, steht "
                "erst im dritten Absatz. Allein der erste Absatz laesst die Kirche als "
                "Ruine erscheinen - inhaltlich falscher Eindruck, deshalb kein Text."),
    580: ("homepage_meta", "'Der Club mit Biergarten, Grill und Aussentresen besticht "
                           "durch Livekonzerte und Neustadtflair.'"),
    587: (None, "im Quelltext selbst mitten im Satz abgeschnitten "
                "('stadtgeschichtlich, kulturhistorisch und')"),
    601: ("homepage_meta", "beschreibt das Studienangebot der Hochschule"),
    657: ("cybersax_adressseite", "Die meta-description der Homepage ist ein "
                                  "Nachrichtenticker ('Update 07. August 2026 ...') und "
                                  "mitten im Wort abgeschnitten. Der Freitext der "
                                  "Adressseite beschreibt dagegen den Club selbst."),
    667: ("homepage_meta", "'Zum Feiern in den Keller gehen' - kurz, aber beschreibt den Ort"),
    679: (None, "Website-Text des gesamten Bibliotheksverbunds, fuer alle sechs "
                "Stadtteilbibliotheken identisch und ueber keine von ihnen"),
    680: (None, "Website-Text des Bibliotheksverbunds, wortgleich mit 679 und ueber diese Zweigstelle nichts gesagt"),
    682: (None, "Website-Text des Bibliotheksverbunds, wortgleich mit 679 und ueber diese Zweigstelle nichts gesagt"),
    683: (None, "Website-Text des Bibliotheksverbunds, wortgleich mit 679 und ueber diese Zweigstelle nichts gesagt"),
    685: (None, "Website-Text des Bibliotheksverbunds, wortgleich mit 679 und ueber diese Zweigstelle nichts gesagt"),
    688: (None, "Website-Text des Bibliotheksverbunds, wortgleich mit 679 und ueber diese Zweigstelle nichts gesagt"),
}

# venues.kind aus NEU GEHOLTEM Text - nicht aus dem Namen und nicht aus
# Weltwissen. P5t hatte diese beiden bewusst auf 'sonstiges' gelassen, weil
# der Name nichts hergab; jetzt sagt der geholte Text es direkt.
# venue_id -> (kind, woertliches Zitat der Belegstelle)
KIND_AUS_TEXT = {
    443: ("galerie", "Homepage-Titel: 'publishandprint – Ausstellungsraum bautzner69 "
                     "publish und print Raum und Verlag Dresden'"),
    580: ("club", "meta-description der Homepage: 'Der Club mit Biergarten, Grill und "
                  "Aussentresen besticht durch Livekonzerte und Neustadtflair.'"),
}


# --- Zusammenbauen ---------------------------------------------------------

def _homepage_root(homepage_url):
    """scheme://netloc - wie tools/load_enrichment.py, reine Stringzerlegung."""
    if not homepage_url:
        return None
    parts = urlsplit(homepage_url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def payload(rec, venue_id=None):
    """Cache-Datensatz -> die Spaltenwerte fuer `venues`.

    Reihenfolge des Covers: es gibt hier nur EINE Quelle (og:image der
    Haus-Homepage), und auch nur dann, wenn probe_image sie fuer brauchbar
    haelt. Die KK-zuerst-Reihenfolge aus tools/load_enrichment.py wird damit
    nicht angetastet - diese 74 haben keine KK-Seite.

    Die Beschreibung kommt NUR aus BESCHREIBUNG_PRUEFUNG. Ohne Eintrag dort
    bleibt meta_description leer, auch wenn Text da waere.
    """
    meta = rec.get("meta") or {}
    homepage_ok = rec.get("homepage_url") and meta.get("status") == "ok"

    cover = None
    if homepage_ok and rec.get("bild", {}).get("verdikt") == "brauchbar":
        cover = meta.get("og_image_url")

    texte = {"homepage_meta": meta.get("meta_description") if homepage_ok else None,
             "cybersax_adressseite": rec.get("cs_description")}
    source = (BESCHREIBUNG_PRUEFUNG.get(venue_id) or (None, ""))[0]
    description = texte.get(source) if source else None
    if source and not description:
        # Die Quelle liefert nicht mehr, was bei der Handpruefung dastand.
        source, description = None, None

    if homepage_ok:
        status = "ok"
    elif rec.get("status", "").startswith("error:"):
        status = rec["status"][:60]
    else:
        status = "not_found"

    return {
        "homepage_url": rec.get("homepage_url") if homepage_ok else None,
        "homepage_root": _homepage_root(rec.get("homepage_url")) if homepage_ok else None,
        "meta_title": meta.get("meta_title") if homepage_ok else None,
        "meta_description": description,
        "og_image_url": cover,
        "cover_source": "homepage" if cover else None,
        "meta_status": status,
        "description_source": source,
    }


def bare_venue_ids(conn):
    """Die "wirklich kargen" Venues - dieselbe Definition wie Abschnitt 4 in
    tools/venue_readiness_report.py, und zwar OHNE Filter auf meta_status
    (der hat dort eine falsche Null gedruckt, siehe dortiger Kommentar)."""
    return [r[0] for r in conn.execute(
        """SELECT v.id FROM venues v
           WHERE v.is_meeting_point = 0
             AND v.og_image_url IS NULL AND v.meta_description IS NULL
             AND (SELECT COUNT(*) FROM events e WHERE e.venue_id = v.id
                    AND e.duplicate_of IS NULL AND e.date >= date('now')) = 1
             AND NOT EXISTS (SELECT 1 FROM events e WHERE e.venue_id = v.id
                    AND e.duplicate_of IS NULL AND e.date >= date('now')
                    AND (COALESCE(e.description, '') <> ''
                         OR COALESCE(e.image_url, '') <> ''))
           ORDER BY v.id""").fetchall()]


def sweep(conn, venue_ids, results):
    """Holt alles Fehlende und fuellt `results` (wird laufend gesichert)."""
    days = [r[0] for r in conn.execute(
        """SELECT DISTINCT date FROM events
           WHERE source = 'cybersax' AND date >= date('now') ORDER BY date""")]
    print(f"Schritt 1: Adresslinks aus {len(days)} cybersax-Tagesseiten ernten ...")
    links = harvest_address_urls(days, LINKS_CACHE)
    print(f"-> {len(links)} Ortsnamen mit Adressseiten-Link.\n")

    qmarks = ",".join("?" * len(venue_ids))
    venues = conn.execute(
        f"SELECT id, slug, name, kind FROM venues WHERE id IN ({qmarks}) ORDER BY id",
        venue_ids).fetchall()

    # Rohstring -> venue_id ueber dieselbe Alias-Tabelle wie der Schreibpfad.
    alias = {r["raw_venue"]: r["venue_id"] for r in
             conn.execute("SELECT raw_venue, venue_id FROM venue_aliases")}
    by_venue = {}
    for raw, url in links.items():
        vid = alias.get(raw)
        if vid is not None:
            by_venue.setdefault(vid, url)

    matched = [v for v in venues if v["id"] in by_venue]
    print(f"Schritt 2+3: {len(venues)} Venues, davon {len(matched)} mit "
          f"Adressseiten-Link, {len(venues) - len(matched)} ohne.\n")

    for i, venue in enumerate(venues, 1):
        key = str(venue["id"])
        if key in results:
            continue
        rec = {"name": venue["name"], "kind": venue["kind"]}
        url = by_venue.get(venue["id"])
        if not url:
            rec["status"] = "kein_adresslink"
            results[key] = rec
            continue

        rec["address_url"] = url
        page = fetch_address_page(url)
        _sleep()
        rec["cs_name"] = page.get("name")
        rec["cs_description"] = page.get("description")
        rec["cs_sections"] = page.get("sections")
        rec["cs_n_images"] = page.get("n_images")
        web = page.get("web_url")
        rec["web_url"] = web
        rec["web_art"] = classify_web_url(web) if web else None

        if page.get("status") != "ok":
            rec["status"] = page["status"]
        elif not web:
            rec["status"] = "kein_web_link"
        elif rec["web_art"] == "social":
            rec["status"] = "nur_social"
        elif rec["web_art"] == "unbrauchbar":
            rec["status"] = "web_unbrauchbar"
        else:
            rec["homepage_url"] = web
            rec["meta"] = fetch_meta(web)
            _sleep()
            rec["status"] = "ok" if rec["meta"].get("status") == "ok" \
                else rec["meta"].get("status", "error:unbekannt")
            og = (rec["meta"] or {}).get("og_image_url")
            if rec["status"] == "ok" and og:
                rec["bild"] = probe_image(og)
                _sleep()

        results[key] = rec
        print(f"  [{i:3}/{len(venues)}] {venue['name'][:34]:34} "
              f"{rec['status']:22} {(web or '-')[:42]}")
        RESULTS_CACHE.write_text(
            json.dumps(results, ensure_ascii=False, indent=1), "utf-8")
    return results


def write(conn, results, apply):
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    rows = {r["id"]: r for r in conn.execute(
        "SELECT id, name FROM venues")}
    written, skipped = 0, []
    for key, rec in results.items():
        vid = int(key)
        row = rows.get(vid)
        if row is None:
            skipped.append((vid, "keine Zeile"))
            continue
        # Gegenprobe ueber den Namen: venues.id ist AUTOINCREMENT, zwischen
        # Sweep und Schreiben kann neu geseedet worden sein.
        if row["name"] != rec.get("name"):
            skipped.append((vid, f"Name weicht ab: {row['name']!r}"))
            continue
        data = payload(rec, vid)
        conn.execute(
            """UPDATE venues SET homepage_url = ?, homepage_root = ?,
                   meta_title = ?, meta_description = ?, og_image_url = ?,
                   cover_source = ?, meta_fetched_at = ?, meta_status = ?
               WHERE id = ?""",
            (data["homepage_url"], data["homepage_root"], data["meta_title"],
             data["meta_description"], data["og_image_url"],
             data["cover_source"], now, data["meta_status"], vid))
        written += 1
    for vid, why in skipped:
        print(f"  UEBERSPRUNGEN venue_id {vid}: {why}")

    # kind getrennt, damit ein Nachlauf ohne neue Belege nichts umsortiert.
    for vid, (kind, beleg) in KIND_AUS_TEXT.items():
        if str(vid) not in results:
            continue
        alt = conn.execute("SELECT kind FROM venues WHERE id = ?", (vid,)).fetchone()
        if alt is None or alt["kind"] == kind:
            continue
        print(f"  kind {vid}: {alt['kind']} -> {kind}  ({beleg})")
        conn.execute("UPDATE venues SET kind = ? WHERE id = ?", (kind, vid))

    if apply:
        conn.commit()
        print(f"\n{written} Venue-Zeilen geschrieben und committed.")
    else:
        conn.rollback()
        print(f"\n{written} Zeilen vorbereitet, nichts geschrieben (Probelauf).")


def summary(results):
    total = len(results)
    stat = Counter(r.get("status", "?") for r in results.values())
    print(f"\n=== Ergebnis ueber alle {total} Venues dieses Laufs ===")
    for key, count in stat.most_common():
        print(f"  {key:24} {count:3}/{total}")
    with_page = sum(1 for r in results.values()
                    if r.get("status") != "kein_adresslink"
                    and not str(r.get("status", "")).startswith("error:adresse"))
    with_web = sum(1 for r in results.values() if r.get("web_url"))
    homepages = sum(1 for r in results.values() if r.get("web_art") == "homepage")
    socials = sum(1 for r in results.values() if r.get("web_art") == "social")
    covers = sum(1 for r in results.values()
                 if (r.get("bild") or {}).get("verdikt") == "brauchbar")
    probed = sum(1 for r in results.values() if r.get("bild"))
    cs_desc = sum(1 for r in results.values() if r.get("cs_description"))
    hp_desc = sum(1 for r in results.values()
                  if (r.get("meta") or {}).get("meta_description"))
    print(f"\n  Adressseite vorhanden:        {with_page}/{total}")
    print(f"  Web-Link im Kontaktblock:     {with_web}/{total}")
    print(f"    davon echte Homepage:       {homepages}/{total}")
    print(f"    davon nur Social:           {socials}/{total}")
    print(f"  og:image ueberhaupt gefunden: {probed}/{total}")
    print(f"    davon als Cover brauchbar:  {covers}/{probed} "
          f"(Ausschussquote {probed - covers}/{probed})")
    for verdikt, count in Counter(
            r["bild"]["verdikt"] for r in results.values()
            if r.get("bild") and r["bild"]["verdikt"] != "brauchbar").most_common():
        print(f"      verworfen: {verdikt:24} {count}")
    print(f"  Freitext auf der Adressseite: {cs_desc}/{total}")
    print(f"  meta-description der Homepage:{hp_desc}/{total}")

    kandidaten, gespeichert, verworfen, ungeprueft = 0, 0, 0, []
    for key, rec in results.items():
        vid = int(key)
        hat_text = bool(rec.get("cs_description")
                        or (rec.get("meta") or {}).get("meta_description"))
        if not hat_text:
            continue
        kandidaten += 1
        if vid not in BESCHREIBUNG_PRUEFUNG:
            ungeprueft.append((vid, rec["name"]))
        elif payload(rec, vid)["meta_description"]:
            gespeichert += 1
        else:
            verworfen += 1
    print(f"\n  Beschreibungs-Kandidaten:     {kandidaten}")
    print(f"    handgeprueft + uebernommen: {gespeichert}/{kandidaten}")
    print(f"    handgeprueft + verworfen:   {verworfen}/{kandidaten}")
    print(f"    NICHT geprueft (verworfen): {len(ungeprueft)}/{kandidaten}")
    for vid, name in ungeprueft:
        print(f"      ungeprueft: {vid} {name} -> Eintrag in "
              "BESCHREIBUNG_PRUEFUNG fehlt, kein Text gespeichert")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    ids, limit = None, None
    for arg in sys.argv[1:]:
        if arg.startswith("--ids="):
            ids = [int(x) for x in arg.split("=", 1)[1].split(",") if x]
        elif arg.startswith("--limit="):
            limit = int(arg.split("=", 1)[1])
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)

    conn = sqlite3.connect(args[0])
    conn.row_factory = sqlite3.Row
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    venue_ids = ids if ids is not None else bare_venue_ids(conn)
    if limit:
        venue_ids = venue_ids[:limit]
    print(f"Zielmenge: {len(venue_ids)} Venues.\n")

    results = json.loads(RESULTS_CACHE.read_text("utf-8")) \
        if RESULTS_CACHE.exists() else {}
    # Bildverdikte aus den gespeicherten Kopfdaten neu bilden: eine
    # geschaerfte Regel (z.B. MAX_ASPECT) wirkt so auch auf schon geholte
    # Bilder, ohne einen einzigen neuen Request.
    for rec in results.values():
        if rec.get("bild"):
            rec["bild"]["verdikt"] = bild_verdikt(rec["bild"])
    results = sweep(conn, venue_ids, results)
    RESULTS_CACHE.write_text(json.dumps(results, ensure_ascii=False, indent=1), "utf-8")

    summary(results)
    write(conn, {k: v for k, v in results.items() if int(k) in set(venue_ids)}, apply)
    conn.close()


if __name__ == "__main__":
    main()

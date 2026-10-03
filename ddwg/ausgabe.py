"""Die Ausgabe: EINE eigenstaendige HTML-Datei (ausgabe/index.html).

Kein Server, keine Nachladerei: die Events der naechsten Wochen stehen als JSON
in der Seite, gerendert und gefiltert wird im Browser (ddwg/vorlage/index.html).
Doppelklick genuegt.

Die Oberflaeche (Zeitstrahl-Galerie und Entdecken-Karte) steckt in der Vorlage;
beim Bauen wird zusaetzlich die Schrift TeX Gyre Heros eingebettet. Wer an der
Oberflaeche baut, aendert die Vorlage - dieses Modul liefert nur die Daten
(daten()) und fuellt sie samt Schrift ein.
"""
import base64
import html as htmllib
import json
import os
import re
import shutil
from datetime import date, datetime, timedelta

from . import db, quellen, richtungen
from .orte import Orte

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUSGABE_PATH = os.environ.get("DDWG_AUSGABE", os.path.join(ROOT, "ausgabe", "index.html"))
VORLAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vorlage", "index.html")
PWA_DIR = os.path.join(os.path.dirname(VORLAGE_PATH), "pwa")
# Manifest, Service Worker und Icons fuer die installierbare/offline-faehige
# Variante (wirkt nur online ueber https, siehe ddwg/vorlage/index.html).
PWA_DATEIEN = ["manifest.webmanifest", "sw.js", "icon-192.png", "icon-512.png", "icon-180.png", "favicon-64.png", "404.html"]
FLAVOURS_PATH = os.path.join(ROOT, "orte", "flavours.json")
# Öffentliche Adresse der Seite (GitHub Pages). Link-Vorschauen brauchen absolute Adressen.
SEITE_URL = "https://trampa336.github.io/DD_was_geht/"

KATEGORIEN = {
    "musik": "Musik",
    "kultur": "Kultur",
    "demo": "Demos",
    "familie": "Familie",
    "outdoor": "Feste & Märkte",
    "sport": "Sport",
    "fuehrungen": "Führungen",
    "sonstiges": "Weiteres",
}

# Laengere Beschreibungen werden gekuerzt - die ganze steht auf der Seite der
# Quelle, und die Datei bleibt so bei rund 2 MB statt 5.
BESCHREIBUNG_MAX = 700


def _kurz(text):
    if not text or len(text) <= BESCHREIBUNG_MAX:
        return text
    return text[:BESCHREIBUNG_MAX].rsplit(" ", 1)[0] + " …"


def _web(url):
    """Nur http(s)-Adressen; javascript: o. Ä. aus einer Quelle käme sonst als Link auf die Seite."""
    return url if url and url.lower().startswith(("http://", "https://")) else None


# Allgemeines Platzhalterbild des Kulturkalenders: zählt als „kein Bild“ (dann Ortsfoto).
KK_PLATZHALTER = "kulturkalender-dresden.de/img/fallback"
_YT_GROSS = re.compile(r"(//i\.ytimg\.com/vi/[^/]+/)(maxresdefault|sddefault)\.jpg")


def _bild(url):
    """Bildadresse für die Seite: nur http(s), kein KK-Platzhalter, YouTube in 480 px statt
    1.280 px (große Bilder ließen das Scrollen am Handy stocken, gemessen 02.10.2026)."""
    url = _web(url)
    if not url or KK_PLATZHALTER in url:
        return None
    return _YT_GROSS.sub(r"\1hqdefault.jpg", url)


def flavours_laden(orte, pfad=None):
    """Flavours (voreingestellte Herz-Sets fuer den ersten Start) aus orte/flavours.json.

    Gibt {"standard": key, "liste": [{"k", "n", "orte": [slug, ...]}]} zurueck. Ein Ort
    zaehlt nur ueber seinen haupt-Flavour, "unklar" und unbekannte slugs fallen weg.
    Fehlt die Datei, gibt es keine Flavours (None)."""
    pfad = pfad or FLAVOURS_PATH
    if not os.path.exists(pfad):
        return None
    with open(pfad, encoding="utf-8") as fh:
        roh = json.load(fh)
    liste = []
    for f in roh.get("flavours", []):
        slugs = [slug for slug, z in roh.get("orte", {}).items()
                 if z.get("haupt") == f["key"] and orte.get(slug)]
        liste.append({"k": f["key"], "n": f["name"], "orte": slugs})
    return {"standard": roh.get("standard"), "liste": liste}


def daten(conn, orte, heute=None, tage=None):
    heute = heute or date.today()
    ende = (heute + timedelta(days=tage)).isoformat() if tage else None
    events = db.events(conn, heute.isoformat(), ende)
    flavours = flavours_laden(orte)
    flavour_von_ort = {slug: f["k"] for f in (flavours or {}).get("liste", []) for slug in f["orte"]}
    used = set()
    out = []
    for ev in events:
        item = {
            "u": ev["uid"], "d": ev["date"], "t": ev["time"], "ti": ev["title"],
            "o": ev["ort"], "or": ev["ort_roh"], "k": ev["category"],
            "url": _web(ev["url"]), "img": _bild(ev["image_url"]),
            "b": _kurz(ev["description"]), "p": ev["price_text"],
            "q": ev["sources"].split(","), "r": ev["region"],
            "rt": richtungen.fuer(ev["title"], ev["category"], ev["ort"],
                                  (orte.get(ev["ort"]) or {}).get("name") if ev["ort"] else ev["ort_roh"],
                                  flavour_von_ort),
        }
        if ev["laufend"]:
            item["l"] = 1
        out.append({k: v for k, v in item.items() if v not in (None, "", [])})
        if ev["ort"]:
            used.add(ev["ort"])

    flavour_orte = {slug for f in (flavours or {}).get("liste", []) for slug in f["orte"]}

    orte_out = {}
    for slug in used | set(orte.herz_orte()) | flavour_orte:
        ort = orte.get(slug)
        if not ort:
            continue
        lat, lon = ort.get("lat"), ort.get("lon")
        orte_out[slug] = {k: v for k, v in {
            "n": ort.get("name"), "h": 1 if ort.get("herz") else None,
            "w": _web(ort.get("homepage")), "a": ort.get("adresse"), "art": ort.get("art"),
            "c": _bild(ort.get("cover")),   # Foto des Orts, Ersatz fuer Termine ohne eigenes Bild
            "lat": round(lat, 5) if lat is not None else None,
            "lon": round(lon, 5) if lon is not None else None,
        }.items() if v}

    return {
        "stand": datetime.now().strftime("%d.%m.%Y, %H:%M"),
        "heute": heute.isoformat(),
        "events": out,
        "orte": orte_out,
        "kategorien": KATEGORIEN,
        "flavours": flavours,
        "richtungen": richtungen.fuer_ausgabe(),
        "quellen": {slug: quellen.name(slug) for slug in quellen.slugs()},
    }


SCHRIFT_DIR = os.path.join(os.path.dirname(VORLAGE_PATH), "schrift")


def _schrift_css():
    """@font-face-Regeln mit den TeX-Gyre-Heros-Dateien als data:-URIs."""
    def b64(datei):
        with open(os.path.join(SCHRIFT_DIR, datei), "rb") as fh:
            return base64.b64encode(fh.read()).decode("ascii")
    return (
        "@font-face{font-family:'TeX Gyre Heros';font-weight:400 500;font-display:swap;"
        "src:url(data:font/woff2;base64,%s) format('woff2')}"
        "@font-face{font-family:'TeX Gyre Heros';font-weight:600 900;font-display:swap;"
        "src:url(data:font/woff2;base64,%s) format('woff2')}"
    ) % (b64("texgyreheros-regular.woff2"), b64("texgyreheros-bold.woff2"))


def schreiben(conn=None, orte=None, pfad=None, heute=None):
    orte = orte or Orte.load()
    if conn is None:
        with db.connect() as conn:
            return schreiben(conn, orte, pfad, heute)
    d = daten(conn, orte, heute)
    payload = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    # "</script>" im Text einer Beschreibung darf den Skriptblock nicht beenden.
    payload = payload.replace("</", "<\\/")
    with open(VORLAGE_PATH, encoding="utf-8") as fh:
        html = fh.read().replace("/*__DATEN__*/null", payload)
    html = html.replace("/*__SCHRIFT__*/", _schrift_css())
    pfad = pfad or AUSGABE_PATH
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as fh:
        fh.write(html)
    for datei in PWA_DATEIEN:
        shutil.copyfile(os.path.join(PWA_DIR, datei), os.path.join(os.path.dirname(pfad), datei))
    vorschau_seiten(d, os.path.dirname(pfad))
    return pfad


# --- Vorschau-Seiten zum Teilen (seit 2026-10-03, Davids Wunsch) -------------------
# WhatsApp, Signal & Co. bauen die Link-Vorschau aus den og:-Angaben der abgerufenen
# Seite, ohne JavaScript und ohne den Teil hinter "#". Darum bekommt jeder Termin eine
# winzige eigene Seite t/<ID>.html mit Titel, Datum, Ort und Bild, die sofort auf das
# Termin-Blatt der Startseite weiterleitet. Nur per JavaScript, ohne meta refresh: dem folgen die
# Abrufdienste von WhatsApp & Co. und zeigten sonst die Vorschau der Startseite (gemerkt 03.10.). Ist ein geteilter Termin nach einem Neubau
# weg, fängt 404.html den Link ab (vorlage/pwa/404.html).
VORSCHAU_DIR = "t"
_WT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
_MON = ["Jan", "Feb", "März", "Apr", "Mai", "Juni", "Juli", "Aug", "Sept", "Okt", "Nov", "Dez"]


def _vorschau_html(ev, ort):
    e = lambda x: htmllib.escape(x or "", quote=True)
    tag = date.fromisoformat(ev["d"])
    wann = f"{_WT[tag.weekday()]} {tag.day}. {_MON[tag.month - 1]}"
    if ev.get("t") and ev["t"] != "00:00":
        wann += ", " + ev["t"]
    ortname = (ort or {}).get("n") or ev.get("or") or ""
    beschreibung = " · ".join(x for x in (wann, ortname) if x)
    bild = ev.get("img") or (ort or {}).get("c") or SEITE_URL + "icon-512.png"
    ziel = "../#t=" + "~".join([ev["u"], ev["d"], ev.get("o") or ""])
    return (
        '<!doctype html><html lang="de"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="robots" content="noindex">'
        f'<title>{e(ev["ti"])} · DD was geht</title>'
        '<meta property="og:type" content="website"><meta property="og:site_name" content="DD was geht">'
        f'<meta property="og:title" content="{e(ev["ti"])}">'
        f'<meta property="og:description" content="{e(beschreibung)}">'
        f'<meta property="og:image" content="{e(bild)}">'
        f'<meta property="og:url" content="{e(SEITE_URL + VORSCHAU_DIR + "/" + ev["u"] + ".html")}">'
        '<meta name="twitter:card" content="summary_large_image">'
        f'<script>location.replace({json.dumps(ziel)})</script>'
        f'</head><body><a href="{e(ziel)}">{e(ev["ti"])}</a></body></html>'
    )


def vorschau_seiten(d, ordner):
    """Schreibt ordner/t/<ID>.html je Termin, alte Seiten fallen vorher weg."""
    ziel = os.path.join(ordner, VORSCHAU_DIR)
    shutil.rmtree(ziel, ignore_errors=True)
    os.makedirs(ziel, exist_ok=True)
    for ev in d["events"]:
        with open(os.path.join(ziel, ev["u"] + ".html"), "w", encoding="utf-8") as fh:
            fh.write(_vorschau_html(ev, d["orte"].get(ev.get("o"))))
    return len(d["events"])

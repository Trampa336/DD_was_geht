"""Die Ausgabe: EINE eigenstaendige HTML-Datei (ausgabe/index.html).

Kein Server, keine Nachladerei: die Events der naechsten Wochen stehen als JSON
in der Seite, gerendert und gefiltert wird im Browser (ddwg/vorlage/index.html).
Doppelklick genuegt.

Diese Seite ist der Zwischenstand bis zum UI-Umbau. Wer daran baut, aendert die
Vorlage - dieses Modul liefert nur die Daten (daten()) und fuellt sie ein.
"""
import json
import os
from datetime import date, datetime, timedelta

from . import db, quellen
from .orte import Orte

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUSGABE_PATH = os.environ.get("DDWG_AUSGABE", os.path.join(ROOT, "ausgabe", "index.html"))
VORLAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vorlage", "index.html")

KATEGORIEN = {
    "musik": "Musik",
    "kultur": "Kultur",
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


def daten(conn, orte, heute=None, tage=None):
    heute = heute or date.today()
    ende = (heute + timedelta(days=tage)).isoformat() if tage else None
    events = db.events(conn, heute.isoformat(), ende)
    used = set()
    out = []
    for ev in events:
        item = {
            "u": ev["uid"], "d": ev["date"], "t": ev["time"], "ti": ev["title"],
            "o": ev["ort"], "or": ev["ort_roh"], "k": ev["category"],
            "url": ev["url"], "img": ev["image_url"],
            "b": _kurz(ev["description"]), "p": ev["price_text"],
            "q": ev["sources"].split(","), "r": ev["region"],
        }
        if ev["laufend"]:
            item["l"] = 1
        out.append({k: v for k, v in item.items() if v not in (None, "", [])})
        if ev["ort"]:
            used.add(ev["ort"])

    orte_out = {}
    for slug in used | set(orte.herz_orte()):
        ort = orte.get(slug)
        if not ort:
            continue
        orte_out[slug] = {k: v for k, v in {
            "n": ort.get("name"), "h": 1 if ort.get("herz") else None,
            "w": ort.get("homepage"), "a": ort.get("adresse"), "art": ort.get("art"),
        }.items() if v}

    return {
        "stand": datetime.now().strftime("%d.%m.%Y, %H:%M"),
        "heute": heute.isoformat(),
        "events": out,
        "orte": orte_out,
        "kategorien": KATEGORIEN,
        "quellen": {slug: quellen.name(slug) for slug in quellen.slugs()},
    }


def schreiben(conn=None, orte=None, pfad=None, heute=None):
    orte = orte or Orte.load()
    if conn is None:
        with db.connect() as conn:
            return schreiben(conn, orte, pfad, heute)
    payload = json.dumps(daten(conn, orte, heute), ensure_ascii=False, separators=(",", ":"))
    # "</script>" im Text einer Beschreibung darf den Skriptblock nicht beenden.
    payload = payload.replace("</", "<\\/")
    with open(VORLAGE_PATH, encoding="utf-8") as fh:
        html = fh.read().replace("/*__DATEN__*/null", payload)
    pfad = pfad or AUSGABE_PATH
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as fh:
        fh.write(html)
    return pfad

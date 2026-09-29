"""Scraper für die Versammlungsliste der Stadt Dresden.

Die Versammlungsbehörde veröffentlicht alle angezeigten Versammlungen der
kommenden drei Monate, täglich bis 8 Uhr aktualisiert:

    https://www.dresden.de/de/rathaus/dienstleistungen/versammlungsuebersicht.php

Die Seite lädt die Liste als JSON nach (gefunden 29.09.2026 im Browser, weil
dresden.de aus Cowork heraus gesperrt ist):

    https://www.dresden.de/data_ext/versammlungsuebersicht/Versammlungen.json
    {"Dateidatum": "2026-09-29", "Tabellenkopf": [...], "Versammlungen": [
      {"Datum": "2026-10-03", "Zeit": "13.00 - 17.00 Uhr", "Thema": "...",
       "Ort": null, "Startpunkt": "Wiener Platz", "Teilnehmer": "100",
       "Veranstalter": "Golden Riders Dresden e. V.", "Status": "beschieden"}, ...]}

Davids Entscheidungen (29.09.2026):
- Alle Versammlungen, keine Auswahl nach Veranstalter - es sind alles Demos.
  Die Liste ist politisch gemischt, sie enthält auch Konvois und Aufmärsche.
- Nur mit bekanntem Ort. Ohne Versammlungsbescheid fehlen Ort und Zeit (am
  29.09.: 22 von 37). Bei Aufzügen zählt der Startpunkt.
- Abgemeldete und verbotene Versammlungen bleiben draußen.
Streiks stehen laut Stadt nicht in der Liste.
"""
import json
import re
from datetime import date, datetime

from .. import normalize
from . import base

SOURCE = "versammlungen"
JSON_URL = "https://www.dresden.de/data_ext/versammlungsuebersicht/Versammlungen.json"
SEITE = "https://www.dresden.de/de/rathaus/dienstleistungen/versammlungsuebersicht.php"
_ZEIT_RE = re.compile(r"(\d{1,2})[.:](\d{2})")
_WEG = ("abgemeldet", "verboten")


def _zeit(text):
    """'13.00 - 17.00 Uhr' -> '13:00' (Beginn)."""
    m = _ZEIT_RE.search(text or "")
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def _sauber(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _parse(daten, start_day, end_day):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt."""
    events = []
    for v in daten.get("Versammlungen") or []:
        ort = _sauber(v.get("Startpunkt") or v.get("Ort"))
        titel = _sauber(v.get("Thema"))
        status = (v.get("Status") or "").lower()
        if not ort or not titel or any(w in status for w in _WEG):
            continue
        try:
            tag = date.fromisoformat(v.get("Datum") or "")
        except ValueError:
            continue
        if not (start_day <= tag <= end_day):
            continue
        zeit = _zeit(v.get("Zeit"))
        teile = []
        if v.get("Startpunkt"):
            teile.append(f"Aufzug, Startpunkt: {ort}.")
        if v.get("Veranstalter"):
            teile.append(f"Veranstalter/-in: {_sauber(v['Veranstalter'])}.")
        if v.get("Teilnehmer"):
            teile.append(f"Teilnehmerprognose lt. Veranstalter: {_sauber(v['Teilnehmer'])}.")
        events.append({
            "uid": normalize.make_event_uid(tag.isoformat(), zeit, titel, ort),
            "source": SOURCE,
            "date": tag.isoformat(),
            "time": zeit,
            "title": titel,
            "venue": ort,
            "category": "demo",
            "raw_category": "Versammlung",
            "url": SEITE,
            "image_url": None,
            "price_text": None,
            "description": " ".join(teile) or None,
            "detail_fetched_at": datetime.utcnow().isoformat(),
        })
    return events


def scrape_range(start_day, end_day):
    return _parse(json.loads(base.fetch_html(JSON_URL)), start_day, end_day)

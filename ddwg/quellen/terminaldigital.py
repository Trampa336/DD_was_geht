"""Scraper für terminal.digital, den linken Veranstaltungskalender für Dresden.

Ein Sammelkalender wie der Kulturkalender, gepflegt von einer selbst-
organisierten Redaktion. Das WordPress-Plugin "Events Manager" bietet einen
ICS-Feed:

    https://terminal.digital/events.ics

Gegen den echten Feed geprüft (29.09.2026, im Browser, weil die Seite aus
Cowork heraus gesperrt ist): 50 Termine - der Feed liefert immer die nächsten
50, das sind etwa drei Wochen. Zeiten mit TZID=Europe/Berlin, ohne RRULE
(Serien stehen als einzelne Termine drin).

Davids Auswahl (29.09.2026, Variante A): nur Demos, Konzerte, Küfa/Kneipe und
Film/Theater - schlank und abendtauglich. Offene Treffen, Beratung, Vorträge,
Workshops usw. bleiben draußen (gemessen: von 50 Terminen wären ~30 neu
gewesen, die meisten davon offene Treffen und Sprechstunden). Ausnahme: Erkennt
der Titel eine Demo (normalize, Stufe 0), kommt der Termin auch ohne passende
Kategorie rein.

Eigenheiten:

1. CATEGORIES trennt mit Komma, aber eine Kategorie heißt selbst "Küfa,
   Kneipe" ("CATEGORIES:Küfa, Kneipe,Offenes Treffen"). Geprüft wird deshalb
   per Stichwort im ganzen Feld, nicht per Liste.
2. LOCATION ist "Name, Straße, Stadt, ...". Manchmal steht dort nur ein Link
   (Google Maps, OpenStreetMap, sogar eine Mailadresse) oder gar nichts - dann
   bleibt der Ort leer.
3. ATTACH trägt das Bild des Termins, DESCRIPTION den ganzen Text.
"""
import html
from datetime import datetime
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

from .. import normalize
from . import base, detail_fetch

SOURCE = "terminaldigital"
CALENDAR_URL = "https://terminal.digital/events.ics"
BERLIN = ZoneInfo("Europe/Berlin")

# Stichwort in CATEGORIES -> Rohkategorie fuer normalize.classify_category.
# Nur was hier steht, kommt auf die Seite (plus Demos laut Titel).
KATEGORIEN = (
    ("demo", "kundgebung"), ("kundgebung", "kundgebung"),
    ("konzert", "konzert"),
    ("film", "film"), ("theater", "theater"),
    ("küfa", ""), ("kneipe", ""),   # Titel entscheidet ("Bar Night" -> musik)
)


def _kategorien(component):
    """CATEGORIES als ein Text, egal wie icalendar es zerlegt hat."""
    werte = component.get("CATEGORIES")
    if werte is None:
        return ""
    if not isinstance(werte, list):
        werte = [werte]
    teile = []
    for w in werte:
        cats = getattr(w, "cats", None)
        teile.extend(str(c) for c in cats) if cats is not None else teile.append(str(w))
    return ",".join(teile)


def _rohkategorie(kategorien):
    """(passt?, Rohkategorie) - siehe KATEGORIEN."""
    k = kategorien.lower()
    for stichwort, roh in KATEGORIEN:
        if stichwort in k:
            return True, roh
    return False, ""


def _ort(location):
    """'Malobeo, Kamenzer Str. 38, Dresden, ...' -> 'Malobeo'. Links zaehlen nicht."""
    name = (location or "").split(",")[0].strip()
    if not name or "://" in name or "@" in name:
        return None
    return name


def _parse_calendar(ics_bytes, start_day, end_day):
    """Reine Parse-Funktion (ohne Netzzugriff), damit sie testbar bleibt."""
    calendar = icalendar.Calendar.from_ical(ics_bytes)
    events = []
    for component in recurring_ical_events.of(calendar).between(start_day, end_day):
        titel = html.unescape(str(component.get("SUMMARY") or "")).strip()
        dt_start = component.get("DTSTART")
        if not titel or dt_start is None:
            continue
        ort = _ort(str(component.get("LOCATION") or ""))
        kategorien = _kategorien(component)
        passt, roh = _rohkategorie(kategorien)
        kategorie = normalize.classify_category(roh, titel, ort)
        if not passt and kategorie != "demo":
            continue

        wert = dt_start.dt
        if isinstance(wert, datetime):
            lokal = wert.astimezone(BERLIN) if wert.tzinfo else wert
            tag, zeit = lokal.date(), f"{lokal.hour:02d}:{lokal.minute:02d}"
        else:
            tag, zeit = wert, None

        text = html.unescape(str(component.get("DESCRIPTION") or "")).strip() or None
        bild = component.get("ATTACH")
        events.append({
            "uid": normalize.make_event_uid(tag.isoformat(), zeit, titel, ort),
            "source": SOURCE,
            "date": tag.isoformat(),
            "time": zeit,
            "title": titel,
            "venue": ort,
            "category": kategorie,
            "raw_category": kategorien or None,
            "url": str(component.get("URL") or "") or "https://terminal.digital/",
            "image_url": str(bild) if bild else None,
            "price_text": detail_fetch.price_from_text(text),
            "description": text,
            "detail_fetched_at": datetime.utcnow().isoformat(),
        })
    return events


def scrape_range(start_day, end_day):
    """Holt den Feed einmal, recurring_ical_events filtert auf den Zeitraum."""
    return _parse_calendar(base.fetch_html(CALENDAR_URL), start_day, end_day)

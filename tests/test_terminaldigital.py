"""terminal.digital ohne Netz, mit echten Einträgen aus events.ics (29.09.2026,
im Browser geholt; Beschreibungen gekürzt). Die Demo stammt aus der Einzel-
Kalenderdatei eines vergangenen Termins (…/ical/), weil im Feed gerade keine steht."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg import normalize  # noqa: E402
from ddwg.quellen import terminaldigital  # noqa: E402


def _vevent(uid, start, url, titel, beschreibung, ort, kategorie=None, bild=None):
    zeilen = ["BEGIN:VEVENT", f"UID:{uid}@terminal.digital", f"DTSTART;TZID=Europe/Berlin:{start}",
              f"URL:https://terminal.digital/events/{url}/", f"SUMMARY:{titel}", f"DESCRIPTION:{beschreibung}"]
    if bild:
        zeilen.append(f"ATTACH;FMTTYPE=image/jpeg:{bild}")
    if kategorie:
        zeilen.append(f"CATEGORIES:{kategorie}")
    zeilen += [f"LOCATION:{ort}", "END:VEVENT"]
    return zeilen


ICS = "\r\n".join(
    ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//wp-events-plugin.com//7.2.3.1//EN", "TZID:Europe/Berlin",
     "X-WR-TIMEZONE:Europe/Berlin"]
    + _vevent(9864, "20260929T160000", "open-alternative-cafe-and-anarchist-library-2026-09-29",
              "Open: alternative café and anarchist library",
              r"*English below*\n[DE]\nDienstags sind Öffnungszeiten der Bibliothek.",
              r"Malobeo\, Kamenzer Str. 38\, Dresden\, Sachsen\, 01099\, Deutschland")
    + _vevent(10090, "20260930T190000", "mittwochskuefa-3-2026-09-30", "Mittwochsküfa",
              r"Wie gewohnt jeden Mittwoch lecker Küche für alle (= Essen für wenig Geld\, vegan)",
              r"AZ Conni\, Rudolf-Leonhard-Straße 39\, Dresden\, 01097\, Deutschland", r"Küfa\, Kneipe")
    + _vevent(11475, "20261002T190000", "screaming-queens-the-riot-at-comptons-cafeteria",
              "Screaming Queens: The riot at compton's cafeteria",
              r"Dokumentarfilm\nSCREAMING QUEENS: THE RIOT\nAT COMPTON’S CAFETERIA",
              r"Kosmotique\, Martin-Luther-Straße 13\, Dresden\, Sachsen\, 01099\, Deutschland", r"Film\, Theater")
    + _vevent(11573, "20261003T190000", "vom-antisemitismus-der-keine-sein-will",
              r"Vom Antisemitismus\, der keine sein will", "Richard Schuberths im März erschienener Essayband",
              r"AZ Conni\, Rudolf-Leonhard-Straße 39\, Dresden\, 01097\, Deutschland", "Lesung")
    + _vevent(10396, "20261007T190000", "probe-des-feministischen-demo-chor-2026-10-07",
              "Probe des feministischen Demo-Chor",
              r"Du möchtest feministische Lieder in Dresden und Umgebung laut und kraftvoll auf Demos singen",
              r"FrauenBildungsHaus\, Oskarstr. 1\, Dresden\, 01219\, Deutschland", "Offenes Treffen")
    + _vevent(10217, "20261007T200000", "bunte-hilfe-beratung-2026-10-07", "Bunte Hilfe Beratung",
              "Anlaufstelle für Alle", r"Kosmotique\, Martin-Luther-Straße 13\, Dresden\, Sachsen", "Beratung")
    + _vevent(10557, "20261016T170000", "unholy-club-queer-pride-dd-bar-night-2",
              "Queer Pride Kick-Off- Treffen + Unholy Club - Queer Pride DD Bar Night",
              r"Unholy Club am 16.10.2026!\nFeste soll man feiern\, wie sie fallen",
              r"AZ Conni\, Rudolf-Leonhard-Straße 39\, Dresden\, 01097\, Deutschland",
              r"Küfa\, Kneipe,Offenes Treffen",
              bild="https://terminal.digital/wp-content/uploads/2026/02/photo_2026-02-06_18-32-25-1.avif")
    + _vevent(11563, "20261017T180000", "solikonzert-fuer-den-roten-baum-3", "Solikonzert für den Roten Baum",
              r"SKA-ALARM IM ROTEN BAUM!\nTanzschuhe schnüren und Offbeats am Start haben",
              "https://maps.app.goo.gl/TgbNRxy9V1swBiy9A", "Konzert")
    + _vevent(7864, "20250125T130000", "jugend-gegen-kuerzungen-demo-gegen-kuerzungen",
              "Jugend gegen Kürzungen: Demo gegen Kürzungen",
              "Am 25.1.25. ist es so weit! Wir wollen unsere erste größere Demo gegen Kürzungen in diesem Jahr machen.",
              r"Rathaus\, Rathausplatz\, Dresden\, 01067\, Deutschland", r"Demo\, Kundgebung")
    + ["END:VCALENDAR", ""]
).encode("utf-8")


def _events(start=date(2025, 1, 1), ende=date(2026, 11, 30)):
    return {e["title"]: e for e in terminaldigital._parse_calendar(ICS, start, ende)}


def test_nur_davids_auswahl():
    # Variante A: Demos, Konzerte, Küfa/Kneipe, Film/Theater - sonst nichts
    assert sorted(_events()) == sorted([
        "Mittwochsküfa", "Screaming Queens: The riot at compton's cafeteria",
        "Queer Pride Kick-Off- Treffen + Unholy Club - Queer Pride DD Bar Night",
        "Solikonzert für den Roten Baum", "Jugend gegen Kürzungen: Demo gegen Kürzungen",
    ])


def test_felder():
    ev = _events()
    demo = ev["Jugend gegen Kürzungen: Demo gegen Kürzungen"]
    assert (demo["date"], demo["time"], demo["venue"], demo["category"]) == ("2025-01-25", "13:00", "Rathaus", "demo")
    kuefa = ev["Mittwochsküfa"]
    assert kuefa["venue"] == "AZ Conni" and kuefa["url"].endswith("/mittwochskuefa-3-2026-09-30/")
    assert "vegan" in kuefa["description"]
    assert ev["Solikonzert für den Roten Baum"]["venue"] is None           # nur ein Karten-Link
    assert ev["Solikonzert für den Roten Baum"]["category"] == "musik"
    assert ev["Screaming Queens: The riot at compton's cafeteria"]["category"] == "kultur"
    bar = ev["Queer Pride Kick-Off- Treffen + Unholy Club - Queer Pride DD Bar Night"]
    assert bar["image_url"].endswith(".avif") and bar["time"] == "17:00"


def test_zeitraum():
    assert "Jugend gegen Kürzungen: Demo gegen Kürzungen" not in _events(start=date(2026, 9, 29))


def test_demo_chor_ist_keine_demo():
    assert normalize.classify_category("", "Probe des feministischen Demo-Chor") != "demo"

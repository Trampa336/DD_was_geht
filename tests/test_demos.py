"""Demo-Quellen ohne Netz: Omas gegen Rechts (ICS) und die Versammlungsliste
der Stadt (JSON). Echte Einträge vom 29.09.2026 (im Browser geholt,
Beschreibungen gekürzt). Ausnahmen sind im Test markiert."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg import dedup  # noqa: E402
from ddwg.quellen import omasgegenrechts, versammlungen  # noqa: E402

START, ENDE = date(2026, 9, 29), date(2026, 12, 31)


def _vevent(start, titel, url, ort, kategorie):
    return ["BEGIN:VEVENT", f"DTSTART;TZID=Europe/Berlin:{start}", f"UID:{url}@omas", f"SUMMARY:{titel}",
            r"DESCRIPTION:Wir unterstützen den Aufruf\, kommt alle!",
            f"URL:https://www.omasgegenrechts-dresden.de/index.php/termine/{url}/",
            f"LOCATION:{ort}", f"CATEGORIES:{kategorie}", "END:VEVENT"]


OMAS_ICS = "\r\n".join(
    ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//OMAS GEGEN RECHTS.DRESDEN - ECPv6.2.3.1//NONSGML v1.0//EN"]
    + _vevent("20261003T114500", "Es brennt: Menschenketten überall - auch in Dresden",
              "es-brennt-menschenketten-ueberall-auch-in-dresden",
              r"Dresden\, Schlossplatz\, Schloßplatz\, Dresden", "Demo,Mahnwache")
    + _vevent("20261008T184500", "Gruppentreffen OGR.DD", "gruppentreffen-ogr-dd-32",
              r"Dresden\, FrauenBildungsHaus\, Oskarstraße 1\, Dresden\, 01219", "Gruppentreffen")
    + _vevent("20261010T140000", "6. PRÜF-Demo in Dresden", "pruef-demo-in-dresden-6",
              r"Dresden\, Theaterplatz\, Theaterplatz\, Dresden\, 01067", "Demo")
    + _vevent("20261015T160000", "Mahnwache für Frieden – gegen Krieg und Gewalt überall",
              "mahnwache-fuer-frieden-gegen-krieg-und-gewalt-ueberall-26",
              r"Dresden\, Neumarkt Südseite\, Kleine Kirchgasse\, Dresden", "Mahnwache")
    # nachgestellt: So stand 2024 eine Demo in Erfurt im Kalender (Ort: Landtag, Erfurt)
    + _vevent("20261017T160000", "Demo in Erfurt: Demokratie schützen – JETZT!", "demo-in-erfurt",
              r"Erfurt\, Landtag\, Jürgen-Fuchs-Straße 1\, Erfurt", "Demo")
    + ["END:VCALENDAR", ""]
).encode("utf-8")

STADT = {"Dateidatum": "2026-09-29", "Versammlungen": [
    {"Datum": "2026-10-03", "Zeit": None, "Thema": "Gemeinsam für Demokratie ", "Ort": None, "Startpunkt": None,
     "Teilnehmer": "1.000", "Veranstalter": "natürliche Person", "Status": "angemeldet"},
    {"Datum": "2026-10-03", "Zeit": "13.00 - 17.00 Uhr", "Thema": "Für mehr Sichtbarkeit im Straßenverkehr",
     "Ort": None, "Startpunkt": "Wiener Platz", "Teilnehmer": "100", "Veranstalter": "Golden Riders Dresden e. V.",
     "Status": "beschieden"},
    {"Datum": "2026-10-05", "Zeit": "19.00 - 21.00 Uhr", "Thema": "Mahnwache für Frieden Dresden",
     "Ort": "Jorge-Gomondai-Platz ", "Startpunkt": None, "Teilnehmer": "50", "Veranstalter": "natürliche Person",
     "Status": "beschieden"},
    # nachgestellt: dieselbe Mahnwache eine Woche später, abgemeldet
    {"Datum": "2026-10-12", "Zeit": "19.00 - 21.00 Uhr", "Thema": "Mahnwache für Frieden Dresden",
     "Ort": "Jorge-Gomondai-Platz", "Startpunkt": None, "Teilnehmer": "50", "Veranstalter": "natürliche Person",
     "Status": "Versammlung abgemeldet"},
    # nachgestellt: die PRÜF-Demo vom 10.10., wie sie nach dem Bescheid aussähe
    {"Datum": "2026-10-10", "Zeit": "14.00 - 17.00 Uhr", "Thema": "Dresden für die Prüfung der rechtsextremen Parteien",
     "Ort": "Theaterplatz", "Startpunkt": None, "Teilnehmer": "500",
     "Veranstalter": "Prüfung Rettet Übringens Freiheit (PRÜF) - Sachsen", "Status": "beschieden"},
]}


def _omas():
    return {e["title"]: e for e in omasgegenrechts._parse_calendar(OMAS_ICS, START, ENDE)}


def _stadt():
    return versammlungen._parse(STADT, START, ENDE)


def test_omas_nur_demos_und_mahnwachen_in_dresden():
    ev = _omas()
    assert sorted(ev) == sorted(["Es brennt: Menschenketten überall - auch in Dresden", "6. PRÜF-Demo in Dresden",
                                 "Mahnwache für Frieden – gegen Krieg und Gewalt überall"])
    pruef = ev["6. PRÜF-Demo in Dresden"]
    assert (pruef["venue"], pruef["time"], pruef["category"]) == ("Theaterplatz", "14:00", "demo")
    assert ev["Es brennt: Menschenketten überall - auch in Dresden"]["venue"] == "Schlossplatz"


def test_stadt_nur_mit_ort_und_nicht_abgemeldet():
    ev = _stadt()
    assert [(e["date"], e["time"], e["venue"]) for e in ev] == [
        ("2026-10-03", "13:00", "Wiener Platz"), ("2026-10-05", "19:00", "Jorge-Gomondai-Platz"),
        ("2026-10-10", "14:00", "Theaterplatz")]
    assert all(e["category"] == "demo" for e in ev)
    assert ev[0]["description"].startswith("Aufzug, Startpunkt: Wiener Platz. Veranstalter/-in: Golden Riders")


def test_dieselbe_demo_von_omas_und_stadt():
    pruef_omas = _omas()["6. PRÜF-Demo in Dresden"]
    pruef_stadt = [e for e in _stadt() if e["venue"] == "Theaterplatz"][0]
    assert dedup.match(pruef_omas, pruef_stadt)
    mahnwache = [e for e in _stadt() if e["venue"] == "Jorge-Gomondai-Platz"][0]
    assert not dedup.match(pruef_omas, mahnwache)   # anderer Ort, anderer Tag

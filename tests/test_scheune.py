"""Scheune-Scraper ohne Netz, mit vier echten Einträgen aus shows.ics (27.09.2026)."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg.quellen import scheune  # noqa: E402

ICS = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//hacksw/handcal//NONSGML v1.0//EN", "CALSCALE:GREGORIAN",
    "BEGIN:VEVENT", "UID:test-1@scheune", "URL:https://scheune.org/show/5478/skating-polly.html?ref=ics",
    "SUMMARY:Skating Polly", "DTSTART:20260929T180000Z", "DTEND:20260929T210000Z",
    "LOCATION:scheune\\, Alaunstrasse  36-40\\, 01099 Dresden", "DESCRIPTION:Konzert\\nEU/UK Tour 2026",
    "DTSTAMP:20260927T145431Z", "END:VEVENT",
    "BEGIN:VEVENT", "UID:test-2@scheune", "URL:https://scheune.org/show/5617/ja-zum-alter.html",
    "SUMMARY:Ja zum Alter", "DTSTART:20261001T110000Z", "DTEND:20261001T150000Z",
    "LOCATION:scheune\\, Alaunstrasse  36-40\\, 01099 Dresden",
    "DESCRIPTION:Internationaler Tag der Älteren Menschen", "DTSTAMP:20260927T145431Z", "END:VEVENT",
    "BEGIN:VEVENT", "UID:test-3@scheune", "URL:https://scheune.org/show/5593/dancing-with-myself.html",
    "SUMMARY:Dancing with Myself", "DTSTART:20261003T190000Z", "DTEND:20261004T020000Z",
    "LOCATION:scheune\\, Alaunstrasse  36-40\\, 01099 Dresden",
    "DESCRIPTION:Party\\n80s Party + Pop Hits\\, 70s Disco\\, NDW", "DTSTAMP:20260927T145431Z", "END:VEVENT",
    "BEGIN:VEVENT", "UID:test-4@scheune", "URL:https://scheune.org/show/5557/10-jahre-hotel-matze.html",
    "SUMMARY:10 Jahre Hotel Matze", "DTSTART:20261103T190000Z", "DTEND:20261103T220000Z",
    "LOCATION:Kulturpalast\\, Schloßstraße 2\\, 01067 Dresden",
    "DESCRIPTION:Live Podcast\\nzu Gast: Juli Zeh", "DTSTAMP:20260927T145431Z", "END:VEVENT",
    "END:VCALENDAR", "",
]).encode("utf-8")


def _events(ende=date(2026, 11, 30)):
    return {e["title"]: e for e in scheune._parse_calendar(ICS, date(2026, 9, 27), ende)}


def test_zeit_in_berliner_ortszeit_und_zeitraum():
    ev = _events()
    assert ev["Skating Polly"]["date"] == "2026-09-29"
    assert ev["Skating Polly"]["time"] == "20:00"
    assert "10 Jahre Hotel Matze" not in _events(ende=date(2026, 10, 28))


def test_sparte_nur_bei_mehreren_zeilen():
    ev = _events()
    assert ev["Skating Polly"]["raw_category"] == "Konzert"
    assert ev["Skating Polly"]["category"] == "musik"
    assert ev["Dancing with Myself"]["raw_category"] == "Party"
    assert ev["Ja zum Alter"]["raw_category"] is None
    assert ev["Ja zum Alter"]["description"] == "Internationaler Tag der Älteren Menschen"


def test_ort_aus_location():
    ev = _events()
    assert ev["Skating Polly"]["venue"] == "Scheune"
    assert ev["10 Jahre Hotel Matze"]["venue"] == "Kulturpalast"


def test_link_ohne_anhang():
    assert _events()["Skating Polly"]["url"] == "https://scheune.org/show/5478/skating-polly.html"

"""Tante-JU- und Puschkin-Scraper ohne Netz, gekürzt aus den echten Feeds (02.10.2026)."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg.quellen import base, puschkin, tanteju  # noqa: E402

TANTEJU_ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//wp-events-plugin.com//5.99912//EN\r\n"
    "TZID:Europe/Berlin\r\nX-WR-TIMEZONE:Europe/Berlin\r\n"
    "BEGIN:VEVENT\r\nUID:744@liveclub-dresden.de\r\n"
    "DTSTART;TZID=Europe/Berlin:20261005T200000\r\nDTEND;TZID=Europe/Berlin:20261005T200000\r\n"
    "DTSTAMP:20260929T080506Z\r\nURL:https://www.liveclub-dresden.de/konzert/dame/\r\n"
    "SUMMARY:DAME (AUSVERKAUFT!)\r\n"
    "DESCRIPTION:\\n\\nDer Weg ist das Ziel 2.0 – Live 2026\\nNach dem bahnbr\r\n echenden Erfolg\\, mit tiefer Stimme.\r\n"
    "CATEGORIES:Highlights,Konzerte\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nUID:792@liveclub-dresden.de\r\n"
    "DTSTART;TZID=Europe/Berlin:20261011T200000\r\nDTEND;TZID=Europe/Berlin:20261011T200000\r\n"
    "DTSTAMP:20261001T143215Z\r\nURL:https://www.liveclub-dresden.de/konzert/sadsvit/\r\n"
    "SUMMARY:SadSvit\r\nDESCRIPTION:In diesem Herbst begibt sich SadSvit auf eine große Europatournee.\r\n"
    "CATEGORIES:Konzerte\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nUID:800@liveclub-dresden.de\r\n"
    "DTSTART;TZID=Europe/Berlin:20261115T200000\r\nDTEND;TZID=Europe/Berlin:20261115T200000\r\n"
    "DTSTAMP:20261001T143215Z\r\nURL:https://www.liveclub-dresden.de/konzert/dominik-hartz/\r\n"
    "SUMMARY:Dominik Hartz (verlegt ins Puschkin)\r\nDESCRIPTION:Text.\r\n"
    "CATEGORIES:Konzerte\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)

PUSCHKIN_ICS = (
    "BEGIN:VCALENDAR\nVERSION:2.0\nMETHOD:PUBLISH\nCALSCALE:GREGORIAN\n"
    "PRODID:-//Events Manager//1.0//EN\n"
    "BEGIN:VEVENT\nUID:0e6f920a-5d3a-406d-8f5f-d62d9b3a06f7\nDTSTART:20261008T180000Z\n"
    "DTEND:20261008T180000Z\nDTSTAMP:20261002T175940Z\nSUMMARY:Dahabflex\nLOCATION:Club Puschkin\n"
    "URL:https://www.clubpuschkin.de/events/dahabflex/\nEND:VEVENT\n"
    "BEGIN:VEVENT\nUID:a1\nDTSTART:20261016T180000Z\nDTEND:20261016T180000Z\n"
    "DTSTAMP:20261002T175940Z\nSUMMARY:VITA &#124\\; Was da los Tour 2026\nLOCATION:Club Puschkin\n"
    "URL:https://www.clubpuschkin.de/events/vita-was-da-los-tour-2026/\nEND:VEVENT\n"
    "BEGIN:VEVENT\nUID:a2\nDTSTART:20261113T170000Z\nDTEND:20261113T170000Z\n"
    "DTSTAMP:20261002T175940Z\nSUMMARY:ENKAY &#124\\; Zwischen den Stühlen Tour 2026 (hochverlegt in die Tante JU)\n"
    "LOCATION:Club Puschkin\nURL:https://www.clubpuschkin.de/events/enkay/\nEND:VEVENT\n"
    "END:VCALENDAR\n"
)


def test_verlegt():
    assert base.verlegt("Dominik Hartz (verlegt ins Puschkin)") == ("Dominik Hartz", "Puschkin")
    assert base.verlegt("ENKAY | Tour (hochverlegt in die Tante JU)") == ("ENKAY | Tour", "Tante JU")
    assert base.verlegt("Verlegt? Nein") == ("Verlegt? Nein", None)


def test_tanteju():
    ev = {e["title"]: e for e in tanteju._parse_calendar(TANTEJU_ICS, date(2026, 10, 1), date(2026, 12, 1))}
    dame = ev["DAME"]
    assert dame["date"] == "2026-10-05" and dame["time"] == "20:00" and dame["venue"] == "Tante JU"
    assert dame["price_text"] == "ausverkauft"
    assert dame["raw_category"] == "Konzert" and dame["category"] == "musik"
    assert dame["description"].startswith("Der Weg ist das Ziel 2.0")
    assert "bahnbrechenden Erfolg, mit" in dame["description"]
    assert dame["url"] == "https://www.liveclub-dresden.de/konzert/dame/"
    assert ev["SadSvit"]["date"] == "2026-10-11"
    assert ev["Dominik Hartz"]["venue"] == "Puschkin"


def test_tanteju_zeitraum():
    ev = tanteju._parse_calendar(TANTEJU_ICS, date(2026, 10, 1), date(2026, 10, 31))
    assert [e["title"] for e in ev] == ["DAME", "SadSvit"]


def test_puschkin():
    ev = {e["title"]: e for e in puschkin._parse_calendar(PUSCHKIN_ICS, date(2026, 10, 1), date(2026, 12, 1))}
    assert set(ev) == {"Dahabflex", "VITA | Was da los Tour 2026", "ENKAY | Zwischen den Stühlen Tour 2026"}
    d = ev["Dahabflex"]
    assert d["date"] == "2026-10-08" and d["time"] == "20:00" and d["venue"] == "Puschkin"
    assert d["description"] is None and d["url"] == "https://www.clubpuschkin.de/events/dahabflex/"
    enkay = ev["ENKAY | Zwischen den Stühlen Tour 2026"]
    assert enkay["venue"] == "Tante JU" and enkay["time"] == "18:00"


def test_tour_im_musikclub_ist_keine_fuehrung():
    from ddwg import normalize
    titel = "HGich.T Live + Acid Aftershow | 30 Jahre Tour"
    assert normalize.classify_category(None, titel, "Puschkin") != "fuehrungen"
    assert normalize.classify_category(None, titel, "Club Puschkin") != "fuehrungen"
    assert normalize.classify_category(None, "Irgendwas Tour", "Tante JU Liveclub") != "fuehrungen"
    assert normalize.classify_category(None, "Irgendwas Tour", "Tante JU") != "fuehrungen"
    # Gegenprobe: an einem beliebigen Ort bleibt eine Tour ohne Jahr eine Führung.
    assert normalize.classify_category(None, "Elbschlösser Tour", "Schloss Albrechtsberg") == "fuehrungen"

"""Verdacht auf doppelte Orte (ddwg/doppelorte.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg.doppelorte import titel_schluessel, verdacht  # noqa: E402


def ev(d, t, o):
    return {"date": d, "title": t, "ort": o}


def test_titel_schluessel_ignoriert_kurze_woerter_und_zusaetze():
    assert titel_schluessel("Der betrunkene Sachse (Premiere)") == "der-betrunkene-sachse"
    assert titel_schluessel("Arsen und Spitzenhäubchen – Komödie") == "arsen-und-spitzenhaeubchen"


def test_paar_braucht_zwei_treffer():
    events = [
        ev("2026-10-01", "Arsen und Spitzenhäubchen", "hoftheater"),
        ev("2026-10-01", "Arsen und Spitzenhäubchen (Komödie)", "hoppes-hoftheater"),
        ev("2026-10-02", "Krabat stirbt", "hoftheater"),
        ev("2026-10-02", "Krabat stirbt", "hoppes-hoftheater"),
        ev("2026-10-03", "Tourkonzert Band X", "beatpol"),
        ev("2026-10-03", "Tourkonzert Band X", "tante-ju"),
    ]
    assert [(a, b, n) for a, b, n, _ in verdacht(events)] == [("hoftheater", "hoppes-hoftheater", 2)]


def test_raus_orte_und_verschiedene_tage_zaehlen_nicht():
    events = [
        ev("2026-10-01", "Offenes Plenum", "a"), ev("2026-10-08", "Offenes Plenum", "b"),
        ev("2026-10-02", "Lesung Heute", "a"), ev("2026-10-02", "Lesung Heute", "theater"),
        ev("2026-10-03", "Lesung Morgen", "a"), ev("2026-10-03", "Lesung Morgen", "theater"),
    ]
    assert verdacht(events, raus={"theater"}) == []

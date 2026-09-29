"""Richtungen (ddwg/richtungen.py): Ort, Titel-Stichwort und Kategorie in einer Liste."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg.richtungen import fuer  # noqa: E402

FL = {"schauburg": "buehne", "chemiefabrik": "rock", "groovestation": "club", "zentralwerk": "buehne", "puppentheater": "familie"}


def rt(titel, kat="sonstiges", ort=None, ort_name=None):
    return fuer(titel, kat, ort, ort_name, FL)


def test_stichwort_findet_club_auch_ohne_club_ort():
    assert rt("PURE TECHNO") == ["club", "musik"]
    assert "club" in rt("Organic House Party", "musik")


def test_ort_zaehlt_nur_wenn_kategorie_passt():
    assert rt("KLEZ.E", "musik", "chemiefabrik") == ["rock", "musik"]
    assert rt("Lesung mit Autorin", "kultur", "chemiefabrik") == ["wort", "kultur"]
    assert rt("Gastspiel", "kultur", "zentralwerk") == ["buehne", "kultur"]


def test_musik_ohne_genauere_richtung():
    assert rt("Konzert", "musik") == ["musik"]


def test_fehlgriffe_bei_stichworten():
    assert rt("Lötpunkt AG Das coole Kreativlabor") == []
    assert "rock" not in rt("Offenes Atelier mit Barockmusik")
    assert "jazz" not in rt("Historisches Experiment: Es funkt!")
    assert "rock" not in rt("The Rocky Horror Show", "kultur")
    assert "buehne" in rt("The Rocky Horror Show", "kultur")


def test_kinderparty_ist_kein_club():
    assert "club" not in rt("Kinderparty im Hort")


def test_sport_mitmachen_breiter():
    assert rt("REWE Team Challenge") == ["sport"]
    assert rt("Hatha Yoga am Morgen") == ["sport"]
    assert "sport" in rt("Lauftreff Großer Garten")


def test_sport_ohne_senioren_familie_zuschauer():
    assert "sport" not in rt("Yoga für Senioren", "sport")
    assert "sport" not in rt("Kinderyoga im Park")
    assert "sport" not in rt("Eltern-Kind-Turnen", "familie")
    assert "sport" not in rt("Dynamo Dresden Heimspiel", "sport")


def test_kategorie_bereiche_ohne_richtung():
    assert rt("Mahnwache", "demo") == ["demo"]
    assert rt("Herbstmarkt", "outdoor") == ["outdoor"]
    assert rt("Kasper kommt", "sonstiges", "puppentheater") == ["familie"]


def test_film_ueber_kino_ort():
    assert rt("Sonnenallee", "kultur", None, "Filmnächte am Elbufer") == ["film", "kultur"]


def test_kino_mit_buehnen_flavour_ist_buehne():
    assert rt("Sarah Hakenberg: Mut zur Tücke", "kultur", "schauburg", "Schauburg Dresden (Kino)") == ["buehne", "kultur"]


def test_sport_am_kinder_ort_zaehlt_nicht():
    assert "sport" not in rt("Yoga mit Pat", "sport", None, "Integrative Kindertagesstätte Pat's Bunnyhouse")

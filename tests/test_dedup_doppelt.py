"""Doppelungen, die bis 2026-10-02 stehen blieben (gemessen auf der Live-Seite)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg import dedup  # noqa: E402


def ev(uid, source, title, venue, time="20:00", date="2026-10-14"):
    return {"uid": uid, "source": source, "date": date, "time": time,
            "title": title, "venue": venue, "raw_category": None}


def gruppen(*events):
    return sorted(sorted(e["uid"] for e in g) for g in dedup.cluster(list(events)))


# --- Punkt 1: dieselbe Quelle fuehrt einen Termin doppelt ------------------

def test_kulturkalender_doppelt_gleiche_zeit():
    assert gruppen(
        ev("a", "kulturkalender", "Ohrwurm & Friends", "Kleinkunstbühne Q24", "10:00"),
        ev("b", "kulturkalender", "Ohrwurm & Friends Figurentheater-Konzert", "Kleinkunstbühne Q24", "10:00"),
    ) == [["a", "b"]]


def test_doppelt_haengt_beide_gruppen_zusammen():
    # Tante JU 25.10.: zwei KK-Zeilen, jede mit eigenem Partner aus einer anderen Quelle.
    assert gruppen(
        ev("k1", "kulturkalender", "LEFTOVERS", "Tante JU"),
        ev("t", "tanteju", "Leftovers", "Tante JU"),
        ev("k2", "kulturkalender", "Leftovers Stadion Tour 2026", "Tante JU"),
        ev("c", "cybersax", "Leftovers", "Tante JU"),
    ) == [["c", "k1", "k2", "t"]]


def test_gleiche_quelle_andere_zeit_bleibt_getrennt():
    # Fuehrung um 11 und um 14 Uhr: zwei Termine.
    assert gruppen(
        ev("a", "kulturkalender", "Highlights der Gemäldegalerie", "Gemäldegalerie", "11:00"),
        ev("b", "kulturkalender", "Highlights der Gemäldegalerie", "Gemäldegalerie", "14:00"),
    ) == [["a"], ["b"]]


def test_andere_nummer_bleibt_getrennt():
    assert gruppen(
        ev("a", "kulturkalender", "Studio*Freispiel #1", "Kleines Haus"),
        ev("b", "kulturkalender", "Studio*Freispiel #2", "Kleines Haus"),
    ) == [["a"], ["b"]]


def test_nur_teilweise_gleicher_titel_bleibt_getrennt():
    # Bibliothek Gorbitz 10.10., 11 Uhr: zwei verschiedene Maerchen.
    assert gruppen(
        ev("a", "kulturkalender", "Bibliothek Gorbitz: Die drei kleinen Schweinchen", "Bibliothek Gorbitz", "11:00"),
        ev("b", "kulturkalender", "Bibliothek Gorbitz: Zaubermärchen mit dem Puppenspieler", "Bibliothek Gorbitz", "11:00"),
    ) == [["a"], ["b"]]


def test_ganztaegig_zaehlt_nicht_als_gleiche_zeit():
    assert gruppen(
        ev("a", "kulturkalender", "Herbstmarkt", "Altmarkt", "00:00"),
        ev("b", "kulturkalender", "Herbstmarkt Kinderprogramm", "Altmarkt", "00:00"),
    ) == [["a"], ["b"]]


# --- Punkt 3: Seite des Hauses, weites Zeitfenster -------------------------

def test_hausseite_weites_fenster():
    assert gruppen(
        ev("p", "puschkin", "SkullCrusher | Benefiz | Metal hilft Kids", "Puschkin", "18:00", "2026-10-03"),
        ev("r", "rauze", "20 Jahre Skullcrusher Benefiz", "Puschkin", "16:00", "2026-10-03"),
    ) == [["p", "r"]]


def test_ohne_hausseite_bleibt_enges_fenster():
    assert gruppen(
        ev("k", "kulturkalender", "SkullCrusher | Benefiz | Metal hilft Kids", "Puschkin", "18:00", "2026-10-03"),
        ev("r", "rauze", "20 Jahre Skullcrusher Benefiz", "Puschkin", "16:00", "2026-10-03"),
    ) == [["k"], ["r"]]


def test_hausseite_reihe_mit_anderem_gast_bleibt_getrennt():
    # "MODUS: Akua" / "MODUS: Anetha": Wort-Ueberdeckung 0.5 < 0.6.
    assert gruppen(
        ev("h", "sektor", "MODUS: Akua", "Sektor Evolution", "23:00"),
        ev("r", "rauze", "MODUS: Anetha", "Sektor Evolution", "21:00"),
    ) == [["h"], ["r"]]


def test_jahreszahl_ist_keine_nummer():
    from ddwg.dedup import _ZAHLEN_RE
    assert _ZAHLEN_RE.findall("Leftovers Stadion Tour 2026") == []
    assert _ZAHLEN_RE.findall("Studio*Freispiel #2") == ["2"]
    assert _ZAHLEN_RE.findall("30 Jahre HGich.T") == ["30"]
    assert _ZAHLEN_RE.findall("Raum 20255") == ["20255"]

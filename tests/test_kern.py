"""Kerntests ohne Netz: python -m pytest tests  (oder: python tests/test_kern.py)"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg import dedup, merge, normalize, pipeline  # noqa: E402
from ddwg.orte import Orte  # noqa: E402

HEUTE = date(2026, 9, 25)


def _orte():
    return Orte({
        "strasse-e": {"name": "Straße E", "aliase": ["Reithalle Straße E", "Strasse E (Reithalle, Bunker)"],
                      "region": "dresden", "herz": True},
        "meissner-dom": {"name": "Meißner Dom", "aliase": [], "region": "weiter"},
    })


def _ev(uid, source, title, venue, time="20:00", **kw):
    return dict(uid=uid, source=source, date="2026-09-26", time=time, title=title, venue=venue,
                ort_roh=venue, category=kw.pop("category", "musik"), **kw)


def test_herz_mehrere_slugs_oder_suchtext():
    from ddwg.__main__ import herz_ziele
    orte = _orte()
    assert herz_ziele(orte, ["strasse-e", "meissner-dom"]) == ["strasse-e", "meissner-dom"]
    assert herz_ziele(orte, ["strasse-e", "strasse-e"]) == ["strasse-e"]
    assert herz_ziele(orte, ["Reithalle", "Straße", "E"]) == ["strasse-e"]   # Suchtext wie bisher
    assert herz_ziele(orte, ["gibt-es-nicht"]) == []


def test_uid_stabil():
    a = normalize.make_event_uid("2026-09-26", "20:00", "Konzert", "Ostpol")
    assert a == normalize.make_event_uid("2026-09-26", "20:00", "Konzert", "Ostpol")


def test_orte_alias_und_kollaps():
    orte = _orte()
    assert orte.resolve("Reithalle Straße E") == "strasse-e"
    assert orte.resolve("Strasse E") == "strasse-e"          # Kollaps-Schluessel
    assert orte.resolve("Neuer Laden") == "neuer-laden" and orte.neu == ["neuer-laden"]
    assert orte.resolve("") is None


def test_weiter_wird_verworfen():
    rows, dropped = pipeline.listing_rows(
        [_ev("a", "kulturkalender", "Domführung", "Meißner Dom"),
         _ev("b", "rauze", "Konzert", "Reithalle Straße E")], _orte(), HEUTE)
    assert dropped == 1 and [r["ort"] for r in rows] == ["strasse-e"]


def test_merge_feldweise_nach_rang():
    group = dedup.cluster([
        _ev("1", "kulturkalender", "TOWER TRANSMISSIONS XII", "Straße E", image_url="kk.jpg"),
        _ev("2", "rauze", "Tower Transmissions XII", "Straße E", time="19:00",
            description="Line-up", price_text="VVK 20"),
    ])
    assert len(group) == 1
    ev = merge.merge(group[0])
    assert ev["title"] == "Tower Transmissions XII" and ev["time"] == "19:00"   # rauze vor KK
    assert ev["description"] == "Line-up" and ev["price_text"] == "VVK 20"
    assert ev["image_url"] == "kk.jpg" and ev["sources"] == "rauze,kulturkalender"


def test_platzhalter_ort_wird_ersetzt():
    group = dedup.cluster([
        _ev("1", "rauze", "Klang und Kruste", "Location siehe Beschreibung"),
        _ev("2", "cybersax", "Klang und Kruste", "Alaunpark"),
    ])
    assert merge.merge(group[0])["ort_roh"] == "Alaunpark"


def test_eine_quelle_je_gruppe():
    """Zwei rauze-Termine duerfen nicht ueber einen dritten Eintrag verketten."""
    groups = dedup.cluster([
        _ev("1", "rauze", "Literatur JETZT: Alles Liebe", "Zentralwerk", time="17:00"),
        _ev("2", "rauze", "Literatur JETZT: Prager Verbrechen", "Zentralwerk", time="18:30"),
        _ev("3", "cybersax", "Literatur JETZT", "Zentralwerk", time="17:30"),
    ])
    assert all(len({m["source"] for m in g}) == len(g) for g in groups)
    assert len(groups) == 2


def test_verschiedene_zeiten_bleiben_getrennt():
    groups = dedup.cluster([
        _ev("1", "rauze", "Cats & Dogs", "Ostpol", time="19:00"),
        _ev("2", "kulturkalender", "Cats & Dogs", "Ostpol", time="23:30"),
    ])
    assert len(groups) == 2


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)

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


def test_flavours_nur_haupt_und_bekannte_orte(tmp_path):
    import json
    from ddwg.ausgabe import flavours_laden
    datei = tmp_path / "flavours.json"
    datei.write_text(json.dumps({"standard": "club", "flavours": [{"key": "club", "name": "Club"}, {"key": "rock", "name": "Rock"}],
        "orte": {"strasse-e": {"haupt": "club", "neben": ["rock"]}, "meissner-dom": {"haupt": "unklar", "neben": []},
                 "gibt-es-nicht": {"haupt": "club", "neben": []}}}), encoding="utf-8")
    f = flavours_laden(_orte(), str(datei))
    assert f["standard"] == "club"
    assert [(x["k"], x["orte"]) for x in f["liste"]] == [("club", ["strasse-e"]), ("rock", [])]
    assert flavours_laden(_orte(), str(tmp_path / "fehlt.json")) is None


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


def test_fuehrungen_werden_verworfen(tmp_path):
    from ddwg import db
    orte = _orte()
    rows, dropped = pipeline.listing_rows(
        [_ev("a", "rauze", "Konzert", "Reithalle Straße E"),
         _ev("b", "kulturkalender", "Stadtführung", "Haltestelle Linie 3", time="14:00", category="fuehrungen")],
        orte, HEUTE)
    # schon beim Einlesen raus, und fuer den Treffpunkt entsteht kein neuer Ort
    assert dropped == 1 and [r["title"] for r in rows] == ["Konzert"] and orte.neu == []
    # build() verwirft auch, was erst dort Fuehrung ist (z. B. geerbt ueber den Ort)
    rows.append(dict(rows[0], uid="c", title="Domführung", time="11:00", category="fuehrungen"))
    with db.connect(str(tmp_path / "t.db")) as conn:
        db.replace_listings(conn, "test", rows)
        assert pipeline.build(conn, orte, HEUTE) == 1
        assert [e["title"] for e in db.events(conn, HEUTE.isoformat())] == ["Konzert"]


def test_details_nachladen_alle_events(tmp_path, monkeypatch):
    from ddwg import db
    monkeypatch.setattr(pipeline.base.time_module, "sleep", lambda s: None)
    kk = "https://www.kulturkalender-dresden.de/veranstaltung/"
    orte = _orte()
    evs = [_ev(str(i), "kulturkalender", f"Abend {i}", "Neuer Laden", time=f"1{i}:00", url=kk + f"e{i}") for i in range(3)]
    evs += [dict(_ev("x", "kulturkalender", "Ausstellung", "Neuer Laden", time=None, url=kk + "a"), date=d)
            for d in ("2026-09-26", "2026-09-27")]
    rows, _ = pipeline.listing_rows(evs, orte, HEUTE)
    abrufe = []

    def fetch(ev):
        abrufe.append(ev["url"])
        if ev["url"].endswith("e1"):
            return {"ok": False}
        return {"ok": True, "description": "Text von der Seite", "price_text": None, "image_url": None}

    with db.connect(str(tmp_path / "t.db")) as conn:
        db.replace_listings(conn, "kulturkalender", rows)
        pipeline.build(conn, orte, HEUTE)
        # kein Herz-Ort noetig; die Ausstellung (zwei Tage, eine Seite) nur einmal
        assert pipeline.details_nachladen(conn, orte, HEUTE, fetch=fetch) == 3
        assert sorted(abrufe) == sorted(kk + x for x in ("a", "e0", "e1", "e2"))
        assert set(db.details(conn)) == {kk + "a", kk + "e0", kk + "e2"}   # Fehlschlag nicht gemerkt
        abrufe.clear()
        assert pipeline.details_nachladen(conn, orte, HEUTE, fetch=fetch) == 0
        assert abrufe == [kk + "e1"]                                        # naechster Lauf versucht es wieder


def test_details_nachladen_bricht_ab(tmp_path, monkeypatch):
    from ddwg import db
    monkeypatch.setattr(pipeline.base.time_module, "sleep", lambda s: None)
    monkeypatch.setattr(pipeline, "DETAIL_ABBRUCH_NACH_FEHLERN", 3)
    kk = "https://www.kulturkalender-dresden.de/veranstaltung/"
    evs = [_ev(str(i), "kulturkalender", f"Abend {i}", "Neuer Laden", time=f"1{i}:00", url=kk + f"e{i}") for i in range(6)]
    orte = _orte()
    rows, _ = pipeline.listing_rows(evs, orte, HEUTE)
    abrufe = []
    with db.connect(str(tmp_path / "t.db")) as conn:
        db.replace_listings(conn, "kulturkalender", rows)
        pipeline.build(conn, orte, HEUTE)
        assert pipeline.details_nachladen(conn, orte, HEUTE, fetch=lambda ev: abrufe.append(1) or {"ok": False}) == 0
        assert len(abrufe) == 3


def test_region_gesichtete_orte():
    from ddwg import geo
    for name in ["BELANTIS Abenteuerpark", "Mittelsächsisches Theater Döbeln", "Sorbisches National-Ensemble",
                 "Toskana Therme", "Neustadthalle - Neustadt in Sachsen", "Schloss Kuckuckstein"]:
        assert geo.classify_region(name) == "weiter", name
    assert geo.classify_region("Ballsäle Coßmannsdorf") == "umland"
    assert geo.classify_region("Scheune Neustadt") == "dresden"   # Dresdner Neustadt bleibt


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

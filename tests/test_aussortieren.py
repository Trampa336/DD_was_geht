"""Aussortieren und Zuordnung (Befund 30.09.2026): Hotels, Senioren, Familie,
abgesagte und Touristen-Termine fliegen raus; Uhrzeit, Link und Preis im Merge;
keine vererbten Demos; Jazz vor Klassik."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg import aussortieren, db, dedup, merge, pipeline  # noqa: E402
from ddwg.orte import Orte  # noqa: E402
from ddwg.richtungen import fuer, fuer_ausgabe  # noqa: E402

FL = {"nickern": "familie", "blue-note": "jazz", "strasse-e": "club"}


def g(titel, kat="sonstiges", ort_slug=None, ort=None):
    return aussortieren.grund(titel, kat, ort_slug, ort, FL)


def test_hotels_und_gasthoefe_am_ortsnamen():
    assert g("Hällas", "musik", "parkhotel", {"name": "Parkhotel Dresden"}) == "Hotel/Gasthof"
    assert g("Revue", "kultur", "zg", {"name": "Zentralgasthof Weinböhla"}) == "Hotel/Gasthof"
    assert g("Konzert", "musik", "x", {"name": "Dormero Hotel Königshof Dresden"}) == "Hotel/Gasthof"
    assert g("Laibach", "musik", "strasse-e", {"name": "Straße E"}) is None


def test_ort_mit_feld_raus():
    assert g("Interkulturelle Tage", "sonstiges", "hdb",
             {"name": "Haus der Brücke", "raus": "Beratung"}) == "Ort: Beratung"


def test_senioren():
    assert g("Zeichnen & Malen für Senior:innen 1") == "Senioren"
    assert g("Sprachcafé für zugewanderte Menschen 60+") == "Senioren"
    assert g("Smartphone-Sprechstunde für Menschen Ü60") == "Senioren"
    assert g("Tag der älteren Menschen") == "Senioren"
    assert g("60 Jahre Stern-Combo Meissen", "musik") is None


def test_familie_ueber_kategorie_und_ort():
    assert g("Teenage Takeover – Jugenddisko (13-15 J.)", "familie", "ostpol") == "Familie"
    assert g("Eltern-Kind-Treff", "sonstiges", "nickern") == "Familie"
    # Familien-Ort, aber klar ein Konzert: bleibt
    assert g("Jazz im Hof", "musik", "nickern") is None


def test_abgesagt_und_touristen():
    assert g("Tahsim Durgun ABGESAGT", "kultur") == "abgesagt"
    assert g("Fällt aus - Regio Tales", "musik") == "abgesagt"
    assert g("Candlelight: Queen vs. ABBA", "musik") == "Touristen-Angebot"
    assert g("Babykonzert in Dresden-Gruna", "musik") == "Touristen-Angebot"
    assert g("Stadtabenteuer: Dresden Altstadt Edition") == "Touristen-Angebot"
    assert g("Weinbergswanderung im Oktober") == "Touristen-Angebot"
    assert g("Große sächsische 8er Weinverkostung") == "Touristen-Angebot"
    # Verschoben oder ausverkauft findet trotzdem statt
    assert g("AUSVERKAUFT! Lesung mit Frank Goldammer", "kultur") is None
    assert g("10. Churfürstliches Weinbergfest", "outdoor") is None


def test_familie_steht_nicht_im_filter():
    assert "familie" not in [b["k"] for b in fuer_ausgabe()]


def test_jazz_vor_klassik():
    assert "klassik" not in fuer("Tito Lopez Quartett", "musik", "blue-note", "Blue Note", FL)
    assert "klassik" in fuer("Streichquartett Nr. 3", "musik", None, None, FL)


def _ev(uid, source, title, venue="Ostpol", time="20:00", **kw):
    return dict(uid=uid, source=source, date="2026-10-01", time=time, title=title, venue=venue,
                ort_roh=venue, category=kw.pop("category", "musik"), **kw)


def test_uhrzeit_aus_naechster_quelle():
    group = dedup.cluster([
        _ev("1", "ostpol", "Sex Magick Wizards", time=None, url="https://www.ost-pol.de/"),
        _ev("2", "cybersax", "Sex Magick Wizards", time="20:00",
            url="https://www.cybersax.de/terminal/day/2026/10/01/"),
        _ev("3", "kulturkalender", "Sex Magick Wizards", time="20:00",
            url="https://www.kulturkalender-dresden.de/veranstaltung/sex-magick-wizards"),
    ])
    assert len(group) == 1
    ev = merge.merge(group[0])
    assert ev["title"] == "Sex Magick Wizards" and ev["time"] == "20:00"
    # Startseite und Tagesuebersicht zaehlen nicht als Link zum Termin
    assert ev["url"] == "https://www.kulturkalender-dresden.de/veranstaltung/sex-magick-wizards"


def test_link_notfalls_startseite():
    ev = merge.merge([_ev("1", "ostpol", "Queer Monday", url="https://www.ost-pol.de/")])
    assert ev["url"] == "https://www.ost-pol.de/"


def test_preis_ohne_quellenangabe():
    assert merge.preis_bereinigen("Quelle: Museen der Stadt Dresden") is None
    assert merge.preis_bereinigen("frei | Ohne Anmeldung Quelle: Bibliothek") == "frei | Ohne Anmeldung"
    assert merge.preis_bereinigen("VVK 27,-") == "VVK 27,-"
    ev = merge.merge([_ev("1", "kulturkalender", "Ausstellung", price_text="Quelle: Museen der Stadt Dresden"),
                      _ev("2", "cybersax", "Ausstellung", price_text="5 €")])
    assert ev["price_text"] == "5 €"


def test_demo_wird_nicht_vom_ort_vererbt(tmp_path):
    orte = Orte({"schlossplatz": {"name": "Schloßplatz", "aliase": ["Schloßplatz"], "region": "dresden", "art": "museum"}})
    rows, _ = pipeline.listing_rows(
        [dict(_ev("a", "versammlungen", "Menschenkette", "Schloßplatz", time="17:00"), category="demo"),
         dict(_ev("b", "kulturkalender", "Schnitzeljagd Altstadt", "Schloßplatz", time="10:00"), category="sonstiges")],
        orte, date(2026, 9, 30))
    with db.connect(str(tmp_path / "t.db")) as conn:
        db.replace_listings(conn, "test", rows)
        pipeline.build(conn, orte, date(2026, 9, 30))
        kat = {e["title"]: e["category"] for e in db.events(conn, "2026-09-30")}
    assert kat == {"Menschenkette": "demo", "Schnitzeljagd Altstadt": "sonstiges"}


def test_build_sortiert_aus(tmp_path):
    orte = Orte({
        "parkhotel": {"name": "Parkhotel Dresden", "aliase": ["Parkhotel Dresden"], "region": "dresden"},
        "strasse-e": {"name": "Straße E", "aliase": ["Straße E"], "region": "dresden"},
    })
    rows, _ = pipeline.listing_rows(
        [_ev("a", "rauze", "Hällas", "Parkhotel Dresden"),
         _ev("b", "rauze", "Laibach", "Straße E"),
         _ev("c", "rauze", "Konzert ABGESAGT", "Straße E", time="21:00")],
        orte, date(2026, 9, 30))
    with db.connect(str(tmp_path / "t.db")) as conn:
        db.replace_listings(conn, "test", rows)
        assert pipeline.build(conn, orte, date(2026, 9, 30)) == 1
        assert [e["title"] for e in db.events(conn, "2026-09-30")] == ["Laibach"]

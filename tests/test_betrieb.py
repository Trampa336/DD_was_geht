"""Betrieb: Bestand nach 30 Tagen aufräumen, kaputte Quellen erkennen (2026-11-10)."""
from datetime import date, datetime, timezone

from ddwg import db
from ddwg.__main__ import quellen_pruefen


def test_aufraeumen_loescht_nur_altes():
    with db.connect(":memory:") as conn:
        _aufraeumen_pruefen(conn)


def _aufraeumen_pruefen(conn):
    heute = date(2026, 11, 10)
    conn.execute("INSERT INTO scrape_runs (source, started_at, finished_at, ok) VALUES ('rauze', '2026-09-01T03:00:00+00:00', '2026-09-01T03:05:00+00:00', 1)")
    conn.execute("INSERT INTO scrape_runs (source, started_at, finished_at, ok) VALUES ('rauze', '2026-11-09T03:00:00+00:00', '2026-11-09T03:05:00+00:00', 1)")
    for url, wann in (("https://kk/alt", "2026-09-01T00:00:00+00:00"), ("https://kk/neu", "2026-11-01T00:00:00+00:00"),
                      ("https://kk/alt-aber-genutzt", "2026-09-01T00:00:00+00:00")):
        db.save_detail(conn, url, "Text", None, None, wann)
    db.replace_listings(conn, "kulturkalender", [
        {"source": "kulturkalender", "uid": "a", "date": "2026-09-01", "title": "Vergangen", "ort_roh": "X", "scraped_at": "2026-11-09T03:00:00+00:00", "url": "https://kk/x"},
        {"source": "kulturkalender", "uid": "b", "date": "2026-11-12", "time": "20:00", "title": "Bald", "ort_roh": "X", "scraped_at": "2026-11-09T03:00:00+00:00", "url": "https://kk/alt-aber-genutzt"},
    ])
    n = db.aufraeumen(conn, heute)
    assert n["scrape_runs"] == 1 and n["listings"] == 1 and n["details"] == 1
    assert sorted(db.details(conn)) == ["https://kk/alt-aber-genutzt", "https://kk/neu"]
    assert conn.execute("SELECT COUNT(*) FROM scrape_runs").fetchone()[0] == 1


def test_quellen_pruefen_meldet_alte_und_nie_erfolgreiche():
    jetzt = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    lauf = lambda tag, ok, error=None: {"finished_at": f"{tag}T11:00:00+00:00", "ok": ok, "error": error}
    runs = {
        "rauze": {"letzter": lauf("2026-11-10", 1), "letzter_ok": lauf("2026-11-10", 1)},
        "sektor": {"letzter": lauf("2026-11-10", 0, "0 Events"), "letzter_ok": lauf("2026-11-01", 1)},
        "ostpol": {"letzter": lauf("2026-11-10", 0, "Timeout")},
        "scheune": {"letzter": lauf("2026-11-05", 0), "letzter_ok": lauf("2026-11-04", 1)},
    }
    kaputt = quellen_pruefen(runs, jetzt)
    assert len(kaputt) == 2
    assert any(z.startswith("Sektor") and "2026-11-01" in z and "0 Events" in z for z in kaputt)
    assert any(z.startswith("Ostpol") and "nie" in z for z in kaputt)

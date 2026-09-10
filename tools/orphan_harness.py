"""P3b-1 scratch harness: orphan-gate scenarios on a synthetic multi-run DB.

Rebuilt from scratch (P3b's harness did not survive its session). Scenarios are
modelled on the states the LIVE system actually enters, see the report:
  A "steady"        - all sources healthy, all still delivering every row
  B "event dropped" - all sources healthy, 3 rows no longer delivered by ANY
                      source for the last 3 runs (cancelled/removed programme)
  C "aggregator down" - kulturkalender's latest run failed; the venue source
                      still delivers the rows it co-reports, and kulturkalender
                      also has aggregator-only rows

Usage: ../.venv/bin/python orphan_harness.py
"""
import datetime as dt
import os
import sys
import tempfile

BACKEND = "/home/admin/dd-was-geht/backend"
sys.path.insert(0, BACKEND)

TMP = tempfile.mkdtemp(prefix="orphan-scratch-")
os.environ["DB_PATH"] = os.path.join(TMP, "scratch.db")

from app import config  # noqa: E402
config.DB_PATH = os.environ["DB_PATH"]
from app import db  # noqa: E402

TODAY = dt.date.today()
NOW = dt.datetime(TODAY.year, TODAY.month, TODAY.day, 12, 0, 0)
# 6 runs, 6h apart -> comfortably past threshold_runs=3 AND MIN_CUTOFF_SPAN=12h.
RUNS = [NOW - dt.timedelta(hours=6 * i) for i in range(5, -1, -1)]

VENUE = "sektor"
AGG = "kulturkalender"


def mk(uid, date, title, venue, source):
    return {
        "uid": uid, "source": source, "date": date.isoformat(), "time": "20:00", "title": title,
        "venue": venue, "category": "musik", "raw_category": None,
        "url": f"https://example.invalid/{uid}", "image_url": None,
        "price_text": None, "description": None, "detail_fetched_at": None,
    }


def build(scenario):
    """Replays 6 scrape runs, writing scrape_runs + events + event_sources the
    way scheduler.run_scrape would, then returns the connection."""
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
    db.init_db()
    conn = db._connect()

    # 9 rows co-reported by venue+aggregator, 9 aggregator-only rows.
    shared = [(f"sh{i}", TODAY + dt.timedelta(days=3 + i)) for i in range(9)]
    aggonly = [(f"ag{i}", TODAY + dt.timedelta(days=3 + i)) for i in range(9)]

    for n, run_at in enumerate(RUNS):
        last = n == len(RUNS) - 1
        tail3 = n >= len(RUNS) - 3
        for source in (AGG, VENUE):
            ok = True
            if scenario == "aggregator down" and source == AGG and last:
                ok = False
            batch = []
            if ok:
                if source == AGG:
                    rows = shared + aggonly
                else:
                    rows = shared
                for uid, date in rows:
                    if scenario == "event dropped" and tail3 and uid in ("sh0", "sh1", "sh2"):
                        continue  # no source delivers these any more
                    batch.append(mk(uid, date, f"Konzert {uid}", "Sektor Evolution", source))
            db.record_scrape_run(
                conn, source, run_at.isoformat(),
                (run_at + dt.timedelta(minutes=2)).isoformat(),
                ok=ok, event_count=len(batch) if ok else 0,
                error=None if ok else "simulierter Ausfall",
            )
            if batch:
                _upsert_at(conn, batch, run_at)
    conn.commit()
    return conn


def _upsert_at(conn, events, when):
    """db.upsert_events with a controllable clock (it stamps datetime.utcnow)."""
    import app.db as m
    real = m.datetime

    class Clock(real):
        @classmethod
        def utcnow(cls):
            return when
    m.datetime = Clock
    try:
        m.upsert_events(conn, events)
    finally:
        m.datetime = real


def counts(conn, fn):
    res = fn(conn, TODAY.isoformat())
    return sum(len(v) for v in res.values()), {k: len(v) for k, v in res.items()}


if __name__ == "__main__":
    from app.db import find_orphaned_events as new_gate
    import importlib
    old = importlib.import_module("legacy_gate").find_orphaned_events_legacy
    vac = importlib.import_module("legacy_gate").find_orphaned_events_vacuous

    print(f"{'scenario':18} {'old':>5} {'new':>5} {'new(vacuous)':>13}")
    for sc in ("steady", "event dropped", "aggregator down"):
        conn = build(sc)
        o, od = counts(conn, old)
        n, nd = counts(conn, new_gate)
        v, vd = counts(conn, vac)
        print(f"{sc:18} {o:>5} {n:>5} {v:>13}")
        print(f"{'':18} old={od}")
        print(f"{'':18} new={nd}")
        print(f"{'':18} vacuous={vd}")
        # row counts must be untouched by a scrape run's expire step
        before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        db.expire_orphaned_events(conn, TODAY.isoformat(), dry_run=False)
        after = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        verdict = "unchanged" if before == after else f"DELETED {before - after}"
        print(f"{'':20} expire_orphaned_events(dry_run=False): rows {before} -> {after} ({verdict})")
        conn.close()

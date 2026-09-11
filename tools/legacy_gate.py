"""Verbatim copy of find_orphaned_events as it stood at 607baf6, so the harness
can measure old-vs-new on the same synthetic DB."""
from app import config, db


def find_orphaned_events_legacy(conn, today, threshold_runs=3):
    result = {}
    for source in config.SOURCES:
        latest = db._last_run(conn, source)
        if not latest or not latest["ok"]:
            continue
        cutoff = db._successful_run_cutoff(conn, source, threshold_runs)
        if cutoff is None:
            continue
        rows = conn.execute(
            """SELECT uid, title, date, time, raw_venue AS venue, last_seen FROM events
               WHERE source = ? AND date >= ? AND last_seen < ?
               ORDER BY date, time""",
            (source, today, cutoff),
        ).fetchall()
        if rows:
            result[source] = [dict(r) for r in rows]
    return result


def find_orphaned_events_vacuous(conn, today, threshold_runs=3):
    """The new gate WITHOUT non-vacuity guard 2 - i.e. a row whose every source
    is currently unhealthy counts as orphaned. This is the reading that produced
    P3b's 9-vs-0 'aggregator down' delta; measured here only for the report."""
    healthy = db._healthy_sources(conn, threshold_runs)
    rows = conn.execute(
        """SELECT e.uid, e.title, e.date, e.time, e.raw_venue AS venue, e.last_seen,
                  s.source AS es_source, s.last_seen AS es_last_seen
             FROM events e JOIN event_sources s ON s.event_uid = e.uid
            WHERE e.date >= ? ORDER BY e.date, e.time, e.uid""", (today,)).fetchall()
    per = {}
    for r in rows:
        per.setdefault(r["uid"], {"row": r, "src": {}})["src"][r["es_source"]] = r["es_last_seen"]
    out = {}
    for uid, e in per.items():
        judging = {s: ls for s, ls in e["src"].items() if s in healthy}
        if not all(ls < healthy[s] for s, ls in judging.items()):
            continue
        out.setdefault("+".join(sorted(e["src"])), []).append(dict(e["row"]))
    return out

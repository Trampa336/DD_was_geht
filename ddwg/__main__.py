"""Kommandozeile.

    python -m ddwg scrape [--tage 31] [--quelle rauze ...] [--ohne-details]
    python -m ddwg build            events neu bauen + ausgabe/index.html schreiben
    python -m ddwg herz <ort>       Ort als Herz-Ort markieren (--weg: entfernen)
    python -m ddwg herz <slug> ...  mehrere Orte auf einmal (exakte slugs)
    python -m ddwg herz --liste     alle Herz-Orte
    python -m ddwg orte <suche>     Orte suchen (slug, Name, Alias)
    python -m ddwg status           letzte Laeufe je Quelle, Bestand, neue Orte
"""
import argparse
import logging
import sys
from collections import Counter
from datetime import date

from . import ausgabe, db, pipeline, quellen
from .orte import Orte


def cmd_scrape(args):
    orte = Orte.load()
    with db.connect() as conn:
        n = pipeline.scrape(tage=args.tage, nur=args.quelle, details=not args.ohne_details,
                            orte=orte, conn=conn)
        pfad = ausgabe.schreiben(conn, orte)
    print(f"{n} Events. Ausgabe: {pfad}")
    if orte.neu:
        print(f"{len(orte.neu)} neue Orte in orte/orte.json (Feld 'erstmals').")
    _status_kurz()


def cmd_build(args):
    orte = Orte.load()
    with db.connect() as conn:
        n = pipeline.build(conn, orte)
        pfad = ausgabe.schreiben(conn, orte)
    print(f"{n} Events. Ausgabe: {pfad}")


def _finde_ort(orte, text):
    hits = orte.suche(text)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        print(f"Kein Ort passt zu '{text}'.")
    else:
        print(f"'{text}' ist mehrdeutig - bitte den slug nehmen:")
        for slug in hits[:30]:
            print(f"  {slug:40} {orte[slug].get('name')}")
    return None


def herz_ziele(orte, woerter):
    """Welche Orte meint 'herz'? Sind alle Woerter exakte slugs, sind es mehrere
    Orte (so kopiert es die Seite: 'herz ostpol scheune'). Sonst ist es ein
    Suchtext wie bisher ('herz straße e')."""
    if len(woerter) > 1 and all(w in orte.by_slug for w in woerter):
        return list(dict.fromkeys(woerter))
    slug = _finde_ort(orte, " ".join(woerter))
    return [slug] if slug else []


def cmd_herz(args):
    orte = Orte.load()
    if args.liste or not args.ort:
        for slug in orte.herz_orte():
            print(f"  ♥ {slug:40} {orte[slug].get('name')}")
        return
    ziele = herz_ziele(orte, args.ort)
    if not ziele:
        sys.exit(1)
    for slug in ziele:
        orte.set_herz(slug, an=not args.weg)
        print(("Herz entfernt: " if args.weg else "♥ Herz gesetzt: ") + f"{slug} ({orte[slug].get('name')})")
    orte.save()
    print("Danach 'python -m ddwg build', damit die Ausgabe es zeigt.")


def cmd_orte(args):
    orte = Orte.load()
    with db.connect() as conn:
        counts = Counter(r["ort"] for r in conn.execute("SELECT ort FROM events"))
    for slug in orte.suche(" ".join(args.suche)):
        ort = orte[slug]
        herz = "♥" if ort.get("herz") else " "
        print(f"{herz} {slug:40} {ort.get('name'):40} {ort.get('region', ''):8} {counts.get(slug, 0):4} Events")


def _status_kurz():
    with db.connect() as conn:
        runs = db.last_runs(conn)
    for slug in quellen.slugs():
        r = runs.get(slug, {})
        last = r.get("letzter")
        if not last:
            print(f"  {quellen.name(slug):18} noch nie gelaufen")
            continue
        mark = "ok " if last["ok"] else "FEHLER"
        extra = f" - {last['error']}" if last["error"] else ""
        print(f"  {quellen.name(slug):18} {mark} {last['finished_at'][:16]}  {last['event_count'] or 0:5} Einträge{extra}")


def cmd_status(args):
    _status_kurz()
    orte = Orte.load()
    heute = date.today().isoformat()
    with db.connect() as conn:
        n_listings = conn.execute("SELECT COUNT(*) FROM listings WHERE date >= ?", (heute,)).fetchone()[0]
        n_events = conn.execute("SELECT COUNT(*) FROM events WHERE date >= ?", (heute,)).fetchone()[0]
        n_merged = conn.execute("SELECT COUNT(*) FROM events WHERE sources LIKE '%,%'").fetchone()[0]
        cats = conn.execute("SELECT category, COUNT(*) n FROM events GROUP BY 1 ORDER BY 2 DESC").fetchall()
        herz = conn.execute(
            f"SELECT COUNT(*) FROM events WHERE ort IN ({','.join('?' * len(orte.herz_orte())) or 'NULL'})",
            orte.herz_orte()).fetchone()[0]
    print(f"\n{n_listings} Einträge -> {n_events} Events ({n_merged} aus mehreren Quellen verschmolzen).")
    print("Kategorien: " + ", ".join(f"{c['category']} {c['n']}" for c in cats))
    print(f"{len(orte)} Orte, {len(orte.herz_orte())} Herz-Orte mit {herz} Events.")
    neu = sorted((o.get("erstmals"), slug) for slug, o in orte.items() if o.get("erstmals"))
    if neu:
        print(f"{len(neu)} Orte seit dem Umzug neu dazugekommen, zuletzt: "
              + ", ".join(slug for _d, slug in neu[-8:]))


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    p = argparse.ArgumentParser(prog="python -m ddwg", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scrape", help="Quellen holen, Events bauen, Ausgabe schreiben")
    s.add_argument("--tage", type=int, default=pipeline.TAGE_VORAUS)
    s.add_argument("--quelle", nargs="*", choices=quellen.slugs())
    s.add_argument("--ohne-details", action="store_true")
    s.set_defaults(func=cmd_scrape)

    b = sub.add_parser("build", help="Events neu bauen und Ausgabe schreiben (ohne Netz)")
    b.set_defaults(func=cmd_build)

    h = sub.add_parser("herz", help="Herz-Orte setzen, entfernen, auflisten")
    h.add_argument("ort", nargs="*")
    h.add_argument("--weg", action="store_true")
    h.add_argument("--liste", action="store_true")
    h.set_defaults(func=cmd_herz)

    o = sub.add_parser("orte", help="Orte suchen")
    o.add_argument("suche", nargs="+")
    o.set_defaults(func=cmd_orte)

    st = sub.add_parser("status", help="Zustand der Quellen und des Bestands")
    st.set_defaults(func=cmd_status)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

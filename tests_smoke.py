"""Schneller Selbsttest ohne Netzwerk: normalize, db, scoring.
Aufruf: python3 tests_smoke.py
"""
import json
import os
import re
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from app import config, db, normalize, registry, scoring  # noqa: E402


def check(label, cond):
    status = "OK " if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        raise SystemExit(1)


# --- normalize ---
check("slugify Umlaute", normalize.slugify("Für dich – Öffnungszeiten") == "fuer-dich-oeffnungszeiten")
check("classify_category raw match", normalize.classify_category("Konzert", "Irgendwas") == "musik")
check("classify_category keyword fallback", normalize.classify_category("", "Theaterabend im Schloss") == "kultur")
check("classify_category unknown -> sonstiges", normalize.classify_category("", "Zufälliges Ereignis") == "sonstiges")

# --- Fuehrungen vs. Feste & Maerkte ---------------------------------------
# Der Schnitt zwischen den beiden Buckets ist der Grund, aus dem es
# "fuehrungen" ueberhaupt gibt: "outdoor" bestand zu ~92% aus Fuehrungen, die
# damit den Newsletter fuellten. Beide Richtungen werden geprueft, weil ein
# falsch einsortierter Schluessel hier still durchrutscht - "fuehrungen" steht
# in EXCLUDED_CATEGORIES, ein Ausrutscher nach dort verschwindet also aus dem
# Digest, statt aufzufallen.
check("Stadtfuehrung -> fuehrungen",
      normalize.classify_category("", "Stadtführung durch die Neustadt") == "fuehrungen")
check("Rundgang -> fuehrungen",
      normalize.classify_category("", "Historischer Rundgang Altstadt") == "fuehrungen")
check("Elbdampfer -> fuehrungen",
      normalize.classify_category("", "Schlösserfahrt mit dem Dampfer") == "fuehrungen")
check("Besichtigung -> fuehrungen",
      normalize.classify_category("", "Besichtigung der Schauwerkstatt") == "fuehrungen")
check("Markt bleibt outdoor",
      normalize.classify_category("", "Elbflohmarkt am Neustädter Ufer") == "outdoor")
check("Stadtteilfest bleibt outdoor",
      normalize.classify_category("", "Hechtfest im Hechtviertel") == "outdoor")
# Die Fuehrungen duerfen die spezifischeren Buckets nicht ueberholen: beide
# Titel enthalten ein Fuehrungs-Stichwort, gehoeren aber woanders hin.
check("Museumsfuehrung fuer Kinder bleibt familie",
      normalize.classify_category("Kinder / Familie", "Kinderführung im Museum") == "familie")
check("Gefuehrte Wanderung bleibt sport",
      normalize.classify_category("", "Geführte Wanderung durch die Heide") == "sport")
check("normalize_time range", normalize.normalize_time("19:00-20:30") == "19:00")
check("normalize_time none", normalize.normalize_time(None) is None)
check("normalize_time En-Dash (Rauze-Format)", normalize.normalize_time("18:00–19:30") == "18:00")

# --- Rauze-Kategorien (gegen die Live-Seite verifiziert) ---
check("Rauze 'Film' -> kultur", normalize.classify_category("Film", "Dresden findet Weiterstadt 2026") == "kultur")
check("Rauze 'Party' -> musik", normalize.classify_category("Party", "No more Tears") == "musik")
check("Rauze 'Konzert' -> musik", normalize.classify_category("Konzert", "Pogendroblem") == "musik")
check("Rauze 'Kunst' -> kultur", normalize.classify_category("Kunst", "Cats & Dogs") == "kultur")
# 'Außerhalb' ist eine Ortsangabe, kein Genre -> muss über den Titel klassifiziert werden
check(
    "Rauze 'Außerhalb' faellt auf Titel-Keywords zurueck",
    normalize.classify_category("Außerhalb", "Cstl Grdn Rave") == "musik",
)
check(
    "Rauze 'Sonstiges' faellt auf Titel-Keywords zurueck",
    normalize.classify_category("Sonstiges", "Schallplattenflohmarkt Vinyl") == "musik",
)

# --- Sport: Mitmachen ja, Zuschauen nein ---
# Der Titel schlaegt hier bewusst die Rohkategorie der Quelle: "Yoga im
# Alaunpark" laeuft auf rauze.de unter "Festival" und landete frueher in musik.
check(
    "Yoga schlaegt die Rohkategorie 'Festival'",
    normalize.classify_category("Festival", "Yoga | Katrin Schuetze Yoga im Alaunpark") == "sport",
)
check("Pilates -> sport", normalize.classify_category("", "Pilates am Elbufer") == "sport")
check("Radtour -> sport", normalize.classify_category("", "Feierabend-Radtour durch die Heide") == "sport")
check("Benefizlauf -> sport", normalize.classify_category("", "NCT/UCC-Benefizlauf") == "sport")
check("Rohkategorie 'Sport' -> sport", normalize.classify_category("Sport", "Offener Klettertreff") == "sport")
check(
    "Ligaspiel trotz Rohkategorie 'Sport' nicht in sport",
    normalize.classify_category("Sport", "SG Dynamo Dresden - Heimspiel") == "sonstiges",
)
check("Fussball -> nicht sport", normalize.classify_category("", "Fussball-Public-Viewing") == "sonstiges")
# Wortgrenzen: Weinbergswanderung ist eine Weinprobe, "Der Wanderer" ein Musical
check("Weinbergswanderung bleibt outdoor/sonstiges", normalize.classify_category("", "Weinbergswanderung im August") != "sport")
check("'Der Wanderer' ist kein Sport", normalize.classify_category("Musik", "DER WANDERER UEBER DEM NEBELMEER") == "musik")
check("'Ablauf' ist kein Lauf", normalize.classify_category("", "Ablauf der Ausstellung") != "sport")
check("Sport-Label existiert", "sport" in config.CATEGORY_LABELS)
# Die Chips in der Kategorienzeile nehmen die Kurzform - fehlt eine, faellt das
# Template auf das lange Label zurueck und die Zeile bricht wieder um.
check(
    "Jede Kategorie hat ein Kurz-Label",
    set(config.CATEGORY_LABELS) == set(config.CATEGORY_SHORT_LABELS),
)
check("Sport ist nicht aus dem Newsletter gefiltert", "sport" not in config.EXCLUDED_CATEGORIES)

# --- Quellen-Registry: die abgeleitete Reihenfolge gegen das alte Literal ----
# app/registry.py hat die vier Quellen-Listen zusammengefuehrt. Die eine, bei
# der Menge nicht reicht, ist SOURCE_PRIORITY: db._source_rank ist ein
# list.index(), und db._best_source und db._keeps_own_url kommen ohne
# Gleichstands-Regel aus, weil jede Quelle genau einen Rang hat. Eine still
# verschobene Quelle wuerde Events neu zuschreiben und events.url bei jedem
# Lauf kippen lassen - data/days/*.json bekaeme alle sechs Stunden einen
# sinnlosen Commit. Deshalb steht hier die Liste, wie sie vor der Ableitung im
# Klartext in app/config.py stand, und wird Element fuer Element verglichen.
_SOURCE_PRIORITY_LITERAL = ["derlude", "strassee", "groovestation", "zentralwerk",
                            "sektor", "azconni", "rauze", "ra", "kulturkalender",
                            "cybersax"]
check("SOURCE_PRIORITY: abgeleitet == Literal, in genau dieser Reihenfolge",
      config.SOURCE_PRIORITY == _SOURCE_PRIORITY_LITERAL)
check("SOURCE_PRIORITY: jede Quelle genau einmal (Rang ist eindeutig)",
      len(set(config.SOURCE_PRIORITY)) == len(config.SOURCE_PRIORITY))
# Scrape-Reihenfolge und Label-Reihenfolge sind dieselbe wie vorher - die
# Reihenfolge von SOURCE_LABELS ist die Reihenfolge der /api/health-Antwort.
_SOURCES_LITERAL = ["kulturkalender", "rauze", "ra", "cybersax", "azconni",
                    "sektor", "derlude", "strassee", "groovestation", "zentralwerk"]
check("config.SOURCES: abgeleitet == frueheres scheduler.SOURCES",
      config.SOURCES == _SOURCES_LITERAL)
check("SOURCE_LABELS: Reihenfolge unveraendert", list(config.SOURCE_LABELS) == _SOURCES_LITERAL)
check("SOURCE_PRIORITY und SOURCES beschreiben dieselbe Menge",
      set(config.SOURCE_PRIORITY) == set(config.SOURCES))
# Die zwei Aufgaben sind getrennt, der Inhalt ist heute noch identisch. Sobald
# Venue-Eintraege dazukommen, darf das auseinanderlaufen - dann faellt dieser
# Check weg, nicht die Trennung.
check("SOURCE_GROUP_LABELS deckt sich heute noch mit SOURCE_LABELS",
      config.SOURCE_GROUP_LABELS == config.SOURCE_LABELS)
check("Registry ohne tier-Feld (Tiers erzeugen erst Gleichstaende)",
      not any("tier" in e for e in registry.SOURCES.values()))

# --- Sport: verbreiterte Stichwoerter und ihre Gegenproben ---
# "Scheliga" endet auf "liga": die Zuschauersport-Regex hat den Kurs frueher aus
# dem Sport-Bucket geworfen. Deshalb matcht "liga" jetzt nur noch mit Praefix.
check(
    "Nachname auf '-liga' blockt Yoga nicht",
    normalize.classify_category("Festival", "Yoga | Simon Scheliga Yoga im Alaunpark") == "sport",
)
check("Kundalini ohne das Wort Yoga -> sport", normalize.classify_category("Workshops", "Kundalini-Aktivierung") == "sport")
check("Meditation -> sport", normalize.classify_category("Workshops", "Lamrim - Systematische Meditationen") == "sport")
# Der eigentliche Trick beim Tanz: Kurs ja, Abend nein.
check("Tanzkurs -> sport", normalize.classify_category("", "Senioren-Tanzkurs Gesellschaftstanz") == "sport")
check("Tanzabend bleibt musik", normalize.classify_category("", "SALSA Tanzabend mit Rueda de Casino") == "musik")
# Gegenproben zu den zwei Stichwoertern, die bewusst draussen geblieben sind.
check("'ACHTSAM MORDEN' bleibt kultur", normalize.classify_category("", "ACHTSAM MORDEN Eine Krimikomoedie") == "kultur")
check("Ensemble 'Sospiratem' bleibt musik", normalize.classify_category("", 'Tacheles - Konzert mit dem Ensemble "Sospiratem"') == "musik")
# --- Zeit-Erkennung im Markup (base.TIME_PATTERN) ---
from app.scrapers import base as scraper_base  # noqa: E402

for sample in ["20:00", "18:00-19:30", "18:00–19:30", "19.30", "22:00 Uhr", " 9:00 "]:
    check(f"TIME_PATTERN erkennt {sample!r}", scraper_base.TIME_PATTERN.match(sample) is not None)
for sample in ["Ostpol", "2026", "12 Personen", ""]:
    check(f"TIME_PATTERN ignoriert {sample!r}", scraper_base.TIME_PATTERN.match(sample) is None)

# --- Rauze URL-Muster (verifiziert gegen die Live-Seite) ---
from app.scrapers import rauze as rauze_scraper  # noqa: E402
import datetime as _dt  # noqa: E402

check(
    "Rauze URL-Muster korrekt",
    rauze_scraper.DATE_URL_TEMPLATE.format(date=_dt.date(2026, 8, 22).isoformat())
    == "https://www.rauze.de/?date=2026-08-22",
)

uid1 = normalize.make_event_uid("2026-08-21", "19:00", "Wincent Weiss", "Filmnächte am Elbufer")
uid2 = normalize.make_event_uid("2026-08-21", "19:00", "Wincent Weiss", "Filmnächte am Elbufer")
check("make_event_uid stabil", uid1 == uid2)

# --- db ---
db.init_db()
with db.get_conn() as conn:
    events = [
        {
            "uid": "evt1", "source": "kulturkalender", "date": "2026-08-21", "time": "19:30",
            "title": "Azzurro - Wie zähme ich einen Italiener?", "venue": "Boulevardtheater Dresden",
            "category": "kultur", "raw_category": "Bühne", "url": "https://example.org/azzurro",
        },
        {
            "uid": "evt2", "source": "rauze", "date": "2026-08-21", "time": "21:00",
            "title": "Sachsentrance", "venue": "objekt klein a",
            "category": "musik", "raw_category": "Party", "url": "https://example.org/sachsentrance",
        },
    ]
    inserted = db.upsert_events(conn, events)
    check("upsert_events: 2 neu", inserted == 2)
    inserted_again = db.upsert_events(conn, events)
    check("upsert_events idempotent: 0 neu beim zweiten Mal", inserted_again == 0)

    rows = db.events_for_range(conn, "2026-08-21", "2026-08-21")
    check("events_for_range findet beide", len(rows) == 2)

    # --- Kategorie-Filter: einzeln, mehrfach, "alle" ---
    def cats_for(cat):
        return sorted(r["category"] for r in
                      db.events_for_range(conn, "2026-08-21", "2026-08-21", cat))

    check("Filter einzeln (String)", cats_for("musik") == ["musik"])
    check("Filter mehrfach (Komma)", cats_for("musik,kultur") == ["kultur", "musik"])
    check("Filter mehrfach (Liste)", cats_for(["musik", "kultur"]) == ["kultur", "musik"])
    check("'alle' filtert nicht", cats_for("alle") == ["kultur", "musik"])
    check("leere Auswahl filtert nicht", cats_for([]) == ["kultur", "musik"])
    check("category_filter normalisiert Leerzeichen/alle",
          db.category_filter(" musik , alle ,kultur") == ["musik", "kultur"])

    # --- scoring: ohne Feedback neutral ---
    scored = scoring.score_events(conn, [dict(r) for r in rows])
    check("score ohne Feedback == 50", all(e["score"] == 50.0 for e in scored))

    # --- scoring: like auf Theater erhöht künftige Theater-Events ---
    theater_event = next(e for e in rows if e["uid"] == "evt1")
    changed = scoring.apply_reaction(conn, theater_event, "like")
    check("apply_reaction meldet Änderung", changed is True)

    new_theater_event = {
        "uid": "evt3", "date": "2026-08-22", "time": "19:00", "title": "Ein neues Theaterstück",
        "venue": "Boulevardtheater Dresden", "category": "kultur",
    }
    score_after_like = scoring.score_event(conn, new_theater_event)
    check("Score für ähnliches Kultur-Event steigt nach Like", score_after_like > 50.0)

    party_event = dict(next(e for e in rows if e["uid"] == "evt2"))
    score_party = scoring.score_event(conn, party_event)
    check("Party-Event bleibt neutral (kein Feedback dafür)", score_party == 50.0)

    # --- idempotenz: gleiche Reaktion nochmal aendert nichts ---
    changed_again = scoring.apply_reaction(conn, theater_event, "like")
    check("Erneutes gleiches Like ist No-Op", changed_again is False)
    score_still = scoring.score_event(conn, new_theater_event)
    check("Score unveraendert nach No-Op-Like", score_still == score_after_like)

    # --- wechsel like -> skip macht alten Effekt rueckgaengig ---
    scoring.apply_reaction(conn, theater_event, "skip")
    score_after_switch = scoring.score_event(conn, new_theater_event)
    check("Score nach Wechsel zu Skip wieder <= 50", score_after_switch <= 50.0)


# --- Parsing-Fixtures: HTML nachgebaut nach den echten Tagesansichten ---
# Diese Fixtures haben einen realen Bug aufgedeckt: der Ortsname
# "Burg Max Jacob Theater" wurde als Kategorie gelesen und machte aus einem
# Rave ein Bühnenstück. Deshalb bleiben sie dauerhaft in der Suite.
from app.scrapers import kulturkalender as kk_scraper  # noqa: E402
from app.scrapers import detail_fetch  # noqa: E402
from app import web  # noqa: E402

RAUZE_FIXTURE = """
<div class="day">
  <article><span>12:00</span><span>( Sonstiges )</span><h3>Schallplattenflohmarkt Vinyl</h3>
    <a href="https://facebook.com/sharer">Teilen</a><a href="/ort/scheune">Scheune</a></article>
  <div class="event"><span>18:00&#8211;19:30</span><span>( Konzert )</span><h3>Clueso</h3>
    <a href="/event.ics">iCal</a><a href="/ort/filmnaechte">Filmn&auml;chte am Elbufer</a>
    <div class="preview"><div class="bg_image" style="background-image: url(https://cdn.example/cover.jpg)"></div></div>
    <div class="details">
      <ul class="attributes"><li class="price"><div>VVK 32,04</div></li></ul>
      <div class="images"><img src="https://cdn.example/gross.jpg" /></div>
      <div class="description"><div>Erster Absatz.</div><div>Zweiter Absatz.</div></div>
      <ul class="social"><li class="share"><a href="https://www.rauze.de/clueso">Link</a></li></ul>
    </div></div>
  <article><span>17:00</span><span>( Au&szlig;erhalb )</span><h3>Cstl Grdn Rave</h3>
    <a href="/ort/max-jacob">Burg Max Jacob Theater</a></article>
  <article><span>22:00</span><span>( Party )</span><h3>No more Tears</h3>
    <a href="/ort/ostpol">Ostpol</a></article>
</div>
"""

rauze_events = rauze_scraper._parse(RAUZE_FIXTURE, _dt.date(2026, 8, 22), "u")
by_title = {e["title"]: e for e in rauze_events}
check("Rauze-Fixture: 4 Events geparst", len(rauze_events) == 4)
check("Rauze-Fixture: En-Dash-Zeit korrekt", by_title["Clueso"]["time"] == "18:00")
check("Rauze-Fixture: Share-/iCal-Links uebersprungen",
      by_title["Clueso"]["venue"] == "Filmnächte am Elbufer")
check("Rauze-Fixture: Ortsname liefert KEINE Kategorie",
      by_title["Cstl Grdn Rave"]["raw_category"] is None)
check("Rauze-Fixture: Rave im 'Theater' bleibt Musik",
      by_title["Cstl Grdn Rave"]["category"] == "musik")
check("Rauze-Fixture: UIDs eindeutig", len({e["uid"] for e in rauze_events}) == 4)
check("Rauze-Fixture: Preis aus li.price", by_title["Clueso"]["price_text"] == "VVK 32,04")
check("Rauze-Fixture: Cover aus dem bg_image-style",
      by_title["Clueso"]["image_url"] == "https://cdn.example/cover.jpg")
check("Rauze-Fixture: Beschreibung aus beiden Absaetzen",
      by_title["Clueso"]["description"] == "Erster Absatz.\n\nZweiter Absatz.")
check("Rauze-Fixture: url ist der Event-Permalink, nicht die Tagesliste",
      by_title["Clueso"]["url"] == "https://www.rauze.de/clueso")
check("Rauze-Fixture: ohne .details faellt url auf die Tagesliste zurueck",
      by_title["No more Tears"]["url"] == "u")
check("Rauze-Fixture: Detail gilt sofort als geladen",
      bool(by_title["Clueso"]["detail_fetched_at"]))

KK_FIXTURE = """
<div>
  <article><span>10:30</span><span>B&uuml;hne</span><h3>Wo wohnt der Wurm? Figurentheater</h3>
    <a href="/ort/landesbuehnen">Landesb&uuml;hnen Sachsen</a></article>
  <section class="component-event">
    <div class="wrapper-event-media"><ul class="list-media"><li>
      <img class="media" srcset="https://kk.example/gross.jpg 1000w, https://kk.example/klein.jpg 200w" />
    </li></ul></div>
    <div class="component-card"><span>19:00</span><span>Musik</span>
      <h3 class="title-event"><a href="/veranstaltung/amy-macdonald">Amy Macdonald</a></h3>
      <a href="/ort/junge-garde">Freilichtb&uuml;hne Junge Garde</a></div>
  </section>
</div>
"""

kk_soup = scraper_base.make_soup(KK_FIXTURE)
kk_parsed = {}
for _time_text, _container in scraper_base.find_event_blocks(kk_soup):
    _title = scraper_base.extract_title(_container)
    _raw = kk_scraper._guess_raw_category(_container)
    kk_parsed[_title] = normalize.classify_category(_raw or "", _title)

check("KK-Fixture: Konzert auf 'Freilichtbühne' bleibt Musik",
      kk_parsed.get("Amy Macdonald") == "musik")
check("KK-Fixture: Figurentheater bleibt Kultur",
      kk_parsed.get("Wo wohnt der Wurm? Figurentheater") == "kultur")

# Das Cover liegt NEBEN dem gefundenen Block (im umgebenden <section>), der
# Permalink in der Ueberschrift - beides wurde frueher gar nicht ausgelesen,
# stattdessen stand in url die Tagesuebersicht.
kk_day = _dt.date(2026, 8, 22)
kk_listing_url = kk_scraper.BASE_URL.format(date=kk_day.isoformat())
kk_containers = {}
for _time_text, _container in scraper_base.find_event_blocks(kk_soup):
    kk_containers[scraper_base.extract_title(_container)] = _container
_amy = kk_containers["Amy Macdonald"]
check("KK-Fixture: Permalink aus der Ueberschrift, absolut gemacht",
      kk_scraper._extract_permalink(_amy, kk_listing_url)
      == "https://www.kulturkalender-dresden.de/veranstaltung/amy-macdonald")
check("KK-Fixture: ohne Permalink bleibt die Tagesliste stehen",
      kk_scraper._extract_permalink(
          kk_containers["Wo wohnt der Wurm? Figurentheater"], kk_listing_url)
      == kk_listing_url)
check("KK-Fixture: groesste Cover-Variante aus dem srcset",
      kk_scraper._extract_image(_amy) == "https://kk.example/gross.jpg")


# --- uid-Schema bei unvollstaendigen Angaben ------------------------------
# Nicht jede Quelle liefert eine Uhrzeit. Das uid-Schema muss das aushalten,
# ohne dass zwei verschiedene Termine dieselbe uid bekommen.
_uid_no_time = normalize.make_event_uid("2026-08-22", None, "Rave 🔥 im Ostpol", "Ostpol")
check("uid ohne Uhrzeit ist stabil",
      _uid_no_time == normalize.make_event_uid("2026-08-22", None, "Rave 🔥 im Ostpol", "Ostpol"))
check("uid ohne Uhrzeit != uid mit Uhrzeit",
      _uid_no_time != normalize.make_event_uid("2026-08-22", "22:00", "Rave 🔥 im Ostpol", "Ostpol"))


# --- Detail-Spalten, Cache und Popup-Endpunkt -----------------------------
db.init_db()  # muss auch auf einer bereits bestehenden DB nachmigrieren
with db.get_conn() as conn:
    _cols = {row["name"] for row in conn.execute("PRAGMA table_info(events)")}
check("Migration: neue Detail-Spalten vorhanden",
      {"image_url", "price_text", "description", "detail_fetched_at"} <= _cols)

_detail_event = {
    "uid": "detail-1", "source": "rauze", "date": "2026-08-22", "time": "20:00",
    "title": "Testkonzert", "venue": "Ostpol", "category": "musik",
    "raw_category": "Konzert", "url": "https://www.rauze.de/testkonzert",
    "image_url": "https://cdn.example/a.jpg", "price_text": "VVK 12,-",
    "description": "Erste Fassung.", "detail_fetched_at": "2026-08-22T10:00:00",
}
with db.get_conn() as conn:
    db.upsert_events(conn, [_detail_event])
    _row = dict(conn.execute("SELECT * FROM events WHERE uid = 'detail-1'").fetchone())
check("Detailfelder werden beim Insert gespeichert",
      _row["price_text"] == "VVK 12,-" and _row["description"] == "Erste Fassung.")

# Ein normaler Kulturkalender-Lauf liefert diese Felder gar nicht mit - das
# darf einen schon geholten Detail-Cache nicht wieder loeschen.
_bare = dict(_detail_event)
for _f in ("image_url", "price_text", "description", "detail_fetched_at"):
    _bare[_f] = None
with db.get_conn() as conn:
    db.upsert_events(conn, [_bare])
    _row = dict(conn.execute("SELECT * FROM events WHERE uid = 'detail-1'").fetchone())
check("Re-Scrape ohne Detailfelder loescht den Cache nicht",
      _row["price_text"] == "VVK 12,-" and _row["description"] == "Erste Fassung.")

# Rauze liefert sie bei jedem Lauf frisch - ein geaenderter Preis muss ankommen.
_fresh = dict(_detail_event, price_text="ausverkauft", description="Zweite Fassung.")
with db.get_conn() as conn:
    db.upsert_events(conn, [_fresh])
    _row = dict(conn.execute("SELECT * FROM events WHERE uid = 'detail-1'").fetchone())
check("Frische Werte aus der Quelle ueberschreiben",
      _row["price_text"] == "ausverkauft" and _row["description"] == "Zweite Fassung.")

with db.get_conn() as conn:
    db.save_event_detail(conn, "detail-1", None, None,
                         detail_fetch.FALLBACK_DESCRIPTION)
    _row = dict(conn.execute("SELECT * FROM events WHERE uid = 'detail-1'").fetchone())
check("save_event_detail setzt den Cache-Stempel auch ohne Fund",
      _row["detail_fetched_at"] and _row["description"] == detail_fetch.FALLBACK_DESCRIPTION)
check("save_event_detail behaelt vorhandenen Preis",
      _row["price_text"] == "ausverkauft")

# --- detail_fetch: darf niemals werfen ------------------------------------
KK_DETAIL_FIXTURE = """
<html><body><main>
  <section class="component-event"><div class="wrapper-event-media">
    <img srcset="https://kk.example/detail.jpg 1000w" /></div></section>
  <div class="box-content"><p>Ein ausf&uuml;hrlicher Beschreibungstext ueber die
  Veranstaltung. Eintritt: 11&euro;-18&euro; pro Person.</p></div>
  <div class="box-content">Veranstaltung teilen</div>
</main></body></html>
"""
_kkd = detail_fetch._parse_kulturkalender_detail(scraper_base.make_soup(KK_DETAIL_FIXTURE))
check("Detailseite: Beschreibung aus .box-content",
      "ausf" in _kkd["description"] and "teilen" not in _kkd["description"])
check("Detailseite: Preis aus dem Fliesstext", _kkd["price_text"] == "11€-18€")
check("Detailseite: Cover aus dem srcset",
      _kkd["image_url"] == "https://kk.example/detail.jpg")

for _junk in ("", "<html></html>", "<div>nichts</div>", "kein html <<<"):
    _out = detail_fetch._parse_kulturkalender_detail(scraper_base.make_soup(_junk))
    check(f"Detailseite: Muell-HTML {_junk[:12]!r} faellt sauber zurueck",
          _out["description"] == detail_fetch.FALLBACK_DESCRIPTION)

# Ein konkreter Betrag muss "Eintritt frei" schlagen - sonst stuende bei
# "11€-18€ (unter 18 Jahren Eintritt frei)" faelschlich "gratis" im Badge.
check("Preis: Betrag schlaegt 'Eintritt frei'",
      detail_fetch.price_from_text(
          "Eintritt: 11€-18€ pro Person (unter 18 Jahren Eintritt frei)") == "11€-18€")
check("Preis: echtes Gratis-Event bleibt frei",
      detail_fetch.price_from_text("Der Eintritt ist frei.") == "Eintritt ist frei")
check("Preis: ohne Angabe kein Badge",
      detail_fetch.price_from_text("Ein Abend ohne jede Preisangabe.") is None)


def _boom(url, timeout=None, retries=None):
    raise RuntimeError("Quelle nicht erreichbar")


check("fetch_detail wirft nicht, wenn die Quelle ausfaellt",
      detail_fetch.fetch_detail(
          {"url": "http://x", "source": "kulturkalender"}, fetch_html=_boom)["ok"] is False)
check("fetch_detail ohne url liefert ok=False",
      detail_fetch.fetch_detail({"source": "kulturkalender"})["ok"] is False)

# --- /api/event/<uid>/details ---------------------------------------------
_lazy = {
    "uid": "lazy-1", "source": "kulturkalender", "date": "2026-08-22", "time": "19:00",
    "title": "Nachzuladendes Event", "venue": "Irgendwo", "category": "kultur",
    "raw_category": None, "url": "https://www.kulturkalender-dresden.de/veranstaltung/x",
}
with db.get_conn() as conn:
    db.upsert_events(conn, [_lazy])

_calls = []


def _fake_fetch(event):
    _calls.append(event["uid"])
    return {"ok": True, "description": "Nachgeladener Text.",
            "price_text": "8 Euro", "image_url": "https://kk.example/lazy.jpg"}


detail_fetch_original = web.detail_fetch.fetch_detail
web.detail_fetch.fetch_detail = _fake_fetch
_client = web.app.test_client()

_first = _client.get("/api/event/lazy-1/details").get_json()
check("Details: erster Aufruf laedt nach", _first["detail_status"] == "fetched")
check("Details: nachgeladene Werte kommen zurueck",
      _first["price_text"] == "8 Euro" and _first["description"] == "Nachgeladener Text.")

_second = _client.get("/api/event/lazy-1/details").get_json()
check("Details: zweiter Aufruf kommt aus der DB", _second["detail_status"] == "cached")
check("Details: kein zweiter Netz-Zugriff", len(_calls) == 1)

check("Details: unbekannte uid -> 404",
      _client.get("/api/event/gibtsnicht/details").status_code == 404)

# Faellt die Quelle aus, darf NICHTS gecacht werden - sonst bliebe das Event
# fuer immer ohne Beschreibung.
with db.get_conn() as conn:
    db.upsert_events(conn, [dict(_lazy, uid="lazy-2")])
web.detail_fetch.fetch_detail = lambda event: {
    "ok": False, "description": None, "price_text": None, "image_url": None}
_failed = _client.get("/api/event/lazy-2/details").get_json()
check("Details: Ausfall meldet 'unavailable'", _failed["detail_status"] == "unavailable")
with db.get_conn() as conn:
    _row = dict(conn.execute("SELECT * FROM events WHERE uid = 'lazy-2'").fetchone())
check("Details: Ausfall wird nicht gecacht (spaeterer Versuch bleibt moeglich)",
      _row["detail_fetched_at"] is None)
web.detail_fetch.fetch_detail = detail_fetch_original


# --- Resident Advisor: Parsen der GraphQL-Antwort --------------------------
# Fixture ist eine gekuerzte, aber unveraenderte Antwort der Live-API vom
# 21.08.2026 (POST https://ra.co/graphql, areas.eq 150 = Dresden). Damit haengt
# der Test nicht am Netz, prueft aber genau die Struktur, die real ankommt.
from app.scrapers import ra as ra_source  # noqa: E402

RA_FIXTURE = {"data": {"eventListings": {"totalResults": 3, "data": [
    {"id": "12480397", "listingDate": "2026-08-21T00:00:00.000", "event": {
        "id": "2480397", "date": "2026-08-21T00:00:00.000",
        "startTime": "2026-08-21T21:00:00.000", "endTime": "2026-08-22T06:00:00.000",
        "title": "Sachsentrance Sommerfest", "contentUrl": "/events/2480397",
        "content": "Sachsentrance Summer at Objekt klein a", "cost": "15-20",
        "images": [{"filename": "https://images.ra.co/2fa0.png", "type": "FLYERFRONT"}],
        "venue": {"id": "133794", "name": "objekt klein a", "area": {"id": "150", "name": "Dresden"}},
        "artists": [{"name": "CARGO (DE)"}, {"name": "GI.O"}]}},
    {"id": "12516858", "listingDate": "2026-08-22T00:00:00.000", "event": {
        "id": "2516858", "date": "2026-08-22T00:00:00.000",
        "startTime": "2026-08-22T23:00:00.000", "endTime": "2026-08-23T10:00:00.000",
        "title": "Pangaea invites", "contentUrl": "/events/2516858",
        "content": "", "cost": "18 €", "images": [],
        "venue": {"id": "25274", "name": "Sektor Evolution", "area": {"id": "150", "name": "Dresden"}},
        "artists": [{"name": "Xiorro"}, {"name": "OLIV"}]}},
    {"id": "12436771", "listingDate": "2026-08-28T00:00:00.000", "event": {
        "id": "2436771", "date": "2026-08-28T00:00:00.000",
        "startTime": "2026-08-28T18:00:00.000", "endTime": "2026-08-28T23:59:00.000",
        "title": "RAVE x RIESLING - Weingut Vincenz Richter", "contentUrl": "/events/2436771",
        "content": "Wein trifft Techno.", "cost": "",
        "images": [{"filename": "https://images.ra.co/b48d.jpg", "type": "FLYERFRONT"}],
        "venue": {"id": "0", "name": "TBA", "area": {"id": "150", "name": "Dresden"}},
        "artists": []}},
]}}}

_ra_events = ra_source.parse_listings(RA_FIXTURE)
check("RA: alle drei Listings geparst", len(_ra_events) == 3)
_ra_first = _ra_events[0]
check("RA: Datum aus listingDate", _ra_first["date"] == "2026-08-21")
check("RA: Startzeit aus startTime", _ra_first["time"] == "21:00")
check("RA: Ort", _ra_first["venue"] == "objekt klein a")
check("RA: Quelle", _ra_first["source"] == "ra")
check("RA: Kategorie musik", all(e["category"] == "musik" for e in _ra_events))
check("RA: absolute Event-URL", _ra_first["url"] == "https://ra.co/events/2480397")
check("RA: Flyer als Bild", _ra_first["image_url"] == "https://images.ra.co/2fa0.png")
check("RA: nackter Betrag bekommt Waehrung", _ra_first["price_text"] == "15-20 €")
check("RA: Preis mit Waehrung bleibt unveraendert", _ra_events[1]["price_text"] == "18 €")
check("RA: leerer Preis -> None", _ra_events[2]["price_text"] is None)
check("RA: Lineup landet in der Beschreibung",
      "Line-up: CARGO (DE), GI.O" in _ra_first["description"])
check("RA: Lineup auch ohne Fliesstext",
      _ra_events[1]["description"] == "Line-up: Xiorro, OLIV")
check("RA: 'TBA' ist kein Ort", _ra_events[2]["venue"] is None)
check("RA: Detailfelder gelten als geladen (kein Nachladen noetig)",
      bool(_ra_first["detail_fetched_at"]))
# Nach Mitternacht: RA nennt als startTime 23:00 des Vortages-Listings - das
# Datum muss der Partytag bleiben, nicht der Kalendertag des Endes.
check("RA: Nachtevent bleibt auf dem Partytag", _ra_events[1]["date"] == "2026-08-22")
check("RA: uid ist dieselbe wie bei den HTML-Quellen (gleiche Bausteine)",
      _ra_first["uid"] == normalize.make_event_uid(
          "2026-08-21", "21:00", "Sachsentrance Sommerfest", "objekt klein a"))


# --- CyberSAX / SAX-Terminal (app/scrapers/cybersax.py) --------------------
# Fixture ist gekuerztes, aber unveraendertes Markup der Tagesseite vom
# 29.08.2026 (https://www.cybersax.de/terminal/day/2026/8/29/). Enthaelt mit
# Absicht alle drei Zeilenarten: Abschnittsueberschrift, normale Eventzeile und
# eine Kinozeile ohne Ortsspalte.
import datetime as _dt2  # noqa: E402

from app.scrapers import cybersax as cybersax_scraper  # noqa: E402

check(
    "CyberSAX: Tages-URL ohne fuehrende Nullen",
    cybersax_scraper.DATE_URL_TEMPLATE.format(year=2026, month=8, day=29)
    == "https://www.cybersax.de/terminal/day/2026/8/29/",
)

CYBERSAX_FIXTURE = """
<div class="tx-usercybersax-pi2">
<h3>Samstag, 29. August 2026</h3>
<table>
<tr id="buehne"><td colspan="3"><h4>B&uuml;hne</h4></td></tr>
<tr><td class="td1">19:00 Uhr<br /></td>
    <td class="td2"><a href="/terminal/adressen/address/hangar-1-dresden/">Hangar 1</a></td>
    <td colspan="1" class="td3">Hamlet &nbsp;<button type="button" data-toggle="popover"
      data-source="#info1"><i class="fas fa-info-circle"></i></button>
      <div id="info1">In D&auml;nemark ist nichts, wie es war.</div></td></tr>
<tr><td class="td1">19:00 Uhr<br /></td>
    <td class="td2"><a href="/terminal/adressen/address/semperoper-dresden/">Semperoper</a></td>
    <td colspan="1" class="td3">Carmen </td></tr>
<tr id="musik"><td colspan="3"><h4>Musik</h4></td></tr>
<tr><td class="td1">19:00 Uhr<br /></td>
    <td class="td2"><a href="/terminal/adressen/address/cafe-saite-dresden/">Caf&eacute; Saite</a></td>
    <td colspan="1" class="td3">The Transsylvanians (D) </td></tr>
<tr id="workshops"><td colspan="3"><h4>Workshops</h4></td></tr>
<tr><td class="td1">10:00 Uhr</td>
    <td class="td2"><a href="/terminal/adressen/address/kafe-zeitlos-dresden/">Kaf&eacute; Zeitlos</a></td>
    <td colspan="1" class="td3">Manifestation Workshop 1 - Mindset </td></tr>
<tr id="film"><td colspan="3"><h4>Film</h4></td></tr>
<tr><td class="td1">21:00 Uhr<br /></td>
    <td colspan="2" class="td3">Exit 8 (JAP 2025; R: Genki Kawamura) </td></tr>
<tr id="klang"><td colspan="3"><h4>Klang&amp;Kruste</h4></td></tr>
<tr><td class="td1">12:30 Uhr<br /></td>
    <td class="td2"><a href="/terminal/adressen/address/alaunpark/">Alaunpark</a></td>
    <td colspan="1" class="td3">leuri303 </td></tr>
<tr><td class="td1">10:00 Uhr<br /></td>
    <td class="td2"><a href="/terminal/adressen/address/alaunpark/">Alaunpark</a></td>
    <td colspan="1" class="td3">DJ Pappenheimer </td></tr>
<tr><td class="td1">22:00 Uhr<br /></td>
    <td class="td2"><a href="/terminal/adressen/address/alaunpark/">Alaunpark</a></td>
    <td colspan="1" class="td3">Micro7oft aka STACHY.DJ </td></tr>
<tr id="musikfest"><td colspan="3"><h4>Musikfest Erzgebirge</h4></td></tr>
<tr><td class="td1">19:00 Uhr<br /></td>
    <td class="td2"><a href="/terminal/adressen/address/nikolaikirche/">Nikolaikirche</a></td>
    <td colspan="1" class="td3">Ars Musica Elletrica </td></tr>
<tr><td class="td1">19:00 Uhr<br /></td>
    <td class="td2"><a href="/terminal/adressen/address/marienkirche/">St. Marienkirche</a></td>
    <td colspan="1" class="td3">Slixs </td></tr>
</table>
</div>
"""

cybersax_events = cybersax_scraper._parse(
    CYBERSAX_FIXTURE, _dt2.date(2026, 8, 29), "https://www.cybersax.de/terminal/day/2026/8/29/"
)
_cs_by_title = {e["title"]: e for e in cybersax_events}

check("CyberSAX-Fixture: 9 Eintraege uebrig (8 Zeilen + 1 Sammel-Eintrag)",
      len(cybersax_events) == 9)
check("CyberSAX: grosses Haus faellt raus (Semperoper)", "Carmen" not in _cs_by_title)
check("CyberSAX: kleiner Laden bleibt drin", "The Transsylvanians (D)" in _cs_by_title)
# Ohne Ortsspalte greift der Kleine-Haeuser-Filter nicht - solche Zeilen sind
# das Kinoprogramm und gehoeren nicht zum Zweck dieser Quelle.
check("CyberSAX: Kinozeile ohne Ort wird verworfen",
      not any("Exit 8" in t for t in _cs_by_title))
check("CyberSAX: Abschnittsueberschrift wird zur Rohkategorie",
      _cs_by_title["Hamlet"]["raw_category"] == "Bühne"
      and _cs_by_title["The Transsylvanians (D)"]["raw_category"] == "Musik")
check("CyberSAX: Kategorie aus der Rohkategorie",
      _cs_by_title["Hamlet"]["category"] == "kultur"
      and _cs_by_title["The Transsylvanians (D)"]["category"] == "musik")
# Titel und Langfassung stehen in derselben Zelle, getrennt durch &nbsp;; die
# Langfassung selbst steckt im aufklappbaren <div id="info...">.
check("CyberSAX: Titel ohne Popover-Text",
      _cs_by_title["Hamlet"]["title"] == "Hamlet")
check("CyberSAX: Beschreibung aus dem Info-Div",
      _cs_by_title["Hamlet"]["description"] == "In Dänemark ist nichts, wie es war.")
check("CyberSAX: ohne Info-Div bleibt die Beschreibung leer",
      _cs_by_title["The Transsylvanians (D)"]["description"] is None)
check("CyberSAX: Ort aus der Ortsspalte",
      _cs_by_title["The Transsylvanians (D)"]["venue"] == "Café Saite")
check("CyberSAX: Zeit normalisiert", _cs_by_title["Hamlet"]["time"] == "19:00")
check("CyberSAX: Quelle und Datum",
      all(e["source"] == "cybersax" and e["date"] == "2026-08-29" for e in cybersax_events))
# Die Quelle hat keine Event-Permalinks, nur Ortsseiten - deshalb die Tagesseite.
check("CyberSAX: url ist die Tagesseite",
      _cs_by_title["Hamlet"]["url"] == "https://www.cybersax.de/terminal/day/2026/8/29/")
check("CyberSAX: keine Bilder/Preise vorhanden",
      all(e["image_url"] is None and e["price_text"] is None for e in cybersax_events))
check("CyberSAX: UIDs eindeutig", len({e["uid"] for e in cybersax_events}) == 9)

check("CyberSAX: _is_big_house erkennt Teilstring-Schreibweisen",
      cybersax_scraper._is_big_house("Schloss Pillnitz, Kunstgewerbemuseum")
      and cybersax_scraper._is_big_house("Deutsches Hygiene-Museum"))
check("CyberSAX: _is_big_house laesst kleine Laeden durch",
      not cybersax_scraper._is_big_house("Ostpol")
      and not cybersax_scraper._is_big_house("Der Lude")
      and not cybersax_scraper._is_big_house(None))

# --- Festival-Ueberschriften: ein Line-up ist EINE Veranstaltung -----------
# Real am 22.08.2026: unter "Klang&Kruste" standen zehn Zeilen, alle im
# Alaunpark - das ist ein Open Air mit Line-up und keine zehn Termine.
check("CyberSAX: Rubrik-Ueberschrift ist kein Veranstaltungsname",
      not cybersax_scraper.is_festival_heading("Musik")
      and not cybersax_scraper.is_festival_heading("Kinder / Familie")
      and not cybersax_scraper.is_festival_heading(None))
check("CyberSAX: Festivalname wird als solcher erkannt",
      cybersax_scraper.is_festival_heading("Klang&Kruste")
      and cybersax_scraper.is_festival_heading("Tag des Offenen Denkmals"))

_cs_umbrella = _cs_by_title["Klang&Kruste"]
check("CyberSAX: Sammel-Eintrag traegt den Festivalnamen als Titel und Rohkategorie",
      _cs_umbrella["raw_category"] == "Klang&Kruste"
      and _cs_umbrella["venue"] == "Alaunpark")
# Die frueheste Slotzeit, NICHT die erste Zeile im Dokument (im Fixture steht
# 12:30 mit Absicht vor 10:00).
check("CyberSAX: Sammel-Eintrag beginnt mit dem fruehesten Programmpunkt",
      _cs_umbrella["time"] == "10:00")
check("CyberSAX: Line-up steht in der Beschreibung",
      _cs_umbrella["description"]
      == "Line-up: 10:00 DJ Pappenheimer · 12:30 leuri303 · 22:00 Micro7oft aka STACHY.DJ")
# "Klang&Kruste" sagt fuer sich genommen nichts - die Kategorie kommt deshalb
# aus dem Programm darunter (siehe _group_category).
check("CyberSAX: Kategorie des Sammel-Eintrags kommt aus dem Line-up",
      _cs_umbrella["category"] == "musik")
# Die Einzelzeilen bleiben erhalten: ausgeblendet werden sie erst in dedup.py,
# so bleibt das Line-up abrufbar und die Zusammenfassung umkehrbar.
check("CyberSAX: Einzelzeilen bleiben zusaetzlich stehen",
      "leuri303" in _cs_by_title and "DJ Pappenheimer" in _cs_by_title)
# Das Musikfest Erzgebirge listet unter einer Ueberschrift echte Einzelkonzerte
# in verschiedenen Kirchen - ueber Orte hinweg wird deshalb nie zusammengefasst.
check("CyberSAX: verschiedene Orte werden nicht zusammengefasst",
      "Musikfest Erzgebirge" not in _cs_by_title)
check("CyberSAX: Rubriken erzeugen keinen Sammel-Eintrag",
      "Musik" not in _cs_by_title and "Bühne" not in _cs_by_title)


# --- AZ Conni (app/scrapers/azconni.py) ------------------------------------
# Fixture ist gekuerztes, aber unveraendertes Markup von
# https://www.azconni.de/termine/ (abgerufen am 22.08.2026).
from app.scrapers import azconni as azconni_scraper  # noqa: E402

AZCONNI_FIXTURE = """
<div id="main-container">
<div class="termin overview"><span class="time">Donnerstag, 3. September ab 19:00 Uhr</span>
<span class="categories">Workshop</span><div style="clear: left;"></div>
<header><a href="https://www.azconni.de/termin-regular/offener-djtreff/">Offener DJ*-Treff</a></header>
<p>Mit dem offenen DJ*-Treff soll ein Raum geschaffen werden. &hellip;
<a class="continue-reading" href="https://www.azconni.de/termin-regular/offener-djtreff/">[weiterlesen]</a></p>
</div>
<div class="termin overview"><span class="time">Sonnabend, 10. Januar ab 21:00 Uhr</span>
<span class="categories">Konzert</span><div style="clear: left;"></div>
<header><a href="https://www.azconni.de/termin/soliparty/">Soliparty</a></header>
<p>Kurzer Teaser.</p>
</div>
</div>
"""

azconni_events = azconni_scraper._parse(AZCONNI_FIXTURE, today=_dt2.date(2026, 8, 22))
_az_by_title = {e["title"]: e for e in azconni_events}
check("AZ Conni-Fixture: 2 Termine geparst", len(azconni_events) == 2)
check("AZ Conni: Ort ist fest gesetzt",
      all(e["venue"] == "AZ Conni" and e["source"] == "azconni" for e in azconni_events))
check("AZ Conni: Datum ohne Jahr -> naechstes Vorkommen",
      _az_by_title["Offener DJ*-Treff"]["date"] == "2026-09-03")
check("AZ Conni: Jahreswechsel wird beruecksichtigt",
      _az_by_title["Soliparty"]["date"] == "2027-01-10")
check("AZ Conni: Zeit aus derselben Zeile",
      _az_by_title["Offener DJ*-Treff"]["time"] == "19:00")
check("AZ Conni: Rohkategorie aus span.categories",
      _az_by_title["Soliparty"]["raw_category"] == "Konzert"
      and _az_by_title["Soliparty"]["category"] == "musik")
# "Workshop" beschreibt die Form, nicht das Thema - der Titel muss entscheiden
# duerfen, sonst waere der DJ-Treff im AZ Conni ploetzlich "Kultur".
check("AZ Conni: 'Workshop' faellt auf Titel-Keywords zurueck",
      _az_by_title["Offener DJ*-Treff"]["category"] == "musik")
check("AZ Conni: Permalink als URL",
      _az_by_title["Soliparty"]["url"] == "https://www.azconni.de/termin/soliparty/")
check("AZ Conni: '[weiterlesen]' steht nicht in der Beschreibung",
      "weiterlesen" not in _az_by_title["Offener DJ*-Treff"]["description"])
check("AZ Conni: Beschreibung ohne haengendes Auslassungszeichen",
      _az_by_title["Offener DJ*-Treff"]["description"]
      == "Mit dem offenen DJ*-Treff soll ein Raum geschaffen werden.")
# Wiederkehrende Termine teilen sich einen Permalink; die uid muss trotzdem
# je Datum eine andere sein.
check("AZ Conni: gleicher Permalink an zwei Tagen -> zwei uids",
      azconni_scraper._parse(AZCONNI_FIXTURE, today=_dt2.date(2026, 8, 22))[0]["uid"]
      != azconni_scraper._parse(AZCONNI_FIXTURE, today=_dt2.date(2026, 10, 1))[0]["uid"])
check("AZ Conni: Detailtext ist noch nachladbar",
      all(e["detail_fetched_at"] is None for e in azconni_events))
check("AZ Conni: unparsbare Datumszeile wirft nicht",
      azconni_scraper._parse_german_date("demnaechst", _dt2.date(2026, 8, 22)) is None
      and azconni_scraper._parse_german_date("30. Februar", _dt2.date(2026, 8, 22)) is None)

# Dedup: "AZ Conni" (eigene Seite) und "Conni" (rauze.de) sind derselbe Laden.
from app import dedup  # noqa: E402

check("Dedup: 'AZ Conni' und 'Conni' sind derselbe Ortsschluessel",
      dedup._venue_key("AZ Conni") == dedup._venue_key("Conni"))
check("Dedup: 'Kafe Zeitlos' und 'Cafe Zeitlos' sind derselbe Ortsschluessel",
      dedup._venue_key("Kafé Zeitlos") == dedup._venue_key("Café Zeitlos"))


# --- Sektor Evolution (app/scrapers/sektor.py) -----------------------------
# Fixtures sind gekuerztes, aber unveraendertes Markup von
# https://www.sektor-evolution.de/dates/ bzw. einer Detailseite
# (abgerufen am 22.08.2026).
from app.scrapers import sektor as sektor_scraper  # noqa: E402


def _sektor_block(day, month, year, title, location, href):
    return f"""
<div class="mod mod-event-1 mod-event-list is-waypoint event-list-item">
  <article class="mod__inner post-6168 angio_events angio_event_type-future-events">
    <a class="mod__click fx-cursor fx-hover-image" href="{href}" data-cursor-class="hover-img">
      <div class="mod__event-content">
        <div class="mod__event-date">
          <span class="mod__event-day">{day}</span>
          <div class="mod__event-date-inner">
            <span class="mod__event-month">{month}</span>
            <span class="mod__event-year">{year}</span>
          </div>
        </div>
        <div class="mod__event-title">
          <h2 class="mod__event-name">{title}</h2>
          <div class="mod__event-location">{location}</div>
        </div>
      </div>
    </a>
  </article>
</div>"""


SEKTOR_LIST_FIXTURE = "<div class=\"events-list\">" + "".join([
    _sektor_block("22", "Aug.", "2026", "Pangaea invites ", "SektorEvolution",
                  "https://www.sektor-evolution.de/event/werkhain-2/"),
    _sektor_block("26", "Sep.", "2026", "Brennpunkt : Chosen Random Selection",
                  "SektorEvolution, objekt klein a, Circie, Club Paula",
                  "https://www.sektor-evolution.de/event/brennpunkt/"),
    _sektor_block("21", "M\u00e4rz", "2025", "Sweet &amp; Spicy", "Sektor Evolutin",
                  "https://www.sektor-evolution.de/event/sweet-spicy/"),
]) + "</div>"

SEKTOR_DETAIL_FIXTURE = """
<div id="ajax-content"><div class="event event--event1">
<div class="event-cover__thumb"><div class="image">
  <img src="https://www.sektor-evolution.de/wp-content/uploads/2026/07/74362987.jpeg" alt="Pangaea invites">
</div></div>
<div class="event__details"><div class="details-list"><ul>
  <li><div class="details-list__name">Date</div><div class="details-list__data">22 Aug. 2026</div></li>
  <li><div class="details-list__name">Time</div><div class="details-list__data">11:00 PM</div></li>
  <li><div class="details-list__name">Venue</div><div class="details-list__data">SektorEvolution</div></li>
</ul></div></div>
<div class="event__text">
<p class="wp-block-paragraph">Shockwerk x Operation x Pangaea Urwaldzirkus</p>
<p class="wp-block-paragraph"><strong>LineUp:<br>XIORRO<br>OLIV<br>COLINE</strong></p>
<p class="wp-block-paragraph">Open: 22:00-05:00<br>Tickets: 5 &euro;</p>
<noscript><div class="pretix-widget">JavaScript ist in Ihrem Browser deaktiviert.</div></noscript>
</div>
</div></div>
"""

sektor_entries = sektor_scraper._parse_list(SEKTOR_LIST_FIXTURE)
_se_by_title = {e["title"]: e for e in sektor_entries}
check("Sektor-Fixture: 3 Termine geparst", len(sektor_entries) == 3)
# Regression: die Uebersicht nennt Tag, Monat und Jahr in drei getrennten
# Spans - wird das Jahr uebersehen, kommt "0022-08-22" heraus und der Termin
# faellt lautlos aus jedem Zeitraum.
check("Sektor: Jahr kommt aus dem eigenen Span",
      _se_by_title["Pangaea invites"]["date"] == "2026-08-22")
check("Sektor: Monat mit Umlaut wird erkannt",
      _se_by_title["Sweet & Spicy"]["date"] == "2025-03-21")
check("Sektor: Permalink als URL",
      _se_by_title["Pangaea invites"]["url"]
      == "https://www.sektor-evolution.de/event/werkhain-2/")
# Das Haus schreibt sich selbst in drei Varianten (samt Tippfehler), und bei
# Abenden ueber mehrere Laeden steht es an erster Stelle. Alles muss auf einen
# Ortsschluessel fallen, sonst greift die Doppelungs-Erkennung nicht.
check("Sektor: alle Schreibweisen ergeben denselben Ort",
      {e["venue"] for e in sektor_entries} == {"Sektor Evolution"})
check("Sektor: fremder Ort bliebe erhalten",
      sektor_scraper._venue_name("Ostpol") == "Ostpol"
      and sektor_scraper._venue_name("") == "Sektor Evolution")

# Die Detailseite gibt die Zeit englisch im 12-Stunden-Format aus.
# normalize.normalize_time() wuerde daraus stumm "11:00" machen.
check("Sektor: 12-Stunden-Zeit wird umgerechnet",
      (sektor_scraper._parse_time("11:00 PM"), sektor_scraper._parse_time("12:00 AM"),
       sektor_scraper._parse_time("12:30 PM")) == ("23:00", "00:00", "12:30"))
check("Sektor: 24-Stunden-Zeit bleibt unveraendert, fehlende bleibt leer",
      sektor_scraper._parse_time("22:00") == "22:00"
      and sektor_scraper._parse_time(None) is None)

_se_detail = sektor_scraper.parse_detail(sektor_scraper.base.make_soup(SEKTOR_DETAIL_FIXTURE))
check("Sektor-Detail: Uhrzeit aus der Angabentabelle", _se_detail["time"] == "23:00")
check("Sektor-Detail: Cover-Bild",
      _se_detail["image_url"].endswith("/74362987.jpeg"))
check("Sektor-Detail: Preis aus dem Flie\u00dftext", _se_detail["price_text"] == "5 \u20ac")
# Das Line-up steht als <br>-getrennte Namensfolge; mit Leerzeichen
# zusammengezogen waere es eine unlesbare Wortschlange.
check("Sektor-Detail: Zeilenumbrueche des Line-ups bleiben erhalten",
      "XIORRO\nOLIV\nCOLINE" in _se_detail["description"])
check("Sektor-Detail: Ticket-Widget steht nicht in der Beschreibung",
      "JavaScript" not in _se_detail["description"])

_se_event = sektor_scraper._build_event(_se_by_title["Pangaea invites"], _se_detail)
check("Sektor: Quelle und Kategorie",
      _se_event["source"] == "sektor" and _se_event["category"] == "musik")
check("Sektor: Event verlinkt das Haus, nicht den Aggregator",
      _se_event["url"].startswith("https://www.sektor-evolution.de/event/"))
check("Sektor: Zeit und Detailstand aus der Detailseite",
      _se_event["time"] == "23:00" and _se_event["detail_fetched_at"])
# Faellt die Detailseite aus, bleibt der Termin trotzdem stehen - dann aber
# ohne Zeit und als "noch nachzuladen" markiert.
_se_bare = sektor_scraper._build_event(_se_by_title["Pangaea invites"])
check("Sektor: ohne Detailseite bleibt der Termin ohne Zeit nachladbar",
      _se_bare["time"] is None and _se_bare["detail_fetched_at"] is None
      and _se_bare["uid"] != _se_event["uid"])


def _sektor_scrape(start, end):
    """scrape_range ohne Netzwerk: Uebersicht gemockt, Detailabruf injiziert."""
    real_fetch, real_delay = sektor_scraper.base.fetch_html, sektor_scraper.DETAIL_DELAY_SECONDS
    sektor_scraper.base.fetch_html = lambda url, **kw: SEKTOR_LIST_FIXTURE
    sektor_scraper.DETAIL_DELAY_SECONDS = 0
    try:
        return sektor_scraper.scrape_range(
            start, end,
            fetch_detail=lambda url: sektor_scraper.parse_detail(
                sektor_scraper.base.make_soup(SEKTOR_DETAIL_FIXTURE)),
        )
    finally:
        sektor_scraper.base.fetch_html = real_fetch
        sektor_scraper.DETAIL_DELAY_SECONDS = real_delay


_se_range = _sektor_scrape(_dt2.date(2026, 8, 1), _dt2.date(2026, 9, 1))
check("Sektor: scrape_range filtert auf den Zeitraum",
      [e["title"] for e in _se_range] == ["Pangaea invites"])
check("Sektor: scrape_range laedt die Detailseite mit",
      _se_range[0]["time"] == "23:00" and _se_range[0]["price_text"] == "5 \u20ac")

check("Dedup: 'SektorEvolution' und 'Sektor Evolution' sind derselbe Ortsschluessel",
      dedup._venue_key("SektorEvolution") == dedup._venue_key("Sektor Evolution"))

# --- CyberSAX-Rohkategorien (gegen die Live-Seite verifiziert) -------------
check("CyberSAX 'Literatur' -> kultur",
      normalize.classify_category("Literatur", "Buchvorstellung") == "kultur")
check("CyberSAX 'Tanz / Party' -> musik",
      normalize.classify_category("Tanz / Party", "Nachtschicht") == "musik")
check("CyberSAX 'Vortrag / Gespraech' -> kultur",
      normalize.classify_category("Vortrag / Gespräch", "Papiere zum Fühlen") == "kultur")
check("CyberSAX 'Kinder / Familie' -> familie",
      normalize.classify_category("Kinder / Familie", "Puppenspiel") == "familie")
check("CyberSAX 'Fuehrungen' -> fuehrungen",
      normalize.classify_category("Führungen", "Durch die Altstadt") == "fuehrungen")
# Festivalnamen stehen im selben <h4> wie die echten Kategorien und sind
# deshalb bewusst keine: der Titel muss entscheiden.
check("CyberSAX: Festivalname als Ueberschrift faellt auf den Titel zurueck",
      normalize.classify_category("Klang&Kruste", "Konzert im Alaunpark") == "musik")
check("CyberSAX 'Aktionen' ist ein Sammelbecken, keine Kategorie",
      normalize.classify_category("Aktionen", "Zufälliges Ereignis") == "sonstiges")
# "fest" darf nicht in RAW_CATEGORY_MAP: der Abgleich laeuft per Teilstring und
# wuerde damit auch auf "Festival" passen - genau die Zuordnung, die dort
# bewusst entfernt wurde.
check("CyberSAX: 'Fest' reisst 'Festival' nicht wieder herein",
      normalize.classify_category("Festival", "Board-Game-Abend") == "sonstiges")

# --- Doppelungen zwischen Quellen (app/dedup.py) ---------------------------
from app import dedup  # noqa: E402


def _ev(uid, source, title, venue, time="23:00", day="2026-09-05", first_seen="2026-09-01"):
    return {"uid": uid, "source": source, "date": day, "time": time,
            "title": title, "venue": venue, "first_seen": first_seen}


# Der reale Fall: dieselbe Nacht, andere Schreibweise auf beiden Seiten.
_pair = [
    _ev("r1", "rauze", "Pangaea Invites", "Sektor Evolution", "23:00"),
    _ev("a1", "ra", "Pangaea invites w/ Xiorro", "Sektor Evolution", "23:00"),
]
_map = dedup.find_duplicates(_pair)
check("Dedup: Rauze/RA-Paar erkannt", set(_map) == {"a1"})
check("Dedup: Rauze gewinnt gegen RA", _map["a1"][0] == "r1")
check("Dedup: Grund wird protokolliert", _map["a1"][2] == "ort+titel")

# Der eigentliche Zweck der Sektor-Quelle: bei derselben Nacht muss der Eintrag
# des Hauses gewinnen, damit der Newsletter auf sektor-evolution.de verlinkt.
_se_pair = [
    _ev("s1", "sektor", "Pangaea invites", "Sektor Evolution", "23:00"),
    _ev("a2", "ra", "Pangaea invites w/ Xiorro", "Sektor Evolution", "23:00"),
    _ev("r2", "rauze", "Pangaea Invites", "Sektor Evolution", "23:00"),
]
_se_map = dedup.find_duplicates(_se_pair)
check("Dedup: Sektor gewinnt gegen RA und Rauze",
      set(_se_map) == {"a2", "r2"} and {v[0] for v in _se_map.values()} == {"s1"})

# Real am 22.08.2026 bei "GLUT x ELOS": Kulturkalender und Sektor lieferten die
# Nacht wortgleich, fielen also schon ueber die uid in EINE Zeile - in
# events.source stand der Erstlieferant (kulturkalender). Ohne _best_rank()
# verlor diese Zeile gegen den RA-Eintrag und der Newsletter verlinkte wieder
# ra.co, obwohl der Link des Hauses laengst in der Zeile stand.
_shared_row = dict(_ev("k1", "kulturkalender", "GLUT x ELOS", "Sektor Evolution", "22:00"),
                   sources=["kulturkalender", "sektor"])
_shared_map = dedup.find_duplicates(
    [_shared_row, _ev("a3", "ra", "GLUT x ELOS", "Sektor Evolution", "23:00")]
)
check("Dedup: gemeinsame Zeile zaehlt mit ihrer besten Quelle",
      _shared_map.get("a3", (None,))[0] == "k1")
check("Dedup: ohne Quellenliste bleibt events.source massgeblich",
      dedup._best_rank({"source": "ra"}) == dedup._source_rank("ra"))

# Ortsschreibweisen, die dieselbe Location meinen.
check("Dedup: 'OKA' == 'objekt klein a'",
      dedup._venue_key("OKA") == dedup._venue_key("objekt klein a"))
check("Dedup: 'Club Paula' == 'Paula'",
      dedup._venue_key("Club Paula") == dedup._venue_key("Paula"))
check("Dedup: 'Chemiefabrik e.V.' == 'Chemiefabrik'",
      dedup._venue_key("Chemiefabrik e.V.") == dedup._venue_key("Chemiefabrik"))
check("Dedup: 'TBA' zaehlt als unbekannter Ort", dedup._venue_key("TBA") == "")

# Einlass vs. Beginn darf zusammenfallen, ein anderer Termin nicht.
check("Dedup: 30 min Unterschied ist dasselbe Event",
      dedup.match(_ev("r2", "rauze", "Cats & Dogs", "Ostpol", "22:00"),
                  _ev("a2", "ra", "Cats & Dogs", "Ostpol", "22:30")) is not None)
check("Dedup: 3 h Unterschied ist ein anderer Termin",
      dedup.match(_ev("r3", "rauze", "Cats & Dogs", "Ostpol", "19:00"),
                  _ev("a3", "ra", "Cats & Dogs", "Ostpol", "22:00")) is None)
check("Dedup: Abstand wird ueber Mitternacht gemessen",
      dedup.match(_ev("r4", "rauze", "Nachtschicht", "Ostpol", "23:30"),
                  _ev("a4", "ra", "Nachtschicht", "Ostpol", "00:30")) is not None)

# Grundregel: zwei Eintraege DERSELBEN Quelle sind nie eine Doppelung -
# sonst wuerde die 11:00- und die 15:00-Fuehrung zu einer verschmelzen, und
# gleichnamige Termine am selben Abend gingen verloren.
_same_source = [
    _ev("k1", "kulturkalender", "Führung durch die Ausstellung", "Albertinum", "11:00"),
    _ev("k2", "kulturkalender", "Führung durch die Ausstellung", "Albertinum", "15:00"),
]
check("Dedup: gleiche Quelle wird nie verschmolzen", dedup.find_duplicates(_same_source) == {})

# Verschiedene Veranstaltungen am selben Abend im selben Laden.
_different = [
    _ev("r5", "rauze", "MODUS: Akua", "objekt klein a", "23:00"),
    _ev("a5", "ra", "MODUS: Anetha", "objekt klein a", "23:00"),
]
check("Dedup: ein gemeinsames Wort reicht nicht", dedup.find_duplicates(_different) == {})

# Verschiedene Orte: nur ein praktisch identischer Titel zaehlt.
check("Dedup: gleicher Titel, klar anderer Ort -> keine Doppelung",
      dedup.match(_ev("r6", "rauze", "Sommerfest im Hof", "Scheune", "20:00"),
                  _ev("a6", "ra", "Sommerfest am Fluss", "Chemiefabrik", "20:00")) is None)

# Drei Quellen, dieselbe Nacht: es darf genau ein Eintrag uebrig bleiben.
_triple = [
    _ev("k7", "kulturkalender", "Sachsentrance Sommerfest", "objekt klein a", "21:00"),
    _ev("a7", "ra", "Sachsentrance Sommerfest", "OKA", "21:00"),
    _ev("r7", "rauze", "Sachsentrance Sommerfest", "objekt klein a", "21:00"),
]
_map3 = dedup.find_duplicates(_triple)
check("Dedup: Dreiergruppe faellt auf einen Eintrag zusammen", len(_map3) == 2)
check("Dedup: Gewinner ist die Quelle mit hoechster Prioritaet (rauze)",
      {v[0] for v in _map3.values()} == {"r7"})

# Die einzige Ausnahme von "gleiche Quelle wird nie verschmolzen": das Line-up
# einer Veranstaltung, das CyberSAX Zeile fuer Zeile liefert. scrapers/cybersax
# haengt dazu einen Sammel-Eintrag an, der den Veranstaltungsnamen als Titel UND
# als raw_category traegt - daran wird die Gruppe hier erkannt.
def _slot(uid, title, time, raw_category="Klang&Kruste", venue="Alaunpark",
          source="cybersax", day="2026-08-22"):
    return dict(_ev(uid, source, title, venue, time, day=day),
                raw_category=raw_category)


_lineup = [
    _slot("c0", "Klang&Kruste", "10:00"),          # der Sammel-Eintrag
    _slot("c1", "DJ Pappenheimer", "10:00"),
    _slot("c2", "leuri303", "12:30"),
    _slot("c3", "Micro7oft aka STACHY.DJ", "22:00"),
]
_lineup_map = dedup.find_duplicates(_lineup)
check("Dedup: Line-up haengt am Sammel-Eintrag",
      set(_lineup_map) == {"c1", "c2", "c3"}
      and {v[0] for v in _lineup_map.values()} == {"c0"})
check("Dedup: Grund der Line-up-Gruppe wird protokolliert",
      _lineup_map["c2"][2] == dedup.MATCH_REASON_HEADING)

# Rauze liefert denselben Tag als EIN Event mit Permalink - dieser Eintrag muss
# gewinnen, sonst verlinkt der Newsletter auf die CyberSAX-Tagesliste.
_lineup_with_rauze = _lineup + [
    _ev("rk", "rauze", "Klang & Kruste", "Location siehe Beschreibung", "10:00",
        day="2026-08-22"),
]
_lineup_map2 = dedup.find_duplicates(_lineup_with_rauze)
check("Dedup: Rauze gewinnt gegen den Sammel-Eintrag",
      set(_lineup_map2) == {"c0", "c1", "c2", "c3"}
      and {v[0] for v in _lineup_map2.values()} == {"rk"})

# Verschiebt die Quelle den Beginn, entsteht ein zweiter Sammel-Eintrag (die
# Startzeit steckt in der uid). Der fruehere gewinnt, der alte verschwindet.
_two_umbrellas = _lineup + [_slot("c0b", "Klang&Kruste", "11:00")]
_map_two = dedup.find_duplicates(_two_umbrellas)
check("Dedup: aelterer Sammel-Eintrag haengt sich unter den frueheren",
      _map_two.get("c0b", (None,))[0] == "c0")

# Gegenprobe zur Ausnahme: gleiche Rohkategorie und gleicher Ort allein
# reichen NICHT - ohne Sammel-Eintrag bleibt jede Zeile ein eigener Termin.
check("Dedup: ohne Sammel-Eintrag bleibt jede Zeile eigenstaendig",
      dedup.find_duplicates([_slot("c4", "DJ Pappenheimer", "10:00"),
                             _slot("c5", "leuri303", "12:30")]) == {})
# Und eine Rubrik als Rohkategorie darf nie eine Gruppe bilden - sonst wuerde
# ein Konzert, das zufaellig "Musik" heisst, den ganzen Abend im selben Laden
# einsammeln.
check("Dedup: Rubrik-Rohkategorie bildet keine Gruppe",
      dedup.find_duplicates([_slot("c6", "Musik", "20:00", raw_category="Musik",
                                   venue="Blue Note"),
                             _slot("c7", "Trio Elf", "22:00", raw_category="Musik",
                                   venue="Blue Note")]) == {})

# Zwei Spielorte desselben Festivaltags sind zwei Termine. Real am 13.09.2026:
# der "Tag des Offenen Denkmals" hat sieben Denkmaeler mit je eigenem Programm -
# ueber die Titel-Regel (verschiedene Orte, identischer Titel) waeren sie sonst
# zu einem einzigen Eintrag verkettet.
_denkmal = [
    _slot("d1", "Tag des Offenen Denkmals", "10:00",
          raw_category="Tag des Offenen Denkmals", venue="Kügelgenhaus",
          day="2026-09-13"),
    _slot("d2", "Tag des Offenen Denkmals", "11:00",
          raw_category="Tag des Offenen Denkmals", venue="Eliasfriedhof",
          day="2026-09-13"),
]
check("Dedup: Sammel-Eintraege verschiedener Orte bleiben getrennt",
      dedup.find_duplicates(_denkmal) == {})
# Ein unbekannter Ort auf der Gegenseite (Rauze: "Location siehe Beschreibung")
# muss dagegen weiter zusammenfallen - sonst stuende Klang & Kruste doppelt.
check("Dedup: Sammel-Eintrag faellt mit unbekanntem Ort weiter zusammen",
      dedup.match(_slot("d3", "Klang&Kruste", "10:00"),
                  _ev("d4", "rauze", "Klang & Kruste", "Location siehe Beschreibung",
                      "10:00", day="2026-08-22")) is not None)

# Verschiedene Tage bleiben getrennt, auch bei identischem Titel/Ort.
check("Dedup: anderer Tag -> keine Doppelung",
      dedup.find_duplicates([
          _ev("r8", "rauze", "Techno Tuesday", "Ostpol", "22:00", day="2026-09-01"),
          _ev("a8", "ra", "Techno Tuesday", "Ostpol", "22:00", day="2026-09-08"),
      ]) == {})


# --- Doppelungen in der DB: ausblenden, auffuellen, wieder loesen -----------
with db.get_conn() as conn:
    db.upsert_events(conn, [
        {"uid": "dup-rauze", "source": "rauze", "date": "2026-09-05", "time": "23:00",
         "title": "Pangaea Invites", "venue": "Sektor Evolution", "category": "musik",
         "raw_category": "Party", "url": "https://www.rauze.de/pangaea"},
        {"uid": "dup-ra", "source": "ra", "date": "2026-09-05", "time": "23:00",
         "title": "Pangaea invites w/ Xiorro", "venue": "Sektor Evolution",
         "category": "musik", "raw_category": "Club", "url": "https://ra.co/events/1",
         "image_url": "https://images.ra.co/flyer.jpg", "price_text": "18 €",
         "description": "Line-up: Xiorro, OLIV", "detail_fetched_at": "2026-09-01T10:00:00"},
    ])
    _linked = dedup.link_duplicates(conn, "2026-09-05", "2026-09-05")
    check("Dedup-DB: eine Doppelung verbucht", _linked == 1)

    _visible = db.events_for_range(conn, "2026-09-05", "2026-09-05")
    check("Dedup-DB: nur ein Eintrag wird ausgeliefert", len(_visible) == 1)
    check("Dedup-DB: ausgeliefert wird die Rauze-Version",
          _visible[0]["uid"] == "dup-rauze")
    check("Dedup-DB: RA-Eintrag bleibt abrufbar",
          len(db.events_for_range(conn, "2026-09-05", "2026-09-05",
                                  include_duplicates=True)) == 2)

    _canonical = _visible[0]
    check("Dedup-DB: fehlendes Bild aus dem Duplikat gefuellt",
          _canonical["image_url"] == "https://images.ra.co/flyer.jpg")
    check("Dedup-DB: fehlender Preis aus dem Duplikat gefuellt",
          _canonical["price_text"] == "18 €")
    check("Dedup-DB: fehlende Beschreibung aus dem Duplikat gefuellt",
          _canonical["description"] == "Line-up: Xiorro, OLIV")
    check("Dedup-DB: uebernommene Beschreibung gilt als geladen "
          "(sonst wuerde das Detail-Popup sie wieder ausnullen)",
          bool(_canonical["detail_fetched_at"]))
    check("Dedup-DB: eigene URL wird NICHT ueberschrieben",
          _canonical["url"] == "https://www.rauze.de/pangaea")

    _tracked = db.duplicates_for_range(conn, "2026-09-05", "2026-09-05")
    check("Dedup-DB: Doppelung ist protokolliert", len(_tracked) == 1)
    check("Dedup-DB: Protokoll nennt beide Quellen",
          _tracked[0]["duplicate_source"] == "ra"
          and _tracked[0]["canonical_source"] == "rauze")
    check("Dedup-DB: Protokoll nennt die Aehnlichkeit",
          0 < _tracked[0]["match_score"] <= 1)
    check("Dedup-DB: Zaehlung je Quellenpaar",
          any(c["duplicate_source"] == "ra" and c["n"] == 1
              for c in db.duplicate_counts(conn)))

    # Zweiter Lauf darf nichts verdoppeln oder umhaengen.
    check("Dedup-DB: erneuter Lauf ist idempotent",
          dedup.link_duplicates(conn, "2026-09-05", "2026-09-05") == 1)
    check("Dedup-DB: weiterhin genau ein Protokolleintrag",
          len(db.duplicates_for_range(conn, "2026-09-05", "2026-09-05")) == 1)

    # Like auf die ausgeblendete Version: der Favorit darf nicht verschwinden,
    # sondern zeigt auf den Eintrag, der sie ersetzt.
    db.set_reaction(conn, "dup-ra", "like")
    _liked_uids = [e["uid"] for e in db.liked_events(conn)]
    check("Dedup-DB: Like auf der Doppelung zeigt auf die sichtbare Version",
          "dup-rauze" in _liked_uids and "dup-ra" not in _liked_uids)

    # Aendert eine Quelle den Titel so stark, dass die Paarung nicht mehr
    # traegt, muss die Verknuepfung wieder aufgehen.
    conn.execute("UPDATE events SET title = ? WHERE uid = ?",
                 ("Ganz anderer Abend im Keller", "dup-ra"))
    check("Dedup-DB: nicht mehr passende Verknuepfung wird geloest",
          dedup.link_duplicates(conn, "2026-09-05", "2026-09-05") == 0)
    check("Dedup-DB: beide Eintraege wieder sichtbar",
          len(db.events_for_range(conn, "2026-09-05", "2026-09-05")) == 2)
    check("Dedup-DB: Protokoll ist mit geleert",
          db.duplicates_for_range(conn, "2026-09-05", "2026-09-05") == [])


# --- Line-up in der DB: eine Zeile fuer "Klang & Kruste" -------------------
# Der reale Fall vom 22.08.2026: CyberSAX listet zehn Programmpunkte im
# Alaunpark, rauze.de dieselbe Veranstaltung einmal - mit Permalink, aber mit
# "Location siehe Beschreibung" als Ort.
with db.get_conn() as conn:
    _kk_day = "2026-08-22"
    db.upsert_events(conn, [
        {"uid": "kk-rauze", "source": "rauze", "date": _kk_day, "time": "10:00",
         "title": "Klang & Kruste", "venue": "Location siehe Beschreibung",
         "category": "musik", "raw_category": "Sonstiges",
         "url": "https://www.rauze.de/klang-kruste-2026"},
        {"uid": "kk-sammel", "source": "cybersax", "date": _kk_day, "time": "10:00",
         "title": "Klang&Kruste", "venue": "Alaunpark", "category": "musik",
         "raw_category": "Klang&Kruste", "url": "https://www.cybersax.de/terminal/day/2026/8/22/",
         "description": "Line-up: 10:00 DJ Pappenheimer · 12:30 leuri303"},
        {"uid": "kk-slot1", "source": "cybersax", "date": _kk_day, "time": "10:00",
         "title": "DJ Pappenheimer", "venue": "Alaunpark", "category": "musik",
         "raw_category": "Klang&Kruste", "url": "https://www.cybersax.de/terminal/day/2026/8/22/",
         "description": "Auftakt im Zelt"},
        {"uid": "kk-slot2", "source": "cybersax", "date": _kk_day, "time": "12:30",
         "title": "leuri303", "venue": "Alaunpark", "category": "sonstiges",
         "raw_category": "Klang&Kruste", "url": "https://www.cybersax.de/terminal/day/2026/8/22/"},
    ])
    # Andere Testabschnitte legen ebenfalls Eintraege auf diesen Tag - deshalb
    # wird hier auf die eigenen uids gefiltert statt auf den ganzen Tag.
    check("Line-up-DB: drei von vier Eintraegen ausgeblendet",
          dedup.link_duplicates(conn, _kk_day, _kk_day) >= 3)

    _kk_visible = [e for e in db.events_for_range(conn, _kk_day, _kk_day)
                   if e["uid"].startswith("kk-")]
    check("Line-up-DB: nur noch eine Zeile im Newsletter", len(_kk_visible) == 1)
    check("Line-up-DB: ausgeliefert wird die Rauze-Version mit Permalink",
          _kk_visible[0]["uid"] == "kk-rauze"
          and _kk_visible[0]["url"] == "https://www.rauze.de/klang-kruste-2026")
    # Ohne _upgrade_placeholder_venue hiesse die Zeile im Newsletter
    # "Klang & Kruste - Location siehe Beschreibung".
    check("Line-up-DB: Platzhalter-Ort durch den echten Ort ersetzt",
          _kk_visible[0]["venue"] == "Alaunpark")
    # Der Sammel-Eintrag wird vor den Einzelzeilen ausgewertet - sonst stuende
    # hier "Auftakt im Zelt" statt des Line-ups.
    check("Line-up-DB: Beschreibung ist das Line-up, nicht die eines Slots",
          _kk_visible[0]["description"] == "Line-up: 10:00 DJ Pappenheimer · 12:30 leuri303")
    check("Line-up-DB: Einzelzeilen bleiben abrufbar",
          len([e for e in db.events_for_range(conn, _kk_day, _kk_day, include_duplicates=True)
               if e["uid"].startswith("kk-")]) == 4)
    _kk_again = dedup.link_duplicates(conn, _kk_day, _kk_day)
    check("Line-up-DB: erneuter Lauf ist idempotent",
          _kk_again >= 3
          and [e["uid"] for e in db.events_for_range(conn, _kk_day, _kk_day)
               if e["uid"].startswith("kk-")] == ["kk-rauze"])


# --- Deckungsgleiche Lieferungen: gleiche uid, mehrere Quellen -------------
# Die aeltere, bis dahin unsichtbare Art von Doppelung: schreiben zwei Quellen
# Datum/Zeit/Titel/Ort identisch, entsteht dieselbe uid und die zweite
# Lieferung aktualisiert nur die erste Zeile. Es gibt also nichts auszublenden,
# gezaehlt werden muss es trotzdem (real: "Creatures of the Night" stand am
# 22.08.2026 wortgleich auf rauze.de und auf ra.co).
_shared = {
    "uid": "shared-1", "source": "rauze", "date": "2026-09-06", "time": "22:00",
    "title": "Creatures of the Night", "venue": "objekt klein a",
    "category": "musik", "raw_category": "Party",
}
with db.get_conn() as conn:
    db.upsert_events(conn, [_shared])
    check("Quellen-Buch: eine Quelle nach dem ersten Lauf",
          db.sources_for_event(conn, "shared-1") == ["rauze"])
    check("Quellen-Buch: noch keine Doppelung",
          db.shared_uid_events(conn, "2026-09-06", "2026-09-06") == [])

    db.upsert_events(conn, [dict(_shared, source="ra",
                                 price_text="12 €", url="https://ra.co/events/2")])
    check("Quellen-Buch: zweite Quelle wird mitgeschrieben",
          sorted(db.sources_for_event(conn, "shared-1")) == ["ra", "rauze"])

    _shared_rows = db.shared_uid_events(conn, "2026-09-06", "2026-09-06")
    check("Quellen-Buch: deckungsgleiche Doppelung wird gezaehlt", len(_shared_rows) == 1)
    check("Quellen-Buch: beide Quellen im Protokoll",
          sorted(_shared_rows[0]["sources"].split(",")) == ["ra", "rauze"])
    check("Quellen-Buch: Eintrag bleibt genau einmal sichtbar",
          len(db.events_for_range(conn, "2026-09-06", "2026-09-06")) == 1)
    check("Quellen-Buch: erste Quelle bleibt die fuehrende",
          db.events_for_range(conn, "2026-09-06", "2026-09-06")[0]["source"] == "rauze")

    # Dritter Lauf derselben Quellen darf nichts verdoppeln.
    db.upsert_events(conn, [_shared])
    check("Quellen-Buch: erneuter Lauf bleibt bei zwei Quellen",
          len(db.sources_for_event(conn, "shared-1")) == 2)

    # Welcher Link in der gemeinsamen Zeile steht, darf NICHT davon abhaengen,
    # welche Quelle im Lauf zuletzt dran war, sondern von SOURCE_PRIORITY -
    # sonst zeigte derselbe Termin je nach Reihenfolge mal auf das Haus, mal
    # auf einen Aggregator (siehe db._keeps_own_url).
    _link_event = {
        "uid": "link-1", "source": "sektor", "date": "2026-09-07", "time": "23:00",
        "title": "Zappelkiste", "venue": "Sektor Evolution",
        "category": "musik", "raw_category": "Club",
    }
    db.upsert_events(conn, [dict(_link_event, url="https://www.sektor-evolution.de/event/zappelkiste/")])
    db.upsert_events(conn, [dict(_link_event, source="ra", url="https://ra.co/events/9")])
    check("Link: schwaechere Quelle ueberschreibt den Link nicht",
          db.events_for_range(conn, "2026-09-07", "2026-09-07")[0]["url"]
          == "https://www.sektor-evolution.de/event/zappelkiste/")

    # Umgekehrt muss die bessere Quelle den Link uebernehmen duerfen, auch wenn
    # sie spaeter kommt.
    _link_event2 = dict(_link_event, uid="link-2", date="2026-09-08")
    db.upsert_events(conn, [dict(_link_event2, source="ra", url="https://ra.co/events/10")])
    db.upsert_events(conn, [dict(_link_event2, url="https://www.sektor-evolution.de/event/lbyrnth/")])
    check("Link: bessere Quelle setzt den Link auch nachtraeglich",
          db.events_for_range(conn, "2026-09-08", "2026-09-08")[0]["url"]
          == "https://www.sektor-evolution.de/event/lbyrnth/")

    # Ein noch leerer Link darf von jeder Quelle gefuellt werden.
    _link_event3 = dict(_link_event, uid="link-3", date="2026-09-09")
    db.upsert_events(conn, [_link_event3])
    db.upsert_events(conn, [dict(_link_event3, source="cybersax", url="https://www.cybersax.de/terminal/day/2026/9/9/")])
    check("Link: leerer Link wird auch von einer hinteren Quelle gefuellt",
          db.events_for_range(conn, "2026-09-09", "2026-09-09")[0]["url"]
          == "https://www.cybersax.de/terminal/day/2026/9/9/")


# --- Kurze Titel gegen lange Titel (der reale Rauze/RA-Unterschied) --------
# Alle drei Paare stammen aus dem Live-Abgleich vom 21.08.2026 und wurden von
# einer frueheren, strengeren Fassung uebersehen.
for _rauze_title, _ra_title, _venue_a, _venue_b in [
    ("Modus", "MODUS: Akua", "objekt klein a", "objekt klein a"),
    ("Sachsentrance", "Sachsentrance Sommerfest", "objekt klein a", "objekt klein a"),
    ("Bratty", "bratty with charli xcx & other brat coded artists dresden",
     "Paula", "Club Paula"),
]:
    check(f"Dedup: '{_rauze_title}' == '{_ra_title[:28]}'",
          dedup.match(_ev("x1", "rauze", _rauze_title, _venue_a, "23:00"),
                      _ev("x2", "ra", _ra_title, _venue_b, "23:00")) is not None)

# Ort auf beiden Seiten unbekannt: Rauze schreibt einen Platzhalter statt eines
# Ortes, RA "TBA". Dann muessen saemtliche Woerter des kuerzeren Titels im
# laengeren stecken (und beide Zeiten passen).
check("Dedup: Platzhalter-Ort zaehlt als unbekannt",
      dedup._venue_key("Location siehe Beschreibung") == "")
check("Dedup: gleiche Wortbasis bei unbekanntem Ort",
      dedup.match(_ev("y1", "rauze", "Rave X Riesling II", "Location siehe Beschreibung", "18:00"),
                  _ev("y2", "ra", "RAVE x RIESLING - Weingut Vincenz Richter", None, "18:00"))
      is not None)
check("Dedup: bei unbekanntem Ort reicht EIN gemeinsames Wort nicht",
      dedup.match(_ev("y3", "rauze", "Sommerfest", "Location siehe Beschreibung", "18:00"),
                  _ev("y4", "ra", "Sommerfest der Feuerwehr", None, "18:00")) is None)
check("Dedup: bei unbekanntem Ort zaehlt eine fehlende Uhrzeit nicht",
      dedup.match(_ev("y5", "rauze", "Rave X Riesling II", None, None),
                  _ev("y6", "ra", "RAVE x RIESLING - Weingut Vincenz Richter", None, "18:00"))
      is None)

# --- Einlass vs. Beginn beim Open Air (das breitere Zeitfenster) ------------
# Real am 21.08.2026: kulturkalender nennt den Beginn, rauze den Einlass, und
# dazwischen liegen zwei Stunden. Das Konzert stand deshalb zweimal im
# Newsletter. Gleicher Ort + praktisch deckungsgleicher Titel darf das
# 90-Minuten-Fenster auf MAX_TIME_DELTA_STRONG_MINUTES aufweiten.
check("Dedup: Einlass 17:00 / Beginn 19:00 ist dasselbe Open-Air-Konzert",
      dedup.match(_ev("w1", "rauze", "Wincent Weiss", "Filmnächte am Elbufer", "17:00"),
                  _ev("w2", "kulturkalender", "Wincent Weiss Sommertour 2026",
                      "FILMNÄCHTE AM ELBUFER", "19:00")) is not None)

# Das weitere Fenster gilt NUR bei starker Evidenz. Zwei Termine derselben
# Reihe unterscheiden sich im entscheidenden Wort (Wort-Ueberdeckung 0.5) und
# bleiben deshalb beim engen Fenster - auch am selben Ort.
check("Dedup: schwacher Titel bekommt das weite Zeitfenster nicht",
      dedup.match(_ev("w3", "rauze", "MODUS: Akua", "objekt klein a", "22:00"),
                  _ev("w4", "ra", "MODUS: Anetha", "OKA", "00:15")) is None)

# --- Kino als Ort (app/normalize._is_film_venue) ---------------------------
# Filmtitel enthalten kein Genre-Wort, und die Quellseite kennt fuer das
# Open-Air-Kino nur die Rohkategorie "Festival". Ohne die Ortsregel landete das
# komplette Filmprogramm in musik - dem Bucket mit den meisten Likes.
check("Kino: Filmtitel am Kino-Ort ist kultur, nicht musik",
      normalize.classify_category("Festival", "Sonnenallee", "FILMNÄCHTE AM ELBUFER") == "kultur")
check("Kino: auch das Rundkino zaehlt",
      normalize.classify_category("", "Zoomania 2", "Rundkino Dresden") == "kultur")
check("Kino: 'Filmnacht' rutscht nicht ueber 'nacht' in musik",
      normalize.classify_category("", "Hamnet Radeberger Filmnacht", None) == "kultur")
check("Kino: Filmmusik bleibt Musik",
      normalize.classify_category("", "Filmmusik-Gala des Orchesters", None) == "musik")
# Die Ortsregel greift erst, wenn die Quelle nichts Brauchbares gesagt hat:
# bei den Filmnaechten spielen auch echte Live-Acts.
check("Kino: ausdrueckliches 'Konzert' schlaegt die Ortsregel",
      normalize.classify_category("Konzert", "Wincent Weiss", "Filmnächte am Elbufer") == "musik")

# "Festival" darf nichts mehr entscheiden - die Quelle benutzt das Label als
# Sammelbecken (Vortraege, Workshops, Fuehrungen, Board-Game-Abend).
check("Festival entscheidet nicht mehr ueber die Kategorie",
      normalize.classify_category("Festival", "Bye Bye Beton - Vortrag zur Bauwende", None)
      == "kultur")

# --- sonstiges ist kein Lern-Feature (app/scoring.NEUTRAL_CATEGORIES) ------
# Vier Skips auf das Restfach des Klassifikators duerfen nicht 40% des Katalogs
# dauerhaft nach unten druecken.
check("Scoring: sonstiges liefert keinen Kategorie-Schluessel",
      not any(kind == "category"
              for kind, _, _ in scoring._feature_keys(
                  {"category": "sonstiges", "title": "Irgendwas", "venue": None})))
check("Scoring: echte Kategorien liefern weiterhin einen Schluessel",
      any(kind == "category"
          for kind, _, _ in scoring._feature_keys(
              {"category": "musik", "title": "Irgendwas", "venue": None})))

# --- Hervorhebung hoch bewerteter Events im Web (config.HIGHLIGHT_SCORE) ----
# Die Schwelle wird an EINER Stelle gesetzt und muss durch beide Render-Pfade
# der Vorlage laufen. Vergisst einer davon highlight_score, ist die Konstante im
# Browser undefined - jeder Vergleich damit ist false, und die Hervorhebung
# bliebe still aus, ohne dass irgendwo ein Fehler auftaucht.
check("Highlight: Schwelle ist eine ganze Zahl", isinstance(config.HIGHLIGHT_SCORE, int))
check("Highlight: Schwelle liegt im Score-Bereich", 0 <= config.HIGHLIGHT_SCORE <= 100)

_ROOT = os.path.dirname(os.path.abspath(__file__))
# Der gelebte Wert kommt aus der .env und ist auf dem Pi bewusst niedriger,
# deshalb wird hier der Standard im Code festgenagelt statt der Laufzeitwert.
check("Highlight: Standard im Code ist 80",
      '_int("HIGHLIGHT_SCORE", 80)' in
      open(os.path.join(_ROOT, "app", "config.py"), encoding="utf-8").read())

_client_web = web.app.test_client()
_page = _client_web.get("/").get_data(as_text=True)


def _bundle(html, asset_dir):
    """Seite PLUS die Dateien, die sie einbindet. Seit dem Umbau steht das
    Frontend nicht mehr in einer Datei; geprueft wird weiter genau das, was im
    Browser ankommt - und nebenbei, dass jede verlinkte Datei auch da ist.

    P5b: die Flask-Seite verlinkt Assets seither ABSOLUT ("/static/...", ueber
    web.api_urls()) statt relativ ("static/..."), damit sie auch von den neu
    hinzugekommenen, tiefer liegenden Routen (/orte/<slug>) aus stimmen - der
    statische Export bleibt bei relativen Pfaden (tools/export_static.py:
    _static_urls), das Muster erlaubt deshalb beides."""
    parts = [html]
    for name in re.findall(r'(?:src|href)="/?static/([A-Za-z0-9_.-]+)\?', html):
        with open(os.path.join(asset_dir, name), encoding="utf-8") as handle:
            parts.append(handle.read())
    return "\n".join(parts)


_page_all = _bundle(_page, os.path.join(_ROOT, "app", "static"))

# Die Vorlage verlinkt genau diese Dateien - fehlt eine davon im Container,
# ist die Seite weiss, ohne dass irgendwo ein Fehler steht. Seit c27a84a
# (Kalender-Popover) kommen die drei flatpickr-Dateien dazu; die Liste ist die
# einzige Stelle, die eine neue Datei kennen muss - Serve-Check und Anzahl
# leiten sich beide von ihr ab, damit sie nie wieder auseinanderlaufen.
_LINKED_ASSETS = ("boot.js", "app.css", "app.js", "background.js", "rating.js",
                  "flatpickr.min.js", "flatpickr.min.css", "flatpickr-de.js")
for _asset in _LINKED_ASSETS:
    check(f"Flask liefert static/{_asset} aus",
          _client_web.get("/static/" + _asset).status_code == 200)
check(f"Seite verlinkt alle {len(_LINKED_ASSETS)} Dateien",
      len(re.findall(r'(?:src|href)="/?static/', _page)) == len(_LINKED_ASSETS))
# Ohne Cache-Buster holte der Browser nach einem Deploy weiter die alte Datei.
check("Verweise tragen eine Version", '?v=' in _page and len(web.asset_version()) == 8)
check("Highlight: Flask-Seite setzt die Schwelle als Zahl",
      f"highlightScore: {config.HIGHLIGHT_SCORE}" in _page)
check("Highlight: Zeile bekommt bei hohem Score die Klasse top-pick",
      "'top-pick'" in _page_all and "HIGHLIGHT_SCORE" in _page_all)
check("Highlight: Einfaerbung wird von einem Label begleitet",
      "'Top-Treffer'" in _page_all and ".tag-pick {" in _page_all)

# Der statische Export rendert dieselbe Vorlage ein zweites Mal - ohne diese
# Zeile bliebe die oeffentliche Kopie ohne Schwelle zurueck.
check("Highlight: statischer Export reicht die Schwelle mit",
      "highlight_score=config.HIGHLIGHT_SCORE" in
      open(os.path.join(_ROOT, "tools", "export_static.py"), encoding="utf-8").read())


# --- statischer Export fuer GitHub Pages (tools/export_static.py) ----------
# Die oeffentliche Kopie ist read-only von Bauart wegen: sie hat keinen Server,
# an den eine Bewertung gehen koennte - bewerten kann nur, wer im Heimnetz die
# Flask-Seite aufmacht. Geprueft wird deshalb, dass der Export vollstaendig ist,
# die Seite wirklich im static-Modus rendert und nichts nachladen will.
sys.path.insert(0, os.path.join(_ROOT, "tools"))
import export_static  # noqa: E402

_export_today = _dt.date.today()
_export_dir = os.path.join(tempfile.mkdtemp(), "site")
with db.get_conn() as conn:
    db.upsert_events(conn, [{
        "uid": "static-heute", "source": "rauze", "date": _export_today.isoformat(),
        "time": "20:00", "title": "Konzert im Beatpol", "venue": "Beatpol",
        "category": "musik", "raw_category": "Konzert",
        "url": "https://example.org/beatpol", "description": "Ein Abend mit Gitarren.",
    }, {
        "uid": "static-spaeter", "source": "rauze",
        "date": (_export_today + _dt.timedelta(days=3)).isoformat(),
        "time": "19:00", "title": "Lesung im Kulturhaus", "venue": "Kulturhaus",
        "category": "kultur", "raw_category": "Lesung",
    }])

_stats = export_static.export(_export_dir, days_ahead=7, today=_export_today)
check("Export: beide Events exportiert", _stats["events"] >= 2)
check("Export: eine Datei je Tag", _stats["days"] >= 2)

_index = json.loads(open(os.path.join(_export_dir, "data", "index.json"), encoding="utf-8").read())
check("Export: index.json listet die Tage mit Version",
      all({"date", "count", "v"} <= set(d) for d in _index["days"]))
# P5b: die Quelle ist jetzt die categories-Tabelle (default_visible), nicht
# mehr config.EXCLUDED_CATEGORIES - siehe Kommentar dort. Nur 'fuehrungen' hat
# default_visible=0; 'familie' ist in der Tabelle sichtbar, obwohl die alte
# Liste es ausschloss (die Drift, die P5b aufgeloest hat).
with db.get_conn() as conn:
    _db_hidden = [c["slug"] for c in db.list_categories(conn) if not c["default_visible"]]
check("Export: index.json reicht die ausgeblendeten Kategorien mit (aus categories-Tabelle)",
      _index["excluded"] == _db_hidden == ["fuehrungen"])
check("Export: 'familie' ist NICHT mehr ausgeblendet (Drift zu EXCLUDED_CATEGORIES aufgeloest)",
      "familie" not in _index["excluded"] and "familie" in config.EXCLUDED_CATEGORIES)

_day = json.loads(open(os.path.join(_export_dir, "data", "days",
                                    f"{_export_today.isoformat()}.json"), encoding="utf-8").read())
_beatpol = [e for e in _day if e["uid"] == "static-heute"][0]
check("Export: Beschreibung liegt in der Tagesdatei (kein Nachladen noetig)",
      _beatpol["description"] == "Ein Abend mit Gitarren.")
# Bewertet wird nur im Heimnetz; oeffentlich geht nur das Ergebnis mit, damit
# die Empfehlungszeile und der "wenig relevant"-Filter dort ueberhaupt etwas
# rechnen koennen. Die Merkmalsschluessel (frueher Feld "fk") braucht der
# Browser seitdem nicht mehr.
check("Export: Score liegt in der Tagesdatei", isinstance(_beatpol["score"], (int, float)))
check("Export: Score liegt im gueltigen Bereich", 0 <= _beatpol["score"] <= 100)
check("Export: keine Merkmalsschluessel mehr im Export", "fk" not in _beatpol)
check("Export: leere Felder fliegen raus", "image_url" not in _beatpol)

_static_html = open(os.path.join(_export_dir, "index.html"), encoding="utf-8").read()
_static_all = _bundle(_static_html, os.path.join(_export_dir, "static"))
check("Export: Seite laeuft im static-Modus", 'mode: "static"' in _static_html)
# Der Export muss die Dateien mitnehmen, sonst liegt auf GitHub Pages eine Seite
# ohne Stylesheet und ohne Skripte.
check("Export: Stylesheet und Skripte liegen daneben",
      sorted(os.listdir(os.path.join(_export_dir, "static")))
      == sorted(web.PUBLIC_ASSETS))
check("Export: rating.js wird nicht mitkopiert",
      not os.path.exists(os.path.join(_export_dir, "static", "rating.js")))
# Der Kern der Rechte-Trennung: auf der oeffentlichen Kopie gibt es keine
# Bewerten-Buttons und keinen Aufruf, der eine Bewertung irgendwohin schickte.
check("Export: oeffentliche Seite kann nicht bewerten",
      "var CAN_RATE = MODE === 'api';" in _static_all and "/api/feedback" not in _static_all)
check("Export: keine Gast-Bewertung im localStorage mehr",
      "guestReact" not in _static_all and "guest.weights" not in _static_all.split("removeItem")[0])
check("Export: Empfehlungszeile heisst oeffentlich anders",
      "Empfehlungen der Woche" in _static_html and "Für dich diese Woche" not in _static_html)
check("Export: Seite bleibt aus Suchmaschinen raus",
      'name="robots" content="noindex, nofollow"' in _static_html)
check("Export: Seite liest die Tagesdateien statt der API",
      "data/index.json?v=" in _static_all and "data/days/" in _static_all)
check("Export: robots.txt verbietet das Crawlen",
      "Disallow: /" in open(os.path.join(_export_dir, "robots.txt"), encoding="utf-8").read())
check("Export: .nojekyll liegt daneben",
      os.path.exists(os.path.join(_export_dir, ".nojekyll")))

# Die Flask-Seite darf davon nichts abbekommen - sie ist die einzige, auf der
# eine Bewertung wirklich in der Datenbank landet.
check("Flask-Seite bleibt im api-Modus", 'mode: "api"' in _page)
check("Flask-Seite kann weiterhin bewerten",
      "/api/feedback" in _page_all and "Für dich diese Woche" in _page)

# Zweiter Lauf ohne Aenderung darf keine Datei anfassen, sonst traegt jeder
# Push neue Blobs in die Git-Historie.
_stats2 = export_static.export(_export_dir, days_ahead=7, today=_export_today)
check("Export: unveraenderte Tage werden nicht neu geschrieben", _stats2["days_written"] == 0)

# Ohne Aenderung darf auch der Zeitstempel nicht weiterlaufen: er steht in
# index.json UND in der Fussnote der Seite, ein neuer Wert waere also viermal
# taeglich ein Commit ueber index.html (~90 KB), ohne dass ein Event dazukam.
_stamp1 = json.loads(open(os.path.join(_export_dir, "data", "index.json"), encoding="utf-8").read())["generated_at"]
export_static.export(_export_dir, days_ahead=7, today=_export_today)
_stamp2 = json.loads(open(os.path.join(_export_dir, "data", "index.json"), encoding="utf-8").read())["generated_at"]
check("Export: unveraenderter Bestand behaelt den Zeitstempel", _stamp1 == _stamp2)

# Ein spaeterer Stichtag laesst die alten Tagesdateien aus dem Fenster laufen -
# die muessen verschwinden, sonst waechst das Repo endlos.
_stats3 = export_static.export(_export_dir, days_ahead=7,
                               today=_export_today + _dt.timedelta(days=30))
check("Export: abgelaufene Tagesdateien werden entfernt", _stats3["days_removed"] >= 2)


# --- Ortsfilter: Dresden, Speckguertel, weiter weg (app/geo.py) -------------
# Der Kulturkalender listet die ganze Region mit; rund 29% der Eintraege liegen
# ausserhalb der Stadtgrenze. Der Schalter "Umgebung einschliessen" im Web und
# der Newsletter trennen entlang genau dieser Zuordnung - liegt sie falsch,
# verschwindet ein Dresdner Termin lautlos aus Liste UND Digest.
from app import geo  # noqa: E402

check("Unbekannter Ort gilt als Dresden", geo.classify_region("Ostpol") == "dresden")
check("Ohne Ort gilt als Dresden", geo.classify_region("") == "dresden")
check("Ortsname im Namen -> weiter", geo.classify_region("Dom zu Meißen - Hochstift Meißen") == "weiter")
check("Zusammengesetzter Ortsname -> weiter", geo.classify_region("Parkhotel Bad Schandau") == "weiter")
check("Speckguertel -> umland", geo.classify_region("Volkssternwarte Radebeul") == "umland")
check("Haus ohne Ortsnamen im Titel -> umland",
      geo.classify_region("Schloss Wackerbarth (Sächs. Staatsweingut)") == "umland")

# Die Strassennamen-Falle: Dresden ist voll von Strassen, die nach dem
# Nachbarort heissen. Deshalb werden Ortsnamen als ganzes Wort geprueft - die
# abgeleitete Form ("pirnaer" statt "pirna") darf nicht zaehlen.
for _venue in ("Festplatz Pirnaer Landstraße / Ecke Moränenende",
               "Gedenkstätte Bautzner Straße Dresden",
               "Radeberger Biertheater",
               "Blaue Fabrik im Alten Leipziger Bahnhof"):
    check(f"Strassenname bleibt Dresden: {_venue}", geo.classify_region(_venue) == "dresden")
# Ausnahme von der Ausnahme: das riesa efau steht an der Adlergasse, nicht in Riesa.
check("riesa efau ist Dresden", geo.classify_region("riesa efau. Kultur Forum Dresden") == "dresden")
# Und der teuerste denkbare Fehltreffer: die Dresdner Neustadt ist nicht
# Neustadt in Sachsen - ein Treffer haette das halbe Nachtleben versteckt.
check("Dresdner Neustadt bleibt Dresden",
      geo.classify_region("Stadtteilhaus Äußere Neustadt") == "dresden")

with db.get_conn() as conn:
    db.upsert_events(conn, [
        {"uid": "geo-dd", "source": "rauze", "date": "2026-09-20", "time": "20:00",
         "title": "Konzert in der Scheune", "venue": "Scheune", "category": "musik"},
        {"uid": "geo-umland", "source": "kulturkalender", "date": "2026-09-20", "time": "19:00",
         "title": "Weinabend", "venue": "Schloss Wackerbarth (Sächs. Staatsweingut)",
         "category": "kultur"},
        {"uid": "geo-weiter", "source": "kulturkalender", "date": "2026-09-20", "time": "18:00",
         "title": "Orgelkonzert", "venue": "Dom zu Meißen - Hochstift Meißen",
         "category": "kultur"},
    ])
    _all = db.events_for_range(conn, "2026-09-20", "2026-09-20")
    check("events_for_range liefert die Ortszuordnung mit",
          {e["uid"]: e["region"] for e in _all} ==
          {"geo-dd": "dresden", "geo-umland": "umland", "geo-weiter": "weiter"})
    _near = db.events_for_range(conn, "2026-09-20", "2026-09-20", exclude_far=True)
    check("exclude_far wirft nur das Entfernte raus",
          sorted(e["uid"] for e in _near) == ["geo-dd", "geo-umland"])

# Der Export schreibt nur das Entfernte mit - Dresden ist der Normalfall und
# braucht kein Feld je Zeile (siehe app/feed.slim_event).
from app import feed  # noqa: E402

check("Export markiert entfernte Events",
      feed.slim_event({"uid": "x", "title": "t", "date": "2026-09-20",
                       "region": "weiter"}).get("region") == "weiter")
check("Export markiert Dresden nicht",
      "region" not in feed.slim_event({"uid": "x", "title": "t", "date": "2026-09-20",
                                       "region": "dresden"}))
# P5b/decision #12: seit dem neuen Regions-Schalter (Standard nur Dresden)
# muss die Exportdatei 'umland' GENAUSO vom Normalfall unterscheiden koennen
# wie 'weiter' - vorher liess slim_event Umland-Zeilen aussehen wie Dresden.
check("Export markiert jetzt auch Umland (P5b, vorher wie Dresden behandelt)",
      feed.slim_event({"uid": "x", "title": "t", "date": "2026-09-20",
                       "region": "umland"}).get("region") == "umland")

# Im Web haengt der Schalter im Filter-Menue und ist standardmaessig AUS.
# P5b/decision #12 aendert die Vorbelegung: vorher blieb Umland immer sichtbar
# und nur "weiter weg" hing am Schalter, jetzt ist der Standard NUR Dresden -
# Label und JS-Bedingung sind deshalb neu (siehe app/templates/index.html,
# app/static/app.js).
check("Web: Regions-Schalter ist da",
      'data-toggle="umgebung"' in _page and "Auch Umland &amp; Umgebung" in _page)
check("Web: Regions-Schalter ist standardmaessig aus (Standard: nur Dresden)",
      "umgebung: false" in _page_all)
check("Web: Umland UND 'weiter weg' werden ohne Schalter ausgeblendet",
      "e.region && e.region !== 'dresden' && !filters.umgebung" in _page_all)
check("Web: der Schalter gilt auch auf der oeffentlichen Kopie",
      'data-toggle="umgebung"' in _static_html)


# --- P5b: Kategorien/Tags aus der Tabelle, Venue-Seiten -----------------------
# Fixture: eine "angereicherte" Venue (Homepage/Cover/Beschreibung wie nach
# tools/load_enrichment.py), eine unangereicherte mit einem Event-Bild (fuer
# den Cover-Fallback), und ein Treffpunkt (bekommt laut Schema keine Seite).
with db.get_conn() as conn:
    db.upsert_events(conn, [
        {"uid": "p5b-enriched", "source": "kulturkalender", "date": "2026-09-25",
         "time": "20:00", "title": "Konzert im Testhaus", "venue": "P5b Testhaus",
         "category": "musik", "url": "https://example.org/testhaus-event"},
        {"uid": "p5b-thin", "source": "rauze", "date": "2026-09-26", "time": "21:00",
         "title": "Party im Testclub", "venue": "P5b Testclub", "category": "musik",
         "url": "https://example.org/testclub-event",
         "image_url": "https://cdn.example/testclub-event.jpg"},
        {"uid": "p5b-meeting", "source": "kulturkalender", "date": "2026-09-27",
         "time": "10:00", "title": "Stadtrundfahrt Test", "venue": "P5b Treffpunkt Test",
         "category": "fuehrungen", "url": "https://example.org/rundfahrt"},
    ])
    _enriched_slug = db.venue_slug("P5b Testhaus")
    _thin_slug = db.venue_slug("P5b Testclub")
    _meeting_slug = db.venue_slug("P5b Treffpunkt Test")
    conn.execute(
        """UPDATE venues SET homepage_url = ?, homepage_root = ?, og_image_url = ?,
             meta_description = ?, cover_source = 'kulturkalender', meta_status = 'ok'
           WHERE slug = ?""",
        ("https://testhaus.example/veranstaltungen/", "https://testhaus.example",
         "https://cdn.example/testhaus-cover.jpg", "Ein Testhaus fuer die Suite.",
         _enriched_slug),
    )
    conn.execute("UPDATE venues SET is_meeting_point = 1 WHERE slug = ?", (_meeting_slug,))

# --- categories/tags aus der Tabelle (ersetzt config.CATEGORY_LABELS/P4e) ---
with db.get_conn() as conn:
    _categories = db.list_categories(conn)
    _tags = db.list_tags(conn)
check("list_categories: enthaelt 'nightlife' (fehlte in config.CATEGORY_LABELS)",
      "nightlife" in {c["slug"] for c in _categories})
check("list_categories: sortiert nach sort_order",
      [c["sort_order"] for c in _categories] == sorted(c["sort_order"] for c in _categories))
check("list_categories: 'fuehrungen' hat default_visible=0, 'familie' hat 1",
      {c["slug"]: c["default_visible"] for c in _categories}["fuehrungen"] == 0
      and {c["slug"]: c["default_visible"] for c in _categories}["familie"] == 1)
check("list_tags: alle 5 Seed-Tags in TAG_LABELS-Reihenfolge",
      [t["slug"] for t in _tags] == list(normalize.TAG_LABELS))

# --- Venue-Aufloesung / Lesezugriffe (db.py) --------------------------------
with db.get_conn() as conn:
    _venue = db.get_venue_by_slug(conn, _enriched_slug)
    _thin_venue = db.get_venue_by_slug(conn, _thin_slug)
    _upcoming = db.venue_upcoming_events(conn, _venue["id"], "2026-09-01")
    _venues_list = db.list_venues(conn, "2026-09-01")
    _unknown_venue = db.get_venue_by_slug(conn, "gibt-es-nicht")
check("get_venue_by_slug findet die angereicherte Venue", _venue is not None)
check("get_venue_by_slug: unbekannter Slug liefert None", _unknown_venue is None)
check("venue_upcoming_events findet das anstehende Event",
      [e["uid"] for e in _upcoming] == ["p5b-enriched"])
check("list_venues laesst den Treffpunkt AUSSEN VOR (migrations §1)",
      _meeting_slug not in {v["slug"] for v in _venues_list})
check("list_venues zaehlt anstehende Termine mit",
      next(v for v in _venues_list if v["slug"] == _enriched_slug)["upcoming_count"] == 1)

# --- Events tragen venue_slug/tags, Treffpunkte keinen venue_slug -----------
with db.get_conn() as conn:
    _p5b_events = {e["uid"]: e for e in db.events_for_range(conn, "2026-09-25", "2026-09-27")}
check("events_for_range: normale Venue liefert venue_slug",
      _p5b_events["p5b-enriched"]["venue_slug"] == _enriched_slug)
check("events_for_range: Treffpunkt liefert KEINEN venue_slug (keine Seite dafuer)",
      _p5b_events["p5b-meeting"]["venue_slug"] is None)

with db.get_conn() as conn:
    _p5b_built = {e["uid"]: e for e in feed.build_events(
        conn, _dt.date(2026, 9, 25), _dt.date(2026, 9, 27))}
check("feed.build_events haengt tags als Liste an jedes Event",
      all(isinstance(e["tags"], list) for e in _p5b_built.values()))

# --- Cover-Reihenfolge (P5a: kk_cover_url/og_image_url vor Event-Bild-Fallback,
# NICHT umkehren) -------------------------------------------------------------
check("feed.venue_cover: og_image_url der Venue gewinnt, auch wenn ein Event ein Bild hat",
      feed.venue_cover(_venue, _upcoming) == "https://cdn.example/testhaus-cover.jpg")
with db.get_conn() as conn:
    _thin_upcoming = db.venue_upcoming_events(conn, _thin_venue["id"], "2026-09-01")
check("feed.venue_cover: ohne venues.og_image_url faellt es auf das Event-Bild zurueck",
      feed.venue_cover(_thin_venue, _thin_upcoming) == "https://cdn.example/testclub-event.jpg")
check("feed.venue_cover: ganz ohne Bild bleibt es None",
      feed.venue_cover({"og_image_url": None}, [{"image_url": None}]) is None)

# --- /orte und /orte/<slug> (Flask) ------------------------------------------
_orte_page = _client_web.get("/orte").get_data(as_text=True)
check("/orte listet die angereicherte Testvenue", "P5b Testhaus" in _orte_page)
check("/orte listet auch die unangereicherte Testvenue", "P5b Testclub" in _orte_page)
check("/orte laesst den Treffpunkt aussen vor", "P5b Treffpunkt Test" not in _orte_page)

_venue_page_resp = _client_web.get(f"/orte/{_enriched_slug}")
_venue_page = _venue_page_resp.get_data(as_text=True)
check("/orte/<slug> antwortet 200", _venue_page_resp.status_code == 200)
check("/orte/<slug>: Homepage-Knopf nutzt homepage_root, NICHT den Deep-Link aus homepage_url",
      'href="https://testhaus.example"' in _venue_page
      and "https://testhaus.example/veranstaltungen/" not in _venue_page)
check("/orte/<slug>: Cover kommt aus og_image_url",
      "https://cdn.example/testhaus-cover.jpg" in _venue_page)
check("/orte/<slug>: meta_description wird gezeigt",
      "Ein Testhaus fuer die Suite." in _venue_page)
check("/orte/<slug>: anstehendes Event ist gelistet",
      "Konzert im Testhaus" in _venue_page)

_thin_venue_page = _client_web.get(f"/orte/{_thin_slug}").get_data(as_text=True)
check("/orte/<slug> ohne Enrichment: kein Homepage-Knopf",
      "venue-homepage-btn" not in _thin_venue_page)
check("/orte/<slug> ohne Enrichment: Event-Bild fuellt das Cover (Fallback)",
      "https://cdn.example/testclub-event.jpg" in _thin_venue_page)

check("/orte/<Treffpunkt-slug> ist 404 (keine Seite fuer Treffpunkte)",
      _client_web.get(f"/orte/{_meeting_slug}").status_code == 404)
check("/orte/<unbekannt> ist 404", _client_web.get("/orte/gibt-es-nicht").status_code == 404)

# --- Event -> Venue-Link in der Hauptliste (app.js/index.html) --------------
check("index.html: Suchfeld ist da", 'id="search-input"' in _page)
check("index.html: Merkmal-Chips (Tags) sind da",
      all(f'data-tag="{slug}"' in _page for slug in normalize.TAG_LABELS))
check("index.html: 'Alle Orte'-Navigation ist da", 'href="/orte"' in _page)
check("app.js: Event-Zeile verlinkt auf die Venue-Seite (decision #4)",
      "venueHref" in _page_all and "orte/" in _page_all)
check("app.js: Suche filtert Titel UND Ort",
      "(e.title || '') + ' ' + (e.venue || '')" in _page_all)

# --- Statischer Export: Venue-Seiten fuer GitHub Pages ----------------------
_venues_export_dir = os.path.join(tempfile.mkdtemp(), "site-venues")
_venue_stats = export_static.export(_venues_export_dir, days_ahead=7, today=_export_today)
with db.get_conn() as conn:
    _expected_venue_count = len(db.list_venues(conn, _dt.date.today().isoformat()))
check("Export: Anzahl Venue-Seiten passt zu list_venues (Treffpunkte ausgenommen)",
      _venue_stats["venues"] == _expected_venue_count)
check("Export: orte/index.html wurde geschrieben",
      os.path.exists(os.path.join(_venues_export_dir, "orte", "index.html")))
check("Export: eine einzelne Venue-Seite wurde geschrieben",
      os.path.exists(os.path.join(_venues_export_dir, "orte", f"{_enriched_slug}.html")))
check("Export: der Treffpunkt bekommt KEINE Datei",
      not os.path.exists(os.path.join(_venues_export_dir, "orte", f"{_meeting_slug}.html")))

_exported_venue_html = open(
    os.path.join(_venues_export_dir, "orte", f"{_enriched_slug}.html"), encoding="utf-8"
).read()
check("Export: Venue-Seite laeuft im static-Modus (noindex)",
      'name="robots" content="noindex, nofollow"' in _exported_venue_html)
check("Export: Venue-Seite verlinkt CSS relativ (eine Ebene hoch)",
      'href="../static/app.css' in _exported_venue_html)
check("Export: Venue-Seite zeigt dasselbe Cover wie im Flask-Modus",
      "https://cdn.example/testhaus-cover.jpg" in _exported_venue_html)

# Zweiter Lauf ohne inhaltliche Aenderung darf keine Venue-Datei neu schreiben
# (dieselbe _write()-Vorsicht wie bei den Tagesdateien).
_venue_stats2 = export_static.export(_venues_export_dir, days_ahead=7, today=_export_today)
check("Export: unveraenderte Venue-Seiten werden nicht neu geschrieben",
      _venue_stats2["venues_written"] == 0)

# --- Schema-Deklaration: homepage_root/cover_source (siehe Bericht zu P5b) --
# P5a (commit b68c680) hat beide Spalten bereits in migrations/001_schema_v2.sql
# deklariert - eine frische DB braucht KEIN ALTER TABLE mehr. Die Behauptung im
# P5b-Paket ("nur per ALTER TABLE angelegt") reproduziert also nicht mehr.
with open(os.path.join(_ROOT, "migrations", "001_schema_v2.sql"), encoding="utf-8") as _f:
    _schema_sql = _f.read()
check("Schema: homepage_root ist in migrations/001_schema_v2.sql deklariert",
      "homepage_root   TEXT" in _schema_sql)
check("Schema: cover_source ist in migrations/001_schema_v2.sql deklariert",
      "cover_source    TEXT CHECK" in _schema_sql)
_fresh_db_dir = tempfile.mkdtemp()
_fresh_db_path = os.path.join(_fresh_db_dir, "fresh.db")
_fresh_conn = sqlite3.connect(_fresh_db_path)
_fresh_conn.executescript(_schema_sql)
_fresh_cols = {row[1] for row in _fresh_conn.execute("PRAGMA table_info(venues)")}
_fresh_conn.close()
check("Schema: eine frische DB aus der DDL hat beide Spalten ohne ALTER TABLE",
      {"homepage_root", "cover_source"} <= _fresh_cols)


# --- Zustand der Scraper: scrape_runs und /api/health ----------------------
# Der Nulltreffer ist der Fall, um den es geht: eine Quelle, die nach einer
# HTML-Aenderung 0 Events liefert, darf NICHT als erfolgreich gelten - sonst
# wandert der "letzter Erfolg"-Zeitstempel mit und der Ausfall bleibt unsichtbar.
with db.get_conn() as conn:
    db.record_scrape_run(conn, "sektor", "2026-08-22T10:00:00", "2026-08-22T10:00:20",
                         ok=True, event_count=12)
    db.record_scrape_run(conn, "sektor", "2026-08-23T10:00:00", "2026-08-23T10:00:05",
                         ok=False, event_count=0, error="0 Events, zuletzt waren es 12.")
    db.record_scrape_run(conn, "ra", "2026-08-23T10:01:00", "2026-08-23T10:01:03",
                         ok=False, error="RuntimeError('kaputt')")

    check("last_successful_run ueberspringt den Fehllauf",
          db.last_successful_run(conn, "sektor")["event_count"] == 12)
    check("last_successful_run ohne je einen Erfolg -> None",
          db.last_successful_run(conn, "ra") is None)
    _health = db.scrape_health(conn)

check("scrape_health listet alle Quellen, auch nie gelaufene",
      sorted(_health) == sorted(config.SOURCE_LABELS))
check("scrape_health: letzter Erfolg bleibt beim alten Lauf stehen",
      _health["sektor"]["ok"] is False and _health["sektor"]["event_count"] == 12
      and _health["sektor"]["last_success"] == "2026-08-22T10:00:20")
check("scrape_health: nie gelaufene Quelle ist leer, nicht abwesend",
      _health["cybersax"]["last_run"] is None and _health["cybersax"]["ok"] is False)

_health_json = web.app.test_client().get("/api/health").get_json()
check("/api/health liefert alle zehn Quellen", len(_health_json) == 10)
check("/api/health nennt Klartext-Namen und Fehlertext",
      _health_json["ra"]["label"] == "Resident Advisor"
      and "kaputt" in _health_json["ra"]["error"])

# --- Verwaiste Events (app/db.py: find_orphaned_events / expire_orphaned_events) ---
# uid haengt an date|time|title|venue - eine korrigierte Startzeit erzeugt also
# eine ZWEITE Zeile statt die erste zu aktualisieren. Die alte bleibt liegen:
# last_seen wird nie wieder geschrieben. Getestet werden alle drei Schutz-
# klauseln aus dem Modul-Kommentar, nicht nur der Normalfall.
with db.get_conn() as conn:
    _heute = "2026-08-23"
    db.upsert_events(conn, [{
        "uid": "verwaist-zukunft", "source": "azconni", "date": "2026-09-01",
        "time": "20:00", "title": "Verwaistes Zukunftsevent", "venue": "Testort",
        "category": "musik", "raw_category": "Test",
    }])
    # Identischer Fall, nur in der Vergangenheit - darf NIE als verwaist gelten,
    # vergangene Events sind historischer Bestand.
    db.upsert_events(conn, [{
        "uid": "verwaist-vergangen", "source": "azconni", "date": "2026-08-01",
        "time": "20:00", "title": "Verwaistes Vergangenheitsevent", "venue": "Testort",
        "category": "musik", "raw_category": "Test",
    }])
    # Zukuenftiges Event derselben Quelle, das weiterhin gesehen wird.
    db.upsert_events(conn, [{
        "uid": "frisch-zukunft", "source": "azconni", "date": "2026-09-02",
        "time": "20:00", "title": "Frisches Zukunftsevent", "venue": "Testort",
        "category": "musik", "raw_category": "Test",
    }])
    # Die beiden "verwaist"-Zeilen kuenstlich vor die naechsten 3 erfolgreichen
    # Laeufe zurueckdatieren - "frisch-zukunft" behaelt sein last_seen von
    # gerade eben und bleibt damit nach dem letzten Lauf.
    # Seit P3b-1 zaehlt event_sources.last_seen (pro Quelle), nicht mehr
    # events.last_seen (nur die zuletzt beliebige Quelle) - beide zurueckdatieren.
    conn.execute("UPDATE events SET last_seen = ? WHERE uid IN (?, ?)",
                 ("2026-08-20T09:00:00", "verwaist-zukunft", "verwaist-vergangen"))
    conn.execute("UPDATE event_sources SET last_seen = ? WHERE event_uid IN (?, ?)",
                 ("2026-08-20T09:00:00", "verwaist-zukunft", "verwaist-vergangen"))
    for _tag in range(21, 25):
        db.record_scrape_run(conn, "azconni", f"2026-08-{_tag}T09:30:00",
                             f"2026-08-{_tag}T09:30:05", ok=True, event_count=1)

    _orphaned = db.find_orphaned_events(conn, _heute, threshold_runs=3)

check("find_orphaned_events: nur die zukuenftige verwaiste Zeile",
      [r["uid"] for r in _orphaned.get("azconni", [])] == ["verwaist-zukunft"])
check("find_orphaned_events: vergangene Zeile bleibt unangetastet",
      "verwaist-vergangen" not in [r["uid"] for r in _orphaned.get("azconni", [])])
check("find_orphaned_events: weiterhin gesehene Zeile bleibt draussen",
      "frisch-zukunft" not in [r["uid"] for r in _orphaned.get("azconni", [])])
check("find_orphaned_events: Quelle mit nicht-ok letztem Lauf wird uebersprungen "
      "(sonst wuerde ein Ausfall die komplette Zukunft der Quelle raeumen)",
      "sektor" not in _orphaned and "ra" not in _orphaned)
# P3b-1: der Schluessel kommt aus event_sources, nicht aus events.source. Hier
# hat die Zeile genau eine Quelle, beide Wege ergaeben "azconni" - deshalb wird
# zusaetzlich geprueft, dass eine zweite, weiterhin liefernde Quelle die Zeile
# heraushaelt UND den Schluessel aendert.
with db.get_conn() as conn:
    db.upsert_events(conn, [{
        "uid": "verwaist-zukunft", "source": "kulturkalender", "date": "2026-09-01",
        "time": "20:00", "title": "Verwaistes Zukunftsevent", "venue": "Testort",
        "category": "musik", "raw_category": "Test",
    }])
    for _tag in range(21, 25):
        db.record_scrape_run(conn, "kulturkalender", f"2026-08-{_tag}T09:30:00",
                             f"2026-08-{_tag}T09:30:05", ok=True, event_count=1)
    _mit_zweiter = db.find_orphaned_events(conn, _heute, threshold_runs=3)
check("P3b-1: eine zweite, frisch liefernde Quelle rettet die Zeile "
      "(azconni ist auf ihr veraltet, kulturkalender nicht)",
      not any("verwaist-zukunft" in [r["uid"] for r in rows]
              for rows in _mit_zweiter.values()))

# Nicht-Leerheit 1: eine Zeile ganz ohne event_sources ist NICHT verwaist.
# "alle gesunden Quellen sind veraltet" waere ueber der leeren Menge wahr.
with db.get_conn() as conn:
    conn.execute("DELETE FROM event_sources WHERE event_uid = 'verwaist-zukunft'")
    _ohne_quellen = db.find_orphaned_events(conn, _heute, threshold_runs=3)
check("P3b-1: Zeile ohne jeden event_sources-Eintrag gilt nie als verwaist",
      not any("verwaist-zukunft" in [r["uid"] for r in rows]
              for rows in _ohne_quellen.values()))

# Nicht-Leerheit 2: sind ALLE Quellen einer Zeile gerade ausgefallen, gilt sie
# ebenfalls nicht als verwaist - niemand kann dann beurteilen, ob das Event weg
# ist oder nur die Quelle. Ohne diese Klausel waere die neue Erkennung hier
# schaerfer als die alte.
with db.get_conn() as conn:
    db.upsert_events(conn, [{
        "uid": "nur-ausgefallene-quelle", "source": "azconni", "date": "2026-09-03",
        "time": "20:00", "title": "Nur von einer ausgefallenen Quelle", "venue": "Testort",
        "category": "musik", "raw_category": "Test",
    }])
    conn.execute("UPDATE event_sources SET last_seen = ? WHERE event_uid = ?",
                 ("2026-08-20T09:00:00", "nur-ausgefallene-quelle"))
    db.record_scrape_run(conn, "azconni", "2026-08-25T09:30:00",
                         "2026-08-25T09:30:05", ok=False, error="simulierter Ausfall")
    _alle_krank = db.find_orphaned_events(conn, _heute, threshold_runs=3)
check("P3b-1: Zeile, deren einzige Quelle gerade ausgefallen ist, gilt nicht "
      "als verwaist (leere Menge gesunder Quellen)",
      not any("nur-ausgefallene-quelle" in [r["uid"] for r in rows]
              for rows in _alle_krank.values()))
# Diesen Ausfall wieder zuruecknehmen, die folgenden Blocks erwarten azconni ok.
with db.get_conn() as conn:
    conn.execute("DELETE FROM scrape_runs WHERE source = 'azconni' AND ok = 0")
    conn.execute("DELETE FROM events WHERE uid = 'nur-ausgefallene-quelle'")
    conn.execute("DELETE FROM event_sources WHERE event_uid = 'nur-ausgefallene-quelle'")
    # verwaist-zukunft wiederherstellen: azconni veraltet, kulturkalender raus.
    conn.execute("DELETE FROM scrape_runs WHERE source = 'kulturkalender'")
    conn.execute(
        """INSERT OR REPLACE INTO event_sources (event_uid, source, first_seen, last_seen)
           VALUES ('verwaist-zukunft', 'azconni', ?, ?)""",
        ("2026-08-20T09:00:00", "2026-08-20T09:00:00"))
    conn.execute("DELETE FROM event_sources WHERE event_uid = 'verwaist-zukunft' "
                 "AND source = 'kulturkalender'")

with db.get_conn() as conn:
    _dry_result = db.expire_orphaned_events(conn, _heute, threshold_runs=3, dry_run=True)
    _nach_dry_run = conn.execute(
        "SELECT count(*) FROM events WHERE uid = 'verwaist-zukunft'").fetchone()[0]
check("expire_orphaned_events(dry_run=True) meldet dieselbe Zeile",
      [r["uid"] for r in _dry_result.get("azconni", [])] == ["verwaist-zukunft"])
check("expire_orphaned_events(dry_run=True) loescht nichts",
      _nach_dry_run == 1)

# Zukuenftiges Event, identisch verwaist wie "verwaist-zukunft", aber geliked -
# darf trotz Verwaisung NIE geloescht werden (data/ enthaelt die einzige Kopie
# der Reaktionen; eine geloeschte Zeile liesse den Favoriten kommentarlos
# verschwinden, siehe db._delete_orphaned_event).
with db.get_conn() as conn:
    db.upsert_events(conn, [{
        "uid": "verwaist-geliked", "source": "azconni", "date": "2026-09-01",
        "time": "20:00", "title": "Verwaist, aber geliked", "venue": "Testort",
        "category": "musik", "raw_category": "Test",
    }])
    conn.execute("UPDATE events SET last_seen = ? WHERE uid = ?",
                 ("2026-08-20T09:00:00", "verwaist-geliked"))
    conn.execute("UPDATE event_sources SET last_seen = ? WHERE event_uid = ?",
                 ("2026-08-20T09:00:00", "verwaist-geliked"))
    db.set_reaction(conn, "verwaist-geliked", "like")

    _gemeldet = db.expire_orphaned_events(conn, _heute, threshold_runs=3, dry_run=False)

    def _existiert(uid):
        return conn.execute(
            "SELECT count(*) FROM events WHERE uid = ?", (uid,)).fetchone()[0] == 1

    _gemeldete_uids = [r["uid"] for rows in _gemeldet.values() for r in rows]
    _zukunft_da = _existiert("verwaist-zukunft")
    _vergangen_da = _existiert("verwaist-vergangen")
    _frisch_da = _existiert("frisch-zukunft")
    _geliked_da = _existiert("verwaist-geliked")
    _sources_da = conn.execute(
        "SELECT count(*) FROM event_sources WHERE event_uid = 'verwaist-zukunft'"
    ).fetchone()[0] == 1

# P3b-1: Loeschen ist bewusst abgeschaltet (db.ORPHAN_DELETION_DISABLED), auch
# bei dry_run=False. Diese Erwartungen sind gegenueber frueher umgedreht - das
# ist die Produktentscheidung, nicht ein kaputt gewordener Test. P3b-3 dreht sie
# zurueck, wenn der Schalter faellt.
check("P3b-1: Loeschen ist abgeschaltet", db.ORPHAN_DELETION_DISABLED)
check("dry_run=False meldet die verwaiste Zukunftszeile", 
      "verwaist-zukunft" in _gemeldete_uids)
check("dry_run=False loescht die verwaiste Zukunftszeile NICHT (abgeschaltet)", _zukunft_da)
check("dry_run=False laesst die vergangene Zeile unangetastet", _vergangen_da)
check("dry_run=False laesst die weiterhin gesehene Zeile stehen", _frisch_da)
check("dry_run=False loescht eine verwaiste, aber geliked Zeile NICHT", _geliked_da)
check("dry_run=False laesst event_sources der gemeldeten Zeile stehen", _sources_da)

# Die Anzahl der Laeufe allein taugt nicht als Schwelle: Deploys und manuelle
# Testlaeufe haeufen sich, drei davon koennen innerhalb weniger Stunden liegen.
# Ohne Mindestspanne flaege ein Zukunfts-Event raus, weil zufaellig dreimal kurz
# hintereinander gescrapt wurde - genau die Lage, in der scrape_runs neu ist.
with db.get_conn() as conn:
    db.upsert_events(conn, [{
        "uid": "verwaist-eng", "source": "cybersax", "date": "2026-09-01",
        "time": "20:00", "title": "Verwaist trotz enger Laeufe", "venue": "Testort",
        "category": "musik", "raw_category": "Test",
    }])
    conn.execute("UPDATE events SET last_seen = ? WHERE uid = ?",
                 ("2026-08-20T09:00:00", "verwaist-eng"))
    conn.execute("UPDATE event_sources SET last_seen = ? WHERE event_uid = ?",
                 ("2026-08-20T09:00:00", "verwaist-eng"))
    # Drei erfolgreiche Laeufe - aber alle innerhalb von knapp vier Stunden.
    for _zeit in ("2026-08-23T08:00:00", "2026-08-23T10:00:00", "2026-08-23T11:45:00"):
        db.record_scrape_run(conn, "cybersax", _zeit, _zeit, ok=True, event_count=1)
    _eng = db.find_orphaned_events(conn, _heute, threshold_runs=3)

check("gehaertete Schwelle: drei eng beieinanderliegende Laeufe qualifizieren nicht",
      "cybersax" not in _eng)

with db.get_conn() as conn:
    # Ein aelterer Lauf weitet das Fenster ueber 12 Stunden - jetzt zaehlt es.
    db.record_scrape_run(conn, "cybersax", "2026-08-22T18:00:00",
                         "2026-08-22T18:00:05", ok=True, event_count=1)
    _weit = db.find_orphaned_events(conn, _heute, threshold_runs=3)

check("gehaertete Schwelle: ab 12 Stunden Spanne qualifiziert dieselbe Quelle",
      [r["uid"] for r in _weit.get("cybersax", [])] == ["verwaist-eng"])

# --- Sicherung der Datenbank (app/backup.py) -------------------------------
# Der Snapshot muss sich wieder oeffnen lassen UND die Daten enthalten - eine
# leere, aber gueltige Datei waere der schlimmste Fall: sie sieht wie eine
# Sicherung aus und ist keine.
from app import backup  # noqa: E402
import sqlite3 as _sqlite3  # noqa: E402
import glob as _glob  # noqa: E402

with db.get_conn() as conn:
    _rows_vorher = conn.execute("SELECT count(*) FROM events").fetchone()[0]

_snapshot = backup.create_backup(today=_dt.date(2026, 8, 23))
check("Sicherung liegt unter data/backups mit Datum im Namen",
      _snapshot.endswith("backups/dd-was-geht-2026-08-23.db") and os.path.exists(_snapshot))

_conn_snap = _sqlite3.connect(_snapshot)
check("Sicherung laesst sich oeffnen und hat dieselben Events",
      _conn_snap.execute("SELECT count(*) FROM events").fetchone()[0] == _rows_vorher)
_conn_snap.close()

# Die Rotation loescht Dateien - deshalb wird sie geprueft, nicht nur gelesen.
# Angelegt werden N+2 Tage, uebrig bleiben duerfen genau die juengsten N.
for _tag in range(1, 8):
    open(os.path.join(backup.backup_dir(), f"dd-was-geht-2026-08-{_tag:02d}.db"), "w").close()
backup.create_backup(keep=5, today=_dt.date(2026, 8, 23))
_uebrig = sorted(os.path.basename(f) for f in
                 _glob.glob(os.path.join(backup.backup_dir(), backup.SNAPSHOT_GLOB)))
check("Rotation behaelt genau die juengsten N Sicherungen",
      _uebrig == ["dd-was-geht-2026-08-04.db", "dd-was-geht-2026-08-05.db",
                  "dd-was-geht-2026-08-06.db", "dd-was-geht-2026-08-07.db",
                  "dd-was-geht-2026-08-23.db"])

# --- Straße E Mojibake-Reparatur (app/scrapers/strassee.py, P1b) ----------
# Der Feed deklariert ISO-8859-1, mischt aber gelegentlich UTF-8-kodierte
# Interpunktion ein - fetch_html() dekodiert alles als ISO-8859-1, wodurch
# aus einem typografischen Apostroph sichtbarer Muell wird. Echtes Mojibake
# nachgebaut statt getippt: UTF-8-Text mit Apostroph, dann als ISO-8859-1
# fehldekodiert - genau das, was fetch_html() dem Parser vorlegt.
from app.scrapers import strassee as strassee_scraper  # noqa: E402

_MOJIBAKE_TITLE = "Black Celebration - Doesn\u2019t Matter".encode("utf-8").decode("iso-8859-1")
_MOJIBAKE_DESC = "Line-up: DJ Doesn\u2019t Care".encode("utf-8").decode("iso-8859-1")

STRASSEE_FIXTURE = f"""<rss><channel>
<item>
<title>2026-09-12, Sa : {_MOJIBAKE_TITLE}</title>
<link>http://www.strasse-e.de/termine.php?id=101</link>
<description>{_MOJIBAKE_DESC}</description>
</item>
<item>
<title>2026-09-19, Sa : Gr\u00f6\u00dfer Bahnhof</title>
<link>http://www.strasse-e.de/termine.php?id=102</link>
<description>Gr\u00f6\u00dfer als sonst</description>
</item>
</channel></rss>"""

_strassee_entries = strassee_scraper._parse_feed(STRASSEE_FIXTURE)
_strassee_by_id = {e["url"].rsplit("=", 1)[1]: e for e in _strassee_entries}

check("Strasse E: UTF-8-Mojibake im Titel repariert",
      _strassee_by_id["101"]["title"] == "Black Celebration - Doesn\u2019t Matter")
check("Strasse E: UTF-8-Mojibake in der Beschreibung repariert",
      _strassee_by_id["101"]["description"] == "Line-up: DJ Doesn\u2019t Care")
check("Strasse E: echtes ISO-8859-1 (\u00df, \u00f6) bleibt unangetastet",
      _strassee_by_id["102"]["title"] == "Gr\u00f6\u00dfer Bahnhof"
      and _strassee_by_id["102"]["description"] == "Gr\u00f6\u00dfer als sonst")

print("\nAlle Smoke-Tests erfolgreich.")

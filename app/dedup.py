"""Doppelungen über Quellen hinweg erkennen, verbuchen und ausblenden.

Warum das nötig wurde: rauze.de und ra.co listen weitgehend dieselben Dresdner
Clubnächte (objekt klein a, Sektor Evolution, Club Paula ...). Die stabile
Event-ID aus normalize.make_event_uid() fällt nur zusammen, wenn Datum, Zeit,
Titel und Ort *identisch* geschrieben sind - real heißt dieselbe Nacht auf der
einen Seite "Pangaea invites" und auf der anderen "Pangaea Invites w/ Xiorro",
und der Ort einmal "objekt klein a", einmal "OKA". Ohne den Abgleich hier
stünde jede solche Nacht doppelt im Newsletter.

Zwei Grundregeln, die Fehltreffer verhindern:

1. **Nur quellenübergreifend.** Zwei Einträge *derselben* Quelle sind nie eine
   Doppelung - eine Führung, die am selben Tag um 11:00 und um 15:00 startet,
   ist zweimal derselbe Titel am selben Ort und trotzdem zweimal ein Event.
   Genau eine Ausnahme, siehe _festival_groups(): die Zeilen eines Line-ups,
   die derselbe Scraper unter einem gemeinsamen Veranstaltungsnamen geliefert
   hat.
2. **Uhrzeit als Gegenprobe.** Liegen zwei Startzeiten mehr als
   MAX_TIME_DELTA_MINUTES auseinander, sind es verschiedene Termine - auch bei
   identischem Titel. Ausnahme: bei gleichem Ort und praktisch deckungsgleichem
   Titel gilt das weitere Fenster MAX_TIME_DELTA_STRONG_MINUTES, weil die
   Quellen dort Einlass und Beginn meinen (Open Air: zwei bis drei Stunden).

Wer gewinnt, entscheidet config.SOURCE_PRIORITY (Standard: die Quellen der
Haeuser selbst - sektor, azconni - vor rauze vor ra vor kulturkalender vor
cybersax vor reddit). Der Verlierer bleibt vollständig in der Datenbank
stehen und wird in events.duplicate_of auf den Gewinner gezeigt; ausgeliefert
(Newsletter, Web) wird nur der Gewinner - siehe db.events_for_range(). Fehlende
Felder des Gewinners (Bild, Preis, Beschreibung) werden aus dem Duplikat
aufgefüllt, vorhandene nie überschrieben.
"""
import difflib
import logging
import re

from . import config, db, normalize
# Sammel-Eintraege entstehen ausschliesslich in diesem Scraper; von dort kommt
# auch das Wissen, welche Abschnittsueberschrift eine Rubrik ist und welche ein
# Veranstaltungsname (siehe _festival_groups).
from .scrapers import cybersax

logger = logging.getLogger("dd-was-geht.dedup")

# Zwei Startzeiten dürfen so weit auseinanderliegen und noch dasselbe Event
# meinen (Quellen zählen mal den Einlass, mal den Beginn).
MAX_TIME_DELTA_MINUTES = 90

# Bei starker Evidenz darf der Abstand deutlich größer sein. Open-Air-Bühnen
# nennen einmal den Einlass und einmal den Beginn, und dazwischen liegen dort
# zwei bis drei Stunden. Real am 21.08.2026: rauze "Wincent Weiss" 17:00 und
# kulturkalender "Wincent Weiss Sommertour 2026" 19:00, beide Filmnächte am
# Elbufer - gleicher Ortsschlüssel, Wort-Überdeckung 1.00, und trotzdem hat das
# 90-Minuten-Fenster die beiden getrennt gelassen. Das Konzert stand danach
# zweimal im Newsletter.
#
# Warum 150 und nicht mehr: der reale Abstand betraegt 120 Minuten, und ab etwa
# drei Stunden ist es glaubhaft ein zweiter Termin am selben Abend (fruehe und
# spaete Vorstellung). Genau diese Grenze prueft tests_smoke.py mit "Cats &
# Dogs" 19:00/22:00. Im Zweifel wird nicht zusammengefasst - lieber ein Event
# zweimal im Newsletter als eines, das stillschweigend verschwindet.
MAX_TIME_DELTA_STRONG_MINUTES = 150

# Ab dieser Wort-Überdeckung gilt der Titel ZUSAMMEN mit gleichem Ort als
# starke Evidenz. Bewusst höher als SAME_VENUE_MIN_OVERLAP: "MODUS: Akua" vs.
# "MODUS: Anetha" liegt bei 0.50 und bleibt damit beim engen Fenster - zwei
# Termine derselben Reihe am selben Abend dürfen nicht verschmelzen.
STRONG_TITLE_OVERLAP = 0.8

# Titel-Ähnlichkeit (0-1), ab der zwei Einträge als dasselbe Event gelten.
# Gleicher Ort + gleicher Tag + passende Zeit ist schon starke Evidenz, deshalb
# darf der Titel dort stärker abweichen als bei unklarem Ort.
#
# Bei gleichem Ort zählen zwei Maße getrennt, und zwar mit Absicht: die
# Wort-Überdeckung darf großzügig sein ("Pangaea Invites" vs. "Pangaea Invites
# w/ Xiorro"), die reine Zeichen-Ähnlichkeit nicht. Sonst verschmelzen zwei
# echte Termine derselben Reihe, deren Titel sich nur im Gastnamen
# unterscheiden ("MODUS: Akua" vs. "MODUS: Anetha" liegt bei 0.72 Zeichen-
# Ähnlichkeit, aber nur 0.5 Wort-Überdeckung).
SAME_VENUE_MIN_OVERLAP = 0.6
SAME_VENUE_MIN_RATIO = 0.75
TITLE_MIN_UNKNOWN_VENUE = 0.85
TITLE_MIN_OTHER_VENUE = 0.9

# Ortsnamen, die dieselbe Location meinen. Links steht, was slugify() aus der
# jeweiligen Schreibweise macht, rechts der gemeinsame Schlüssel.
VENUE_ALIASES = {
    "oka": "objekt-klein-a",
    "objektkleina": "objekt-klein-a",
    "objekt-klein-a-oka": "objekt-klein-a",
    "groove-station": "groovestation",
    "chemo": "chemiefabrik",
    "chemiefabrik-dresden": "chemiefabrik",
    "sektor": "sektor-evolution",
    # Das Haus selbst schreibt sich auf seiner Seite ohne Leerzeichen.
    "sektorevolution": "sektor-evolution",
    "beatpol-ehemals-starclub": "beatpol",
    "starclub": "beatpol",
    "kraftwerk-mitte-dresden": "kraftwerk-mitte",
    "tante-ju-dresden": "tante-ju",
    "puschkin-club": "puschkin",
    "blauer-salon-puschkin": "puschkin",
    # AZ Conni schreibt sich selbst "AZ Conni", rauze.de listet es genauso,
    # umgangssprachlich heisst es nur "Conni".
    "az-conni": "conni",
    "conni-club": "conni",
    "azc": "conni",
    # CyberSAX schreibt "Kafe Zeitlos", andere Quellen "Cafe Zeitlos".
    "kafe-zeitlos": "cafe-zeitlos",
    "kafe-saite": "cafe-saite",
    "blaue-fabrik-im-alten-leipziger-bahnhof": "blaue-fabrik",
}

# Füllwörter in Ortsnamen: "Club Paula" (RA) und "Paula" (Rauze) sind derselbe
# Laden, "Chemiefabrik e.V." und "Chemiefabrik" auch.
_GENERIC_VENUE_WORDS = {"club", "dresden", "e", "v", "ev", "der", "die", "das", "im", "in"}

# Ort unbekannt - dann darf der Ort weder für noch gegen eine Doppelung zählen.
# (Rauze schreibt Platzhalter in dieses Feld, statt es leer zu lassen.)
_UNKNOWN_VENUES = {
    "tba", "tbc", "unknown", "unbekannt", "secret-location", "ort-folgt",
    "location-siehe-beschreibung", "siehe-beschreibung", "geheim", "secret",
    "location-tba", "wird-noch-bekannt-gegeben",
}

# Titel-Beiwerk, das je Quelle unterschiedlich mitgeschleppt wird.
_TITLE_STOPWORDS = {
    "the", "und", "and", "mit", "with", "feat", "featuring", "presents",
    "praesentiert", "pres", "der", "die", "das", "dresden", "party", "im", "in",
}


def _venue_key(venue):
    """Vergleichbarer Ortsschlüssel. Leerer String = Ort unbekannt."""
    slug = normalize.slugify(venue or "")
    if not slug or slug in _UNKNOWN_VENUES:
        return ""
    parts = [p for p in slug.split("-") if p and p not in _GENERIC_VENUE_WORDS]
    slug = "-".join(parts) or slug
    return VENUE_ALIASES.get(slug, slug)


def _title_tokens(slug):
    return {w for w in slug.split("-") if len(w) >= 3 and w not in _TITLE_STOPWORDS}


def _title_scores(title_a, title_b):
    """(Zeichen-Ähnlichkeit, Wort-Überdeckung) - bewusst zwei getrennte Maße.

    Die Wort-Überdeckung ("wie viele bedeutsame Wörter des kürzeren Titels
    stecken im längeren") ist das entscheidende Maß, weil die Quellen genau so
    auseinandergehen: Rauze kürzt auf den Reihennamen, RA hängt das Line-up an.
    Real gemessen am 21.08.2026:

        Rauze "Modus"          / RA "MODUS: Akua"                  -> 1.00
        Rauze "Sachsentrance"  / RA "Sachsentrance Sommerfest"     -> 1.00
        Rauze "Bratty"         / RA "bratty with charli xcx ..."   -> 1.00

    Die Zeichen-Ähnlichkeit liegt in allen drei Fällen unter 0.75 und taugt
    dafür nicht. Umgekehrt bleibt die Wort-Überdeckung streng genug, wenn beide
    Titel gleich lang sind und sich im entscheidenden Wort unterscheiden
    ("MODUS: Akua" vs. "MODUS: Anetha" -> 0.50).

    Weil ein einzelnes enthaltenes Wort für sich schwach ist, darf dieses Maß
    nur zusammen mit einem übereinstimmenden Ort voll zählen; ohne Ort verlangt
    match() zusätzlich vollständige Überdeckung von mindestens zwei Wörtern.
    """
    slug_a, slug_b = normalize.slugify(title_a or ""), normalize.slugify(title_b or "")
    if not slug_a or not slug_b:
        return 0.0, 0.0
    ratio = difflib.SequenceMatcher(None, slug_a, slug_b).ratio()

    tokens_a, tokens_b = _title_tokens(slug_a), _title_tokens(slug_b)
    smaller = min(len(tokens_a), len(tokens_b))
    if not smaller:
        return ratio, 0.0
    return ratio, len(tokens_a & tokens_b) / smaller


_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _minutes(time_text):
    match = _TIME_RE.match((time_text or "").strip())
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _time_compatible(time_a, time_b, max_delta=MAX_TIME_DELTA_MINUTES):
    """Fehlt eine Zeit, zählt sie weder für noch gegen die Doppelung.
    Der Abstand wird über Mitternacht hinweg gemessen (23:30 vs. 00:30 = 60 min).
    Wie groß max_delta sein darf, entscheidet match() anhand der übrigen
    Evidenz (siehe MAX_TIME_DELTA_STRONG_MINUTES)."""
    minutes_a, minutes_b = _minutes(time_a), _minutes(time_b)
    if minutes_a is None or minutes_b is None:
        return True
    delta = abs(minutes_a - minutes_b)
    return min(delta, 1440 - delta) <= max_delta


def match(event_a, event_b):
    """Sind das zwei Einträge derselben Veranstaltung?
    Gibt (score, grund) zurück oder None."""
    if event_a["date"] != event_b["date"]:
        return None
    if event_a["source"] == event_b["source"]:
        return None  # siehe Grundregel 1 im Modul-Docstring

    ratio, overlap = _title_scores(event_a.get("title"), event_b.get("title"))
    key_a, key_b = _venue_key(event_a.get("venue")), _venue_key(event_b.get("venue"))
    same_venue = bool(key_a and key_b and key_a == key_b)

    # Die Uhrzeit bleibt die Gegenprobe (Grundregel 2), aber wie streng sie
    # ausfällt, hängt von der übrigen Evidenz ab: gleicher Ort UND ein praktisch
    # deckungsgleicher Titel wiegen schwerer als zwei Stunden Zeitunterschied.
    # Deshalb wird sie erst hier ausgewertet, nach Ort und Titel.
    max_delta = (
        MAX_TIME_DELTA_STRONG_MINUTES
        if same_venue and overlap >= STRONG_TITLE_OVERLAP
        else MAX_TIME_DELTA_MINUTES
    )
    if not _time_compatible(event_a.get("time"), event_b.get("time"), max_delta):
        return None

    if same_venue:
        if overlap >= SAME_VENUE_MIN_OVERLAP or ratio >= SAME_VENUE_MIN_RATIO:
            return max(ratio, overlap), "ort+titel"
        return None
    if key_a and key_b:
        # Sammel-Einträge sind per Konstruktion an EINEN Ort gebunden und tragen
        # alle denselben Titel (den Festivalnamen). Über die Titel-Regel würden
        # deshalb sämtliche Spielorte eines Festivaltags zu einem Eintrag
        # verketten - real am 13.09.2026: die sieben Denkmäler des "Tags des
        # Offenen Denkmals" fielen zu einem einzigen zusammen.
        if _is_umbrella(event_a) or _is_umbrella(event_b):
            return None
        # Verschiedene Orte: nur ein praktisch identischer Titel zählt, und die
        # großzügige Wort-Überdeckung bleibt hier bewusst außen vor.
        return (ratio, "titel") if ratio >= TITLE_MIN_OTHER_VENUE else None

    # Mindestens ein Ort unbekannt ("Location siehe Beschreibung" bei Rauze,
    # "TBA" bei RA). Dann trägt entweder ein fast identischer Titel - oder ein
    # Titel, dessen sämtliche Wörter im anderen stecken, aber erst ab zwei
    # Wörtern und nur mit beidseitig bekannter, passender Uhrzeit.
    if ratio >= TITLE_MIN_UNKNOWN_VENUE:
        return ratio, "titel"
    tokens_known = min(
        len(_title_tokens(normalize.slugify(event_a.get("title") or ""))),
        len(_title_tokens(normalize.slugify(event_b.get("title") or ""))),
    )
    both_times = event_a.get("time") and event_b.get("time")
    if overlap >= 1.0 and tokens_known >= 2 and both_times:
        return overlap, "titel+zeit"
    return None


# --- Line-ups einer Quelle unter einem gemeinsamen Namen -------------------
# Die einzige Ausnahme von Grundregel 1. Hintergrund: das SAX-Terminal listet
# ein Open Air als Überschrift plus eine Zeile je Programmpunkt ("Klang&Kruste"
# im Alaunpark: zehn Zeilen am 22.08.2026). scrapers/cybersax.py fasst solche
# Gruppen zu einem zusätzlichen Sammel-Eintrag zusammen und markiert ihn, indem
# der Veranstaltungsname sowohl als Titel als auch als raw_category dransteht.
# Hier werden die Einzelzeilen an diesen Sammel-Eintrag gehängt.
#
# Warum das keine echten Termine verschluckt: verlangt werden gleicher Tag,
# gleiche Quelle, gleicher Ort UND dieselbe Rohkategorie, und es passiert nur,
# wenn ein Eintrag der Gruppe genau diese Rohkategorie als Titel trägt. Über den
# gesamten Bestand (5500 Zeilen, 22.08.2026) trifft das auf keinen einzigen
# Eintrag zufällig zu - die Markierung entsteht ausschließlich im Scraper.
MATCH_REASON_HEADING = "ueberschrift"


def _is_umbrella(event):
    """Sammel-Eintrag einer Line-up-Gruppe?

    Drei Bedingungen, alle noetig: der Eintrag stammt aus der einzigen Quelle,
    die solche Gruppen bildet, seine Rohkategorie ist dort ein
    Veranstaltungsname und keine Rubrik, und er traegt genau diesen Namen als
    Titel. Ohne die ersten beiden wuerde ein Event, das zufaellig wie seine
    Rubrik heisst ("Musik" im Blue Note), seine Nachbarzeilen einsammeln.
    """
    if event.get("source") != cybersax.SOURCE:
        return False
    raw_category = event.get("raw_category")
    if not cybersax.is_festival_heading(raw_category):
        return False
    return normalize.slugify(event.get("title") or "") == normalize.slugify(raw_category)


def _umbrella_key(event):
    """Schlüssel der Line-up-Gruppe, oder None wenn der Eintrag keiner angehört."""
    raw_category = normalize.slugify(event.get("raw_category") or "")
    venue_key = _venue_key(event.get("venue"))
    if not raw_category or not venue_key:
        return None
    return (event["source"], event["date"], venue_key, raw_category)


def _festival_groups(events):
    """{Sammel-Eintrag-uid: [uids der Einzelzeilen]} - siehe Modul-Docstring."""
    groups = {}
    for event in events:
        key = _umbrella_key(event)
        if key is not None:
            groups.setdefault(key, []).append(event)

    result = {}
    for members in groups.values():
        umbrellas = [e for e in members if _is_umbrella(e)]
        others = [e for e in members if not _is_umbrella(e)]
        if not umbrellas or len(members) < 2:
            continue
        # Mehrere Sammel-Einträge derselben Gruppe gibt es, wenn die Quelle den
        # Beginn verschoben hat (die Startzeit steckt in der uid): der frühere
        # gewinnt, der ältere hängt sich als Doppelung darunter.
        umbrellas.sort(key=lambda e: (e.get("time") or "99:99", e["uid"]))
        head, rest = umbrellas[0], umbrellas[1:]
        result[head["uid"]] = [e["uid"] for e in rest + others]
    return result


def _source_rank(source):
    priority = config.SOURCE_PRIORITY
    return priority.index(source) if source in priority else len(priority)


def _best_rank(event):
    """Bester Quellen-Rang dieses Eintrags - über ALLE Quellen, die ihn
    geliefert haben, nicht nur über events.source.

    Der Umweg ist nötig, weil es zwei Arten von Doppelung gibt. Schreiben zwei
    Quellen Datum, Zeit, Titel und Ort identisch, fallen sie schon über die uid
    in dieselbe Zeile, und in events.source steht dann nur, wer zuerst da war
    (siehe die Tabelle event_sources). Ohne diese Funktion verliert eine solche
    Zeile gegen einen Aggregator, obwohl die bessere Quelle sie ebenfalls
    geliefert hat.

    Real am 22.08.2026 bei "GLUT x ELOS" im Sektor Evolution: der Eintrag trug
    bereits den Link auf sektor-evolution.de, stand aber als "kulturkalender"
    in der Zeile - und wurde deshalb zugunsten des ra.co-Eintrags ausgeblendet.
    Im Newsletter zeigte der Link damit wieder auf RA.

    Fehlt die Liste (reine Unit-Tests, Reddit-Pfad), zählt events.source.
    """
    sources = event.get("sources") or [event["source"]]
    return min(_source_rank(s) for s in sources)


def _canonical_key(event):
    """Sortierschlüssel für die Gewinnerwahl.

    Die Quellen-Priorität steht bewusst ganz vorn: bei "Klang & Kruste" liefert
    rauze.de denselben Tag als ein Event mit Permalink, Bild und Preis - dieser
    Eintrag soll gewinnen, nicht der aus dem Line-up gebaute Sammel-Eintrag.
    Erst INNERHALB derselben Quelle schlägt der Sammel-Eintrag seine
    Einzelzeilen (sonst hieße der Termin im Newsletter "DJ Pappenheimer"), und
    unter zwei Sammel-Einträgen der mit der früheren Startzeit.
    """
    umbrella = _is_umbrella(event)
    return (
        _best_rank(event),
        0 if umbrella else 1,
        (event.get("time") or "99:99") if umbrella else "",
        event.get("first_seen") or "",
        event["uid"],
    )


def _canonical_of(cluster):
    """Aus einer Gruppe zusammengehöriger Einträge den Gewinner wählen:
    Quellen-Priorität, dann der Sammel-Eintrag einer Line-up-Gruppe, dann der
    ältere Eintrag, dann die uid (nur damit das Ergebnis bei Gleichstand stabil
    bleibt)."""
    return min(cluster, key=_canonical_key)


def find_duplicates(events):
    """events: Liste von Event-dicts (uid/source/date/time/title/venue/first_seen).
    Gibt {duplikat_uid: (kanonische_uid, score, grund)} zurück.

    Ohne Netzwerk und ohne Datenbank testbar - link_duplicates() ist nur die
    Verdrahtung dieser Funktion mit SQLite.
    """
    by_date = {}
    for event in events:
        by_date.setdefault(event["date"], []).append(event)

    parent = {e["uid"]: e["uid"] for e in events}
    by_uid = {e["uid"]: e for e in events}
    # Bester (score, grund) je verschmolzenem Paar, für die Protokollierung.
    evidence = {}

    def find(uid):
        while parent[uid] != uid:
            parent[uid] = parent[parent[uid]]
            uid = parent[uid]
        return uid

    def union(uid_a, uid_b):
        root_a, root_b = find(uid_a), find(uid_b)
        if root_a != root_b:
            parent[root_b] = root_a

    for day_events in by_date.values():
        for index, event_a in enumerate(day_events):
            for event_b in day_events[index + 1:]:
                result = match(event_a, event_b)
                if result is None:
                    continue
                union(event_a["uid"], event_b["uid"])
                pair = frozenset((event_a["uid"], event_b["uid"]))
                evidence[pair] = result

    # Die Ausnahme von Grundregel 1: Zeilen desselben Line-ups an ihren
    # Sammel-Eintrag hängen (siehe _festival_groups).
    lineup_members = set()
    for umbrella_uid, member_uids in _festival_groups(events).items():
        for member_uid in member_uids:
            union(umbrella_uid, member_uid)
            evidence[frozenset((umbrella_uid, member_uid))] = (1.0, MATCH_REASON_HEADING)
            lineup_members.add(member_uid)

    clusters = {}
    for uid in parent:
        clusters.setdefault(find(uid), []).append(by_uid[uid])

    mapping = {}
    for cluster in clusters.values():
        if len(cluster) < 2:
            continue
        canonical = _canonical_of(cluster)
        for event in cluster:
            if event["uid"] == canonical["uid"]:
                continue
            # Gewinnt eine bessere Quelle die ganze Gruppe (rauze bei
            # "Klang & Kruste"), gibt es zur Einzelzeile kein direkt gemessenes
            # Paar - der Grund bleibt trotzdem die gemeinsame Überschrift.
            default = ((1.0, MATCH_REASON_HEADING) if event["uid"] in lineup_members
                       else (0.0, "gruppe"))
            score, reason = evidence.get(
                frozenset((event["uid"], canonical["uid"])), default
            )
            mapping[event["uid"]] = (canonical["uid"], score, reason)
    return mapping


def _upgrade_placeholder_venue(conn, canonical, duplicate):
    """Platzhalter im Ort des Gewinners durch den echten Ort des Duplikats ersetzen.

    Rauze schreibt "Location siehe Beschreibung" in das Feld, statt es leer zu
    lassen (siehe _UNKNOWN_VENUES) - fill_missing_from_duplicate() sieht darin
    einen gefüllten Wert und lässt ihn stehen. Im Newsletter stand deshalb
    "Klang & Kruste - Location siehe Beschreibung", obwohl CyberSAX den Ort
    (Alaunpark) mitgeliefert hat. Ein echter Ort wird nie überschrieben.
    """
    if not canonical or not duplicate:
        return False
    if _venue_key(canonical.get("venue")) or not _venue_key(duplicate.get("venue")):
        return False
    db.set_venue(conn, canonical["uid"], duplicate["venue"])
    canonical["venue"] = duplicate["venue"]
    return True


def link_duplicates(conn, start_date, end_date):
    """Doppelungen im Zeitraum neu berechnen und in der DB verbuchen.

    Idempotent: Verknüpfungen, die nicht mehr gelten (z.B. weil eine Quelle den
    Titel geändert hat), werden wieder gelöst. Gibt die Anzahl der aktuell
    verbuchten Doppelungen im Zeitraum zurück.
    """
    if not config.DEDUP_ENABLED:
        # Abgeschaltet heißt: auch schon verbuchte Ausblendungen aufheben,
        # sonst blieben Einträge aus einem früheren Lauf für immer unsichtbar.
        for row in conn.execute(
            """SELECT uid FROM events
               WHERE duplicate_of IS NOT NULL AND date >= ? AND date <= ?""",
            (start_date, end_date),
        ).fetchall():
            db.unlink_duplicate(conn, row["uid"])
        return 0

    # GROUP_CONCAT holt alle Quellen mit, die diese uid geliefert haben - siehe
    # _best_rank(). LEFT JOIN, damit ein Eintrag ohne Quellen-Buchung (Bestand
    # aus der Zeit vor der Tabelle) nicht stillschweigend verschwindet.
    rows = []
    for row in conn.execute(
        """SELECT e.uid, e.source, e.date, e.time, e.title, e.venue, e.raw_category,
                  e.first_seen, e.duplicate_of, GROUP_CONCAT(s.source, ',') AS sources
           FROM events e LEFT JOIN event_sources s ON s.event_uid = e.uid
           WHERE e.date >= ? AND e.date <= ?
           GROUP BY e.uid""",
        (start_date, end_date),
    ):
        row = dict(row)
        row["sources"] = row["sources"].split(",") if row["sources"] else [row["source"]]
        rows.append(row)
    mapping = find_duplicates(rows)
    by_uid = {row["uid"]: row for row in rows}

    # Sammel-Einträge zuerst: sie tragen das Line-up als Beschreibung, und
    # fill_missing_from_duplicate() füllt beim Gewinner immer nur das erste, was
    # kommt. Ohne die Sortierung landete dort die Beschreibung irgendeiner
    # einzelnen Zeile des Line-ups.
    for row in sorted(rows, key=lambda r: 0 if _is_umbrella(r) else 1):
        wanted = mapping.get(row["uid"])
        current = row["duplicate_of"]
        if wanted is None:
            if current:
                db.unlink_duplicate(conn, row["uid"])
            continue
        canonical_uid, score, reason = wanted
        db.link_duplicate(conn, row["uid"], canonical_uid, score, reason)
        # Auch bei unveränderter Verknüpfung: die Quelle kann inzwischen ein
        # Bild oder einen Preis nachgereicht haben.
        db.fill_missing_from_duplicate(conn, canonical_uid, row["uid"])
        _upgrade_placeholder_venue(conn, by_uid.get(canonical_uid), row)

    if mapping:
        logger.info(
            "Doppelungen %s bis %s: %d Einträge ausgeblendet.",
            start_date, end_date, len(mapping),
        )
    return len(mapping)

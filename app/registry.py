"""Verzeichnis aller Quellen - die einzige Stelle, an der eine Quelle steht.

Bisher war eine Quelle an vier Stellen erklaert: einmal als Slug in
scheduler.SOURCES (Scrape-Reihenfolge), einmal als Label in
config.SOURCE_LABELS (UI-Chip *und* Vollstaendigkeitsliste fuer /api/health und
die Verwaisungs-Erkennung), einmal als Position in config.SOURCE_PRIORITY
(Dedup-Rang) und - fuer drei Haeuser - noch einmal als Ortsname in
dedup.VENUE_ALIASES. Vier Listen, die niemand zusammen aendert: genau so faellt
eine neue Quelle aus /api/health raus, waehrend sie im UI erscheint.

Hier steht sie einmal. config.py leitet daraus die alten Namen ab, damit kein
Aufrufer umzieht.

Felder je Eintrag:
    name        Beschriftung im Web-UI und in /api/health.
    status      "live" = wird gescrapt. (Weitere Zustaende kommen mit den
                Venue-Eintraegen; heute ist alles live.)
    priority    Rang bei Doppelungen, klein = gewinnt. **Muss eindeutig sein.**
                db._source_rank leitet daraus per list.index() einen Rang ab,
                und db._best_source/_keeps_own_url verlassen sich darauf, dass
                zwei Quellen nie gleichauf liegen (siehe config.SOURCE_PRIORITY
                und db.py:196-215). Deshalb prueft _check_unique() das beim
                Import, statt es zu hoffen.
    venue_key   Optional: der gemeinsame Ortsschluessel dieses Hauses in der
                Doppelungs-Erkennung (dedup._venue_key).
    aliases     Optional: Schreibweisen, die auf venue_key zeigen. Links steht,
                was normalize.slugify() aus der jeweiligen Schreibweise macht.

Bewusst KEIN "tier"-Feld. Tiers sind Vokabular fuer spaeter; sie gruppieren
Quellen und erzeugen damit erst die Gleichstaende, auf deren Abwesenheit die
Dedup-Pfade heute bauen. Solange hier flache, eindeutige priority-Zahlen
stehen, gibt es nichts zu entscheiden.

Die Reihenfolge der Eintraege ist die SCRAPE-Reihenfolge (frueher
scheduler.SOURCES) und zugleich die Reihenfolge, in der /api/health und die
Quellen-Chips die Quellen auflisten. Sie ist NICHT die Prioritaet - die steht
als Zahl im Eintrag.
"""

SOURCES = {
    "kulturkalender": {
        "name": "Kulturkalender",
        "status": "live",
        "priority": 90,
    },
    "rauze": {
        "name": "Rauze",
        "status": "live",
        "priority": 70,
    },
    "ra": {
        "name": "Resident Advisor",
        "status": "live",
        "priority": 80,
    },
    "cybersax": {
        "name": "SAX Terminal",
        "status": "live",
        "priority": 100,
    },
    "azconni": {
        "name": "AZ Conni",
        "status": "live",
        "priority": 60,
        "venue_key": "conni",
        # Das Haus schreibt sich selbst "AZ Conni", rauze.de listet es genauso,
        # umgangssprachlich heisst es nur "Conni".
        "aliases": ["az-conni", "conni-club", "azc"],
    },
    "sektor": {
        "name": "Sektor Evolution",
        "status": "live",
        "priority": 50,
        "venue_key": "sektor-evolution",
        # Das Haus selbst schreibt sich auf seiner Seite ohne Leerzeichen.
        "aliases": ["sektor", "sektorevolution"],
    },
    "derlude": {
        "name": "Der Lude",
        "status": "live",
        "priority": 10,
    },
    "strassee": {
        "name": "Straße E",
        "status": "live",
        "priority": 20,
    },
    "groovestation": {
        "name": "GrooveStation",
        "status": "live",
        "priority": 30,
        "venue_key": "groovestation",
        "aliases": ["groove-station"],
    },
    "zentralwerk": {
        "name": "Zentralwerk",
        "status": "live",
        "priority": 40,
    },
}

# Ortsnamen von Haeusern, zu denen es (noch) keine eigene Quelle gibt. Sobald
# ein Haus hier eine eigene Quelle bekommt, wandern seine Aliase nach oben in
# den Eintrag und verschwinden hier.
EXTRA_VENUE_ALIASES = {
    "objekt-klein-a": ["oka", "objektkleina", "objekt-klein-a-oka"],
    "chemiefabrik": ["chemo", "chemiefabrik-dresden"],
    "beatpol": ["beatpol-ehemals-starclub", "starclub"],
    "kraftwerk-mitte": ["kraftwerk-mitte-dresden"],
    "tante-ju": ["tante-ju-dresden"],
    "puschkin": ["puschkin-club", "blauer-salon-puschkin"],
    # CyberSAX schreibt "Kafe Zeitlos", andere Quellen "Cafe Zeitlos".
    "cafe-zeitlos": ["kafe-zeitlos"],
    "cafe-saite": ["kafe-saite"],
    "blaue-fabrik": ["blaue-fabrik-im-alten-leipziger-bahnhof"],
}


def _check_unique():
    """Eindeutige Slugs und eindeutige Prioritaeten - beim Import, nicht im Test.

    Zwei gleiche priority-Werte waeren kein Tippfehler mit spaeter Wirkung,
    sondern genau der Gleichstand, den db._best_source und db._keeps_own_url
    nicht aufloesen koennen: beide Quellen gaelten als beste, events.url kippte
    bei jedem Lauf hin und her und data/days/*.json bekaeme alle sechs Stunden
    einen sinnlosen Commit.
    """
    seen = {}
    for slug, entry in SOURCES.items():
        prio = entry["priority"]
        if prio in seen:
            raise ValueError(
                f"priority {prio} doppelt vergeben: {seen[prio]} und {slug}. "
                "Prioritaeten muessen eindeutig sein (siehe Modul-Docstring).")
        seen[prio] = slug


_check_unique()


def live_slugs():
    """Alle aktiven Quellen in Scrape-Reihenfolge."""
    return [slug for slug, e in SOURCES.items() if e["status"] == "live"]


def labels():
    """Slug -> Beschriftung, in Scrape-Reihenfolge."""
    return {slug: SOURCES[slug]["name"] for slug in live_slugs()}


def priority_order():
    """Alle aktiven Slugs, beste Quelle zuerst - fuer config.SOURCE_PRIORITY."""
    return sorted(live_slugs(), key=lambda slug: SOURCES[slug]["priority"])


def venue_aliases():
    """Alias-Slug -> gemeinsamer Ortsschluessel (fuer dedup._venue_key)."""
    out = {}
    for entry in SOURCES.values():
        key = entry.get("venue_key")
        if not key:
            continue
        for alias in entry.get("aliases", ()):
            out[alias] = key
    for key, aliases in EXTRA_VENUE_ALIASES.items():
        for alias in aliases:
            out[alias] = key
    return out

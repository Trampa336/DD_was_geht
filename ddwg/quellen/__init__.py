"""Verzeichnis aller Quellen - die einzige Stelle, an der eine Quelle steht.

Die Reihenfolge der Eintraege ist die SCRAPE-Reihenfolge. Der RANG ist eine
eigene Zahl und entscheidet, wessen Angaben beim Verschmelzen einer Doppelung
gewinnen (klein = besser, siehe ddwg/merge.py):

    Seite des Hauses selbst  <  rauze  <  kulturkalender  <  cybersax

Das ist Davids Rangfolge (2026-09-25): die Venues sind die eigentliche Quelle,
die Sammelkalender sind fuer Vollstaendigkeit und zum Entdecken da. rauze
liefert fast immer Bild, Beschreibung und Preis und steht deshalb vor dem
Kulturkalender (Bild ja, Beschreibung 2 %, Preis 0 %) und vor cybersax (kein
Bild, keine Event-Permalinks - nur die Tagesseite).

Felder je Eintrag:
    name    Beschriftung in Ausgabe und Protokoll.
    rang    Rang beim Verschmelzen. **Muss eindeutig sein** - _check_unique()
            prueft das beim Import, weil zwei gleichrangige Quellen die
            Feldwahl bei jedem Lauf kippen lassen koennten.
    ort     Optional: slug des Ortes in orte/orte.json, wenn die Quelle die
            Seite eines einzelnen Hauses ist. Damit weiss die Ausgabe, welche
            Herz-Orte schon eine eigene Quelle haben und welche nicht.
    alias   Optional: Schreibweisen des Hauses, die dedup._venue_key auf einen
            gemeinsamen Schluessel legt (Links steht, was normalize.slugify()
            aus der Schreibweise macht). Seit orte.json die Aliase aufloest,
            ist das nur noch das Sicherheitsnetz fuer Schreibweisen, die dort
            noch fehlen.

Resident Advisor ist mit v3 rausgeflogen: 12 Zeilen, jede davon auch bei rauze
oder auf der Seite des Hauses (gemessen 2026-09-25).
"""

QUELLEN = {
    "kulturkalender": {"name": "Kulturkalender", "rang": 90},
    "rauze": {"name": "Rauze", "rang": 70},
    "cybersax": {"name": "SAX Terminal", "rang": 100},
    "azconni": {
        "name": "AZ Conni", "rang": 60, "ort": "az-conni",
        # Das Haus schreibt sich selbst "AZ Conni", rauze.de listet es genauso,
        # umgangssprachlich heisst es nur "Conni".
        "venue_key": "conni", "alias": ["az-conni", "conni-club", "azc"],
    },
    "sektor": {
        "name": "Sektor Evolution", "rang": 50, "ort": "sektor-evolution",
        # Das Haus selbst schreibt sich auf seiner Seite ohne Leerzeichen.
        "venue_key": "sektor-evolution", "alias": ["sektor", "sektorevolution"],
    },
    "derlude": {"name": "Der Lude", "rang": 10, "ort": "der-lude"},
    "strassee": {"name": "Straße E", "rang": 20, "ort": "strasse-e"},
    "groovestation": {
        "name": "GrooveStation", "rang": 30, "ort": "groovestation",
        "venue_key": "groovestation", "alias": ["groove-station"],
    },
    "zentralwerk": {"name": "Zentralwerk", "rang": 40, "ort": "zentralwerk"},
}

# Ortsnamen von Haeusern ohne eigene Quelle, die die Aggregatoren
# unterschiedlich schreiben. Sicherheitsnetz fuer dedup._venue_key, siehe oben.
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
    "paula": ["club-paula"],
}


def _check_unique():
    seen = {}
    for slug, entry in QUELLEN.items():
        rang = entry["rang"]
        if rang in seen:
            raise ValueError(f"rang {rang} doppelt vergeben: {seen[rang]} und {slug}.")
        seen[rang] = slug


_check_unique()


def slugs():
    """Alle Quellen in Scrape-Reihenfolge."""
    return list(QUELLEN)


def name(slug):
    return QUELLEN.get(slug, {}).get("name", slug)


def rang_liste():
    """Alle Slugs, beste Quelle zuerst."""
    return sorted(QUELLEN, key=lambda slug: QUELLEN[slug]["rang"])


def rang(slug):
    """Rang als Position in rang_liste(); unbekannte Quellen landen hinten."""
    order = rang_liste()
    return order.index(slug) if slug in order else len(order)


def eigene_quelle_je_ort():
    """ort-slug -> quellen-slug fuer alle Haeuser mit eigener Quelle."""
    return {e["ort"]: slug for slug, e in QUELLEN.items() if e.get("ort")}


def venue_aliases():
    """Alias-Slug -> gemeinsamer Ortsschluessel (fuer dedup._venue_key)."""
    out = {}
    for entry in QUELLEN.values():
        key = entry.get("venue_key")
        if not key:
            continue
        for alias in entry.get("alias", ()):
            out[alias] = key
    for key, aliases in EXTRA_VENUE_ALIASES.items():
        for alias in aliases:
            out[alias] = key
    return out

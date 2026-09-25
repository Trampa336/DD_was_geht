"""Einmalig: die Orte aus der v2-Datenbank nach orte/orte.json uebernehmen.

Aufruf:
    python werkzeuge/orte_export.py <pfad/zur/dd-was-geht-v2.db>

Uebernommen wird alles, was an einem Ort haengt und nur mit vielen Requests
wiederzubeschaffen waere: Aliase, Region, Art, Homepage, Cover (Medien-Slider
der Kulturkalender-Ortsseite), Beschreibung, Adresse, Telefon,
Oeffnungszeiten, Koordinaten. Events werden NICHT uebernommen - die baut der
naechste Scrape frisch auf.

Dabei werden die bekannten doppelt angelegten Haeuser zusammengelegt
(ZUSAMMENLEGEN unten) und die Haeuser mit eigener Quelle als Start-Herzen
markiert.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg import quellen  # noqa: E402
from ddwg.orte import ORTE_PATH, Orte  # noqa: E402

# ziel-slug -> (neuer Name oder None, [slugs, die darin aufgehen])
ZUSAMMENLEGEN = {
    # Vier Eintraege fuer ein Haus: die Quellen schreiben mal die Halle
    # ("Bunker Straße E", "Reithalle Straße E"), mal das ganze Gelaende. Die
    # Halle bleibt am Event sichtbar (ort_roh), der Ort ist einer.
    "strasse": ("Straße E", ["reithalle-strasse", "bunker-strasse", "strasse-reithalle"]),
    "paula": ("Club Paula", ["club-paula"]),
    "club-baerenzwinger": (None, ["baerenzwinger"]),
    "erich-kaestner-haus-fuer-literatur": (None, ["das-erich-kaestner-haus-fuer-literatur"]),
}
UMBENENNEN = {"strasse": "strasse-e"}


def _adresse(row):
    if row["street"]:
        stadt = " ".join(p for p in (row["postcode"], row["city"]) if p)
        return ", ".join(p for p in (row["street"], stadt) if p)
    return row["address"]


def main(db_path):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    aliase = {}
    for row in conn.execute("SELECT raw_venue, venue_id FROM venue_aliases ORDER BY raw_venue"):
        aliase.setdefault(row["venue_id"], []).append(row["raw_venue"])

    data = {}
    for row in conn.execute("SELECT * FROM venues ORDER BY slug"):
        data[row["slug"]] = {
            "name": row["name"],
            "aliase": aliase.get(row["id"], []),
            "region": row["region"],
            "art": row["kind"],
            "treffpunkt": bool(row["is_meeting_point"]),
            "homepage": row["homepage_url"],
            "cover": row["og_image_url"],
            "beschreibung": row["meta_description"],
            "adresse": _adresse(row),
            "telefon": row["phone"],
            "oeffnungszeiten": row["opening_hours"],
            "lat": row["lat"],
            "lon": row["lon"],
            "geo_quelle": row["geo_source"],
        }
    orte = Orte(data, ORTE_PATH)
    print(f"{len(orte)} Orte aus {db_path} gelesen.")

    for ziel, (name, weitere) in ZUSAMMENLEGEN.items():
        vorher = [orte[s]["name"] for s in [ziel, *weitere]]
        orte.zusammenlegen(ziel, *weitere)
        if name:
            orte[ziel]["name"] = name
        print(f"  zusammengelegt: {' + '.join(vorher)} -> {orte[ziel]['name']}")
    for alt, neu in UMBENENNEN.items():
        orte.by_slug[neu] = orte.by_slug.pop(alt)
        orte._reindex()
        print(f"  umbenannt: {alt} -> {neu}")

    for ort_slug in sorted(quellen.eigene_quelle_je_ort()):
        if orte.get(ort_slug) is None:
            print(f"  WARNUNG: Ort {ort_slug} aus ddwg/quellen fehlt in der DB")
            continue
        orte.set_herz(ort_slug)
    print(f"  Herz gesetzt: {', '.join(orte.herz_orte())}")

    os.makedirs(os.path.dirname(ORTE_PATH), exist_ok=True)
    orte.save()
    print(f"{len(orte)} Orte nach {ORTE_PATH} geschrieben.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])

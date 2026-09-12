"""Kuratiert venues.kind fuer die 74 Venues aus Paket P5t.

Hintergrund: P5b massa 74 der 726 adressierbaren Venues als "wirklich karg"
(ein Event, kein Bild, keine Beschreibung, siehe tools/venue_readiness_report.py).
P5t hat auf genau diese 74 tools/enrich_venues.py --ids=... laufen lassen
(voller Tages-Zensus, nicht die Stichprobe) - Ergebnis: 0/74 haben einen
Kulturkalender-Link. Grund ist strukturell, nicht mangelnder Versuch: alle 74
haben als einzige Quelle 'cybersax', und dieser Scraper listet laut eigenem
Docstring (app/scrapers/cybersax.py) ausdruecklich NUR, was der Kulturkalender
NICHT ohnehin schon fuehrt - eine cybersax-only-Venue hat also nie eine
Kulturkalender-Seite, ueber die tools/enrich_venues.py Homepage/Cover/
Beschreibung finden koennte. Cover/Homepage/meta_description bleiben fuer
alle 74 leer; das einzige, was noch manuell zu heben war, ist `kind`.

REGEL (P5t-packet.md, "Hard rule on descriptions"): kind wird NUR aus dem
Venue-NAMEN und den echten Event-TITELN erschlossen, nie aus Weltwissen ueber
die tatsaechliche Einrichtung. Gezaehlt hat hier ausschliesslich ein direkter,
im Namenstext lesbarer Hinweis (".. kirche" -> kirche, "Museum .." -> museum,
".. Theater .." -> theater, ".. Club .." -> club, ".. Galerie .." -> galerie,
".. park" -> park). Blieb der Name uneindeutig, blieb kind='sonstiges' -
das ist eine bewusste, gueltige Antwort (Entscheidung #14), keine Luecke.

20 von 74 hatten einen Namens-Hinweis dieser Art, siehe MAPPING (mit
Begruendung je Zeile). Die anderen 54 bleiben 'sonstiges'; 9 davon waren
Kandidaten mit einem plausiblen, aber nicht eindeutig lesbaren Hinweis - die
stehen im P5t-Bericht als "unsicher", nicht hier im MAPPING.

Aufruf:
    ../.venv/bin/python tools/curate_kind_p5t.py <db> [--apply]
    (ohne --apply: nur Bericht, nichts geschrieben)
"""
import sys
import sqlite3

# venue_id -> (neues kind, Begruendung - nur Dokumentation, nicht geschrieben)
MAPPING = {
    447: ("treffpunkt", "Name enthaelt 'Nachbarschaftstreff' (ZWICKmühle)"),
    475: ("theater", "Name enthaelt 'Theater' (TheaterScheune)"),
    494: ("kirche", "Name enthaelt 'kirche' (St. Michaelskirche Dresden-Bühlau)"),
    504: ("kirche", "Name enthaelt 'kirche' (Schifferkirche Maria am Wasser)"),
    507: ("club", "Name enthaelt 'Club' (Sachsenkeller-Club)"),
    519: ("museum", "Name enthaelt 'sammlung' (Puppentheatersammlung) - "
                     "'Sammlung' liest sich als Museumsbestand; geringere "
                     "Zuversicht als die reinen Keyword-Treffer, siehe Bericht"),
    523: ("theater", "Name enthaelt 'Theater' (Piccolo Theater)"),
    537: ("museum", "Name enthaelt 'Museum' (Museum für Sächs. Volkskunst)"),
    538: ("museum", "Name enthaelt 'Museum' (Museum der Westlausitz)"),
    568: ("kirche", "Name enthaelt 'Kirche' (Kirche St. Marien)"),
    572: ("kirche", "Name enthaelt 'Kirche' (Kirche Loschwitz)"),
    598: ("kirche", "Name enthaelt 'kirche' (Hospitalkirche)"),
    619: ("theater", "Name enthaelt 'Theater' (Gerhart Hauptmann-Theater Görlitz)"),
    625: ("galerie", "Name enthaelt 'Galerie' (Galerie kunstgehaeuse)"),
    655: ("kirche", "Name enthaelt 'kirche' (Emmanuskirche Kaditz)"),
    657: ("club", "Name enthaelt 'club' (Eastclub)"),
    658: ("kirche", "Name enthaelt 'kirche' (Dreikönigskirche)"),
    659: ("kirche", "Name enthaelt 'kirche' (Dorfkirche)"),
    667: ("club", "Name enthaelt 'Club' (Club Count Down)"),
    706: ("park", "Name enthaelt 'park' (Alaunpark)"),
}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)

    conn = sqlite3.connect(args[0])
    conn.row_factory = sqlite3.Row
    ids = list(MAPPING.keys())
    qmarks = ",".join("?" * len(ids))
    rows = {r["id"]: r for r in conn.execute(
        f"SELECT id, name, kind FROM venues WHERE id IN ({qmarks})", ids).fetchall()}

    changed = 0
    for vid, (new_kind, why) in MAPPING.items():
        row = rows.get(vid)
        if row is None:
            print(f"  WARNUNG: venue_id {vid} nicht gefunden - uebersprungen")
            continue
        if row["kind"] == new_kind:
            print(f"  {vid:4} {row['name']:45} bereits {new_kind}")
            continue
        print(f"  {vid:4} {row['name']:45} {row['kind']:10} -> {new_kind:10} ({why})")
        changed += 1
        if apply:
            conn.execute("UPDATE venues SET kind = ? WHERE id = ?", (new_kind, vid))

    if apply:
        conn.commit()
        print(f"\n{changed} Zeilen geschrieben und committed.")
    else:
        conn.rollback()
        print(f"\n{changed} Zeilen wuerden sich aendern (Probelauf, nichts geschrieben).")


if __name__ == "__main__":
    main()

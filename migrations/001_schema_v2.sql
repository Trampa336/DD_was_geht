-- dd-was-geht: Schema v2 (Frischstart, keine Migration aus v1)
--
-- Entwurf zu Paket P2. Begruendungen stehen als Kommentar direkt an der
-- Spalte, die sie betrifft - jede Zahl darin ist gemessen, nicht geschaetzt.
-- Messgrundlage: 12 veroeffentlichte Staende im Git von /root/dd-was-geht-site
-- (2026-08-22 bis 2026-09-11) plus die Live-DB vom 2026-09-11.
--
-- Zaehlweisen werden hier konsequent benannt, weil sie staendig verwechselt
-- werden: "Gewinner" = events mit duplicate_of IS NULL (5386, davon 5235 in
-- der Zukunft), "Reichweite" = Zeilen in event_sources (6045), "Lauf-gesehen"
-- = event_count in scrape_runs.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;


-- ===========================================================================
-- 1. VENUES - ab jetzt erstklassige Zeilen statt Freitext
-- ===========================================================================
--
-- Messung: 744 verschiedene venue-Strings bei den Gewinnern in der Zukunft.
-- Reine String-Normalisierung (Kleinschreibung, Umlaute, Klammern, "Dresden"/
-- "e.V."/"GmbH" entfernt) legt davon nur 35 zusammen - 4,7% Kollaps, also
-- rund 710 kanonische Venues. Wer mehr erwartet hat, irrt sich: die Strings
-- sind ueberwiegend echt verschieden, nicht schlampig geschrieben.
--
-- Das eigentliche Problem ist deshalb NICHT Dedup, sondern der lange Schwanz:
-- 284 der 744 Strings (38,2%) haben genau EIN Event, 415 (55,8%) hoechstens
-- zwei. Eine Venue-Seite mit "kommende Termine" ist nur fuer den Kopf
-- sinnvoll - rund 120 Venues mit >10 Events tragen den Grossteil des
-- Katalogs. P4 sollte Metadaten deshalb nach Eventzahl absteigend holen und
-- nicht versuchen, 744 Homepages zu finden.
CREATE TABLE venues (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Der Kollaps-Schluessel. Zwei Rohstrings mit demselben slug sind
    -- dieselbe Venue. slug wird aus dem Anzeigenamen erzeugt (normalize.
    -- slugify + Entfernen von "dresden"/"e.V."/"GmbH"/Klammerzusaetzen).
    slug            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,              -- Anzeigename, gepflegt

    -- Region wandert vom Event an die Venue. Bisher rechnet db.py das je
    -- Event zur Lesezeit aus (geo.classify_region), also 5235 Aufrufe statt
    -- 744. Der Grund fuer "nicht speichern" war laut Kommentar in db.py, dass
    -- die Ortslisten in geo.py weiterwachsen und ein gespeicherter Wert
    -- veraltet. An der Venue ist das entschaerft: es sind 744 Zeilen, die ein
    -- Reclassify-Lauf in Sekunden neu setzt (siehe tools/reclassify.py).
    -- Werte: 'dresden' | 'umland' | 'weiter' - exakt geo.REGION_*.
    region          TEXT NOT NULL DEFAULT 'dresden'
                        CHECK (region IN ('dresden', 'umland', 'weiter')),

    -- DAS ist der Hebel fuer bessere Kategorien (siehe Abschnitt 4).
    -- Beispiel aus der Messung: von 1179 "fuehrungen" stecken 634 (54%) in
    -- nur sechs Venues - Dom zu Meissen (286), Schloss Wackerbarth (111),
    -- Erlebniswelt Meissen (70), Terrassenufer (62), Frauenkirche (54),
    -- "Dresden City" (51). Einmal die Venue-Art pflegen schlaegt jede
    -- Titel-Heuristik pro Event.
    -- Werte z.B.: 'museum','club','kirche','theater','kino','weingut',
    -- 'galerie','buehne','treffpunkt','park','sonstiges'
    kind            TEXT NOT NULL DEFAULT 'sonstiges',

    -- "Dresden City", "Terrassenufer Dresden", "Theaterplatz Dresden" sind
    -- keine Spielstaetten, sondern Treffpunkte fuer Stadtrundfahrten. Sie
    -- bekommen keine Venue-Seite und sollen aus "Orte in Dresden" heraus.
    is_meeting_point INTEGER NOT NULL DEFAULT 0 CHECK (is_meeting_point IN (0,1)),

    -- Traeger-Hierarchie statt Dedup: 48 Strings tragen ein " - "-Suffix,
    -- 14 davon "Staatliche Kunstsammlungen Dresden" (Gemaeldegalerie,
    -- Residenzschloss, Gruenes Gewoelbe, Japanisches Palais ...). Das sind
    -- echte, getrennte Haeuser EINES Traegers - zusammenwerfen waere falsch,
    -- aber die Venue-Seite will "weitere Haeuser der SKD" zeigen koennen.
    parent_venue_id INTEGER REFERENCES venues(id) ON DELETE SET NULL,

    -- --- ab hier fuellt P4, alles bewusst NULL-bar ---
    homepage_url    TEXT,
    -- scheme://netloc von homepage_url, zusaetzlich zur vollen URL (P5a/P4c-
    -- Carry-in): 45 von 123 gespeicherten Homepages sind keine Site-Wurzeln,
    -- sondern /veranstaltungen/, /programm/, /spielplan/ - der Pfad, den die
    -- Venue beim Kulturkalender hinterlegt hat. Ein "Homepage"-Knopf, der auf
    -- der eigenen Terminliste der Venue landet, ist schlechte UX. Beide
    -- Spalten bleiben nebeneinander stehen, keine ersetzt die andere.
    homepage_root   TEXT,
    meta_title      TEXT,
    meta_description TEXT,
    og_image_url    TEXT,
    -- Welche Quelle das Cover geliefert hat - og_image_url selbst haelt nur
    -- das Ergebnis des Fallbacks (tools/load_enrichment.py: kk_cover_url ODER
    -- homepage-og:image), nicht welche der beiden Seiten gewonnen hat.
    -- NICHT die Reihenfolge des Fallbacks aendern: KK zuerst, Homepage-
    -- og:image nur als zweite Wahl - eine Umkehr wuerde sofort kaputte Bilder
    -- zeigen (og_image_audit.py: nur 13 von 34 Homepage-og:image-Treffern
    -- taugen ueberhaupt als Cover).
    cover_source    TEXT CHECK (cover_source IN ('kulturkalender', 'homepage') OR cover_source IS NULL),
    -- Wann zuletzt geholt und mit welchem Ergebnis. Ohne Status-Spalte
    -- versucht P4 bei jedem Lauf erneut die 300 Venues ohne Homepage.
    meta_fetched_at TEXT,
    meta_status     TEXT,                       -- 'ok' | 'not_found' | 'error:<kurz>'

    -- --- ab hier fuellt P5v, ebenfalls NULL-bar ---
    -- Adresse/Telefon/Oeffnungszeiten aus den cybersax-Adressseiten (74 Venues,
    -- siehe tools/load_cybersax_contact.py). Rohtext der Quelle, unveraendert:
    -- Oeffnungszeiten insbesondere NICHT in ein Stunden/Wochentag-Schema
    -- zerlegt - das wuerde der Quelle eine Praezision unterstellen, die sie
    -- nicht hat, und die Seite ist oeffentlich (echte Dresdner Adressen).
    address              TEXT,
    phone                TEXT,
    opening_hours        TEXT,
    -- Datum (nicht Uhrzeit) der cybersax-Adressseite, aus der die drei obigen
    -- Felder stammen. Oeffnungszeiten veralten, eine Adresse/Telefonnummer
    -- kaum - app/templates/venue.html zeigt dieses Datum deshalb NUR neben
    -- opening_hours, nicht neben address/phone (siehe Bericht zu P5v).
    contact_fetched_at   TEXT,

    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL
);

CREATE INDEX idx_venues_region ON venues(region);
CREATE INDEX idx_venues_kind   ON venues(kind);
CREATE INDEX idx_venues_parent ON venues(parent_venue_id);


-- Die Zuordnung Rohstring -> Venue gehoert in DATEN, nicht in Code.
-- Die Scraper liefern weiter Freitext; hier wird er aufgeloest. Ein neuer,
-- unbekannter String legt automatisch Venue + Alias an. Stellt sich spaeter
-- heraus, dass "Scheune" und "Scheune Dresden (Vorplatz)" dasselbe sind,
-- zeigt man den Alias auf die andere venue_id um - ohne Deploy, ohne dass
-- ein einziges Event angefasst werden muss (und ohne dass ein Herz bricht).
CREATE TABLE venue_aliases (
    raw_venue   TEXT PRIMARY KEY,               -- exakt wie vom Scraper geliefert
    venue_id    INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    -- 'auto' = beim Import erzeugt, 'manuell' = David hat zusammengelegt.
    -- Ein Reclassify-Lauf darf 'manuell' NIE ueberschreiben.
    origin      TEXT NOT NULL DEFAULT 'auto' CHECK (origin IN ('auto','manuell')),
    first_seen  TEXT NOT NULL
);

CREATE INDEX idx_venue_aliases_venue ON venue_aliases(venue_id);


-- ===========================================================================
-- 2. KATEGORIEN - Tabelle, nicht Spalte
-- ===========================================================================
--
-- Warum eine Tabelle: die Anforderung lautet "Kultur/Musik/Nightlife by
-- default sichtbar, Tourismus-Schwanz einen Schalter entfernt, aber alles
-- bleibt in der DB". Sichtbarkeit ist damit eine Eigenschaft der Kategorie.
-- Als Spalte muesste sie in Code stehen und jede Meinungsaenderung waere ein
-- Deploy; als Zeile ist sie ein UPDATE.
--
-- WAS DER AGGREGATOR WIRKLICH HERGIBT (das war bisher unbekannt und blockiert
-- "bessere Kategorien" - hier ist die Messung):
--   * raw_category ist bei 1599/5235 = 30,5% der Gewinner ueberhaupt gefuellt.
--     Ausgerechnet der Kulturkalender, der 4472 der 5235 Events (85%) liefert,
--     fuellt sie nur zu 20,6%. cybersax 100%, rauze 71%, zentralwerk 0%.
--   * description ist bei 9,1% gefuellt - beim Kulturkalender bei 2,5%.
--     Es gibt also praktisch KEINEN Fliesstext zum Klassifizieren.
--   * Das URL-Pfadsegment taugt fast nichts: der Kulturkalender legt 3862 von
--     4472 Events unter /veranstaltung/ ab. Trennscharf sind nur
--     /ausstellung/ (457) und /festival/ (73).
-- Fazit: fuer 85% des Katalogs sind TITEL und VENUE das einzige Signal. Und
-- die Venue ist davon das stabilere - deshalb venues.kind oben.
CREATE TABLE categories (
    slug            TEXT PRIMARY KEY,           -- 'musik','kultur','fuehrungen',...
    label           TEXT NOT NULL,              -- Anzeigename im UI
    -- Steuert die Startansicht. Der Tourismus-Schwanz bleibt in der DB, ist
    -- aber abgewaehlt - genau ein Schalter im UI kippt das.
    default_visible INTEGER NOT NULL DEFAULT 1 CHECK (default_visible IN (0,1)),
    sort_order      INTEGER NOT NULL DEFAULT 100
);

INSERT INTO categories (slug, label, default_visible, sort_order) VALUES
    ('musik',      'Musik',            1, 10),
    ('nightlife',  'Nightlife',        1, 20),   -- neu; heute in musik/sonstiges versteckt
    ('kultur',     'Kultur',           1, 30),
    ('familie',    'Familie',          1, 40),
    ('outdoor',    'Outdoor',          1, 50),
    ('sport',      'Sport',            1, 60),
    -- 1179 Eintraege, groesster einzelner Block nach sonstiges. Nicht loeschen,
    -- nur standardmaessig aus.
    ('fuehrungen', 'Führungen & Touren', 0, 70),
    -- 1832 Eintraege (35%). Restfach des Klassifikators, KEIN Geschmacksmerkmal
    -- (siehe scoring.NEUTRAL_CATEGORIES - vier Skips hatten hier einmal 40% des
    -- Katalogs stummgeschaltet).
    ('sonstiges',  'Sonstiges',        1, 99);


-- Querschnitts-Etiketten, die keine Kategorie sind. Messung: der haeufigste
-- raw_category-Wert ueberhaupt ist "Festival" (317), gefolgt von "Ausstellung"
-- (220+78), "Fuehrung" (139+35), "Interkulturelle Tage" (51), "Tag des
-- Offenen Denkmals" (33), "Herbst- und Weinfest" (25). Ein Festival ist aber
-- kein Gegensatz zu Musik, und "Tag des Offenen Denkmals" ist ein Datum, kein
-- Genre. Solche Werte gehoeren nebeneinander, nicht in eine 1:1-Spalte -
-- deshalb Kategorie = 1 pro Event (FK), Tags = n pro Event.
CREATE TABLE tags (
    slug  TEXT PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE event_tags (
    event_uid TEXT NOT NULL REFERENCES events(uid) ON DELETE CASCADE,
    tag_slug  TEXT NOT NULL REFERENCES tags(slug)  ON DELETE CASCADE,
    PRIMARY KEY (event_uid, tag_slug)
);

CREATE INDEX idx_event_tags_tag ON event_tags(tag_slug);


-- ===========================================================================
-- 3. EVENTS
-- ===========================================================================
--
-- uid BLEIBT der Identitaetsschluessel, und das ist ein Messergebnis, keine
-- Bequemlichkeit. uid = sha1("<date>|<time>|<slug(title)>|<slug(venue)>")[:16]
-- (normalize.make_event_uid), also ein INHALTS-Hash: aendert die Quelle eines
-- dieser vier Felder, entsteht eine neue uid.
--
-- Gemessen wurde deshalb nicht der Code, sondern die veroeffentlichten Staende.
-- Identitaet unabhaengig von der uid ueber (source, url, date), beschraenkt auf
-- Schluessel, die in beiden Staenden genau einmal vorkommen:
--   38.558 Vergleiche derselben Veranstaltung ueber 11 Uebergaenge
--   -> 40 uid-Wechsel = 0,104%
--   -> in 8 von 11 Uebergaengen exakt 0,00%
--   -> die Ausreisser sind die grossen ZEITLUECKEN, nicht die Re-Scrapes:
--      15 Tage Pause = 1,83%, 3 Tage = 0,13%. Zwischen zwei 6h-Laeufen: 0,00%.
--   -> Ursache der 40 Wechsel: venue 19, title 14, time 6, time+title 1.
--   -> Kollisionen (eine uid zeigt ueber die Zeit auf zwei verschiedene
--      Quell-URLs): 31 von 8468 = 0,37%, ausschliesslich bei generischen
--      Wiederholungstiteln ("Wein-Fuehrung"/"Sekt-Fuehrung").
-- WICHTIG zur Interpretation: ein erster, naiverer Lauf ueber (source,url)
-- zeigte 0,55% und "date" als Hauptursache. Das war ein Artefakt - 3680 der
-- 5235 Events teilen sich eine URL mit anderen (Terminserien nutzen EINE
-- Seite). Auf Vorkommens-Ebene wandern Daten nicht: 0 von 2280 eindeutigen
-- Serien haben binnen 24h ihr Datum gewechselt.
--
-- Verdikt: Re-Scrapes erzeugen KEINE neuen Zeilen. Die Herz-Praemisse haelt.
-- Rest-Risiko ist nicht null: redigiert eine Quelle Titel/Zeit/Ort, bricht die
-- uid. Fuer ein Herz, das ~30 Tage bis zum Termin liegt, sind das grob 3-4%.
-- Darum wird das in Abschnitt 5 aufgefangen, statt eine neue ID zu erfinden.
CREATE TABLE events (
    uid             TEXT PRIMARY KEY,           -- normalize.make_event_uid(), unveraendert

    -- Vorkommens-Schluessel: sha1("<source>|<url>|<date>"). BEWUSST NICHT
    -- UNIQUE - 1263 der 5235 Events teilen sich (source,url,date), weil
    -- Serien eine Seite benutzen. Er ist keine Identitaet, sondern der
    -- Wiederanknuepfungs-Griff fuer Herzen (Abschnitt 5): wenn eine uid
    -- wegbricht, sind die Kandidaten fuer "das ist dasselbe Event" genau die
    -- Zeilen mit demselben identity_key.
    identity_key    TEXT NOT NULL,

    source          TEXT NOT NULL,              -- Gewinner-Quelle (event_sources = Reichweite)
    date            TEXT NOT NULL,              -- ISO YYYY-MM-DD
    time            TEXT,                       -- HH:MM oder NULL
    title           TEXT NOT NULL,

    -- Aufgeloeste Venue. NULL-bar, weil einige Quellen keinen Ort liefern;
    -- ON DELETE RESTRICT, damit niemand eine Venue loeschen kann, an der noch
    -- Events haengen.
    venue_id        INTEGER REFERENCES venues(id) ON DELETE RESTRICT,
    -- Der Rohstring bleibt erhalten. Ohne ihn ist nach dem ersten
    -- Alias-Umbiegen nicht mehr nachvollziehbar, was die Quelle gesagt hat.
    raw_venue       TEXT,

    category_slug   TEXT NOT NULL DEFAULT 'sonstiges'
                        REFERENCES categories(slug) ON DELETE RESTRICT,
    raw_category    TEXT,                       -- nur zu 30,5% gefuellt, s.o.

    url             TEXT,
    image_url       TEXT,
    price_text      TEXT,
    description     TEXT,                       -- nur zu 9,1% gefuellt, s.o.
    detail_fetched_at TEXT,

    -- Unveraendert aus v1 uebernommen: Zeile bleibt, wird aber nicht mehr
    -- ausgeliefert (app/dedup.py).
    duplicate_of    TEXT REFERENCES events(uid) ON DELETE SET NULL,

    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL
);

CREATE INDEX idx_events_date         ON events(date);
CREATE INDEX idx_events_duplicate_of ON events(duplicate_of);
CREATE INDEX idx_events_venue        ON events(venue_id);
CREATE INDEX idx_events_category     ON events(category_slug);
CREATE INDEX idx_events_identity     ON events(identity_key);
-- Die Startansicht fragt immer "Gewinner, ab heute, nach Datum" - dieser
-- Teilindex bedient sie ohne die 561 Duplikat-Zeilen anzufassen.
CREATE INDEX idx_events_live ON events(date, category_slug)
    WHERE duplicate_of IS NULL;


-- ===========================================================================
-- 4. BUCHFUEHRUNG - unveraendert aus v1, weil sie traegt
-- ===========================================================================
-- Diese drei Tabellen sind der Grund, warum eine kaputte Quelle ueberhaupt
-- auffaellt. P3 darf sie NICHT wegrationalisieren.

CREATE TABLE event_sources (
    event_uid   TEXT NOT NULL REFERENCES events(uid) ON DELETE CASCADE,
    source      TEXT NOT NULL,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    PRIMARY KEY (event_uid, source)
);
CREATE INDEX idx_event_sources_uid ON event_sources(event_uid);

CREATE TABLE event_duplicates (
    duplicate_uid    TEXT PRIMARY KEY,
    canonical_uid    TEXT NOT NULL,
    duplicate_source TEXT,
    canonical_source TEXT,
    match_score      REAL,
    matched_on       TEXT,
    first_seen       TEXT NOT NULL,
    last_seen        TEXT NOT NULL
);
CREATE INDEX idx_event_duplicates_canonical ON event_duplicates(canonical_uid);

-- Ohne diese Tabelle sieht eine Quelle, die nach einer HTML-Aenderung 0 Events
-- liefert, exakt aus wie ein ruhiger Tag.
CREATE TABLE scrape_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    ok          INTEGER NOT NULL DEFAULT 0,
    event_count INTEGER,
    error       TEXT
);
CREATE INDEX idx_scrape_runs_source ON scrape_runs(source, started_at);


-- ===========================================================================
-- 5. HERZEN - Davids redaktionelle Auswahl
-- ===========================================================================
--
-- Akzeptanztest des ganzen Umbaus: ein Herz muss einen Re-Scrape ueberleben.
-- Nach der Messung oben ist das fuer 99,9% der Faelle geschenkt. Die Tabelle
-- ist fuer die restlichen 0,1% gebaut.
--
-- ZWEI Regeln, und beide sind wichtiger als sie aussehen:
--
-- (a) KEIN "ON DELETE CASCADE" auf event_uid. Ein Herz darf NIE verschwinden,
--     weil eine Event-Zeile verschwindet. Genau das ist der Fehler, der den
--     ganzen Umbau wertlos machen wuerde, und er faellt beim Testen nicht auf -
--     er faellt drei Monate spaeter auf, wenn die kuratierte Seite leer ist.
--     Deshalb ist hier bewusst gar kein FOREIGN KEY auf events(uid) definiert.
--
-- (b) Das Herz traegt einen SCHNAPPSCHUSS des Events mit sich. Damit ist es
--     auch dann noch anzeigbar und wiederfindbar, wenn die Event-Zeile weg
--     oder die uid gewechselt ist. Das kostet ein paar hundert Byte pro Herz
--     und ersetzt eine ganze Reparatur-Mechanik.
CREATE TABLE hearts (
    event_uid       TEXT PRIMARY KEY,           -- absichtlich OHNE FK, siehe (a)

    -- Wiederanknuepfung: bricht die uid, sucht ein Reparaturlauf Events mit
    -- diesem identity_key und - falls die URL sich auch geaendert hat - mit
    -- gleichem Datum und aehnlichem Titel (app/dedup.py kann das schon).
    identity_key    TEXT NOT NULL,

    -- Schnappschuss, siehe (b). Nicht normalisiert, das ist Absicht.
    snap_title      TEXT NOT NULL,
    snap_date       TEXT NOT NULL,
    snap_time       TEXT,
    snap_venue      TEXT,
    snap_url        TEXT,
    snap_source     TEXT,

    -- Redaktion: freie Notiz und eine Sortierung fuer die kuratierte Seite.
    note            TEXT,
    sort_order      INTEGER NOT NULL DEFAULT 0,

    -- 'ok'      = uid zeigt auf eine lebende Event-Zeile
    -- 'verwaist'= uid nicht mehr da, Wiederanknuepfung offen (UI: nachfragen)
    -- 'neu_verknuepft' = automatisch auf eine neue uid gezogen
    link_status     TEXT NOT NULL DEFAULT 'ok'
                        CHECK (link_status IN ('ok','verwaist','neu_verknuepft')),
    relinked_from   TEXT,                       -- vorherige uid, zur Nachvollziehbarkeit

    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX idx_hearts_identity ON hearts(identity_key);
CREATE INDEX idx_hearts_date     ON hearts(snap_date);
CREATE INDEX idx_hearts_status   ON hearts(link_status);


-- ===========================================================================
-- 6. SCORE / REAKTIONEN - was davon bleibt
-- ===========================================================================
--
-- Befund: score ist KEINE Spalte und war nie eine. app/scoring.py rechnet ihn
-- zur Auslieferungszeit aus Laplace-geglaetteten Like-Raten, feed.py schreibt
-- ihn ins Export-JSON. In der Live-DB stehen aber 0 Zeilen in reactions und
-- 0 Zeilen in weights. Das heisst: der score ist derzeit fuer JEDES der 5235
-- Events konstant 50.0 - ein Feld, das in jedem Tages-JSON mitfaehrt und
-- null Information traegt.
--
-- Empfehlung: die Mechanik behalten, das Signal wechseln. Herzen sind das
-- bessere Feedback als ein nie benutztes Daumen-hoch/runter, und zwei
-- konkurrierende Bewertungssysteme im selben UI will niemand. weights bleibt
-- also, gefuettert aus hearts statt aus reactions; reactions faellt weg.
-- Bis weights Daten hat, sollte feed.py den score NICHT exportieren - ein
-- konstantes 50.0 im JSON verleitet P5 dazu, danach zu sortieren.
CREATE TABLE weights (
    key    TEXT PRIMARY KEY,                    -- 'category:musik', 'venue:scheune', 'keyword:...'
    likes  INTEGER NOT NULL DEFAULT 0,
    skips  INTEGER NOT NULL DEFAULT 0
);


-- ===========================================================================
-- 7. Schema-Version
-- ===========================================================================
CREATE TABLE schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO schema_meta (key, value) VALUES
    ('schema_version', '2'),
    ('created_by',     'P2'),
    ('uid_churn_measured', '0.104% ueber 38558 Vergleiche, 12 Staende 2026-08-22..2026-09-11');

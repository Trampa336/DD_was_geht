# dd-was-geht – Projektgedächtnis

Persönlicher Dresdner Veranstaltungskalender von David. Scraper holen Termine aus
Sammelkalendern und direkt von den Seiten der Orte. Daraus entsteht **eine statische
HTML-Datei** (`ausgabe/index.html`) plus drei kleine PWA-Begleitdateien (Manifest,
Service Worker, Icons) im selben Ordner, siehe Abschnitt „Website (GitHub Pages)“.
Es gibt keinen eigenen Server und kein Docker. Seit 2026-09-25 wird das Projekt nur
noch in Claude Cowork bearbeitet (v3). Der alte Stand liegt als Tag `v2-final` in git.

## Befehle
Der Projektordner liegt auf dem Proxmox-Server und ist eingebunden. Symlinks funktionieren
dort nicht, deshalb liegt die Python-Umgebung mit `--copies` unter `venv/`. Keine `.venv`
anlegen: Die alte ist an einem kaputten Symlink gescheitert und ließ sich nur direkt auf
dem Server löschen.
```
python3 -m venv --copies venv    # einmalig, danach venv/bin/python statt python
venv/bin/pip install -r requirements.txt
python -m ddwg scrape            # alle Quellen holen, Events bauen, Ausgabe schreiben (~5–10 min)
python -m ddwg scrape --quelle rauze sektor --ohne-details   # nur ausgewählte Quellen
python -m ddwg build             # ohne Netz: Events neu bauen + ausgabe/index.html
python -m ddwg herz <ort>        # Ort als Herz-Ort markieren (--weg entfernt, --liste zeigt alle)
python -m ddwg orte <suche>      # Orte suchen: slug, Name, Region, Anzahl Events
python -m ddwg status            # letzter Lauf je Quelle, Bestand, neu entdeckte Orte
python -m pytest tests           # Kerntests ohne Netz
```

## Grundprinzip
**Alles Kuratierte liegt in Dateien (git), die Events liegen in einer Wegwerf-DB.**
- `orte/orte.json` (Quelle der Wahrheit, von Hand und von Werkzeugen gepflegt): rund 750 Orte
  mit Aliasen, Region, Art, Herz, Homepage, Cover, Adresse und Koordinaten.
  Unbekannte Schreibweisen legt der Scrape als neuen Ort mit `erstmals` an.
- `orte/flavours.json`: 8 Flavours (voreingestellte Herz-Sets für den ersten Start) und die
  Zuordnung der Top 100 Orte (`haupt`, `neben`, `unklar`), Standard `club`. Zuordnung von
  Sonnet nur aus gescrapten Terminen, korrigiert von David. Es zählt nur `haupt`.
- `cache/events.db` (SQLite, gitignored): `listings` (je Quelle roh, pro Lauf ersetzt) →
  `events` (verschmolzen, bei jedem Build komplett neu) + `scrape_runs` + `details`.
  Löschen ist erlaubt, der nächste Scrape baut die Datenbank neu auf.

## Ablauf (ddwg/pipeline.py)
1. Jede Quelle (`ddwg/quellen/<slug>.py`, Funktion `scrape_range(start, ende)`) liefert Event-dicts.
2. Führungen fallen gleich raus (so entstehen für sie keine Treffpunkt-Orte). Jede übrige
   Zeile wird über `orte.resolve()` einem Ort zugeordnet. **Region `weiter` wird
   verworfen**, also Meißen, Bautzen usw. (Davids Entscheidung). Umland bleibt gespeichert.
3. `dedup.cluster()` bildet Gruppen derselben Veranstaltung. Eine Gruppe enthält von
   jeder Quelle höchstens einen Eintrag.
4. `merge.merge()` verschmilzt Feld für Feld nach Quellen-Rang: Datum, Zeit und Titel
   kommen von der ranghöchsten Quelle, Beschreibung, Preis und Bild von der
   ranghöchsten Quelle, die sie hat.
   Danach verwirft `build()` noch einmal alle Führungen (auch über den Ort geerbte).
5. Für alle Events ohne Beschreibung lädt die Pipeline die Kulturkalender-Detailseite
   nach (seit 2026-09-29, vorher nur Herz-Orte): nächste Tage zuerst, jede Seite nur
   einmal, höchstens 2.500 pro Lauf, Abbruch nach 20 Fehlschlägen in Folge. Ergebnisse
   liegen in der Tabelle `details`; Netzfehler werden nicht gemerkt, sondern beim
   nächsten Lauf erneut versucht.
6. `ausgabe.py` füllt `ddwg/vorlage/index.html` mit JSON → `ausgabe/index.html`.

## Website (GitHub Pages)
Seit 2026-09-26 laeuft `.github/workflows/publish.yml` taeglich (und manuell ueber
„Run workflow“): scraped frisch und veroeffentlicht den Ordner `ausgabe/` auf dem
Branch `gh-pages`. Adresse: `https://trampa336.github.io/DD_was_geht/`. Einmalig
noetig, falls GitHub es nicht selbst erkennt: in den Repo-Einstellungen unter
„Pages“ die Quelle auf Branch `gh-pages` (Ordner `/`) stellen.
Der Workflow behaelt `cache/events.db` per `actions/cache` von Lauf zu Lauf, damit
die nachgeladenen Beschreibungen (`details`) erhalten bleiben. Fehlt der Cache
(z. B. nach 7 Tagen ohne Lauf), laedt der erste Lauf alle Detailseiten neu (~45 min).

`ddwg/vorlage/pwa/` enthaelt Manifest, Service Worker (`sw.js`) und Icons.
`ausgabe.py` kopiert sie beim Bauen neben `index.html`. Lokal per Doppelklick
geoeffnet (`file://`) aendert sich nichts, der Service Worker registriert sich
nur online (http/https). Der Service Worker cacht die Seite „network-first“:
online kommen immer frische Termine, offline der zuletzt geladene Stand. Wer
die Liste der gecachten Dateien in `sw.js` (`ASSETS`) aendert, muss den
`CACHE`-Namen hochzaehlen, sonst bleibt der alte Stand haengen. Die
Entdecken-Karte braucht wegen Leaflet/markercluster von cdnjs und den
Kartenkacheln weiterhin Internet, auch offline-installiert.

## Quellen und Rang (ddwg/quellen/__init__.py, kleiner = besser)
Seiten der Orte selbst (derlude 10, strassee 20, groovestation 30, zentralwerk 40,
sektor 50, azconni 60, ostpol 65, scheune 66, chemiefabrik 67, holeoffame 68) < rauze 70 < kulturkalender 90 < cybersax 100.
Davids Regel: **Venue-Seite > Rauze > KK/cybersax.** Die Sammelkalender dienen der
Vollständigkeit und dem Entdecken.

Gemessen am 15.09.2026, v2-DB, Anteil der Zeilen mit Feld:

| Quelle | Bild | Beschreibung | Preis |
|---|---|---|---|
| KK | 100 % | 2 % | 0 % |
| cybersax | 0 % | 24 % | 0 %, keine Event-Permalinks |
| rauze | 99 % | 99 % | 91 % |
| Venue-Seiten | – | fast immer | – |

Sektor Evolution ist ohne den eigenen Scraper praktisch unsichtbar: Rauze führt 2 der
Termine, KK 1. Resident Advisor ist raus, dort gab es nichts Eigenes.

## Herzen
Herzen gibt es **nur für Orte**, nicht für einzelne Events. **Herzen gehören dem Browser:**
Flavours beim ersten Start (ohne Wahl: Club) plus eigene Änderungen am Herz-Knopf.
`"herz": true` in orte.json ist Davids Liste (steuert seit 2026-09-29 keinen Abruf mehr);
„Herzen nach orte.json“ klein in der Karte gleicht sie per `python -m ddwg herz …` ab.
Davids Herz-Orte sind zehn, seit 2026-09-27 alle mit eigener Quelle: Sektor,
Straße E, Der Lude, GrooveStation, Zentralwerk, AZ Conni, Ostpol, Scheune (ICS),
Chemiefabrik und Hole of Fame (beide mit Detailseiten je Termin).
Neue Herz-Orte ohne eigene Quelle zeigt `python -m ddwg status` zusammen mit orte.json.
**Nächster sinnvoller Schritt:** siehe Roadmap im Leitstand, Phase „Als Nächstes“
(z. B. Flavours verfeinern).
**Netz:** Die Netzfreigabe von Cowork sperrt die Seiten der Orte, kulturkalender-dresden.de
und nominatim (Stand 2026-09-27). Seiten dann im Browser (Claude in Chrome)
ansehen, Test-Beispiel in `tests/` ablegen, echter Lauf über GitHub Actions.

## Regeln (gelernt, bitte einhalten)
- **Nichts erfinden.** Beschreibungen kommen nur aus gescraptem Text. Das gilt auch für
  Orte, die man kennt. Öffentlich über echte Dresdner Läden zu schreiben verlangt das.
- **`sonstiges` ist eine gültige Antwort.** Kategorie-Reihenfolge: Rohkategorie der
  Quelle → Titel-Stichwort (`normalize.py`) → Art des Ortes, nur wenn der Ort genau
  eine Kategorie hat → `sonstiges`. Nichts wird zwangsweise einsortiert.
- **Scraper höflich:** `base.REQUEST_DELAY_SECONDS` (1,2 s) zwischen Requests,
  Detailabrufe gedeckelt.
- **Nach Änderungen an einem Scraper `status` prüfen.** Ein Lauf mit 0 Events, wo es
  vorher welche gab, gilt als Fehler, und die alten Einträge bleiben stehen. Nur so
  unterscheidet man einen kaputten Selektor von einem ruhigen Tag.
- **Kennzahlen immer mit Nenner angeben.** Zahlen aus alten Berichten nicht ungeprüft
  übernehmen, sondern neu messen.
- `normalize.make_event_uid` (sha1 aus Datum|Zeit|Titel|Ort) ist stabil gemessen,
  Signatur nicht ändern.
- Code, Kommentare und UI sind auf Deutsch.

## Offene Ideen
- Neue Oberfläche steht: Zeitstrahl-Galerie (Reiter „Was geht“) und Entdecken-Karte
  mit Leaflet + markercluster von cdnjs (Reiter „Entdecken“). Die Schrift TeX Gyre
  Heros aus `ddwg/vorlage/schrift/` wird beim Bauen eingebettet. Herzen und Flavours
  siehe Abschnitt „Herzen“. Entwürfe liegen unter `docs/ui-entwuerfe/`.
- Führungen kommen seit 2026-09-29 gar nicht mehr auf die Seite (Davids Entscheidung):
  `build()` verwirft die Kategorie `fuehrungen` (`VERWORFENE_KATEGORIEN` in
  `pipeline.py`), also Stadt-, Museums-, Schiffs- und Familienführungen. Erkannt werden
  sie weiter in `normalize.py`. `AUSGEBLENDET` in der Vorlage ist damit ohne Wirkung.
  Seit sie schon beim Einlesen rausfallen, entstehen keine Treffpunkt-Orte mehr.
- Werkzeuge für orte.json (füllen nur leere Felder): `werkzeuge/enrich_venues.py`
  (Homepage, Cover, Kurzbeschreibung über die Kulturkalender-Ortsseite) und
  `werkzeuge/fetch_venue_locations.py` (Adresse, Koordinaten über KK und nominatim).
  Ohne `--apply` nur Bericht. Weil Cowork beide Seiten sperrt, laufen sie über den
  Workflow „Orte ergänzen“ (`.github/workflows/orte-ergaenzen.yml`, nur von Hand):
  ohne Häkchen nur Bericht im Log, mit Häkchen „anwenden“ ein Pull Request mit der
  geänderten orte.json. Damit der Workflow Pull Requests anlegen darf, muss einmalig
  in den Repo-Einstellungen unter Actions → General „Allow GitHub Actions to create
  and approve pull requests“ an sein.
- Bekannte Grenzfälle der Doppelungs-Erkennung: Quellen nennen Einlass statt Beginn
  (bis 150 min Toleranz bei gleichem Ort und Titel). Festival-Sammeleinträge von
  cybersax können einzelne Programmpunkte an sich ziehen.
- Tag springen: Ein kurzer Tipp aufs große Datum in der Leiste öffnet einen Kalender
  (`zeigeKalender` in der Vorlage), Wischen bleibt. Tage ohne Termine sind grau. Man muss
  den Tipp kennen, ein Kalender-Knopf im Kopf wäre der einfachste Zusatz.

## Historie
`docs/historie/`: Supervisor-Pläne und Packet-Berichte der v2-Überarbeitung (Sept. 2026),
das v2-Schema, der v2-Code (`db.py`, `tests_smoke.py` mit HTML-Fixtures aller Scraper),
die UI v2 und `STACK.md` (alter Docker-Betrieb auf CT103).

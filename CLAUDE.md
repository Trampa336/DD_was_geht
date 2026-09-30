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
In Cowork das Löschen im Projektordner freigeben lassen, bevor gebaut oder committet
wird: Sonst bleiben `cache/events.db-journal` und `.git/*.lock` liegen, und der nächste
`build` scheitert mit „disk I/O error“.
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

**Vorschau am Handy vor dem Push** (bei Änderungen an der Oberfläche, seit 2026-09-30):
nach `python -m ddwg build` auf dem Proxmox-Rechner `cd ausgabe && python3 -m http.server 8000`
starten und am Handy im selben WLAN `http://<IP des Proxmox-Rechners>:8000` öffnen. So lassen sich
Wischen, Vibration und Zurück-Knopf am echten Gerät prüfen. Der Service Worker (offline) läuft dort
nicht, er braucht https. Claude kann den Server nicht selbst dauerhaft starten (Cowork-Befehle enden
nach höchstens 3 min, und das Handy erreicht Claudes Shell nicht), sagt aber vor dem Push Bescheid,
wenn eine Vorschau sinnvoll ist. Schnelle Checks am PC: Chrome, F12, Handy-Ansicht.

## Grundprinzip
**Alles Kuratierte liegt in Dateien (git), die Events liegen in einer Wegwerf-DB.**
- `orte/orte.json` (Quelle der Wahrheit, von Hand und von Werkzeugen gepflegt): rund 775 Orte
  mit Aliasen, Region, Art, Herz, Homepage, Cover, Adresse und Koordinaten.
  Unbekannte Schreibweisen legt der Scrape als neuen Ort mit `erstmals` an.
  Feld `raus` (Grund als Text): alle Termine dieses Orts werden aussortiert
  (Haus der Brücke, TimeRide, Erlwein Forum, Dampfschifffahrt, Dampfzug, Wackerbarth, Kadampa,
  AnuKan, riesa efau). Seit 2026-09-30 auch unklare Ortsnamen, die nur cybersax liefert
  („Theater“, „Kulturhaus“, „Schloss“, „Börse“ usw.): Davids Regel „Quelle nicht eindeutig,
  lieber verwerfen“. Neue solche Namen zeigt `python -m ddwg status` unter den neuen Orten.
  **Doppelte Orte** (dieselbe Bühne unter zwei Schreibweisen) legt `Orte.zusammenlegen(ziel, …)`
  zusammen: Die Schreibweisen werden Aliase, leere Felder wandern zum Ziel. Wichtig, weil
  `dedup` Termine nur am selben Ort zusammenlegt; sonst stehen sie doppelt im Zeitstrahl.
  Verschiedene Bühnen im selben Haus (Kulturpalast, Kraftwerk Mitte) bleiben getrennt.
  Ein Eintrag in flavours.json muss dabei zum Ziel-Slug wandern (am 30.09. 25 Orte zusammengelegt).
  `python -m ddwg status` meldet Verdachtsfälle (`ddwg/doppelorte.py`): Orts-Paare mit mindestens
  zwei Terminen am selben Tag und gleichem Titelanfang. Dieselbe Filmvorführung in zwei Kinos
  (Rundkino, UCI) ist ein bekannter harmloser Treffer. Lokal zeigt `status` alte Ortsnamen, bis
  der nächste Scrape die Einträge neu zuordnet (`build` ordnet nicht neu zu).
- `orte/flavours.json`: 8 Flavours (liefern die Orte der Richtungen, siehe „Oberfläche“) und die
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
   ranghöchsten Quelle, die sie hat. Seit 2026-09-30: Fehlt der besten Quelle die
   Uhrzeit, kommt sie von der nächsten (Ostpol nennt oft keine). Der Link ist der erste
   Einzellink; Startseiten und cybersax-Tagesseiten nur, wenn es nichts anderes gibt.
   Im Preis fällt ein angehängtes „Quelle: …“ weg.
   Danach verwirft `build()` noch einmal alle Führungen (auch über den Ort geerbte)
   und alles aus **`ddwg/aussortieren.py`** (Davids Entscheidung 29./30.09.2026, weder
   Zeitstrahl noch Karte): Orte mit `raus`, Hotels und Gasthöfe (am Ortsnamen), Familie
   und Kinder (Richtung `familie`), Senioren, abgesagte Termine und Touristen-Angebote
   (Candlelight, Babykonzerte, Stadtabenteuer, Weinwanderungen und -proben). Umland
   bleibt. Das Log von `build` nennt die Anzahl je Grund.
5. Für alle Events ohne Beschreibung lädt die Pipeline die Kulturkalender-Detailseite
   nach (seit 2026-09-29, vorher nur Herz-Orte): nächste Tage zuerst, jede Seite nur
   einmal, höchstens 2.500 pro Lauf, Abbruch nach 20 Fehlschlägen in Folge. Ergebnisse
   liegen in der Tabelle `details`; Netzfehler werden nicht gemerkt, sondern beim
   nächsten Lauf erneut versucht.
6. `ausgabe.py` füllt `ddwg/vorlage/index.html` mit JSON → `ausgabe/index.html`. Dabei bekommt
   jeder Termin seine Richtungen (`rt`, aus `ddwg/richtungen.py`).

## Website (GitHub Pages)
Seit 2026-09-26 laeuft `.github/workflows/publish.yml` taeglich (und manuell ueber
„Run workflow“): scraped frisch und veroeffentlicht den Ordner `ausgabe/` auf dem
Branch `gh-pages`. Adresse: `https://trampa336.github.io/DD_was_geht/`. Einmalig
noetig, falls GitHub es nicht selbst erkennt: in den Repo-Einstellungen unter
„Pages“ die Quelle auf Branch `gh-pages` (Ordner `/`) stellen.
Der Workflow behaelt `cache/events.db` per `actions/cache` von Lauf zu Lauf, damit
die nachgeladenen Beschreibungen (`details`) erhalten bleiben. Fehlt der Cache
(z. B. nach 7 Tagen ohne Lauf), laedt der erste Lauf alle Detailseiten neu (~45 min).
Claude startet Läufe selbst (seit 2026-09-29): Der git-Token in
`.git/dd-was-geht-credentials` hat „Actions: Read and write“. Starten per
`git credential fill` + `POST /repos/Trampa336/DD_was_geht/actions/workflows/publish.yml/dispatches`
(Body `{"ref":"main"}`), Status über `…/publish.yml/runs`. Token nie ausgeben.

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
sektor 50, azconni 60, ostpol 65, scheune 66, chemiefabrik 67, holeoffame 68) < rauze 70
< omasgegenrechts 80 < terminaldigital 85 < kulturkalender 90 < versammlungen 95 < cybersax 100.
Davids Regel: **Venue-Seite > Rauze > Sammelkalender (terminal.digital, KK, cybersax).**
Die Sammelkalender dienen der Vollständigkeit und dem Entdecken.
terminal.digital (seit 2026-09-29, ICS-Feed, linker Kalender) liefert nur Demos,
Konzerte, Küfa/Kneipe und Film/Theater (Davids Auswahl); offene Treffen, Beratung,
Vorträge usw. bleiben draußen. Der Feed hat immer die nächsten 50 Termine (~3 Wochen).
**Demos** (seit 2026-09-29, Kategorie `demo`): Omas gegen Rechts Dresden (ICS, Demos und
Mahnwachen, nur Dresden und Umland) und die Versammlungsliste der Stadt Dresden (JSON
`dresden.de/data_ext/versammlungsuebersicht/Versammlungen.json`). Von der Stadt kommen
alle Versammlungen, die schon einen Ort oder Startpunkt haben (Davids Entscheidung, keine
Auswahl nach Veranstalter; die Liste ist politisch gemischt); abgemeldete und verbotene
bleiben draußen. `dedup.match` legt zwei Demos am selben Ort, Tag und zu passender Zeit
zusammen, auch bei ganz anderem Titel.

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
Die gewählten Richtungen bringen die Orte ihres Flavours als Herzen mit (ohne Wahl: Club,
seit 2026-09-29 ohne Auswahlbildschirm), dazu eigene Änderungen am Herz-Knopf.
`"herz": true` in orte.json ist Davids Liste (steuert seit 2026-09-29 keinen Abruf mehr);
„Herzen nach orte.json“ klein in der Karte gleicht sie per `python -m ddwg herz …` ab.
Davids Herz-Orte sind zehn, seit 2026-09-27 alle mit eigener Quelle: Sektor,
Straße E, Der Lude, GrooveStation, Zentralwerk, AZ Conni, Ostpol, Scheune (ICS),
Chemiefabrik und Hole of Fame (beide mit Detailseiten je Termin).
Neue Herz-Orte ohne eigene Quelle zeigt `python -m ddwg status` zusammen mit orte.json.
**Nächster sinnvoller Schritt:** siehe Roadmap im Leitstand, Phase „Als Nächstes“.
Flavour-Check (80 Orte mit Terminen) und doppelte Orte sind seit 2026-09-30 erledigt.
Hole of Fame und C. Rockefeller Center bleiben „museum“ (Kunstateliers, Davids Entscheidung).
Seit 2026-09-30 haben alle Herz-Orte einen Flavour (Straße E und Sektor club, Der Lude
indie = Bar). Ohne Flavour bekam z. B. Laibach in der Reithalle gar keine Richtung.
**Netz:** Die Netzfreigabe von Cowork sperrt die Seiten der Orte, kulturkalender-dresden.de,
terminal.digital, dresden.de, omasgegenrechts-dresden.de und nominatim (Stand 2026-09-29). Seiten dann im Browser (Claude in Chrome)
ansehen, Test-Beispiel in `tests/` ablegen, echter Lauf über GitHub Actions.

## Regeln (gelernt, bitte einhalten)
- **Nichts erfinden.** Beschreibungen kommen nur aus gescraptem Text. Das gilt auch für
  Orte, die man kennt. Öffentlich über echte Dresdner Läden zu schreiben verlangt das.
- **`sonstiges` ist eine gültige Antwort.** Kategorie-Reihenfolge: **Titel-Stichwort für Demos und Führungen**
  (`_titel_entscheidet` in `normalize.py`, seit 2026-09-29, schlägt die Quelle) →
  Rohkategorie der Quelle → Titel-Stichwort (`normalize.py`) → Art des Ortes, nur wenn
  der Ort genau eine Kategorie hat (Demos werden dabei nie vererbt, `NICHT_VERERBEN`;
  sonst wurde die Schnitzeljagd auf dem Schloßplatz zur Demo) → `sonstiges`.
  Nichts wird zwangsweise einsortiert.
  Demos sind ausdrücklich erwünscht und haben die Kategorie `demo` („Demos“).
  Die Kategorie ist grob; genauer sind die Richtungen (siehe „Oberfläche“).
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

## Oberfläche (seit 2026-09-29: Richtungen, Filter, Sortierung)
- Zeitstrahl-Galerie (Reiter „Was geht“) und Entdecken-Karte mit Leaflet + markercluster
  von cdnjs (Reiter „Entdecken“). Die Schrift TeX Gyre Heros aus `ddwg/vorlage/schrift/`
  wird beim Bauen eingebettet. Entwürfe liegen unter `docs/ui-entwuerfe/` (gitignored).
- **Bilder** (seit 2026-09-30): Hat ein Termin kein eigenes Bild, zeigt die Kachel das Foto des Orts
  (`cover` aus orte.json, in der Ausgabe `c`), sonst ein Schrift-Plakat mit dem Ortsnamen. Für die
  Relevanz zählt nur das eigene Bild (`e.img`).
- **Grundprinzip (Davids Entscheidung): sortieren statt verstecken.** Je Tag werden die
  8 passendsten Termine Kacheln, der Rest kompakte Zeilen darunter. Relevanz
  (`relevanz()` in der Vorlage): Herz-Ort +100, eigene Richtung +40, Bild +10,
  Beschreibung +5, mehrere Quellen +8, ab 18 Uhr +5, keine Richtung −10, Umland −10.
- **Richtungen** verschmelzen Flavours und Kategorien (`ddwg/richtungen.py`, Tests in
  `tests/test_richtungen.py`): Musik (Club, Rock & Metal, Punk/Indie & Bars, Jazz, Klassik;
  Punk zählt seit 2026-09-30 zu Indie, Davids Entscheidung), Kultur (Bühne,
  Film, Lesung, Ausstellungen), Demos, Feste & Märkte, Sport. Familie wird noch berechnet
  (zum Aussortieren), steht aber nicht mehr im Filter. Jazz schlägt Klassik
  („Quartett“ im Blue Note). Ein Termin trifft
  über den Flavour seines Ortes, ein Titel-Stichwort (auf dem Slug, mit Wortgrenzen und
  Liste falscher Freunde) oder die Kategorie. Ort und Stichwort zählen nur, wenn die
  Kategorie passt oder `sonstiges` ist. Sport = Mitmachen, ohne Senioren-, Familien-
  und Zuschauersport (auch am Ortsnamen erkannt). Neue Stichworte immer mit Test.
- **Zeitstrahl-Leiste** links (seit 2026-09-29 fertig): Alle Tage mit Terminen stehen als kleine,
  blasse Skala (Wochentag + Tag) auf der Leiste, der aktuelle Tag groß in der Mitte; oben und
  hinter der Reiter-Leiste blendet sie aus. Wochenende (Fr–So) sandfarben und kräftiger,
  Monatswechsel als feine Linie mit Monatskürzel (sonst kein Monat auf der Leiste). Tipp auf ein kleines Datum springt hin, Tipp
  aufs große öffnet den Kalender, Wischen folgt dem Finger (ein Tag je 40 px, `FERN`).
  Beim Scrollen folgt die Skala ohne Nachlauf, der nächste Tag rastet weich auf den letzten
  40 % des Tages ein. Vibration nur 2 ms und höchstens alle 90 ms.
  Sprünge setzen den Tag ganz nach oben; beim Scrollen gilt ein Tag als aktuell, sobald seine
  Überschrift die Lesekante oben erreicht (`LESE` = 60 px), nicht die Mitte der Leiste.
- **Zurück-Knopf** (seit 2026-09-30): Jede geöffnete Ebene legt einen Eintrag im Browser-Verlauf
  an (`ebenen` in der Vorlage): Blatt (Termin, Ort, Kalender, Filter, Herzen), Orts-Karte,
  Reiter Entdecken. „Zurück“ schließt die oberste; Termin → Ort → Zurück zeigt wieder den
  Termin. ✕, Tippen daneben und Escape gehen über denselben Weg (`zurueckBis`), sonst
  entstehen tote Zurück-Schritte. Sprünge in der Zeitleiste zählen nicht (Davids Entscheidung).
- **Filter-Knopf** unten rechts öffnet ein Blatt: Suche (Titel, Ort, Beschreibung), Orte
  (Alle / Meine / Neue), Deine Richtungen (Tippen merkt und holt nach vorne) und
  „Nur meine Richtungen“. Der Filter gilt in beiden Reitern und wird im Browser gemerkt
  (`ddwg-filter`), Herzen und Richtungen unter `ddwg-meine`. Oben zeigt eine Zeile den
  aktiven Filter mit ✕. Die Karte hat oben nur noch die Zeit-Knöpfe.
- **Dauerausstellungen** (seit 2026-09-30): Laufende Termine (`l`, gleicher Titel an
  mindestens 7 Tagen) stehen weder im Zeitstrahl noch auf der Karte. Ausnahme: Ausstellungen
  (`l` und Richtung Kunst) zeigt der Chip „Dauerausstellungen zeigen“ im Filter-Blatt, je
  Ausstellung einmal am ersten Tag. Ohne eigene Wahl (`F.dauer` null) ist er an, sobald die
  Richtung Ausstellungen oder Kultur gewählt ist; Tippen auf diese Richtung setzt die Wahl zurück.

## Offene Ideen
- Führungen kommen seit 2026-09-29 gar nicht mehr auf die Seite (Davids Entscheidung):
  `build()` verwirft die Kategorie `fuehrungen` (`VERWORFENE_KATEGORIEN` in
  `pipeline.py`), also Stadt-, Museums-, Schiffs- und Familienführungen. Erkannt werden
  sie weiter in `normalize.py`.
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

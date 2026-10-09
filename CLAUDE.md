# dd-was-geht – Projektgedächtnis

Persönlicher Dresdner Veranstaltungskalender von David. Scraper holen Termine aus
Sammelkalendern und direkt von den Seiten der Orte. Daraus entsteht **eine statische
HTML-Datei** (`ausgabe/index.html`) plus drei kleine PWA-Begleitdateien (Manifest,
Service Worker, Icons) im selben Ordner, siehe Abschnitt „Website (GitHub Pages)“.
Es gibt keinen eigenen Server und kein Docker (einzige Ausnahme: der kleine Cloudflare-Dienst für
gemeinsame Lesezeichen, siehe „Gemeinsame Lesezeichen“). Seit 2026-09-25 wird das Projekt nur
noch in Claude Cowork bearbeitet (v3). Der alte Stand liegt als Tag `v2-final` in git.

## Befehle
**GitHub ist die Quelle der Wahrheit** (`Trampa336/DD_was_geht`). Seit 2026-10-08 ist der lokale
Arbeitsordner ein Klon davon auf Davids Rechner: `/home/leo/Claude/dd-was-geht` (vorher ein
Proxmox-Share, der in Cowork zuletzt leer erschien; dort liegt nichts mehr, das gebraucht wird).
Neu aufsetzen = `git clone https://github.com/Trampa336/DD_was_geht dd-was-geht`. `cache/events.db`
fehlt nach dem Klonen; `python -m ddwg scrape` baut sie neu (oder für Oberflächen-Checks die Live-Seite
vom Branch `gh-pages` als Datenquelle nehmen).
In Cowork das Löschen im Projektordner freigeben lassen, bevor geklont, gebaut oder committet
wird: Sonst bleiben `.git/*.lock` und `cache/events.db-journal` liegen, und git bzw. `build`
scheitern („File exists“ / „disk I/O error“).
**Pushen:** Der Klon hat noch keinen Zugang zum Pushen (der Token lag in der Proxmox-Kopie unter
`.git/dd-was-geht-credentials`). Bis David einen neuen Fine-grained Token hinterlegt (Rechte: Contents
und Actions „Read and write“, gespeichert mit `git config credential.helper "store --file=.git/dd-was-geht-credentials"`),
committet und pusht Claude aus einer Cloud-Kopie des Repos, danach im Arbeitsordner `git pull`.
```
python3 -m venv venv             # einmalig, danach venv/bin/python statt python
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
nach `python -m ddwg build` auf Davids Rechner `cd ausgabe && python3 -m http.server 8000`
starten und am Handy im selben WLAN `http://<IP des Rechners>:8000` öffnen. So lassen sich
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
- `orte/flavours.json`: 8 Flavours = **Genre des Orts** (Club, Rock, Punk/Indie, Jazz, Klassik,
  Bühne, Ausstellungen, Familie) für gut 100 Orte (`haupt`, `neben`, `unklar`), Standard-Richtung
  `club`. Es zählt nur `haupt`. Wofür (seit 2026-09-30): 1. Termine bekommen darüber ihre genaue
  Richtung, wenn der Titel nichts sagt (gemessen: 733 von 2.395 Terminen nur so); 2. jede Gruppe
  ist ein Knopf in der Orte-Liste. Flavours setzen **keine** Herzen mehr über Richtungen.
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
   Uhrzeit, kommt sie von der nächsten (Ostpol nennt oft keine). Seit 2026-10-02: Eine Beschreibung
   unter 80 Zeichen (`merge.KURZZEILE`, z. B. Scheune/GrooveStation-ICS „Literatur / Gegenmacht“) verliert gegen
   einen ausführlichen Text einer rangniedrigeren Quelle oder der Detailseite. Der Link ist der erste
   Einzellink; Startseiten und cybersax-Tagesseiten nur, wenn es nichts anderes gibt.
   Im Preis fällt ein angehängtes „Quelle: …“ weg.
   Danach verwirft `build()` noch einmal alle Führungen (auch über den Ort geerbte)
   und alles aus **`ddwg/aussortieren.py`** (Davids Entscheidung 29./30.09.2026, weder
   Zeitstrahl noch Karte): Orte mit `raus`, Hotels und Gasthöfe (am Ortsnamen), Familie
   und Kinder (Richtung `familie`), Senioren, abgesagte Termine und Touristen-Angebote
   (Candlelight, Babykonzerte, Stadtabenteuer, Weinwanderungen und -proben). Umland
   bleibt. Das Log von `build` nennt die Anzahl je Grund.
5. Für alle Events ohne Beschreibung oder nur mit Kurzzeile (seit 2026-10-02) lädt die Pipeline die Kulturkalender-Detailseite
   nach (seit 2026-09-29, vorher nur Herz-Orte): nächste Tage zuerst, jede Seite nur
   einmal, höchstens 2.500 pro Lauf, Abbruch nach 20 Fehlschlägen in Folge. Ergebnisse
   liegen in der Tabelle `details`; Netzfehler werden nicht gemerkt, sondern beim
   nächsten Lauf erneut versucht.
6. `ausgabe.py` füllt `ddwg/vorlage/index.html` mit JSON → `ausgabe/index.html`. Dabei bekommt
   jeder Termin seine Richtungen (`rt`, aus `ddwg/richtungen.py`).

## Website (GitHub Pages)
Seit 2026-09-26 laeuft `.github/workflows/publish.yml` taeglich (und manuell ueber
„Run workflow“): scraped frisch und veroeffentlicht den Ordner `ausgabe/` auf dem
Branch `gh-pages`. Adresse: `https://trampa336.github.io/DD_was_geht/`.
**Push = schnell live** (seit 2026-10-02): Ein Push auf `main` scrapt nicht, sondern baut
die Seite nur aus der Datenbank vom letzten Lauf neu (`python -m ddwg build`, ~2 min) und
veröffentlicht sie. Das gilt für Oberfläche und orte.json/flavours.json. Pushes, die nur
`*.md`, `docs/` oder `tests/` ändern, lösen nichts aus. Fehlt die Datenbank im Cache, scrapt
auch der Push-Lauf voll, ebenso wenn der letzte Scrape über 20 h her ist (ein Push verdrängt
einen wartenden Tageslauf). Täglicher Lauf (03:17 UTC, krumme Minute gegen Verspätung) und
„Run workflow“ scrapen immer frisch. Unter 200 Events endet `scrape`/`build` mit Fehler
(`MINDEST_EVENTS`), dann bleibt die alte Seite stehen. Einmalig
noetig, falls GitHub es nicht selbst erkennt: in den Repo-Einstellungen unter
„Pages“ die Quelle auf Branch `gh-pages` (Ordner `/`) stellen.
Der Workflow behaelt `cache/events.db` per `actions/cache` von Lauf zu Lauf, damit
die nachgeladenen Beschreibungen (`details`) erhalten bleiben. Fehlt der Cache
(z. B. nach 7 Tagen ohne Lauf), laedt der erste Lauf alle Detailseiten neu (~45 min).
Claude startet Läufe selbst (seit 2026-09-29): Der git-Token in
`.git/dd-was-geht-credentials` hat „Actions: Read and write“. Starten per
`git credential fill` + `POST /repos/Trampa336/DD_was_geht/actions/workflows/publish.yml/dispatches`
(Body `{"ref":"main"}`), Status über `…/publish.yml/runs`. Token nie ausgeben.
Seit dem Umzug (2026-10-08) fehlt dieser Token im neuen Arbeitsordner, siehe „Befehle“ → Pushen.

`ddwg/vorlage/pwa/` enthaelt Manifest, Service Worker (`sw.js`) und Icons.
`ausgabe.py` kopiert sie beim Bauen neben `index.html`, dazu `404.html` und die Vorschau-Seiten `t/` (siehe „Teilen“). Lokal per Doppelklick
geoeffnet (`file://`) aendert sich nichts, der Service Worker registriert sich
nur online (http/https). Der Service Worker cacht die Seite „network-first“:
online kommen immer frische Termine, offline der zuletzt geladene Stand. Wer
die Liste der gecachten Dateien in `sw.js` (`ASSETS`) aendert, muss den
`CACHE`-Namen hochzaehlen, sonst bleibt der alte Stand haengen. Die
Entdecken-Karte braucht wegen Leaflet/markercluster von cdnjs und den
Kartenkacheln weiterhin Internet, auch offline-installiert. Fremde Dateien (Bilder, Kacheln)
cacht der Service Worker nicht (seit 2026-10-02, sonst wächst der Cache endlos).
Die Seite nimmt „Heute“ vom Gerät, wenn sie älter ist, und blendet Vergangenes aus.
Teilen nur im Freundeskreis: `noindex`, Link-Vorschau über `og:`-Tags in der Vorlage.

## Quellen und Rang (ddwg/quellen/__init__.py, kleiner = besser)
Seiten der Orte selbst (derlude 10, strassee 20, groovestation 30, zentralwerk 40,
sektor 50, azconni 60, tanteju 61, puschkin 62, arteum 63, ostpol 65, scheune 66, chemiefabrik 67, holeoffame 68,
objektkleina 69) < rauze 70 < omasgegenrechts 80 < terminaldigital 85 < kulturkalender 90 < versammlungen 95 < cybersax 100.
Davids Regel: **Venue-Seite > Rauze > Sammelkalender (terminal.digital, KK, cybersax).**
Die Sammelkalender dienen der Vollständigkeit und dem Entdecken.
Seit 2026-10-02: **objekt klein a** über die Monatsseiten (Menü der Startseite nennt
„Oktober 2026“ usw., die Adressen sind unregelmäßig, darum zählt der Linktext), und das
**Arteum** (Partykeller am Waldschlösschen, normaler Ort mit Flavour Club, kein Herz) über
das Galerie-JSON `wix-warmup-data` auf /partys: nur Titel, Tag ohne Jahr, Uhrzeit, Bild,
Ticket-Link, keine Beschreibung. Ebenfalls seit 2026-10-02: **Tante JU** und **Puschkin** über ihre
iCal-Feeds (`/events.ics`, WordPress-Plugin Events Manager; Puschkin nur Titel, Beginn, Link).
Termine mit „(verlegt ins Puschkin)“ / „(hochverlegt in die Tante JU)“ im Titel landen über
`base.verlegt()` beim neuen Ort. Abgleich 02.10. (eigene Seite gegen Live-Seite, 32 Tage): Paula war
schon vollständig (kein Scraper nötig). Koralle, Gisela, Klub Neu, Showboxx, Kashay, Club SVS haben
kein lesbares Programm (Koralle-Domain leitet auf eine fremde Seite um, Gisela lädt per Facebook-JS).
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
Seit 2026-09-30 (Davids Entscheidung) kommen Herzen nur aus der **Orte-Liste** („Orte entdecken“,
Knopf unter der Entdecken-Karte und im Filter-Blatt): Gruppen-Knöpfe `M.gr` („Solider Anfang“ =
Herz-Orte aus orte.json, dazu je Genre eine Gruppe) plus Feinjustieren je Ort (`M.an`, `M.weg`).
Von Hand Gesetztes gilt immer vor den Gruppen. Aufbau der Liste (seit 2026-10-02, Davids Wunsch): Überschrift ganz oben neben dem ✕, kein
Erklärtext, Gruppen-Pillen untereinander und flach, Kopf „Gruppen · Zahl“ (Herzen insgesamt, ohne Wort), darunter eine Suchzeile (`OL_Q`, gilt nur
solange die Seite offen ist), die beim Tippen nur passende Orte **aus der Liste** zeigt (Gruppen + „Weitere
Orte“ ab 3 Terminen, Davids Wahl). Je Zeile nur Name und grau die Zahl der Termine; feiner Strich zwischen den
Gruppen. Herzen gibt es auch für Orte außerhalb der Liste (Herz-Knopf im Orts-Blatt). Erster Start: „Solider Anfang“ an, keine Richtung
(= alles). Alte Browser-Stände (ohne `v: 2`) bekommen einmal „Solider Anfang“, eigene
Herzen und Abwahlen bleiben. Richtungen setzen keine Herzen mehr.
`"herz": true` in orte.json ist Davids Liste (steuert seit 2026-09-29 keinen Abruf mehr),
gepflegt nur per `python -m ddwg herz …`. Den Abgleich-Knopf in der Karte gibt es seit
2026-10-02 nicht mehr (Davids Wunsch: überall die gleiche Bedienung).
Davids Herz-Orte (= Gruppe „Solider Anfang“) sind seit 2026-10-02 dreizehn: Sektor, Straße E,
Der Lude, GrooveStation, AZ Conni, Ostpol, Scheune, Hole of Fame, objekt klein a, Tante JU,
Puschkin (alle mit eigener Quelle) sowie Paula und seit 2026-10-02 das Deutsche Hygiene-Museum (beide ohne eigene Quelle, Sammelkalender reichen). Chemiefabrik und Zentralwerk
haben weiter eigene Quellen, sind aber keine Herz-Orte mehr (Davids Entscheidung).
Neue Herz-Orte ohne eigene Quelle zeigt `python -m ddwg status` zusammen mit orte.json.
**Nächster sinnvoller Schritt:** siehe Roadmap im Leitstand, Phase „Als Nächstes“.
Flavour-Check (80 Orte mit Terminen), doppelte Orte, Koordinaten für Musik-Orte (Adressen von den
Seiten der Orte, Koordinaten über nominatim im Browser, weil Cowork nominatim sperrt) und Ortsfoto
als Ersatzbild sind seit 2026-09-30 erledigt, ebenso Richtungs-Check (12 Orte mit Genre, „Internet“
raus, Stichwort Eislaufen = Sport), Orte-Liste mit „Solider Anfang“ und Tageszeit-Chips.
Offen: welche Orte genau in „Solider Anfang“ gehören (= `herz` in orte.json, mit David besprechen).
Hole of Fame und C. Rockefeller Center bleiben „museum“ (Kunstateliers, Davids Entscheidung).
Seit 2026-09-30 haben alle Herz-Orte einen Flavour (Straße E und Sektor club, Der Lude
indie = Bar; Chemiefabrik seit 2026-10-02 indie statt club, Davids Wunsch). Ohne Flavour bekam z. B. Laibach in der Reithalle gar keine Richtung.
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
- Zeitstrahl-Galerie (Reiter „Feed“) und Entdecken-Karte mit Leaflet + markercluster
  von cdnjs (Reiter „Karte“; im Code weiter `was` und `karte`). Die Schrift TeX Gyre Heros aus `ddwg/vorlage/schrift/`
  wird beim Bauen eingebettet. Entwürfe liegen unter `docs/ui-entwuerfe/` (gitignored).
- **Themes** (seit 2026-10-02, Davids Wunsch): 5 dunkle Farbsätze, Industriegelände (Standard), Blaues
  Wunder, Neustadt, Platte, Heide (Namen von David; intern elbe, neon, platte, wald) (Davids Auswahl aus 10 Entwürfen; Kellerbar, Nachtviolett, Mitternacht und die
  hellen Papier und Salbei sind raus). Nur Farben über die CSS-Variablen in `:root[data-theme=…]`, dazu `--glow`
  (Schimmer oben), `--tiles` (Kartenfilter), `--shade`, `--dim`. Einziger Zugang: kleiner Paletten-Knopf rechts
  neben dem Titel „DD was geht“ (`themeBlatt`), gemerkt als `ddwg-theme`; ein kleines Skript im Kopf setzt das
  Theme vor dem ersten Zeichnen, unbekannte fallen auf den Standard zurück. Neues Theme = CSS-Block plus Eintrag
  in `THEMES` (Muster und Statusleisten-Farbe).
- **Bildgröße** (seit 2026-10-02): Große Bilder ließen das Scrollen am Handy stocken (gemessen mit 4× gebremster
  CPU: 1.200 px 19–33 Stocker über 50 ms, 400 px 5–14). Darum nehmen Kulturkalender-Scraper und Detailabruf aus
  dem srcset die kleinste Fassung ab 500 px (`base.srcset_waehlen`), `ausgabe._bild` macht YouTube-Vorschauen
  klein (hqdefault) und wirft das KK-Platzhalterbild weg; Bilder blenden weich ein (`.da`). YouTube-Bilder
  in 4:3 (hq/sddefault) haben schwarze Balken: Klasse `yt` schneidet sie ab (clip-path + Vergrößerung).
- **Kein Seitenzoom** (seit 2026-10-02, Davids Wunsch): Viewport `maximum-scale=1, user-scalable=no` (Android),
  `touch-action: pan-x pan-y` auf `html` (auch kein Doppeltipp-Zoom) und `gesturestart` abgefangen (iOS ignoriert
  user-scalable). Die Karte zoomt weiter, Leaflet rechnet Zwei-Finger-Gesten selbst. Kein `pinch-zoom` in touch-action setzen.
- **Bilder** (seit 2026-09-30): Hat ein Termin kein eigenes Bild, zeigt die Kachel das Foto des Orts
  (`cover` aus orte.json, in der Ausgabe `c`), sonst ein Schrift-Plakat mit dem Ortsnamen. Für die
  Relevanz zählt nur das eigene Bild (`e.img`).
- **Herz-Orte im Feed** (seit 2026-09-30): nur eine kleine rote Ecke oben rechts an der Kachel
  (`.herz-b`), kein Etikett, kein roter Rahmen (Davids Wunsch).
- **Grundprinzip (Davids Entscheidung): sortieren statt verstecken.** Je Tag werden die
  8 passendsten Termine Kacheln, der Rest kompakte Zeilen darunter. Relevanz
  (`relevanz()` in der Vorlage): Lesezeichen +200, Herz-Ort +100, eigene Richtung +40,
  von anderen gemerkt +10 je Gerät (höchstens +30, seit 2026-10-08), Bild +10,
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
  blasse Skala (Wochentag + Tag) auf der Leiste, der aktuelle Tag groß in der Mitte; oben (erst ab 56 px, früher
  saß dort der Lesezeichen-Knopf) und am unteren Rand blendet sie aus. Wochenende (Fr–So) sandfarben und kräftiger,
  Monatswechsel als feine Linie mit Monatskürzel (sonst kein Monat auf der Leiste). Tipp auf ein kleines Datum springt hin, Tipp
  aufs große öffnet den Kalender, Wischen folgt dem Finger (ein Tag je 40 px, `FERN`).
  Das große Datum steht immer fest bei 1/3 der Höhe (`mitte`, CSS `--mitte`). Über „Heute“ zeigt die Leiste die 3
  vergangenen Tage grau und ohne Termine (`VORBEI`, data-k negativ, nicht antippbar), damit oben keine
  leere Fläche bleibt (Davids Wahl 2026-10-02; verworfen: vergangene Termine laden, Datum wandern lassen).
  Beim Scrollen folgt die Skala ohne Nachlauf, das große Datum läuft ab 30 % des Tages
  sanft zum nächsten mit (seit 2026-10-02 weniger magnetisch, vorher erst auf den letzten 40 %). Vibration nur 2 ms und höchstens alle 90 ms.
  Sprünge setzen den Tag ganz nach oben; beim Scrollen gilt ein Tag als aktuell, sobald seine
  Überschrift die Lesekante oben erreicht (`LESE` = 60 px), nicht die Mitte der Leiste.
- **Zurück-Knopf** (seit 2026-09-30): Jede geöffnete Ebene legt einen Eintrag im Browser-Verlauf
  an (`ebenen` in der Vorlage): Blatt (Termin, Ort, Kalender, Suche, Filter, Herzen), Orts-Karte,
  Reiter Entdecken. „Zurück“ schließt die oberste; Termin → Ort → Zurück zeigt wieder den
  Termin. ✕, Tippen daneben und Escape gehen über denselben Weg (`zurueckBis`), sonst
  entstehen tote Zurück-Schritte. Sprünge in der Zeitleiste zählen nicht (Davids Entscheidung).
  **Schutz vor versehentlichem Schließen** (seit 2026-10-02, Davids Wunsch): Über dem Start-Eintrag liegt ein
  Wächter-Eintrag (`{dd: 0, w: 1}`, `waechterSetzen`, erst bei der ersten Berührung, sonst überspringt Chrome ihn).
  Landet „Zurück“ darunter, zeigt `.hinweis-unten` „Zum Schließen nochmal Zurück“; ein zweites Zurück innerhalb
  `WARN_MS` = 2,5 s schließt, danach steht der Wächter wieder. Ein echter Dialog ist bei „Zurück“ nicht möglich.
  **Feed-Position** (seit 2026-10-02): Wechsel zur Karte merkt `feedY`, zurück zum Feed landet man wieder dort
  (ein neuer Filter auf der Karte setzt sie auf oben).
- **Blätter** (seit 2026-10-02, Davids Wunsch): Alle Blätter (Termin, Ort, Suche, Filter, Kalender, Herzen)
  sind schwebende Karten mit runden Ecken rundum und 8 px Abstand zum Rand, der untere Rand ist immer
  zu sehen. Nach unten wischen schließt (`wischenEinrichten`), aber nur, wenn das Blatt ganz oben steht;
  ab `WISCH_ZU` = 100 px oder schnellem Wisch zu, sonst federt es zurück. Geschlossen wird über `sheetZu`
  (Zurück-Verlauf). Klebende Fußleisten im Blatt (`.fi-fuss`) brauchen `bottom: -20px` als Ausgleich
  für den Innenabstand der Karte.
- **Feed ↔ Karte** (seit 2026-10-02, Davids Wunsch, ersetzt die Reiter-Pille unten): Im Feed nach links
  wischen öffnet die Karte (`tabWischen`; die Seite folgt dem Finger, ab `WISCH_TAB` = 90 px oder schnellem
  Wisch um, sonst federt sie zurück; `#tab-was` hat `touch-action: pan-y`). Dazu ein kleiner, dezenter
  Karten-Knopf unten rechts (`.karte-knopf`), auf der Karte nicht zu sehen (Davids Wahl). Zurück zum Feed:
  Zurück-Knopf/-Geste (die Karte ist eine Ebene im Verlauf), Escape oder Wisch nach rechts, der am linken
  Rand (`.rand-zurueck`, 32 px, nur Touch) oder außerhalb der Karte beginnt (Kopf, Suchleiste, Zeit-Knöpfe,
  darunter); auf der Karte selbst verschiebt Wischen die Karte. 22 px Rand allein reichten am Handy nicht. Am PC ohne Wischen nur
  Zurück/Escape. Die neue Seite gleitet von der Seite herein (`.rein-r`/`.rein-l`).
- **Leisten** (seit 2026-09-30, Davids Wunsch): Die Zeitleiste geht bis ganz nach unten. Oben liegt die **Leiste** (`#oben`) mit Suchleiste und
  Filter-Knopf rechts daneben, darunter die Zeile mit dem aktiven Filter. Sie liegt nur über der
  Terminspalte, nicht über der Zeitleiste. Sie folgt dem Scrollen 1:1 wie die Adressleiste in
  Chrome (`obenPruefen`, `--oy`, seit 2026-10-02): runter schiebt sie weg, hoch holt sie erst nach `OBEN_TOT` = 14 px
  zurück (Fingerzucken), steht die Seite 160 ms still, rastet sie ganz ein oder aus. Vorher ganz da / ganz weg
  nach 28 px, das sprang bei langsamem Scrollen hin und her (Davids Video 02.10.). Ganz oben
  und im Reiter Karte ist sie immer da, Hintergrund bekommt sie erst, wenn sie klebt. Sprünge über
  Zeitleiste und Kalender blenden sie nicht ein oder aus (`obenRuhe`); ist sie sichtbar, landet
  der Tag unter ihr, und die Lesekante der Zeitleiste rückt um ihre Höhe nach unten (`obenH`).
- **Suche** (seit 2026-09-30, Davids Wahl): Tipp auf die Suchleiste oben öffnet ein eigenes Blatt, nur
  Suchfeld (Tastatur sofort offen) und eine Trefferliste ab heute (Datum, Zeit, Titel, Ort,
  höchstens 100). Sucht in allen Terminen, **unabhängig vom Filter**; jedes Wort muss in
  Titel, Ort oder Beschreibung stehen, laufende Termine erscheinen einmal. Der Begriff gilt
  nur, solange die Seite offen ist (`SU` in der Vorlage). Termin → Zurück zeigt die Liste
  an derselben Stelle. Seit 2026-10-02 stehen passende Orte (Name enthält alle Wörter, höchstens 5)
  als eigene Zeilen über den Terminen; Tipp öffnet das Orts-Blatt.
- **Auch hier** (seit 2026-10-02): Das Termin-Blatt zeigt unten die nächsten 4 Termine am selben Ort
  (`auchHier`), bei mehr einen Knopf „Alle … Termine“ zum Orts-Blatt.
- **Lesezeichen** (seit 2026-10-02, Davids Wunsch; eine Funktion statt „Anpinnen“ und „Favorisieren“):
  Knopf rechts neben dem Titel im Termin-Blatt merkt den Termin, gespeichert im Browser (`ddwg-lesezeichen`,
  je Termin-ID `u` mit Datum, Ort, Titel). Ändert ein Neubau die ID (z. B. neue Uhrzeit), findet der Termin über
  Datum + Ort + Titel zurück; Vergangenes fällt beim Laden raus. Gemerkte Termine stehen im Tag ganz vorne
  (Relevanz +200) und haben ein helles Bändchen oben links an der Kachel. Runder Knopf in der Leiste oben
  zwischen Suche und Filter (mit Zahl; seit 2026-10-02 dort, vorher fest oben links über der Zeitleiste) öffnet das Blatt „Lesezeichen“ (Liste wie bei der Suche). Bewusst ohne Akzentfarbe.
  Im Termin-Blatt hängen der Quell-Link und „Seite vom Ort ↗“ (seit 2026-10-03, Davids Wunsch) als eine schmale Zeile
  unten an der Ortsbox (gleicher Grund, gleiche Ecken, `.sh-ort.mit-fuss`); die Pille „Dein Ort“ gibt es dort nicht
  mehr (das ♥ am Ortsnamen reicht). Der Quell-Link zeigt seit 2026-10-09 (Davids Wunsch) die Domain des Ziels statt
  „Quelle“ (`domainVon`, ohne „www.“, lange mit „…“; bei kaputtem Link bleibt „Quelle“). Gemessen auf der Live-Seite
  (gh-pages, 09.10.): 1.781 von 2.302 Links führen zum Kulturkalender, dort steht also `kulturkalender-dresden.de`;
  die Domain des Ortes steht nur, wenn die Seite des Ortes die Quelle ist.
- **Gemeinsame Lesezeichen** (seit 2026-10-08, Davids Wunsch): Hat auch jemand anderes einen Termin gemerkt,
  zeigt der Lesezeichen-Knopf im Termin-Blatt eine kleine Zahl (alle Geräte, das eigene mitgezählt; ohne andere keine
  Zahl). Nur eine Zahl, keine Namen, offen für alle ohne Einladung (Davids Wahl). Details unter „Gemeinsame Lesezeichen“.
- **Teilen** (seit 2026-10-03, Davids Wunsch): Knopf links neben dem Lesezeichen im Termin-Blatt. Verschickt
  `t/<Termin-ID>.html#<Datum>~<Ort>`: eine winzige Vorschau-Seite je Termin (`ausgabe.vorschau_seiten`, beim Bauen
  neu, ~1.900 Dateien à ~1 KB) mit og:-Titel, Datum + Ort und Bild (eigenes, sonst Ortsfoto, sonst App-Icon), weil
  WhatsApp/Signal die Vorschau ohne JavaScript und ohne „#“ bauen. Sie leitet auf `#t=<Termin-ID>~<Datum>~<Ort>` weiter;
  die Startseite zeigt dann das Termin-Blatt (`geteiltOeffnen`, der Hash wird danach entfernt). Ändert ein Neubau die
  ID, fehlt die Vorschau-Seite: `404.html` (aus `vorlage/pwa/`) leitet mit Datum + Ort zur Startseite, dort gilt genau
  ein Termin am Ort an dem Tag, sonst das Orts-Blatt mit Hinweis. Der Service Worker cacht `t/` nicht. Geteilt wird ein
  einziger Text (Davids Format): Link, Leerzeile, Veranstaltungsname, „Ort - Sa 03.10., 21:00“. Am Handy das Teilen-Menü
  des Systems (`navigator.share`, nur `text`, sonst ordnen Messenger um), am PC wird der Text kopiert. Messenger merken sich Vorschauen eine Weile.
  Alle Blätter ohne Bild haben die Überschrift oben neben dem ✕ (Klasse `.sh.hoch`).
- **Filter-Knopf** oben rechts öffnet ein Blatt (seit dem Suchknopf ohne Suchfeld, aufgeräumt
  am 2026-10-02 auf Davids Wunsch: gleiche Bedienung für Gleiches, keine grauen Erklärtexte):
  Orte als Umschalter (Alle / ♥ Meine / Neue, Link „♥ Orte auswählen“ rechts neben der
  Überschrift), Tageszeit als Umschalter (Immer / Tagsüber / Abends), Deine Richtungen als
  schlanke Liste (je Zeile ca. 40 px: Icon, Name, Zahl grau, rechts ein dezentes Häkchen). **Ein Häkchen
  filtert** (seit 2026-10-02, Davids Wunsch): mit Häkchen nur diese Richtungen, ohne Häkchen alles;
  der Schalter „Nur meine Richtungen“ ist weg. Gewählte Richtungen sortieren zusätzlich nach vorne.
  Alte Browser-Stände (`ddwg-meine` ohne `v: 3`) mit Schalter aus starten einmal ohne Richtung,
  damit nicht plötzlich Termine fehlen. Darunter ein kleiner Schalter „Dauerausstellungen“. Häkchen für die Mehrfachauswahl, Schalter nur für Einstellungen (übliche
  Regel, z. B. Material Design; Davids Wahl 02.10.). Listen haben denselben Rahmen wie die Umschalter. Die Umschalter haben
  eine gleitende Fläche (`--i`), die Schalter gleiten auch: `sanftNeu` zeichnet das Blatt neu und
  setzt Elemente mit gleichem `data-k` kurz auf den alten Zustand, damit CSS animiert.
  Unten „Zeigen“ mit Zahl. **Zahlen ohne Wort** (seit 2026-10-02): Suche, Filter-Zeile und
  Tageskopf zeigen nur die Zahl, nicht „198 Treffer“/„Termine“. Der Kopf zeigt keinen Stand mehr.
  **Icons je Richtung** (`RT_ICON` in der Vorlage, Linien-Icons aus Lucide, ISC-Lizenz, inline):
  im Filter und auf der Karte. Ein Ort-Punkt der Karte zeigt das Icon seiner häufigsten Richtung
  im Zeitraum (`hauptRichtung`, feinste zuerst) statt der Zahl, Herz-Orte dunkel mit rotem Ring; Sammelpunkte
  behalten die Zahl. Neue Richtung = neues Icon in `RT_ICON`, sonst bleibt der Punkt leer.
  **Tageszeit** (seit 2026-09-30): „Tagsüber“ / „Abends“; die Grenze (`TZ_GRENZE`) legt die Seite beim Laden auf die halbe Stunde,
  die die sichtbaren Termine am ehesten hälftig teilt (30.09.: 19:00, 1.067 von 2.011 ab dann).
  Ohne Uhrzeit oder 00:00 (ganztägig) zählt als tagsüber. Der Filter gilt in beiden Reitern und wird im Browser gemerkt
  (`ddwg-filter`), Herzen und Richtungen unter `ddwg-meine`. Oben zeigt eine Zeile den
  aktiven Filter mit ✕. Die Karte hat oben nur noch die Zeit-Knöpfe.
- **Dauerausstellungen** (seit 2026-09-30): Laufende Termine (`l`, gleicher Titel an
  mindestens 7 Tagen) stehen weder im Zeitstrahl noch auf der Karte. Ausnahme: Ausstellungen
  (`l` und Richtung Kunst) zeigt der Chip „Dauerausstellungen zeigen“ im Filter-Blatt, je
  Ausstellung einmal am ersten Tag. Ohne eigene Wahl (`F.dauer` null) ist er an, sobald die
  Richtung Ausstellungen oder Kultur gewählt ist; Tippen auf diese Richtung setzt die Wahl zurück.

## Gemeinsame Lesezeichen (Cloudflare-Dienst, seit 2026-10-08)
Eine statische Seite kann nichts zwischen Geräten teilen, darum gibt es einen winzigen Dienst:
`dienst/lesezeichen.js`, ein Cloudflare Worker mit D1-Datenbank (Binding `DB`, kostenlos). D1 statt KV, weil KV
bei fast gleichzeitigen Klicks Änderungen verlieren kann. Die Tabelle `merk` legt der Dienst selbst an.
- **Seite → Dienst:** Konstante `GEMEINSAM` in der Vorlage (Adresse des Workers, leer = aus, dann sendet und lädt die
  Seite nichts). Jedes Gerät hat eine zufällige Kennung (`ddwg-geraet`). Bei jedem Merken/Entfernen und beim Start schickt
  `fzAbgleich` die **ganze** eigene Liste (`POST /abgleich`, text/plain, ersetzt die alte; nur wenn sie sich seit dem
  letzten Erfolg geändert hat, `ddwg-freunde-gesendet`). So holt der nächste Start nach, was offline verloren ging.
- **Dienst → Seite:** `fzLaden` holt `GET /zahlen?g=<gerät>` (heute und später, ohne das eigene Gerät) und merkt sie
  (`ddwg-freunde`). Beim Start sortiert die Seite mit den Zahlen vom letzten Besuch; frische zeichnen den Feed nur neu, wenn
  er ganz oben steht und kein Blatt offen ist (sonst springt die Liste).
- **Schlüssel** wie beim Rückfall der Lesezeichen: `Datum|Ort|Titel klein`, auf 200 Zeichen gekürzt (`fzK`). Ändert die
  Quelle den Titel, beginnt die Zählung neu. Vergangenes löscht der Dienst bei jedem Abgleich.
- **Grenzen:** höchstens 100 Lesezeichen je Gerät, höchstens 10 Geräte je Netz (IP, nur als Hash) und Tag. Das bremst
  Hochtreiben, schützt aber nicht vor Absicht: Wer die Adresse kennt, kann Zahlen fälschen. Für den Freundeskreis reicht das.
- **Fehler bleiben still:** Ist der Dienst weg, läuft die Seite wie vorher, nur ohne Zahlen. Der Service Worker cacht
  fremde Adressen nicht.
- **Tests:** `tests/dienst_lesezeichen.test.mjs` (D1 mit node:sqlite nachgebaut), aufgerufen über
  `tests/test_dienst_lesezeichen.py`; übersprungen ohne Node 22.5+.
- **Einrichtung (einmalig, David):** dash.cloudflare.com → Konto anlegen. „Storage & Databases“ → D1 → Datenbank
  `ddwg-lesezeichen` anlegen. „Workers & Pages“ → Worker `ddwg-lesezeichen` aus „Hello World“ anlegen, „Edit code“,
  Inhalt von `dienst/lesezeichen.js` einfügen, Deploy. Im Worker unter „Bindings“ eine D1-Datenbank mit Namen `DB`
  verbinden, Deploy. Die Adresse (`https://ddwg-lesezeichen.<konto>.workers.dev`) in `GEMEINSAM` eintragen und pushen.
  Ändert sich `dienst/lesezeichen.js`, muss der Code dort von Hand neu eingefügt werden (kein Workflow dafür).
- **Stand 2026-10-08:** Code und Tests fertig, `GEMEINSAM` noch leer (Dienst noch nicht eingerichtet).

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
  (bis 150 min Toleranz bei gleichem Ort und Titel; seit 2026-10-02 auch bei Wortüberdeckung
  ab 0,6, wenn eine Zeile von der Seite des Hauses kommt). Seit 2026-10-02 legt `dedup` auch
  zwei Zeilen DERSELBEN Quelle zusammen, wenn Ort, Tag und Uhrzeit gleich sind, alle Wörter des
  kürzeren Titels im längeren stehen und die Zahlen gleich sind (der Kulturkalender führt
  manche Termine doppelt; „Studio*Freispiel #1/#2“ bleibt getrennt). Gemessen: auf der
  Live-Seite rund 20 echte Doppelungen von 2.398, lokal 6 neue Zusammenlegungen, alle richtig.
  Offen: gleiche Uhrzeit, aber verschiedene Titel aus zwei Quellen („farbwerkDisco (farbwerk
  e.V.)“ / „farbwerkDisco – Inklusive Disco-Reihe“) und kaputte Zeichen im KK („Mis?yrming“). Festival-Sammeleinträge von
  cybersax können einzelne Programmpunkte an sich ziehen.
- Tag springen: Ein kurzer Tipp aufs große Datum in der Leiste öffnet einen Kalender
  (`zeigeKalender` in der Vorlage), Wischen bleibt. Tage ohne Termine sind grau. Man muss
  den Tipp kennen, ein Kalender-Knopf im Kopf wäre der einfachste Zusatz.

## Historie
`docs/historie/`: Supervisor-Pläne und Packet-Berichte der v2-Überarbeitung (Sept. 2026),
das v2-Schema, der v2-Code (`db.py`, `tests_smoke.py` mit HTML-Fixtures aller Scraper),
die UI v2 und `STACK.md` (alter Docker-Betrieb auf CT103).

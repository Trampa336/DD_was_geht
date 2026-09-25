# dd-was-geht – Projektgedächtnis

Persönlicher Dresdner Veranstaltungskalender von David. Scraper holen Termine aus
Sammelkalendern und direkt von den Seiten der Orte. Daraus entsteht **eine statische
HTML-Datei** (`ausgabe/index.html`). Es gibt keinen Server, kein Docker und kein
Deployment. Seit 2026-09-25 wird das Projekt nur noch in Claude Cowork bearbeitet
(v3). Der alte Stand liegt als Tag `v2-final` in git.

## Befehle
```
pip install -r requirements.txt
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
- `cache/events.db` (SQLite, gitignored): `listings` (je Quelle roh, pro Lauf ersetzt) →
  `events` (verschmolzen, bei jedem Build komplett neu) + `scrape_runs` + `details`.
  Löschen ist erlaubt, der nächste Scrape baut die Datenbank neu auf.

## Ablauf (ddwg/pipeline.py)
1. Jede Quelle (`ddwg/quellen/<slug>.py`, Funktion `scrape_range(start, ende)`) liefert Event-dicts.
2. Jede Zeile wird über `orte.resolve()` einem Ort zugeordnet. **Region `weiter` wird
   verworfen**, also Meißen, Bautzen usw. (Davids Entscheidung). Umland bleibt gespeichert.
3. `dedup.cluster()` bildet Gruppen derselben Veranstaltung. Eine Gruppe enthält von
   jeder Quelle höchstens einen Eintrag.
4. `merge.merge()` verschmilzt Feld für Feld nach Quellen-Rang: Datum, Zeit und Titel
   kommen von der ranghöchsten Quelle, Beschreibung, Preis und Bild von der
   ranghöchsten Quelle, die sie hat.
5. Für Events an Herz-Orten lädt die Pipeline fehlende Beschreibungen von
   Kulturkalender-Detailseiten nach, höchstens 120 pro Lauf, zwischengespeichert in `details`.
6. `ausgabe.py` füllt `ddwg/vorlage/index.html` mit JSON → `ausgabe/index.html`.

## Quellen und Rang (ddwg/quellen/__init__.py, kleiner = besser)
Seiten der Orte selbst (derlude 10, strassee 20, groovestation 30, zentralwerk 40,
sektor 50, azconni 60) < rauze 70 < kulturkalender 90 < cybersax 100.
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
Herzen gibt es **nur für Orte** (`"herz": true` in orte.json), nicht für einzelne Events.
Events an Herz-Orten stehen oben unter „Deine Orte“. Start-Herzen sind die Orte mit
eigener Quelle: Sektor, Straße E, Der Lude, GrooveStation, Zentralwerk und AZ Conni.
**Nächster sinnvoller Schritt:** Herz-Orte ohne eigene Quelle bekommen einen eigenen
Scraper. Kandidaten sind Ostpol, Chemiefabrik, Scheune und Hole of Fame. Welche Orte
betroffen sind, zeigt `python -m ddwg status` zusammen mit orte.json.

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
  Heros aus `ddwg/vorlage/schrift/` wird beim Bauen eingebettet. Herzen werden im
  Browser gesetzt und per Übernehmen-Befehl (`python -m ddwg herz …`) in orte.json
  überführt. Entwürfe liegen unter `docs/ui-entwuerfe/`.
- Kartenansicht: 431 Orte haben schon `lat`/`lon`. `werkzeuge/fetch_venue_locations.py`
  ergänzt weitere, hängt aber noch an der v2-DB und muss auf orte.json umgestellt werden.
- `werkzeuge/enrich_venues.py` (Homepage und Cover über die Kulturkalender-Ortsseite)
  muss ebenfalls auf orte.json umgestellt werden.
- Bekannte Grenzfälle der Doppelungs-Erkennung: Quellen nennen Einlass statt Beginn
  (bis 150 min Toleranz bei gleichem Ort und Titel). Festival-Sammeleinträge von
  cybersax können einzelne Programmpunkte an sich ziehen.
- Datepicker für die Tagesansicht (großzügig springen, Wischen bleibt): in eigener Session besprechen.

## Historie
`docs/historie/`: Supervisor-Pläne und Packet-Berichte der v2-Überarbeitung (Sept. 2026),
das v2-Schema, der v2-Code (`db.py`, `tests_smoke.py` mit HTML-Fixtures aller Scraper),
die UI v2 und `STACK.md` (alter Docker-Betrieb auf CT103).

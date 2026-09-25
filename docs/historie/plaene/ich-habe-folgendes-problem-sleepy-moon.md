# dd-was-geht v3 → Cowork: Neubau hier, dann Übergabe, dann Abriss

## Context
David nimmt dd-was-geht aus dem Docker-Betrieb auf CT103 und arbeitet künftig nur noch in Claude
Cowork (Ordner auf seinem Rechner). Er nutzt den Umzug für einen Umbau. **Den v3-Neubau bereite ich
hier auf `leo` vor**, übergebe ihn als Zip und reiße danach alles andere ab: CT103-Stack, die
Arbeitskopie auf leo, GitHub Pages samt Repo `DD_was_geht` (**löschen**) und das Forgejo-Remote
(**GitHub bleibt**).

Davids Entscheidungen (2026-09-25):
- **Herzen nur noch für Orte.** Events an Herz-Orten kommen auf der Landing Page nach vorn.
  Event-Herzen fallen weg; in der DB stehen 0 Herzen, es geht also nichts verloren. Die UI wird
  später in Cowork neu gebaut.
- **Venue-first.** Die eigenen Seiten der Orte sind die Hauptquelle, Sammelkalender dienen der
  Vollständigkeit und dem Entdecken. Rangfolge: **Venue-Seite > Rauze > KK/cybersax**.
  Sektor und Straße E sind essenziell.
- **Ausgabe: statische HTML-Datei**, kein Server.
- **Region `weiter` wird gar nicht gespeichert** (922 Events).
  Annahme, die sich leicht umstellen lässt: Umland und Führungen werden gespeichert, stehen aber
  nie auf der Landing Page.

## Messung, die das Design trägt (v2-DB, Stand 15.09., nur gelesen)
| Quelle | Zeilen | Bild | Beschreibung | Preis |
|---|---|---|---|---|
| kulturkalender | 4925 | 100 % | 2 % | 0 % |
| cybersax | 1167 | **0 %** | 24 % | 0 % |
| rauze | 202 | 99 % | 99 % | 91 % |
| Venue-Scraper (6) | 82 | 39–100 % | 94–100 % | 0–94 % |

- **Sektor Evolution:** Der eigene Scraper liefert 9 Events. Rauze führt davon 2, KK 1 und
  cybersax 0. **Ohne Venue-Scraper ist Sektor praktisch unsichtbar.**
- **Straße E** liegt als 3 getrennte Orte vor („Bunker Straße E“, „Reithalle Straße E“,
  „Strasse E (Reithalle, Bunker)“). Das ist ein Identitätsfehler.
- Überschneidungen: cybersax↔KK 295 Doppelungen, KK↔rauze 86, cybersax↔rauze 64, cybersax↔cybersax 91.
  Rauze: 99 von 202 Events gibt es auch anderswo, rund die Hälfte ist exklusiv.
- RA: 12 Zeilen, alle auch bei rauze oder bei Venue-Seiten → **fliegt raus**.
- Die Prioritäten in `app/registry.py` entsprechen schon Davids Rangfolge (kleiner = besser:
  derlude 10, strassee 20, …, sektor 50, rauze 70, KK 90, cybersax 100).
- **Der eigentliche Qualitätshebel:** Heute gewinnt ein Eintrag komplett, die Felder der
  Duplikate gehen verloren. v3 **verschmilzt Felder**: Titel und Zeit von der besten Quelle,
  Beschreibung und Preis von der besten Quelle, die sie hat, das Bild von der Venue-Seite oder KK.
- Mögliche Venue-Scraper für später, abhängig von Davids Herzen: Ostpol (64 Zeilen aus 4 Quellen),
  Chemiefabrik, Scheune, Hole of Fame.

## v3-Architektur
**Grundprinzip: Kuratiertes steht in Dateien (git), Events stehen in einer Wegwerf-DB.**
Die DB lässt sich jederzeit löschen und mit einem Scrape neu aufbauen.

```
dd-was-geht/
  CLAUDE.md                 Projektgedächtnis für Cowork (Zweck, Befehle, Regeln)
  orte/orte.json            755→~750 Orte: slug, name, aliase[], region, kind, herz, homepage,
                            cover, adresse, lat/lon, scraper (eigener Scraper-Slug oder null)
  ddwg/                     Paket (Umbenennung von app/)
    quellen/                base.py + kulturkalender, cybersax, rauze,
                            sektor, strassee, derlude, groovestation, zentralwerk, azconni
    normalize.py            unverändert übernommen (Kategorien, slugify, make_event_uid)
    geo.py                  unverändert (classify_region)
    dedup.py                match()-Logik übernommen, Ausgabe = Cluster statt duplicate_of
    orte.py                 orte.json laden/speichern, Alias-Auflösung, herz setzen
    db.py                   neu, klein: listings, events, event_listings, scrape_runs
    merge.py                neu: Felder je Cluster nach Quellen-Rang verschmelzen
    ausgabe.py              neu: ausgabe/index.html (eingebettetes JSON + wenig JS)
    __main__.py             CLI: scrape | build | herz <ort> | orte-suchen <text> | status
  werkzeuge/                enrich_venues.py, fetch_venue_locations.py (neue Orte anreichern)
  tests/                    pytest, fokussiert (siehe Verifikation)
  cache/events.db           gitignored
  cache/venue_cache/        gitignored (übernommen, ~76 MB, spart Requests)
  ausgabe/index.html        gitignored
  docs/historie/            archivierte Supervisor-Pläne und Packets, CUTOVER.md, STACK.md
```

**DB-Schema (neu, klein)**
- `listings(source, date, time, title, venue_slug, raw_venue, url, image_url, description,
  price_text, raw_category, scraped_at)`: Je Quelle wird bei jedem erfolgreichen Lauf alles
  ersetzt. Ein fehlgeschlagener Lauf lässt die alten Zeilen stehen.
- `events(uid, date, time, title, venue_slug, category_slug, url, venue_url, image_url,
  description, price_text, sources)`: wird nach jedem Scrape **komplett neu gebaut**
  (~6000 Zeilen in 31 Tagen, dauert Sekunden). Es gibt kein `duplicate_of` mehr und kein
  Gewinner-Prädikat.
- `event_listings(uid, listing_rowid)` für die Nachvollziehbarkeit.
- `scrape_runs` wie heute. Die Warnung „0 Events, zuletzt N“ aus `app/scheduler.py:run_scrape`
  wird übernommen.
- Import-Filter: Die Region wird über `orte.json` bzw. `geo.classify_region` bestimmt,
  `weiter` wird verworfen.

**Herzen auf Orten**
- `herz: true` in `orte.json`. Setzen per CLI (`python -m ddwg herz sektor-evolution`), oder
  Cowork editiert die Datei direkt. Die Kurationsgeschichte liegt damit in git.
- Landing Page: nächste 7 Tage, zuerst Events an Herz-Orten, darunter entdeckte Events aus
  Musik und Kultur. Führungen und Umland erscheinen nur in der Gesamtliste.
- Startwerte für Herzen: die Orte mit eigenem Scraper (Sektor, Straße E, Der Lude,
  GrooveStation, Zentralwerk, AZ Conni). David ergänzt in Cowork.

**Ausgabe:** Eine eigenständige `ausgabe/index.html` mit eingebettetem JSON.
- Abschnitte: „Deine Orte“ und „Alles“, dazu Tag-Leiste und Kategorie-Chips auf Clientseite.
- Optik aus `app/static/app.css` übernommen (Themes, Schriften).
- Die Karte (Leaflet) bleibt vorerst draußen und kommt mit dem UI-Umbau zurück. `karte.js` liegt
  unter `docs/historie/ui-v2/` bereit, zusammen mit den übrigen v2-Templates und -Skripten.

**Was wegfällt:**
- Flask/`web.py`, APScheduler/`scheduler.py`, `main.py`, Docker, `publish_site.sh`,
  `export_static.py`, `backup.py`, `scoring.py`, `feed.py`, `ranges.py`
- Herzen, weights und tags, alle Templates und `static/`
- RA-Scraper und die einmaligen Tools (`curate_kind_p5t`, `legacy_gate`, `orphan_harness`,
  `load_*`, `og_image_audit`, …)
- `tests_smoke.py`: Vorher wird sie nach wiederverwendbaren Scraper-Fixtures durchsucht.

## Ablauf
**Phase 0 – Absichern**
1. Dev-Server :8090 (PID 2177044) stoppen und die v2-DB checkpointen.
2. Branch `v3` in `/home/admin/dd-was-geht/backend`. Den Stand `6c7f2d7` vorher nach GitHub
   pushen, damit v2 als Tag `v2-final` erhalten bleibt.

**Phase 1 – Orte-Datei** (Opus)
3. `werkzeuge/orte_export.py`: exportiert v2 `venues` + `venue_aliases` nach `orte/orte.json`.
   `registry.EXTRA_VENUE_ALIASES` und die Venue-Aliase der Scraper werden mit eingemischt.
4. Straße E zu einem Ort zusammenführen, mit den anderen beiden Namen als Aliase. Die 3 bekannten
   Split-Paare aus dem alten Plan (`paula`/`club-paula`, `club-baerenzwinger`/`baerenzwinger`,
   Erich-Kästner) ebenfalls. Jede Zusammenführung wird David gezeigt.

**Phase 2 – Kern** (Opus)
5. `ddwg/` anlegen: die Quellen, `normalize.py` und `geo.py` verschieben (git mv),
   `ra.py` löschen.
6. Neue Module `orte.py`, `db.py`, `merge.py`, `dedup.py` (auf Cluster umgestellt, `match()`
   unverändert) und die CLI `scrape`/`build`/`herz`/`status`.
7. `ausgabe.py` + Template → `ausgabe/index.html`.
8. Ungenutztes löschen (Liste oben), `requirements.txt` schrumpfen: requests, beautifulsoup4,
   lxml o. ä., ohne Flask und APScheduler.

**Phase 3 – Verifizieren und Übergabe vorbereiten**
9. Echter Scrape auf leo gegen alle 9 Quellen, danach `build`. Ergebnis an David als
   HTML-Vorschau.
10. `CLAUDE.md` schreiben: Zweck, Befehle, Quellen-Rang, Regeln („keine erfundenen
    Beschreibungen“, „sonstiges ist eine gültige Antwort“, Scraper nur mit Pausen, `scrape_runs`
    prüfen) und die offenen Ideen (Venue-Scraper für Herz-Orte, UI-Umbau, Karte).
11. `docs/historie/` befüllen: Pläne aus `~/.claude/plans/` (dd-bezogen), `CUTOVER.md` und
    `STACK.md` aus CT103, UI v2.
12. Merge nach `main`, Push nach GitHub.

**Phase 4 – Zip und Test in Cowork**
13. Zip ohne `.venv`/`__pycache__`, mit `.git`, `cache/` (DB + venue_cache) und
    `cache/archiv/dd-was-geht-v1-ct103.db` (per `pct pull`). Übergabe per SendUserFile.
14. David entpackt und öffnet den Ordner in Cowork. Dort laufen `pip install -r requirements.txt`,
    `pytest`, `python -m ddwg scrape && python -m ddwg build`.
    **Stopp, bis David bestätigt, dass die Cowork-Sandbox die Quellen erreicht.**

**Phase 5 – Abriss** (erst nach dem OK aus Phase 4; jeder irreversible Schritt wird einzeln angesagt)
15. CT103: `/opt/dd-was-geht/data` als tar nach leo `/root/dd-was-geht-ct103-final.tar.gz`.
    Danach Cron-Zeile raus, `docker compose down --rmi all`, `/opt/dd-was-geht`,
    `/root/dd-was-geht-site`, `/root/.ssh/dd-was-geht-deploy*` und den `github-dd`-Block in
    `/root/.ssh/config` entfernen.
16. GitHub: Repo `Trampa336/DD_was_geht` **löschen** (`gh repo delete`, braucht den Scope
    `delete_repo`; sonst macht David das im Browser). Im Repo `dd-was-geht` den Deploy-Key von
    leo widerrufen, außer David will ihn für Cowork behalten.
17. Forgejo CT108: Repo `erwin/dd-was-geht` löschen und das Remote `origin` entfernen.
18. leo: `/home/admin/dd-was-geht` (backend, frontend, .venv) löschen.
19. Referenzen prüfen und entfernen: Uptime-Kuma-Monitor :1111 (sqlite), Homepage-Kachel
    (CT103), Node-RED-Alerts.
20. Memory: `dd-was-geht.md` neu schreiben („lebt in Cowork auf Davids Rechner, GitHub
    `Trampa336/dd-was-geht`, nichts mehr auf leo oder CT103“). Die dd-Plan-Dateien in
    `~/.claude/plans/` löschen; sie sind im Repo unter `docs/historie/` archiviert.

## Verifikation
- `pytest` deckt ab:
  - normalize: uid, Kategorien
  - dedup: Cluster aus bekannten Paaren (cybersax↔KK)
  - merge: Beschreibung und Preis kommen von der richtigen Quelle, der Rang gilt
  - orte: Alias-Auflösung inkl. Straße E
  - Import-Filter: `weiter` wird verworfen
  - Scraper-Parser gegen gespeicherte HTML-Fixtures, soweit aus `tests_smoke.py` übernehmbar
- Echter Scrape: `scrape_runs` ist für alle 9 Quellen ok. Sektor und Straße E haben Events.
  Die Zahl der Events ist plausibel, verglichen mit den v2-Gewinnern ohne `weiter`
  (≈ 5300 − RA-Anteil).
- Merge-Stichprobe: Ein Event, das rauze und KK führen, hat Beschreibung und Preis von rauze und
  ein Bild.
- `ausgabe/index.html` öffnet ohne Server, „Deine Orte“ zeigt die Herz-Orte zuerst.
- Abriss: `pct exec 103 -- docker ps -a` und `crontab -l` ohne dd. Die Pages-URL liefert 404,
  `gh repo view Trampa336/DD_was_geht` schlägt fehl. `git remote -v` zeigt nur GitHub.
  Kuma und Homepage enthalten keine dd-Einträge mehr.

## Modell
Phasen 1–3 (Datenmodell, Dedup auf Cluster umstellen, Merge): **Opus 5.5**, weil es um Korrektheit
über mehrere Dateien geht. Phasen 4–5 (Zip, Abriss) sind mechanisch: **Sonnet 5**.

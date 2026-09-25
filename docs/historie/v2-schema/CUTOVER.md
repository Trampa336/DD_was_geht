# Cutover v1 -> v2 (Entwurf P2, ausgeführt von P3)

Es gibt **keine Migration**. Die alte DB wird eingefroren, die neue leer
gestartet und von den Scrapern neu gefüllt. Das ist vertretbar, weil ein
voller Scrape-Zyklus 6h dauert und der Katalog ohnehin rollierend ist —
und weil P2 gemessen hat, dass die `uid`-Berechnung unverändert bleibt
(`normalize.make_event_uid`), die neu gescrapten Events also **dieselben
uids** bekommen wie heute. Das ist der Grund, warum Herzen einen Cutover
überleben können, obwohl keine Event-Zeile mitgenommen wird.

## 0. Voraussetzung

Prüfen, dass `make_event_uid` nicht angefasst wurde. Ändert P3 Slugify,
Zeitnormalisierung oder die Feldreihenfolge, bricht **jede** uid und jedes
Herz. Diese Funktion ist ab jetzt eingefrorene Schnittstelle.

## 1. Alte DB einfrieren

Im Container, nicht auf dem Host — die DB liegt im Volume:

```
docker exec dd-was-geht sh -c '
  sqlite3 /app/data/dd-was-geht.db ".backup /app/data/backups/v1-frozen-$(date +%F).db"
'
```

`.backup` statt `cp`, weil die DB im WAL-Modus läuft und ein nacktes `cp`
eine inkonsistente Datei liefert. Die eingefrorene Kopie ist der
Rollback-Stand und wird **nicht** gelöscht; `backend/app/backup.py` darf sie
nicht in die Rotation nehmen.

Zusätzlich vor dem Umschalten die Herz-Vorlage retten, falls schon welche
existieren (heute: `reactions` ist leer, es gibt also nichts zu retten —
vor dem Lauf nachprüfen, nicht annehmen).

## 2. Neue DB anlegen

```
docker exec dd-was-geht sh -c '
  sqlite3 /app/data/dd-was-geht-v2.db < /app/migrations/001_schema_v2.sql
'
```

Danach `PRAGMA integrity_check` und `PRAGMA foreign_key_check` — beide müssen
leer/`ok` sein.

## 3. Venues vorbefüllen (einmalig, vor dem ersten Scrape)

Die 744 Rohstrings aus der eingefrorenen DB ziehen, normalisieren und als
`venues` + `venue_aliases` schreiben. Region kommt aus
`geo.classify_region(raw)`, `kind` bleibt zunächst `sonstiges`.

Das muss **vor** dem ersten Scrape laufen, sonst legt der Import 744 Venues
in zufälliger Reihenfolge an und die ids sind nicht reproduzierbar.

Nacharbeit von Hand, nach Eventzahl absteigend (die Top-120 decken den
Großteil ab): `kind` setzen, `is_meeting_point` für "Dresden City",
"Terrassenufer Dresden", "Theaterplatz Dresden" setzen, die 14 SKD-Häuser
über `parent_venue_id` verhängen.

## 4. Schreibpfad umstellen (die eigentliche P3-Arbeit)

Die 10 Scraper selbst müssen **nicht** angefasst werden — sie liefern Dicts
mit Freitext-`venue`, und das bleibt so. Geändert wird nur die Schicht
darunter, `app/db.py`:

1. `upsert_event()` löst `venue` über `venue_aliases` auf; unbekannter String
   legt Venue + Alias (`origin='auto'`) an und schreibt `venue_id` +
   `raw_venue`.
2. `upsert_event()` berechnet und schreibt `identity_key` =
   `sha1(source|url|date)`.
3. `category` heißt jetzt `category_slug` und ist ein FK — unbekannte Werte
   müssen auf `sonstiges` fallen, **nicht** die Transaktion killen.
4. Der Lesepfad, der heute `geo.classify_region(event["venue"])` pro Event
   ruft (`db.py` ~Zeile 342), liest die Region stattdessen per JOIN aus
   `venues`. Das ist derselbe Wert, nur 744 statt 5235 Auswertungen.
5. `reactions` fällt weg. `app/web.py` `/api/reaction` und die 👍/👎-Route
   dazu ebenfalls — sie werden von Herzen abgelöst.
6. `feed.py` exportiert `score` vorerst **nicht** mehr (Begründung in der
   DDL, Abschnitt 6: der Wert ist heute konstant 50.0).

`DB_PATH` per Env auf die v2-Datei zeigen lassen, erst dann Container neu
starten.

## 5. Verifikation vor dem Scharfschalten

* `python tests_smoke.py` grün.
* Einen einzelnen Scraper von Hand laufen lassen und prüfen, dass die
  erzeugten `uid`s mit denen im letzten veröffentlichten Tages-JSON
  übereinstimmen. **Das ist der Beweis, dass Herzen den Cutover überleben** —
  nicht der Smoke-Test.
* `/api/health` gegen den letzten `scrape_runs`-Stand der alten DB halten:
  Lauf-gesehen pro Quelle muss in derselben Größenordnung liegen. Eine
  Quelle, die plötzlich 0 liefert, ist ein kaputter Selektor, kein ruhiger Tag.
* Erst danach die Publish-Cron (`15 1,7,13,19`) wieder auf den neuen Stand
  lassen. Während des Umbaus Cron aussetzen, sonst veröffentlicht sie einen
  halbleeren Katalog auf GitHub Pages.

## 6. Rollback

`DB_PATH` zurück auf `dd-was-geht.db`, Container neu starten. Die v1-Datei
wurde nie angefasst. Die eingefrorene Kopie aus Schritt 1 ist die zweite
Sicherung, falls doch jemand darauf geschrieben hat.

# DD was geht – Self-Hosted Edition

Persönlicher Dresden-Eventdienst für deinen Raspberry Pi: Scraper (kulturkalender-dresden.de, rauze.de, ra.co, cybersax.de, azconni.de, sektor-evolution.de) → SQLite → Telegram-Bot (täglicher/wöchentlicher Push) → Web-Oberfläche im „DD was geht“-Look, die aus deinem Feedback lernt, was dir gefällt. Bewertet wird ausschließlich auf der Weboberfläche im Heimnetz; Newsletter und öffentliche Kopie sind reine Lesekanäle. Die Personalisierung ist eine einfache, transparente Scoring-Logik ohne KI (siehe unten).

## Was verifiziert ist – und was nicht

**Verifiziert gegen die echten Seiten:**

- URL-Muster beider Quellen: Kulturkalender `/heute/{YYYY-MM-DD}`, Rauze `/?date={YYYY-MM-DD}` – beide für nahe und weit entfernte Tage getestet.
- Die real gelieferten Kategorienamen (Rauze vergibt: Konzert, Party, Kunst, Festival, Film, Sonstiges, Außerhalb).
- Die tatsächlich verwendeten Zeitformate, inklusive des En-Dash in Zeitspannen (`18:00–19:30`) – ein echter Fallstrick, der einen naiven Parser stillschweigend Events überspringen lässt.
- Die komplette Kernlogik: Datenbank, Lern-Algorithmus, Bot-Logik, Web-Endpunkte (`python3 tests_smoke.py`, siehe „Tests“).
- **Resident Advisor:** die GraphQL-Schnittstelle `POST https://ra.co/graphql` inklusive Gebiets-ID 150 für Dresden, der gelieferten Felder (Titel, Startzeit, Ort, `cost`, `content`, Flyer, Line-up) und der Pagination – anders als bei den HTML-Quellen ist hier also auch die Datenstruktur selbst verifiziert, weil es eine API ist.
- **Doppelungs-Erkennung:** gegen einen echten Abgleich beider Quellen über zwei Wochen geprüft (alle 7 RA-Termine korrekt einem Rauze-Eintrag zugeordnet, keine falschen Treffer).
- **Statische Kopie für GitHub Pages** ([„Öffentliche Seite für Freunde"](#öffentliche-seite-für-freunde-github-pages)): der Export wurde gegen die Live-Datenbank gefahren und die entstandene Seite in einem echten Browser durchgeklickt – Heute/Woche/Monat, Filter-Menü, Kategorienzeile, Popup, Reload; Bewerten gibt es dort seit dem Umbau nicht mehr (nachgeprüft: kein Buttonpaar in Liste und Popup). Die Liste für „Heute" stimmte dabei Event für Event mit `/api/events` überein (190 = 190, keine Abweichung), und es ging keine einzige Anfrage an `/api/...` raus.

**Nicht verifiziert:** die exakte HTML-Struktur (Klassennamen, Verschachtelung), weil die Entwicklungsumgebung nur gerenderten Text sehen konnte. Die Parsing-Heuristik ist deshalb bewusst strukturunabhängig gebaut (sie sucht Uhrzeiten und arbeitet sich zum umgebenden Block hoch, statt auf CSS-Klassen zu setzen) und gegen nachgebaute Fixtures getestet. Sollte nach dem ersten Lauf etwas fehlen, hilft „Scraper kalibrieren“ unten – meist 5–10 Minuten.

## Voraussetzungen

- Raspberry Pi mit Docker + Docker Compose (bei dir bereits vorhanden)
- Architektur egal: Auf 64-bit-Pi-OS (aarch64) installiert sich alles per fertigem Wheel; auf 32-bit-Pi-OS (armv7) fehlt für `lxml` ein Wheel – das ist eingeplant, der Build überspringt es dann und der Code nutzt automatisch Pythons eingebauten Parser. Prüfen kannst du es mit `uname -m`.
- Ein Telegram-Bot-Token von [@BotFather](https://t.me/BotFather) (`/newbot`)
- Deine Telegram-Chat-ID

**Wichtiger Sicherheitshinweis:** Dein Bot-Token ist ein Passwort – wer ihn hat, kann als dein Bot senden. Trag ihn **nur** in die lokale `.env`-Datei auf deinem Pi ein (nie in Code, der geteilt/committed wird). Falls du ihn schon einmal irgendwo im Klartext geteilt hast, kannst du ihn bei @BotFather jederzeit per `/revoke` neu erzeugen lassen, sicherheitshalber.

## Setup (vom Linux-Laptop auf den Pi, per SSH)

Der Dienst wird als Git-Repo auf den Pi geholt und dort als Container gebaut. Ein
Klon auf dem Laptop ist nicht nötig – gebaut wird ohnehin auf dem Pi, weil dort die
Datenbank und die `.env` liegen.

> Wo das Repo liegt: Der Code steckt derzeit noch als Unterordner im privaten
> Homelab-Repo; ein eigenes Repo für den Dienst ist geplant. Nicht zu verwechseln
> mit `DD_was_geht` – das ist das **öffentliche** Repo, in dem nur die exportierte
> Seite liegt (siehe „Öffentliche Seite für Freunde“), kein Quellcode.

```bash
# --- Auf dem Pi (per ssh pi@raspberrypi.local) ---------------------------
# 1. Repo holen und in den Projektordner wechseln
git clone <repo-url> ~/dd-was-geht
cd ~/dd-was-geht

# 2. .env aus der Vorlage anlegen und ausfüllen
cp .env.example .env
nano .env      # TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID eintragen, dann Strg+O, Enter, Strg+X

# 3. Bauen und starten (erster Build dauert auf einem Pi 5-15 Minuten)
docker compose up --build -d

# 4. Zusehen, was passiert
docker compose logs -f     # beenden mit Strg+C, der Container läuft weiter
```

Danach: Web-UI unter `http://<pi-ip>:1111`, und in Telegram `/start` an deinen Bot
schicken. Der Bot antwortet auf `/start`, `/heute`, `/woche`, `/monat`, `/favoriten`.

Der Port steht so in `docker-compose.yml`: Host **1111** → Container 8080. `WEB_PORT`
in der `.env` ist der Port *innerhalb* des Containers und wird normalerweise nicht
angefasst; von außen erreichbar ist der Dienst über die linke Zahl der `ports`-Zeile.

Die mitgelieferte `.gitignore` hält `.env` (dein Bot-Token!) und `data/` (Datenbank)
bewusst aus der Versionskontrolle heraus. Nach einer Änderung an der Konfiguration
lohnt einmal `git status`, um sicherzugehen, dass `.env` **nicht** in der Liste steht.

### Falls etwas nicht läuft

```bash
docker compose ps                    # läuft der Container überhaupt?
docker compose logs --tail 50        # letzte Meldungen
docker compose restart               # neu starten
docker compose down && docker compose up --build -d   # kompletter Neuaufbau
```

Häufigster Stolperstein beim ersten Start: `.env` nicht ausgefüllt – dann beendet sich der Container sofort mit einer klaren Meldung, welche Variable fehlt.

## Updates einspielen

```bash
# Pi:
cd ~/dd-was-geht
git pull
docker compose up --build -d
```

`.env` und `data/` sind nicht im Repo und werden von `git pull` deshalb gar nicht
erst angefasst; die Datenbank liegt außerdem per Bind-Mount außerhalb des Images.
Ein Neubau kostet also weder die Konfiguration noch die gelernten Bewertungen.

Zurückrollen geht damit auch: `git log --oneline`, dann `git checkout <commit>` und
noch einmal `docker compose up --build -d`.

### Chat-ID herausfinden

1. Suche deinen Bot in Telegram (Name, den du bei BotFather vergeben hast) und drücke **Start**.
2. Öffne im Browser: `https://api.telegram.org/bot<DEIN-TOKEN>/getUpdates`
3. Suche nach `"chat":{"id": ...}` – diese Zahl ist deine `TELEGRAM_CHAT_ID`.

(Für einen Kanal statt Direktnachrichten: Bot als Admin zum Kanal hinzufügen, Chat-ID ist dann negativ, z.B. `-1001234567890`.)

## Scraper kalibrieren

Die Scraper suchen im HTML nach Textstellen, die wie eine Uhrzeit aussehen (`HH:MM`), und interpretieren deren nächstgelegenen übergeordneten Block als „ein Event“. Das ist robuster als exakte CSS-Klassennamen zu raten, kann aber je nach echter Seitenstruktur trotzdem daneben liegen.

Zum Prüfen/Justieren gibt es `tools/inspect_source.py`:

```bash
docker compose exec dd-was-geht python3 tools/inspect_source.py https://www.kulturkalender-dresden.de/heute
docker compose exec dd-was-geht python3 tools/inspect_source.py https://www.rauze.de/
```

Das lädt die Seite herunter, speichert das rohe HTML unter `data/last_fetch.html` und zeigt, welche Events die Heuristik erkannt hat. Falls Titel/Ort fehlen oder Events übersehen werden: `data/last_fetch.html` im Editor öffnen, kurz die Struktur um eine Uhrzeit herum ansehen und bei Bedarf `app/scrapers/kulturkalender.py` bzw. `app/scrapers/rauze.py` anpassen (z.B. `extract_venue`/`extract_title` in `app/scrapers/base.py`, die von beiden genutzt werden).

### Kategorie-Erkennung: die Ortsnamen-Falle

Ein Detail, das beim Kalibrieren echten Ärger macht und hier bereits gelöst ist: Ortsnamen enthalten oft selbst Genre-Wörter – „Burg Max Jacob **Theater**“, „Landes**bühnen** Sachsen“, „Jazz**club** Tonne“, „Freilicht**bühne** Junge Garde“. Wer die Kategorie per Stichwortsuche über den ganzen Block ermittelt, macht damit aus einem Rave im Max-Jacob-Theater ein Bühnenstück.

Deshalb blendet `base.text_excluding_links()` alle Linktexte (= die Orte) aus, bevor nach Kategorien gesucht wird, und bei Rauze wird zuerst die gerenderte Klammerform `( Konzert )` ausgewertet. Falls du die Kategorie-Logik anfasst: die Fixture-Tests in `tests_smoke.py` decken genau diese Fälle ab.

**Die eine bewusste Ausnahme – Kinos:** Für Filme ist der Ort das einzige Signal. Die Filmnächte am Elbufer laufen auf der Quellseite unter der Rohkategorie „Festival“, und Filmtitel wie „Sonnenallee“, „Zoomania 2“ oder „In the Grey“ enthalten kein einziges Genre-Wort – das komplette Open-Air-Kinoprogramm landete deshalb in *Musik & Nightlife* und dominierte den Newsletter. `normalize._is_film_venue()` prüft daher eine kurze, ausdrückliche Liste Dresdner Spielstätten (Filmnächte, Rundkino, UFA-Kristallpalast, Schauburg, Programmkino Ost, Zentralkino, Lichtspielhaus, CinemaxX, Thalia, Kino im Kasten). Getroffene Einträge landen in *Kultur & Bühne*. Das widerspricht der Ortsnamen-Falle nicht: dort geht es um Genre-Wörter, die *zufällig* in Ortsnamen stecken, hier um eine geprüfte Liste. Die Regel greift außerdem erst **nach** `RAW_CATEGORY_MAP` – sagt die Quelle ausdrücklich „Konzert“, ist es auch am Kino-Ort ein Konzert (Wincent Weiss und Clueso spielen dort live).

**„Festival“ entscheidet nichts mehr:** Die Quellseite benutzt das Label als Sammelbecken. Von 200 so markierten Einträgen waren (gemessen am 21.08.2026) nur rund 17 % wirklich Musik – der Rest sind Vorträge, Workshops, Führungen, Jüdische Kulturtage, ein Board-Game-Abend und eben das Kinoprogramm. `festival → musik` ist deshalb aus `RAW_CATEGORY_MAP` entfernt; es entscheidet jetzt der Titel (und beim Kino der Ort).

**Rauze-Kategorien „Sonstiges“ und „Außerhalb“:** Beide sagen nichts über die Art der Veranstaltung aus („Außerhalb“ heißt nur: im Umland). Sie werden deshalb absichtlich *nicht* übernommen, sondern fallen auf die Titel-Schlüsselwörter durch – so landet „Cstl Grdn Rave“ korrekt bei Musik statt bei „Weiteres“.

## Resident Advisor als Quelle

[ra.co](https://ra.co/events/de/dresden) ist die Referenz für elektronische Clubmusik und listet Dresden mit Preis, Line-up, Flyer und Beschreibung – oft ausführlicher als die deutschen Kalender.

**Warum das kein HTML-Scraper ist:** ra.co baut seine Seiten im Browser zusammen und schiebt jeden normalen Seitenabruf durch einen Bot-Schutz (DataDome). Ein `GET https://ra.co/events/de/dresden` antwortet mit **HTTP 403** und „Please enable JS“ – mit jedem User-Agent. Die GraphQL-Schnittstelle, aus der sich die Seite selbst bedient, ist dagegen offen:

```bash
curl -s https://ra.co/graphql -H "Content-Type: application/json" \
  -H "User-Agent: DresdenTakt/1.0" \
  -d '{"query":"query { areas { id name country { name } } }"}'
```

Damit findest du auch die Gebiets-IDs für `RA_AREA_ID` (Konstante in `app/config.py`): **150 = Dresden** (Standard), 149 Leipzig, 265 Chemnitz, 356 Sachsen. Ein einziger Request deckt einen ganzen Zeitraum ab – nicht Tag für Tag wie bei den HTML-Quellen –, und `content`/`cost` kommen schon in der Liste mit, es gibt also **nichts nachzuladen**. Ein User-Agent muss gesetzt sein, sonst antwortet auch `/graphql` mit 403.

Fällt die API aus, läuft der Rest des Scrapes normal weiter – jede Quelle hat in `app/scheduler.py:run_scrape()` ihren eigenen `try/except`. Abschalten heißt: die Zeile dort auskommentieren.

## Einzelne Häuser: CyberSAX, AZ Conni und Sektor Evolution als Quellen

Kulturkalender und Rauze decken zwei Enden ab – institutionelle Häuser und die kuratierte Neustadt-Auswahl. Dazwischen fehlten die **kleinen Bars, Cafés und Kleinbühnen mit Programm**. Messung vom 22.08.2026: von 4.309 Einträgen in der Datenbank kamen 4.161 vom Kulturkalender, das AZ Conni stand mit *einem* Termin drin.

### CyberSAX / SAX-Terminal

Der Tageskalender des SAX-Stadtmagazins, `https://www.cybersax.de/terminal/day/{YYYY}/{M}/{D}/` – **ohne führende Nullen** (`/2026/8/29/`). Verifiziert gegen die Live-Seite: 50–180 Zeilen pro Tag, 146 verschiedene Orte in acht Tagen. Neu dazugekommen sind damit u.a. Blue Note, Café Saite, Kafé Zeitlos, Der Lude, Downtown, Eselnest, Bürgergarten, Gartenlokal Fortschritt, Blaue Fabrik, Kleinkunstbühne Q24 und Hoppes Hoftheater.

Der Seitenaufbau ist eine schlichte Tabelle mit drei Zeilenarten:

| Markup | Bedeutung |
|---|---|
| `<td colspan="3"><h4>Musik</h4></td>` | Abschnittsüberschrift = Rohkategorie |
| `td1` Zeit, `td2` Ort, `td3` Titel | ein Event |
| `td1` Zeit, `td3` über zwei Spalten | Kinoprogramm (kein Ort) |

Deshalb wird hier **nicht** über `base.find_event_blocks()` geparst, sondern direkt über die `<tr>`: die Heuristik dort sucht Container mit Überschrift oder `class="event"`, und beides hat eine Tabellenzeile nicht.

**Nur kleine Häuser.** Das Terminal listet auch das komplette Programm von Semperoper, Frauenkirche und Residenzschloss – das steht aber schon vollständig im Kulturkalender. `cybersax.BIG_VENUE_SLUGS` wirft diese Orte deshalb schon **beim Scrapen** raus, damit sie gar nicht erst in die Datenbank kommen. Das ist bewusst eine kurze, ausdrückliche Liste und keine Rateheuristik: „groß“ sieht man einem Namen nicht an. Im Testlauf blieben so aus ~90 Rohzeilen pro Tag rund 26 übrig. Rutscht ein großes Haus durch, findet man es mit

```sql
SELECT venue, count(*) c FROM events WHERE source='cybersax' GROUP BY 1 ORDER BY c DESC LIMIT 40;
```

und trägt den Ortsnamen (durch `slugify()` geschickt) in die Liste ein. Achtung auf Schreibweisen: CyberSAX nennt das Haus des Staatsschauspiels schlicht „Schauspielhaus“.

**Festival-Überschriften: ein Line-up ist EINE Veranstaltung.** In der Überschriftenzeile steht meistens eine Rubrik („Musik“, „Bühne“), manchmal aber der Name einer einzelnen Veranstaltung – dann sind die folgenden Zeilen ihr Programm. Real am 22.08.2026: unter „Klang&Kruste“ standen **zehn** Zeilen, alle im Alaunpark; im Newsletter war ein Open Air damit zehnmal derselbe Termin. `cybersax` hängt für jede solche Gruppe (gleicher Tag, gleiche Überschrift, gleicher Ort, ab zwei Zeilen) einen **Sammel-Eintrag** an: Titel = Festivalname, Zeit = frühester Programmpunkt, Beschreibung = Line-up (`10:00 DJ Pappenheimer · 12:30 leuri303 · …`). Die Einzelzeilen bleiben erhalten und werden erst von der Doppelungs-Erkennung ausgeblendet (siehe unten) – das Line-up bleibt also abrufbar und die Zusammenfassung umkehrbar.

Unterschieden wird über `cybersax.SECTION_HEADINGS`, die ausdrückliche Liste der echten Rubriken; alles andere gilt als Festivalname (andersherum ginge es nicht – Festivalnamen sind beliebig). Jede Zusammenfassung steht im Lauf-Protokoll (`[cybersax] 2026-08-22: 'Klang&Kruste' als eine Veranstaltung zusammengefasst (10 Zeilen, Alaunpark)`); führt die Quelle eine neue **Rubrik** ein, fällt sie dort auf und gehört in die Liste. **Über Orte hinweg wird nie zusammengefasst:** das Musikfest Erzgebirge listet unter einer Überschrift echte Einzelkonzerte in verschiedenen Kirchen der Region, und der „Tag des Offenen Denkmals“ jedes Denkmal für sich.

**Zwei Eigenheiten der Quelle:** Titel und Langfassung stehen in derselben Zelle, getrennt durch ein `&nbsp;`, wobei die Langfassung im aufklappbaren `<div id="info…">` steckt – wird das Div einfach mitentfernt, gibt es gar keine Beschreibung mehr. Und es gibt **keine Event-Permalinks**, nur Ortsseiten; als `url` steht deshalb die Tagesseite drin. Bilder und Preise liefert die Quelle gar nicht.

### AZ Conni

Das AZ Conni steht in **keinem** Aggregator – nicht im Kulturkalender, nicht im SAX-Terminal, und auf Rauze stand genau ein Termin. Deshalb wird `https://www.azconni.de/termine/` direkt geholt: eine einzige Übersichtsseite für alle kommenden Termine, also ein Request pro Lauf statt Tag für Tag.

Das Markup ist sauber (`div.termin` mit `span.time`, `span.categories`, `header a`), hat aber einen Haken: **in der Datumszeile steht kein Jahr** („Donnerstag, 3. September ab 19:00 Uhr“). `_parse_german_date()` nimmt deshalb das nächste Vorkommen ab heute – im Dezember gehört ein Januartermin also ins Folgejahr. Wiederkehrende Termine teilen sich außerdem einen Permalink; das stört nicht, weil `make_event_uid()` das Datum mit einrechnet.

### Sektor Evolution

Die einzige dieser drei Quellen, bei der es **nicht** um Abdeckung geht: das Sektor Evolution steht sowohl bei Rauze als auch bei RA. Nur zeigte der Link im Newsletter dann eben auf `ra.co` statt auf den Laden. Mit `sektor` ganz vorn in `SOURCE_PRIORITY` gewinnt bei jeder erkannten Doppelung der Eintrag des Hauses, und verlinkt wird der echte Termin-Permalink (`…/event/werkhain-2/`). Was RA zusätzlich weiß (Preis, Flyer), trägt die Doppelungs-Erkennung weiterhin nach.

`https://www.sektor-evolution.de/dates/` ist – wie beim AZ Conni – eine **einzige Seite mit allen Terminen** (Vergangenheit und Zukunft, keine Blätterfunktion), gefiltert wird lokal. Markup des WordPress-Themes „angio“: `.mod-event-list` mit `.mod__event-day/-month/-year`, `.mod__event-name`, `.mod__event-location` und dem Permalink am umschließenden `<a>`.

Zwei Eigenheiten, die einen zweiten Request je Termin nötig machen:

* **Die Übersicht nennt keine Uhrzeit** – die steht nur auf der Detailseite, und zwar englisch im 12-Stunden-Format („Time: 11:00 PM“). `normalize.normalize_time()` würde daraus stumm `11:00` machen, deshalb rechnet `sektor._parse_time()` das Format zuerst selbst um. Die Uhrzeit ist auch deshalb wichtig, weil `make_event_uid()` sie mit einrechnet: nachträglich ergänzt, entstünde eine zweite Zeile für denselben Abend.
* **Preis, Flyer und Beschreibung** liefert ebenfalls nur die Detailseite.

`scrape_range()` holt sie deshalb für jeden Termin *im Zeitraum* mit – bei 31 Tagen Vorlauf rund zehn Requests pro Lauf, mit einer halben Sekunde Abstand und gedeckelt auf `MAX_DETAIL_FETCHES`. Fällt eine Detailseite aus, bleibt der Termin trotzdem stehen, nur ohne Uhrzeit. Dieselbe Parse-Funktion (`sektor.parse_detail()`) bedient das Detail-Popup im Web-UI, ist dafür in `detail_fetch._PARSERS` registriert.

Das Haus schreibt sich auf der eigenen Seite mal „SektorEvolution“, mal „Sektor Evolution“, einmal „Sektor Evolutin“; alle Varianten werden auf eine Schreibweise vereinheitlicht, sonst zerfiele der Ortsschlüssel der Doppelungs-Erkennung.

### Was noch fehlt

Für einzelne Läden (z.B. das KAWA) gibt es keine auffindbare Website mit Terminliste. Steht nur Instagram dahinter, gibt es dafür aktuell keinen Weg über einen Scraper.

## Doppelungen zwischen den Quellen

Rauze und Resident Advisor listen weitgehend **dieselben** Dresdner Clubnächte. Im Live-Abgleich über zwei Wochen (21.08.2026) waren alle 7 RA-Termine auch bei Rauze zu finden. Ohne Abgleich stünde jede dieser Nächte doppelt im Newsletter.

Der Abgleich läuft über *alle* Quellen, nicht nur über RA – und dort liegt der größere Effekt. Ein vollständiger Lauf über 31 Tage (4.395 gesehene Einträge) fand **71 Doppelungen**:

| ausgeblendet | zugunsten von | Anzahl |
|---|---|---|
| kulturkalender | rauze | 63 |
| ra | rauze | 7 |
| kulturkalender | ra | 1 |

Der Kulturkalender und Rauze führen dieselben Konzerte also laufend doppelt, nur unterschiedlich ausführlich betitelt („Ńoko“ vs. „ŃOKO [pol] Grenzenlose Klänge zwischen Dark Jazz…“). Weil `SOURCE_PRIORITY` mit `rauze` beginnt, steht im Newsletter die kurze Fassung – Preis, Bild und Beschreibung liefert Rauze ohnehin mit. Wer lieber die ausführlichen Titel des Kulturkalenders sehen will, stellt `SOURCE_PRIORITY` in `app/config.py` auf `["sektor", "azconni", "kulturkalender", "rauze", "ra", "cybersax"]` um; die fehlenden Felder werden dann aus dem Rauze-Eintrag aufgefüllt.

**Warum `cybersax` hinten steht,** ist gemessen und nicht geraten: Die Quelle hat keine Event-Permalinks, sondern nur die Tagesseite. Stand sie *vor* `kulturkalender`, verdrängte sie in einem Testlauf 40 Kulturkalender-Einträge, und der Newsletter verlinkte danach auf eine Tagesliste mit 90 Zeilen statt auf die Veranstaltung – das Auffüllen fehlender Felder konnte den besseren Link nicht nachtragen, weil die Tagesseite das `url`-Feld ja schon belegte. Der Gewinn dieser Quelle ist ihre **Abdeckung**, nicht die Qualität der einzelnen Zeile.

Es gibt zwei Arten von Doppelung, und beide werden mitgezählt:

1. **Deckungsgleich geliefert.** Schreiben zwei Quellen Datum, Zeit, Titel und Ort identisch, erzeugt `normalize.make_event_uid()` ohnehin dieselbe ID und es entsteht nur *ein* Eintrag. Bisher war das unsichtbar; jetzt hält die Tabelle `event_sources` fest, welche Quellen ihn geliefert haben.
2. **Unterschiedlich geschrieben.** Der Normalfall – Rauze kürzt auf den Reihennamen, RA hängt das Line-up an:

   | rauze.de | ra.co |
   |---|---|
   | Modus | MODUS: Akua |
   | Sachsentrance | Sachsentrance Sommerfest |
   | Bratty | bratty with charli xcx & other brat coded artists dresden |
   | Balearic Sunday | Balearic Sunday 2026 |

   Diese Fälle erkennt `app/dedup.py` und verbucht sie in `event_duplicates`.

**Wer sichtbar bleibt,** entscheidet `SOURCE_PRIORITY` in `app/config.py` (Standard `sektor, azconni, rauze, ra, kulturkalender, cybersax`): Bei einer Doppelung wird nur der Eintrag der vordersten Quelle ausgeliefert, der andere bleibt vollständig in der Datenbank, wird aber nicht mehr gelistet. Vorn stehen dabei die Quellen der Häuser selbst, weil nur sie auf den Laden verlinken statt auf einen Aggregator. **Fehlende Felder des sichtbaren Eintrags werden aus dem verdeckten aufgefüllt** – nennt Rauze keinen Preis und RA schon, steht der Preis trotzdem da. Vorhandene Werte werden nie überschrieben.

**Die Rangfolge gilt auch innerhalb einer Zeile.** Bei deckungsgleicher Lieferung (Fall 1) gibt es nichts auszublenden – es gibt ja nur einen Eintrag –, und in `events.source` steht dann schlicht, wer zuerst da war. Daraus folgen zwei Regeln, ohne die die Priorität ins Leere liefe:

* **Der Link gehört der bestplatzierten Quelle.** Ohne Regel gewönne, wer im Lauf zuletzt dran war (`db._keeps_own_url()`). Ein noch leeres `url`-Feld darf weiterhin jede Quelle füllen.
* **Für die Doppelungs-Erkennung zählt die beste Quelle der Zeile, nicht der Erstlieferant** (`dedup._best_rank()`, gespeist aus `event_sources`). Real am 22.08.2026 bei „GLUT x ELOS“ im Sektor Evolution: Kulturkalender und Sektor lieferten die Nacht wortgleich, die Zeile trug also längst den Link des Hauses – stand aber als `kulturkalender` da und wurde deshalb zugunsten des RA-Eintrags ausgeblendet. Im Newsletter zeigte der Link damit wieder auf ra.co.

Woran ein Paar erkannt wird – bewusst mit mehreren Gegenproben, damit nichts falsch verschmilzt:

* **Nur quellenübergreifend.** Zwei Einträge *derselben* Quelle gelten nie als Doppelung. Sonst würde aus der 11:00- und der 15:00-Führung im Albertinum eine einzige. **Genau eine Ausnahme:** die Zeilen eines Line-ups, die CyberSAX unter einem gemeinsamen Veranstaltungsnamen liefert (siehe oben). Sie hängen sich an den Sammel-Eintrag ihrer Gruppe, erkennbar daran, dass dieser den Veranstaltungsnamen als Titel *und* als Rohkategorie trägt – eine Markierung, die nur der Scraper setzt. Verlangt werden zusätzlich gleicher Tag, gleiche Quelle und gleicher Ort; im Protokoll steht als Grund `ueberschrift`.
* **Uhrzeit als Gegenprobe.** Mehr als 90 Minuten Abstand (über Mitternacht hinweg gemessen) heißt: verschiedene Termine, auch bei identischem Titel. **Ausnahme bei starker Evidenz:** Stimmen Ort *und* Titel praktisch überein (Wort-Überdeckung ≥ 0,8), gilt ein Fenster von 150 Minuten – Open-Air-Bühnen nennen mal den Einlass, mal den Beginn. Real am 21.08.2026: Rauze führte „Wincent Weiss“ um 17:00, der Kulturkalender „Wincent Weiss Sommertour 2026“ um 19:00, beide Filmnächte am Elbufer; das Konzert stand dadurch zweimal im Newsletter. Bei 150 statt 240 Minuten bleibt eine frühe und eine späte Vorstellung desselben Titels weiterhin getrennt.
* **Ort mit Alias-Liste.** „OKA“ = „objekt klein a“, „Club Paula“ = „Paula“, „Chemiefabrik e.V.“ = „Chemiefabrik“. Platzhalter wie „TBA“ oder „Location siehe Beschreibung“ zählen als *unbekannt* – dann darf der Ort weder für noch gegen eine Doppelung sprechen. Kennt der sichtbare Eintrag nur so einen Platzhalter und der verdeckte den echten Ort, wird er übernommen: aus „Klang & Kruste — Location siehe Beschreibung“ wird „Klang & Kruste — Alaunpark“.
* **Titel über zwei getrennte Maße.** Die Wort-Überdeckung („stecken alle bedeutsamen Wörter des kürzeren Titels im längeren?“) trägt die Fälle aus der Tabelle oben; die reine Zeichen-Ähnlichkeit taugt dafür nicht (bei „Modus“/„MODUS: Akua“ liegt sie nur bei 0,67). Umgekehrt bleibt die Wort-Überdeckung streng, wenn beide Titel gleich lang sind und sich im entscheidenden Wort unterscheiden: **„MODUS: Akua“ und „MODUS: Anetha“ verschmelzen nicht.** Bei unbekanntem Ort verlangt die Erkennung zusätzlich vollständige Überdeckung von mindestens zwei Wörtern *und* passende Uhrzeiten auf beiden Seiten.

Nachsehen, was zusammengefasst wurde:

```bash
docker compose exec dd-was-geht python3 tools/show_duplicates.py
docker compose exec dd-was-geht python3 tools/show_duplicates.py --tage 7
docker compose exec dd-was-geht python3 tools/show_duplicates.py --neu-berechnen
```

Die Ausgabe zeigt zu jedem Paar beide Fassungen, den Grund des Treffers und die Ähnlichkeit – gut geeignet, um zu prüfen, ob die Erkennung zu großzügig oder zu streng ist. Fehlt ein Ortsname in der Alias-Liste, steht sie als `VENUE_ALIASES` oben in `app/dedup.py`.

Die Erkennung läuft automatisch nach jedem Scrape über den kompletten Zeitraum (nicht nur über die frisch geholten Events) und ist idempotent: Ändert eine Quelle ihren Titel so, dass die Paarung nicht mehr trägt, löst sich die Verknüpfung von selbst wieder.

## Was im Newsletter steht

Der tägliche Push (Standard 8:00) schickt eine Überschrift und danach je eine Nachricht pro Empfehlung – eine eigene Nachricht deshalb, weil so jedes Event sein eigenes Cover bekommt. Bewerten geht im Newsletter **nicht**: 👍/👎 trainieren ein einziges, persönliches Modell, und das soll nur über die Weboberfläche im Heimnetz beschickt werden. Eine Zeile sieht so aus:

```
Sa 22.08.  18:00  Clueso — Filmnächte am Elbufer
```

* **Der Titel ist ein Link** auf die Veranstaltungsseite der Quelle. Alles, was aus den Quellen kommt, wird vorher maskiert – 286 Titel in der Datenbank enthalten ein `&` („Semperoper & Dresdner Altstadt“), und ein unmaskiertes Sonderzeichen lässt Telegram die ganze Nachricht mit HTTP 400 ablehnen. Linkvorschauen sind abgeschaltet, sonst wächst an jeder der sechs Nachrichten eine Vorschaukarte.
* **Der Wochentag steht nur im Wochen- und Monatsdigest** (`/woche`, `/monat`). Der Tagesdigest lässt ihn weg, dort ist er redundant.
* **Der Score entscheidet, *wer* in den Digest kommt – die Reihenfolge macht das Datum.** Über mehrere Tage hinweg liest sich eine nach Score sortierte Liste sonst wie Zufall: zwölf Zeilen mit Uhrzeit, aber ohne erkennbaren Tag.

Wie der nächste Push aussehen wird, lässt sich ansehen, ohne etwas zu verschicken:

```bash
docker compose exec dd-was-geht python3 tools/preview_digest.py
docker compose exec dd-was-geht python3 tools/preview_digest.py --tag 2026-09-05
docker compose exec dd-was-geht python3 tools/preview_digest.py --roh   # das gesendete HTML
```

**Cover-Bilder:** Wo eine Quelle ein Bild mitliefert (`image_url`), wird es angezeigt – in der Web-Liste als kleines Vorschaubild links vom Titel und im Detail-Popup groß. Im Telegram-Newsletter geht ein solches Event als Foto mit Bildunterschrift raus statt als reine Textzeile. Extra nachgeladen wird dafür **nichts** – benutzt wird nur, was ohnehin schon in der Datenbank steht (rauze und RA liefern das Bild beim Scrapen mit, beim Kulturkalender kommt es über den Detail-Abruf dazu). Events ohne Bild bekommen im Web eine Platzhalterfläche mit dem Anfangsbuchstaben der Kategorie und in Telegram die bisherige Textzeile; dasselbe passiert, wenn Telegram eine Bild-URL ablehnt (toter Link, >5 MB). Mit `python3 tools/preview_digest.py` zeigt ein 🖼 vor der Zeile, welche Events als Foto rausgehen.

**Dauerangebote im Web-UI:** Rund die Hälfte aller Einträge gehört zu Reihen, die an vielen Tagen hintereinander laufen – Ausstellungen, Werksführungen, der Hop-on-Hop-off-Bus (2097 von 4297 Zeilen; an einem einzelnen Tag rund 70 von 150). Sie sind nicht falsch, aber sie sind etwas anderes als „was ist heute Abend los“. Im Web werden sie deshalb in warmem Sandstein statt im Elbe-Türkis gezeichnet und mit „Dauerangebot“ beschriftet (`db.ONGOING_MIN_DAYS`, Standard 7 Tage). Im Telegram-Digest ändert sich nichts – dort werden sie ganz normal mitgewertet.

**Top-Treffer im Web-UI:** Das Gegenstück nach oben. Erreicht ein Event den gelernten „Für dich“-Score aus `HIGHLIGHT_SCORE` (`.env`, Standard 80), bekommt die Zeile den Elbe-Türkis-Balken und das Label „Top-Treffer“ – derselbe Aufbau wie beim Dauerangebot, nur in der Akzentfarbe, die den echten Empfehlungen vorbehalten ist. Wichtig zur Einordnung: Solange wenig Bewertungen vorliegen, deckelt die Laplace-Glättung die Scores nach oben – bei 29 Likes / 17 Skips lag das Maximum über alle 5008 kommenden Events bei **78,6**, die 80 wurde also von keinem Event erreicht. Deshalb ist die Schwelle absenkbar; auf dem Pi steht sie zunächst auf **70** und kann hochgezogen werden, sobald das Modell mehr gelernt hat. Der Telegram-Newsletter bleibt davon unberührt.

## Dresden oder Ausflug: der Schalter „Umgebung einschließen“

Der Kulturkalender heißt zwar „Dresden“, listet aber die ganze Region mit. Gemessen am 22.08.2026 liegen rund **29 % aller Einträge außerhalb der Stadtgrenze** – allein Meißen (Dom, Erlebniswelt, Albrechtsburg) stellt etwa 440 Zeilen, dazu Bad Schandau, Kamenz, Pulsnitz, Gohrisch, das Osterzgebirge, vereinzelt Leipzig, Cottbus und Weimar. Für „was geht heute in Dresden“ ist das Rauschen, als Ausflugstipp ist es willkommen. Deshalb gibt es drei Stufen (`app/geo.py`):

| Stufe | was dazugehört | wo sichtbar |
| --- | --- | --- |
| `dresden` | Stadtgebiet inkl. aller Ortsteile (Pillnitz, Langebrück, Schönfeld-Weißig, Cossebaude …) | immer |
| `umland` | Speckgürtel, rund 20 km: Radebeul, Freital, Pirna, Coswig, Heidenau, Moritzburg, Radeberg, Radeburg, Dohna … | immer |
| `weiter` | alles andere: Meißen, Kamenz, Bautzen, Sächsische Schweiz, Lausitz, Leipzig … | im Web nur mit Schalter, im Newsletter nie |

Im Web-UI sitzt der Schalter im Filter-Menü unter „Zeigen“, neben „Dauerangebote“ und „Wenig relevant“; er ist **standardmäßig aus**, zählt im Filter-Zähler mit und wird wie die anderen Filter im `localStorage` gemerkt. Ist er an, tragen die zusätzlichen Zeilen das Label „Umgebung“ – ohne Markierung liest sich Meißen mitten zwischen Neustadt-Konzerten wie ein Fehler. Der Telegram-Digest filtert dagegen immer (`db.events_for_range(..., exclude_far=True)`): dort steht „Heute **in Dresden**“ drüber, und ein Orgelkonzert im Meißner Dom hat da nichts verloren.

**Woher die Zuordnung kommt – und warum sie eine Liste ist.** Mehr als der Ortsname im Feld `venue` ist nicht da: die Detailseiten des Kulturkalenders nennen keine Adresse (geprüft – das `<address>`-Element enthält denselben Namen wie die Tagesliste), Geokoordinaten liefert keine Quelle. Die Zuordnung läuft deshalb über ausdrückliche Listen, dieselbe Bauart wie `cybersax.BIG_VENUE_SLUGS`: eine Ortsnamen-Liste je Stufe plus `VENUE_REGIONS` für Häuser, deren Name den Ort nicht verrät (Schloss Wackerbarth steht in Radebeul – mit 139 Einträgen der größte Einzelposten überhaupt).

Der eine Trick, der dabei wirklich zählt: **Ortsnamen werden als ganzes Wort geprüft, nicht als Teilstring.** Dresden ist voll von Straßen, die nach dem Nachbarort heißen, und die tragen im Deutschen zuverlässig die abgeleitete Form – „Bautzner Straße“, „Meißner Landstraße“, „Pirnaer Landstraße“, „Radeberger Biertheater“, „Riesaer Straße“, „Leipziger Bahnhof“. Als eigenes Wort fällt keine davon durch (`pirnaer` ≠ `pirna`). Aus demselben Grund steht `neustadt` in **keiner** der Listen: Neustadt in Sachsen liegt 40 km weg, die Dresdner Neustadt ist das Zentrum des Nachtlebens – ein Treffer hätte das halbe Musikprogramm versteckt. Die wenigen Dresdner Häuser, die trotzdem einen fremden Ortsnamen als Wort führen (`riesa efau` an der Adlergasse, der Alte Leipziger Bahnhof), stehen als Ausnahme in `DRESDEN_VENUES`.

Im Zweifel gilt **Dresden**: ein unbekannter Name ist viel wahrscheinlicher ein Dresdner Laden als ein Ausflugsziel, und ein falsch als „weiter“ gewerteter Eintrag verschwände lautlos aus Liste *und* Newsletter. Der lange Ausklang mit ein bis drei Terminen je Haus ist deshalb bewusst nicht vollständig erfasst. Rutscht ein Ausflugsziel durch, kommt es in die Liste in `app/geo.py`:

```sql
SELECT venue, count(*) c FROM events WHERE duplicate_of IS NULL GROUP BY 1 ORDER BY c DESC;
```

## Wie die Personalisierung funktioniert

Jedes 👍/👎 auf ein Event passt drei Arten von „Gewichten“ an: die **Kategorie** (Kultur & Bühne / Musik & Nightlife / Familie & Kinder / Führungen & Touren / Feste & Märkte / Sport & Bewegung / Weiteres), den **Ort** und ein paar **Schlüsselwörter** aus dem Titel. Für jedes neue Event wird daraus ein 0–100-„Für dich“-Score berechnet (Laplace-geglättete Like-Rate über die betroffenen Features, 50 = neutral/unbekannt). Kein Modell, keine externe API, alles nachvollziehbar in `app/scoring.py` (per `python3 tests_smoke.py` durchgetestet). Reaktionen sind idempotent – mehrfaches Klicken derselben Bewertung verändert nichts weiter, ein Wechsel (z.B. von 👎 zu 👍) macht die alte Gewichtung sauber rückgängig.

**„Weiteres“ (`sonstiges`) zählt bewusst nicht als Geschmacksmerkmal.** Es ist das Restfach des Klassifikators – dort landet, was keine Regel erkannt hat. Als Lern-Feature ist es schädlich: In der Live-Datenbank stand `category:sonstiges` bei 0 Likes / 4 Skips, und die Laplace-Glättung drückte damit *alle* 1734 Einträge dieses Buckets dauerhaft auf 29–41 %, darunter reichlich nur falsch einsortierte Veranstaltungen. Vier Klicks dürfen nicht 40 % des Katalogs stummschalten, deshalb liefert `sonstiges` in `scoring._feature_keys()` keinen Kategorie-Schlüssel mehr (`NEUTRAL_CATEGORIES`). Ort und Schlüsselwörter wirken dort weiterhin ganz normal.

Unabhängig vom Lern-Score gibt es zwei harte Filter. Der eine ist der Ort (siehe „Dresden oder Ausflug“ oben): Was weiter weg liegt als der Speckgürtel, kommt gar nicht erst in den Digest. Der andere ist `EXCLUDED_CATEGORIES` (`app/config.py`, Standard `familie`, `fuehrungen`): er blendet Kategorien aus dem Telegram-Newsletter (täglich/wöchentlich/`/monat`) und der Web-Startansicht komplett aus. Im Web-UI bleibt die Kategorie über den Filter-Chip trotzdem erreichbar.

Die Kategorien stehen im Web-UI als eine einzige, nicht umbrechende Chip-Zeile über der Liste (Kurzform aus `CATEGORY_SHORT_LABELS`; passt sie nicht, wird seitlich gewischt). Alles andere – „Dauerangebote", „Wenig relevant", die Quellen und „Auswahl zurücksetzen" – liegt rechts daneben im Klappmenü **Filter**, dessen Zähler anzeigt, wie viele Einstellungen vom Standard abweichen. Die Kategorie-Chips selbst sind eine **Mehrfachauswahl**: Jeder Chip lässt sich einzeln an- und abschalten, mehrere gewählte Kategorien werden zusammen angezeigt (`/api/events?cat=musik,kultur`, gleiches für `/api/fuer-dich`). „Alle“ setzt die Auswahl zurück – nur dann greift `EXCLUDED_CATEGORIES`; sobald mindestens ein Chip aktiv ist, zählt ausschließlich die Auswahl. Die Auswahl bleibt pro Browser im `localStorage` erhalten. „Familie & Kinder“ ist bewusst von „Führungen & Touren“ (Führungen, Rundgänge, Schiffsfahrten) und „Feste & Märkte“ getrennt, damit der Filter nicht versehentlich auch nicht-familienbezogene Events verschluckt.

**„Sport & Bewegung“ meint Mitmachen, nicht Zuschauen:** Yoga, Pilates, offene Radausfahrten, Lauftreffs, Klettern, Wanderungen. Zuschauersport (Fußball, Liga- und Heimspiele, Public Viewing) ist ausdrücklich ausgenommen und bleibt in „Weiteres“. Weil Quellseiten solche Termine gern unter ihrer eigenen Rubrik führen – „Yoga im Alaunpark“ läuft auf rauze.de als Rohkategorie „Festival“ –, wird Sport in `normalize.classify_category()` als Titel-Vorprüfung **vor** `RAW_CATEGORY_MAP` ausgewertet, und mit Wortgrenzen statt Substring-Treffern: sonst würden „Weinbergswanderung“ (Weinprobe) oder „Der Wanderer über dem Nebelmeer“ (Musical) mitkommen.

## Öffentliche Seite für Freunde (GitHub Pages)

Der Kalender lässt sich teilen, **ohne irgendetwas ins Netz zu öffnen**: keine Portfreigabe, kein Tunnel, kein VPN. Der Pi exportiert den Bestand als statische Seite und schiebt sie in ein öffentliches GitHub-Repo; Freunde lesen dort. Eingehende Verbindungen zum Pi gibt es dabei nicht.

**Das ist zugleich die Rechte-Trennung.** Bewerten kann nur, wer die Flask-Seite im Heimnetz aufmacht – dort landet jedes 👍/👎 in der SQLite und trainiert den „Für dich"-Score. Die öffentliche Kopie zeigt gar keine Bewerten-Buttons mehr: Der Code dafür steht in einer eigenen Datei (`app/static/rating.js`), die Vorlage bindet sie per Jinja (`{% if mode != 'static' %}`) nur in der Flask-Fassung ein, und der Exporter kopiert sie nicht mit (`web.PUBLIC_ASSETS`) – es liegt dort also nicht einmal Code für eine Bewertung. Mitgeliefert wird nur das Ergebnis – das Feld `score` je Event –, damit die Zeile „Empfehlungen der Woche" und der Filter „Wenig relevant" auch öffentlich rechnen können.

```
Container (LAN)                              GitHub               Freunde
  Scraper alle 6 h
  Flask :1111  ← hier wird bewertet
  tools/export_static.py → data/site/
        │
  Host-Cron: tools/publish_site.sh ──push──▶ DD_was_geht ──Pages──▶ Browser
                                             (öffentlich, noindex)   (nur lesen)
```

### Wie der Export gebaut ist

`tools/export_static.py` rendert **dieselbe** `app/templates/index.html` ein zweites Mal, nur mit `mode="static"` statt `mode="api"` – es gibt also kein zweites Frontend, das mit der Zeit auseinanderläuft. Stylesheet und Skripte sind ebenfalls dieselben Dateien: sie liegen in `app/static/` und werden mitkopiert (`web.PUBLIC_ASSETS`). Was sich unterscheidet: Liste und Empfehlungen lesen aus JSON-Dateien statt aus `/api/...`, das Detail-Popup lädt nichts nach, und Bewerten gibt es dort nicht (`CAN_RATE` in `app/static/app.js`).

Ausgabe (nach `data/site/`):

| Datei | Inhalt |
|---|---|
| `index.html` | die Seite im static-Modus, inkl. `noindex` |
| `static/*` | Stylesheet und Skripte, dieselben Dateien wie auf dem Pi – ohne `rating.js` |
| `data/index.json` | welche Tage es gibt, je Tag ein Inhalts-Hash als Cache-Buster |
| `data/days/JJJJ-MM-TT.json` | die Events eines Tages, inkl. Beschreibung, Bild und Preis |
| `robots.txt`, `.nojekyll` | kein Crawling; GitHub Pages soll nichts wegfiltern |

**Warum eine Datei pro Tag?** Der Bestand sind rund 5.000 Events auf 32 Tagen ≈ 2,5 MB (gemessen am 22.08.2026: 4.928 Events, 32 Tage). Als eine einzige Datei wäre das bei vier Pushes am Tag jedes Mal ein neuer 2,5-MB-Blob in der Git-Historie. So schreibt der Export nur die Tage neu, an denen sich wirklich etwas geändert hat (byte-genauer Vergleich vor dem Schreiben), und der Browser lädt für „Heute" auch nur einen Tag (~18 KB gzip). Tage, die aus dem Zeitfenster gelaufen sind, werden gelöscht.

Den „Für dich"-Score rechnet der **Exporter** aus (`scoring.score_events()`, dieselbe Funktion wie hinter `/api/events`) und legt ihn als Feld `score` in die Tagesdatei. Im Browser wird nichts nachgerechnet: Die frühere Gast-Bewertung im `localStorage` samt JS-Nachbau von `app/scoring.py` ist ersatzlos entfallen, seit öffentlich nicht mehr bewertet wird.

### Einrichten (einmalig)

1. **Repo anlegen** – bei GitHub ein **öffentliches** Repo `DD_was_geht`. Öffentlich muss es sein, weil GitHub Pages aus privaten Repos nur mit GitHub Pro geht; deshalb ein eigenes Repo und nicht das (private) Homelab-Repo.
2. **Deploy-Key auf dem Pi**:

   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/dd-was-geht-deploy -N ""
   cat ~/.ssh/dd-was-geht-deploy.pub     # → GitHub: Repo → Settings → Deploy keys
   ```

   Beim Eintragen **„Allow write access"** ankreuzen. Dann in `~/.ssh/config`:

   ```
   Host github-dd
       HostName github.com
       User git
       IdentityFile ~/.ssh/dd-was-geht-deploy
       IdentitiesOnly yes
   ```

3. **Site-Repo auschecken** (liegt bewusst neben dem Projekt, nicht darin):

   ```bash
   git clone git@github-dd:Trampa336/DD_was_geht.git ~/dd-was-geht-site
   git -C ~/dd-was-geht-site config user.name  "dd-was-geht"
   git -C ~/dd-was-geht-site config user.email "dd-was-geht@localhost"
   ```

4. **Pages aktivieren** – Repo → Settings → Pages → Source: Branch `main`, Ordner `/ (root)`.
5. **Erster Lauf von Hand**:

   ```bash
   ~/dd-was-geht/tools/publish_site.sh
   ```

6. **Cron** (45 Minuten nach jedem Scrape, der um `*/6:30` läuft), `crontab -e`:

   ```
   15 1,7,13,19 * * * /home/pi/dd-was-geht/tools/publish_site.sh >> /home/pi/dd-was-geht/data/publish.log 2>&1
   ```

Die Seite steht danach unter `https://trampa336.github.io/DD_was_geht/`.

### Was das Skript absichert

`tools/publish_site.sh` läuft auf dem **Host** (dort liegt der Deploy-Key), exportiert aber im **Container** (dort liegen die Abhängigkeiten und die DB) – das Ergebnis landet über den vorhandenen Bind-Mount direkt in `data/site/`. Vor dem `rsync --delete` prüft es, ob der Export überhaupt vollständig ist: ein leerer oder halber Export würde sonst die öffentliche Seite löschen. Ändert sich nichts, wird auch nicht committet – dafür läuft sogar der Zeitstempel `generated_at` nur weiter, wenn sich am Bestand wirklich etwas getan hat. Sonst bekämen `index.json` und `index.html` (der Stand steht in ihrer Fußnote) viermal täglich einen neuen Blob, ohne dass ein einziges Event dazugekommen wäre. Die Skripte unter `static/` (zusammen rund 95 KB) ändern sich ohnehin nur, wenn am Frontend etwas geändert wurde.

### Grenzen

* **Öffentlich ist öffentlich.** `noindex` und `robots.txt` halten Suchmaschinen fern, mehr nicht. Wer die URL hat, sieht den Kalender. Ein echtes Passwort kann statisches Hosting nicht – das ginge nur mit Cloudflare Access o.ä. vor einem Tunnel.
* **Bilder sind heiß verlinkt** (wie im LAN auch): sie kommen weiter von den Quellseiten. Fällt eines aus, greift der vorhandene Platzhalter.
* Die Seite ist bis zu sechs Stunden alt (Scrape-Takt). Für „Heute" reicht das; ganz frisch eingetragene Termine erscheinen erst nach dem nächsten Push.

## Projektstruktur

```
dd-was-geht/
  main.py                 Startpunkt: Web-UI-Thread + Scheduler + Bot-Polling
  app/
    config.py              .env-Werte (Secrets, Pfade, Zeiten) + feste Konstanten
    db.py                  SQLite: Events, Reaktionen, Gewichte
    normalize.py            Kategorisierung, Schlüsselwörter, stabile Event-IDs
    dedup.py                Doppelungen zwischen Quellen erkennen und verbuchen
    geo.py                  Dresden / Speckgürtel / weiter weg (Schalter „Umgebung“)
    scoring.py              Lern-/Bewertungslogik
    feed.py                 Die ausgelieferte Event-Liste - einmal gebaut, von
                            Web-UI und statischem Export gemeinsam benutzt
    ranges.py               Datumsbereiche heute/woche/monat
    bot.py                  Telegram-Bot (aiogram)
    web.py                  Web-Oberfläche (Flask)
    scheduler.py             Tägliche/wöchentliche Jobs (APScheduler)
    scrapers/
      base.py                Gemeinsame Fetch-/Parsing-Heuristik
      kulturkalender.py       Quelle 1
      rauze.py                Quelle 2
      ra.py                   Quelle 3: Resident Advisor (GraphQL-API, kein HTML)
      cybersax.py             Quelle 4: SAX-Terminal (kleine Läden)
      azconni.py              Quelle 5: AZ Conni (einzelnes Haus)
      sektor.py               Quelle 6: Sektor Evolution (einzelnes Haus)
      detail_fetch.py         Beschreibung/Preis einzelner Events nachladen
    templates/index.html     Web-UI - eine Vorlage, zwei Modi: 'api' (Flask im LAN)
                             und 'static' (oeffentliche Kopie, liest JSON-Dateien).
                             Nur noch Markup; Konfiguration reicht window.DD durch
    static/boot.js           Theme setzen, bevor gezeichnet wird (blockierend im Kopf)
    static/app.css           Stylesheet
    static/app.js            Liste, Filter, Popup, Empfehlungen
    static/background.js     Hintergrund-Animationen
    static/rating.js         Bewerten mit 👍/👎 - NUR in der Flask-Fassung
  tools/inspect_source.py    Debug-Helfer zur Scraper-Kalibrierung
  tools/show_duplicates.py   Zeigt, welche Doppelungen verbucht sind
  tools/preview_digest.py    Zeigt den Newsletter, ohne ihn zu verschicken
  tools/reclassify.py        Kategorien im Bestand nachziehen (Backfill)
  tools/export_static.py     Statische Kopie fuer GitHub Pages bauen
  tools/publish_site.sh      Diese Kopie committen und pushen (laeuft auf dem Host)
  tests_smoke.py             Schnelltest der Kernlogik ohne Netzwerk
  .env.example
  docker-compose.yml / Dockerfile
```

## Tests

```bash
python3 tests_smoke.py
```

Prüft Normalisierung, die Ortszuordnung (`app/geo.py` samt Straßennamen-Gegenproben), Datenbank, die komplette Lernlogik, Preis-/Detail-Extraktion, den Detail-Endpunkt, das Parsen der RA-Antwort, die Doppelungs-Erkennung, den statischen Export (Vollständigkeit, static-Modus, `noindex`, unveränderte Tage werden nicht neu geschrieben), dass Flask alle Dateien aus `app/static/` ausliefert und die Vorlage sie mit Cache-Buster verlinkt, und seit Neuestem auch die Newsletter-Zeile selbst (`bot._event_line`: Datumsspalte, Verlinkung, Maskierung von `&` und spitzen Klammern) – alles mit synthetischen Daten bzw. mitgelieferten Fixtures (kein Netzwerk nötig). Sollte nach jeder Änderung an `app/normalize.py`, `app/db.py`, `app/scoring.py`, `app/dedup.py`, den Scrapern oder `app/web.py` grün sein.

Die Fixtures sind bewusst echte, nur gekürzte Antworten der Live-Quellen, und mehrere Testfälle stammen direkt aus Live-Abgleichen (die Titel-Paare „Modus“/„MODUS: Akua“ usw. haben eine zu strenge erste Fassung der Erkennung auffliegen lassen).

## Preise, Cover und das Detail-Popup

Im Web-UI trägt jedes Event ein Preis-Badge (sofern die Quelle einen Preis nennt) und einen „Details"-Knopf, der ein Popup mit Cover, Beschreibung und Preis öffnet – ohne die Seite zu verlassen. Woher die Daten kommen, unterscheidet sich je Quelle:

* **Rauze** liefert den kompletten Detailinhalt bereits in der Tagesliste mit (dort nur per JavaScript zugeklappt): Preis, Cover, Beschreibung und den sauberen Event-Permalink. Das wird beim normalen Scrape mitgenommen – **keine zusätzlichen Requests**.
* **Kulturkalender** zeigt in der Tagesliste nur Cover und Permalink, aber keinen Preis und keine Beschreibung. Beides holt `scrapers/detail_fetch.py` **erst beim ersten Klick** auf „Details" von der Event-Seite und schreibt es in die DB; ab dann kommt es von dort. Der nächtliche Scrape bleibt dadurch genauso schnell wie vorher.

Preise stehen beim Kulturkalender nur im Fließtext („Eintritt: 11€-18€"), werden also per Mustererkennung herausgezogen – ein konkreter Betrag schlägt dabei bewusst ein beiläufiges „Eintritt frei" im selben Satz. Findet sich nichts, bleibt das Badge einfach weg.

Falls der Kulturkalender sein Markup ändert und Beschreibungen leer bleiben: die Selektoren stecken in `_parse_kulturkalender_detail`, kalibrieren wie im Abschnitt „Scraper kalibrieren".

## Quellen

| Quelle | Abdeckung | Zeitraum |
|---|---|---|
| kulturkalender-dresden.de | Bühne, Oper, Ausstellungen, Führungen, Familie | Tag für Tag, beliebig weit |
| rauze.de | Clubs, Partys, Konzerte, Raves, Kunst, Film | Tag für Tag, beliebig weit |
| ra.co (Resident Advisor) | Elektronische Clubmusik, mit Line-up, Preis und Flyer | ein Request pro Zeitraum (GraphQL-API) |
| cybersax.de (SAX-Terminal) | Kleine Bars, Cafés, Kleinbühnen mit Programm | Tag für Tag |
| azconni.de | AZ Conni, in keinem Aggregator | ein Request pro Lauf |
| sektor-evolution.de | Sektor Evolution, für den Link auf das Haus selbst | ein Request plus einer je Termin im Zeitraum |

Der Kulturkalender ist stark bei Hochkultur und Tagesprogramm, Rauze bei Nightlife (Ostpol, objekt klein a, GrooveStation, Sektor Evolution, Chemiefabrik, Scheune). **Resident Advisor überschneidet sich fast vollständig mit Rauze** – im Live-Abgleich über zwei Wochen war jeder RA-Termin auch bei Rauze zu finden. Der Gewinn liegt deshalb weniger in zusätzlichen Terminen als in den besseren Daten: Line-up, Preis und Flyer, die über die Doppelungs-Erkennung in den Rauze-Eintrag einfließen (siehe „Doppelungen zwischen den Quellen“). Über einen längeren Vorlauf listet RA außerdem Termine, die bei Rauze noch nicht eingetragen sind.

Eine weitere Quelle hinzuzufügen heißt: eine Datei nach dem Vorbild von `app/scrapers/rauze.py` (HTML) oder `app/scrapers/ra.py` (API) anlegen, in `app/scheduler.py:run_scrape()` eintragen und in `SOURCE_PRIORITY` einsortieren.

## Grenzen (Stand jetzt, bewusst offen dokumentiert)

- HTML-Struktur der Quellen nicht gegen rohes Markup verifiziert – siehe „Was verifiziert ist“ und „Scraper kalibrieren“.
- Die Doppelungs-Erkennung (`app/dedup.py`) arbeitet mit Schwellwerten, nicht mit Gewissheit. Sie ist bewusst so eingestellt, dass sie im Zweifel *nicht* zusammenfasst: lieber ein Event zweimal im Newsletter als eines, das stillschweigend verschwindet. Zwei Termine derselben Reihe am selben Abend („MODUS: Akua“ / „MODUS: Anetha“) bleiben deshalb getrennt, und Läden mit mehreren gleichzeitigen Bühnen können ebenfalls zwei Einträge behalten. Was tatsächlich zusammengefasst wurde, zeigt `tools/show_duplicates.py`.
- Wird ein Eintrag als Doppelung ausgeblendet, verschwindet er aus Newsletter und Web – ein 👍/👎 auf genau diese Fassung bleibt in der Lernlogik gültig, und in `/favoriten` erscheint statt seiner die sichtbare Fassung.
- Ein Nutzerkonto/eine Person – die Lernlogik ist bewusst nicht für mehrere Nutzer mit unterschiedlichem Geschmack ausgelegt.
- Die HTML-Quellen werden höflich, aber ohne offizielle Schnittstelle abgefragt (1,2 s Pause zwischen Anfragen, klarer User-Agent); nur Resident Advisor hat eine echte API. Ändert eine Seite ihr Layout grundlegend, ist eine Nachjustierung fällig.

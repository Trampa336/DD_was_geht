/* Die Eventliste: Filter, Liste, Empfehlungszeile und Detail-Popup. Alles, was
   von Konfiguration oder Betriebsart abhaengt, kommt aus window.DD - gesetzt im
   Kopf der Vorlage (app/templates/index.html), sonst weiss diese Datei nichts
   von Jinja. Aussehen und Klappmenues stehen seit der Kartenansicht in
   chrome.js, das vor dieser Datei geladen wird. */
(function () {
  var DD = window.DD;
  // Seit P5b eine Liste (categories-Tabelle, sort_order/default_visible statt
  // dem alten config.CATEGORY_LABELS-Woerterbuch) - fuer die Label-Suche in
  // dieser Datei reicht ein einfaches Nachschlage-Objekt daraus.
  var CAT_LABEL = {};
  (DD.categories || []).forEach(function (c) { CAT_LABEL[c.slug] = c.label; });

  // Die beiden Betriebsarten sind im Kopf der Vorlage beschrieben.
  var MODE = DD.mode;
  // Geherzt wird ausschliesslich im Heimnetz. Das ist keine Pruefung, sondern
  // die Bauart: auf der statischen Kopie gibt es nichts, wohin ein Klick ginge -
  // herzen.js wird dort gar nicht erst mitgeliefert (bis P5c hiess dieselbe
  // Weiche CAN_RATE und galt fuer rating.js).
  var CAN_HEART = MODE === 'api';
  var EXCLUDED = DD.excluded;
  var DATA_V = DD.dataVersion;

  var listEl = document.getElementById('list');
  var pickRow = document.getElementById('fuer-dich-row');
  // Keine Persistenz ueber einen Reload hinweg (wie zuvor bei den Reitern) -
  // "keine Auswahl" heisst also bei jedem Aufruf wieder "heute".
  var selectedDate = isoDay(new Date());
  var selectedCats = [];  // leer = "Alle" (ohne die per EXCLUDED_CATEGORIES ausgeblendeten)

  // Sichtbarkeits-Schalter. Anders als die Kategorien laufen die NICHT gegen die
  // API: /api/events liefert ongoing, source und score ohnehin mit, deshalb wird
  // hier nach dem Laden gefiltert statt neu geholt.
  var SRC_LABEL = DD.sources;
  /* Bis P5c stand hier LOW_SCORE = 40 und ein Filter "Wenig relevant", der
     alles darunter ausblendete. Der Score kommt jetzt aus den Herzen, und ein
     Herz ist ein einseitiges Signal: die Laplace-Rate in app/scoring.py kann
     50 nicht mehr unterschreiten, unter 40 kommt also nie wieder ein Event.
     Der Schalter ist deshalb entfernt und nicht nur abgeschaltet - ein Filter,
     der nichts filtern kann, sieht aus wie eine kaputte Liste. */
  // Gegenstueck nach oben (config.HIGHLIGHT_SCORE): ab hier wird die Zeile als
  // Treffer hervorgehoben. Kommt aus der .env, damit die Schwelle mitwachsen
  // kann, waehrend das Lernmodell noch wenig Bewertungen kennt.
  var HIGHLIGHT_SCORE = DD.highlightScore;
  /* umgebung=false ist der Standard (P5b/decision #12): gezeigt wird NUR
     Dresden. Umland (Radebeul, Freital, Pirna, Moritzburg ...) UND alles
     weiter Weg (Meissen, Saechsische Schweiz, Lausitz, Leipzig - beides
     region != 'dresden', siehe app/geo.py) kommen erst mit dem Schalter dazu.
     Vorher blieb Umland immer sichtbar und nur "weiter" hing am Schalter -
     das ist die Verhaltensaenderung aus dem P5b-Bericht.
     tags=[] ist die neue Merkmal-Auswahl (kirche/museum/open-air/klassik/
     techno, echte Tabelle seit P2) - leer heisst keine Einschraenkung, wie bei
     den Kategorien. */
  var filters = { ongoing: false, umgebung: false, tags: [], sources: Object.keys(SRC_LABEL) };
  // Die Suche ist bewusst NICHT gespeichert (wie die Datumsauswahl) - ein
  // neuer Aufruf der Seite soll wieder bei "keine Suche" anfangen.
  var searchQuery = '';

  function loadFilters() {
    try {
      var saved = JSON.parse(stored('filters', '') || 'null');
      if (!saved) { return; }
      filters.ongoing = !!saved.ongoing;
      // saved.lowscore aus einem Browser, der die Seite vor P5c zuletzt gesehen
      // hat, wird hier schlicht nicht mehr gelesen - der Schalter ist weg.
      filters.umgebung = !!saved.umgebung;
      if (Array.isArray(saved.tags)) {
        var knownTags = Array.prototype.map.call(document.querySelectorAll('.chip-tag'), function (c) { return c.dataset.tag; });
        filters.tags = saved.tags.filter(function (t) { return knownTags.indexOf(t) !== -1; });
      }
      if (Array.isArray(saved.sources)) {
        filters.sources = saved.sources.filter(function (s) { return s in SRC_LABEL; });
      }
    } catch (e) { /* kaputter Eintrag - Standardwerte bleiben */ }
  }

  function saveFilters() { store('filters', JSON.stringify(filters)); }

  function syncFilterChips() {
    press('.chip-toggle', function (chip) { return filters[chip.dataset.toggle]; });
    press('.chip-tag', function (chip) { return filters.tags.indexOf(chip.dataset.tag) !== -1; });
    press('.chip-src', function (chip) { return filters.sources.indexOf(chip.dataset.src) !== -1; });
    syncFilterBadge();
  }

  /* Zaehlt, was vom Standard abweicht - zugeklappt sieht man dem Menue sonst
     nicht an, dass es gerade etwas ausblendet. Die Schalter und Merkmale
     zaehlen im EIN-Zustand, weil sie standardmaessig aus sind; bei den
     Quellen zaehlt jede abgewaehlte. */
  function syncFilterBadge() {
    var badge = document.getElementById('filter-badge');
    var n = (filters.ongoing ? 1 : 0)
      + (filters.umgebung ? 1 : 0) + filters.tags.length
      + (Object.keys(SRC_LABEL).length - filters.sources.length);
    badge.textContent = n;
    badge.hidden = n === 0;
  }

  function passesFilters(e) {
    if (e.ongoing && !filters.ongoing) { return false; }
    // Ohne region-Feld gilt ein Event als Dresden - so bleibt eine Tagesdatei
    // aus einem aelteren Export lesbar (siehe tools/export_static.py).
    if (e.region && e.region !== 'dresden' && !filters.umgebung) { return false; }
    // Eine unbekannte Quelle (neuer Scraper, noch kein Label) bleibt sichtbar -
    // sonst verschwaende sie kommentarlos aus der Liste.
    if (e.source in SRC_LABEL && filters.sources.indexOf(e.source) === -1) { return false; }
    // Merkmale: mindestens eines der ausgewaehlten muss zutreffen (ODER, wie
    // bei den Kategorien) - keine Auswahl heisst keine Einschraenkung.
    if (filters.tags.length) {
      var eventTags = e.tags || [];
      if (!filters.tags.some(function (t) { return eventTags.indexOf(t) !== -1; })) { return false; }
    }
    if (searchQuery) {
      var haystack = ((e.title || '') + ' ' + (e.venue || '')).toLowerCase();
      if (haystack.indexOf(searchQuery) === -1) { return false; }
    }
    return true;
  }

  function knownCats() { return Object.keys(CAT_LABEL); }

  function loadSelection() {
    try {
      return (JSON.parse(stored('cats', '') || '[]') || [])
        .filter(function (c) { return knownCats().indexOf(c) !== -1; });
    } catch (e) { return []; }
  }

  function saveSelection() { store('cats', JSON.stringify(selectedCats)); }

  function catQuery() { return selectedCats.length ? selectedCats.join(',') : 'alle'; }

  /* --- static-Modus: Daten, Bewertungen und Score ohne Server ---------------
     Alles ab hier laeuft nur auf der GitHub-Pages-Kopie. Im api-Modus wird
     keine dieser Funktionen aufgerufen; die Flask-Seite verhaelt sich exakt
     wie vorher. */

  var staticIndexPromise = null;
  var dayCache = {};

  function staticIndex() {
    if (!staticIndexPromise) {
      staticIndexPromise = fetch('data/index.json?v=' + encodeURIComponent(DATA_V))
        .then(function (r) { return r.json(); });
    }
    return staticIndexPromise;
  }

  // Lokales Datum. toISOString() waere hier falsch - das rechnet in UTC und
  // liefert abends in Berlin schon den Folgetag.
  function isoDay(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
      + '-' + String(d.getDate()).padStart(2, '0');
  }

  // Dasselbe rollierende Fenster wie week_range() in app/ranges.py: sieben
  // Tage ab heute, nicht ab Wochenanfang. Nur noch fuer die Empfehlungszeile
  // gebraucht (staticPicks) - die Liste selbst zeigt seit dem Kalender-Umbau
  // immer genau einen Tag.
  function weekDays() {
    var today = new Date(); today.setHours(0, 0, 0, 0);
    var last = new Date(today); last.setDate(last.getDate() + 6);
    var days = [], cur = new Date(today);
    while (cur <= last) { days.push(isoDay(cur)); cur.setDate(cur.getDate() + 1); }
    return days;
  }

  function loadDay(day, version) {
    if (!dayCache[day]) {
      dayCache[day] = fetch('data/days/' + day + '.json?v=' + encodeURIComponent(version))
        .then(function (r) { return r.ok ? r.json() : []; })
        .catch(function () { return []; });
    }
    return dayCache[day];
  }

  /* Ersatz fuer GET /api/events: nur die Tagesdateien des Zeitraums holen und
     danach dieselben Filter anwenden, die im api-Modus in SQL stehen
     (db.events_for_range + web._selected_categories). Doppelungen und die
     ongoing-Markierung hat schon der Exporter erledigt. */
  function staticEvents(days, cats) {
    return staticIndex().then(function (idx) {
      var versions = {};
      idx.days.forEach(function (d) { versions[d.date] = d.v; });
      // Tage ohne Datei (Seite laenger nicht aktualisiert) bleiben einfach leer.
      var wanted = days.filter(function (d) { return d in versions; });
      return Promise.all(wanted.map(function (d) { return loadDay(d, versions[d]); }));
    }).then(function (chunks) {
      var events = [];
      chunks.forEach(function (chunk) {
        chunk.forEach(function (e) {
          if (cats.length) { if (cats.indexOf(e.category) === -1) { return; } }
          else if (EXCLUDED.indexOf(e.category) !== -1) { return; }
          events.push(e);
        });
      });
      events.sort(function (a, b) {
        return (a.date + (a.time || '99:99')).localeCompare(b.date + (b.time || '99:99'));
      });
      return events;
    });
  }

  function syncChips() {
    press('.chip[data-cat]', function (chip) {
      return chip.dataset.cat === 'alle'
        ? selectedCats.length === 0
        : selectedCats.indexOf(chip.dataset.cat) !== -1;
    });
    document.getElementById('chip-reset').hidden = selectedCats.length === 0;
  }

  var overlayEl = document.getElementById('modal-overlay');
  var modalEl = overlayEl.querySelector('.modal');
  var currentModalEvent = null;
  var lastFocusedEl = null;


  function formatDay(iso) {
    var today = new Date().toISOString().slice(0, 10);
    if (iso === today) { return 'Heute'; }
    return new Date(iso + 'T00:00:00').toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: 'long' });
  }

  // Die Zeile unter dem Titel - im Popup und auf den Empfehlungskarten dieselbe.
  function whenLabel(ev) { return formatDay(ev.date) + (ev.time ? ' · ' + ev.time : ''); }

  /* Die Herzen dieser Sitzung: die Schluessel der Serien, die David schon
     geherzt hat (GET /api/geherzt, eine Abfrage fuer die ganze Seite statt einer
     je Event). Im static-Modus bleibt die Menge leer und wird nie gefuellt -
     dort gibt es keinen Server, der sie kennte. */
  var heartedKeys = {};

  function loadHearts() {
    if (!CAN_HEART) { return Promise.resolve(); }
    return fetch('/api/geherzt').then(function (r) { return r.json(); }).then(function (data) {
      heartedKeys = {};
      (data.run_keys || []).forEach(function (k) { heartedKeys[k] = true; });
    }).catch(function () { /* Liste zeichnet dann eben ohne Markierung */ });
  }

  /* Der Herz-Knopf steckt in herzen.js und liegt nur auf der Flask-Seite. Von
     hier geht der Serien-Schluessel hinein, eine Zeigung der Serie (an ihr
     loest der Server auf, welche Zeilen dazugehoeren) und der Weg zurueck:
     nach dem Umschalten werden Liste und Empfehlungen neu gezeichnet, das
     offene Popup gleich mit. */
  function herzButton(ev) {
    var key = runKey(ev);
    return window.ddHerzButton(key, ev.uid, !!heartedKeys[key], function (data) {
      if (data.run_key) { heartedKeys[data.run_key] = !!data.an; }
      if (!data.an && data.run_key) { delete heartedKeys[data.run_key]; }
      refresh();
      if (currentModalEvent === ev) { renderModalFooter(); }
    });
  }

  /* Ziel der Venue-Seite (P5b/decision #4): "/orte/<slug>" unter Flask,
     "orte/<slug>.html" (relativ, Seite liegt im selben Verzeichnis wie
     index.html) im statischen Export - siehe tools/export_static.py.
     null, wenn das Event keine Venue hat oder die Venue ein Treffpunkt ist
     (venue_slug fehlt dann schon im Datensatz, siehe db.list_venues). */
  function venueHref(ev) {
    if (!ev.venue_slug) { return null; }
    var slug = encodeURIComponent(ev.venue_slug);
    return MODE === 'static' ? 'orte/' + slug + '.html' : '/orte/' + slug;
  }

  /* Cover-Fuellung fuer Liste UND Popup. Gibt es kein Bild, uebernimmt der
     Anfangsbuchstabe der Kategorie den Platz - so bleibt die Flaeche in beiden
     Faellen gleich gross und die Spalten der Liste bleiben buendig. */
  function fillCover(el, ev, baseClass) {
    if (ev.image_url) {
      el.className = baseClass;
      el.textContent = '';
      el.style.backgroundImage = 'url("' + ev.image_url + '")';
    } else {
      el.className = baseClass + ' placeholder';
      el.style.backgroundImage = '';
      el.textContent = (CAT_LABEL[ev.category] || ev.category || '?').charAt(0);
    }
  }

  function renderModalFooter() {
    var host = document.getElementById('modal-herz');
    host.innerHTML = '';
    if (CAN_HEART && currentModalEvent) { host.appendChild(herzButton(currentModalEvent)); }
  }

  function renderModal() {
    var ev = currentModalEvent;
    if (!ev) { return; }

    document.getElementById('modal-title').textContent = ev.title;
    document.getElementById('modal-datetime').textContent = whenLabel(ev);
    var venueEl = document.getElementById('modal-venue');
    venueEl.textContent = ev.venue || '';
    var vHref = venueHref(ev);
    if (vHref) { venueEl.href = vHref; } else { venueEl.removeAttribute('href'); }

    var pageLink = document.getElementById('modal-venue-page-link');
    if (vHref) { pageLink.href = vHref; pageLink.hidden = false; } else { pageLink.hidden = true; }

    var tags = document.getElementById('modal-tags');
    tags.innerHTML = '';
    var catTag = document.createElement('span');
    catTag.className = 'tag';
    catTag.textContent = CAT_LABEL[ev.category] || ev.category;
    tags.appendChild(catTag);
    (ev.tags || []).forEach(function (slug) {
      var chip = document.querySelector('.chip-tag[data-tag="' + slug + '"]');
      var span = document.createElement('span');
      span.className = 'tag';
      span.textContent = chip ? chip.textContent : slug;
      tags.appendChild(span);
    });
    if (ev.price_text) {
      var priceTag = document.createElement('span');
      priceTag.className = 'price-tag';
      priceTag.textContent = ev.price_text;
      tags.appendChild(priceTag);
    }

    var cover = document.getElementById('modal-cover');
    fillCover(cover, ev, 'modal-cover');

    var descEl = document.getElementById('modal-description');
    if (ev.description === undefined) {
      descEl.innerHTML = '<div class="loading">Lädt …</div>';
    } else {
      descEl.textContent = ev.description || 'Keine weitere Beschreibung verfügbar.';
    }

    var link = document.getElementById('modal-source-link');
    if (ev.url) { link.href = ev.url; link.hidden = false; } else { link.hidden = true; }

    renderModalFooter();
  }

  function openModal(ev) {
    currentModalEvent = ev;
    lastFocusedEl = document.activeElement;
    renderModal();
    overlayEl.hidden = false;
    document.body.style.overflow = 'hidden';
    modalEl.focus();

    // undefined = noch nie geladen. Rauze-Events bringen die Beschreibung schon
    // aus /api/events mit, beim Kulturkalender wird sie hier einmalig geholt.
    // Im static-Modus gibt es nichts nachzuladen: was der Exporter an
    // Beschreibung hatte, steckt in der Tagesdatei, alles andere bleibt leer.
    if (MODE === 'static') {
      if (ev.description === undefined) { ev.description = ''; renderModal(); }
      return;
    }
    if (ev.description === undefined) {
      fetch('/api/event/' + ev.uid + '/details')
        .then(function (r) { return r.json(); })
        .then(function (d) {
          ev.description = d.description || '';
          if (d.image_url) { ev.image_url = d.image_url; }
          if (d.price_text) { ev.price_text = d.price_text; }
          if (currentModalEvent === ev) { renderModal(); }
        })
        .catch(function () {
          ev.description = 'Details konnten gerade nicht geladen werden.';
          if (currentModalEvent === ev) { renderModal(); }
        });
    }
  }

  function closeModal() {
    overlayEl.hidden = true;
    document.body.style.overflow = '';
    currentModalEvent = null;
    if (lastFocusedEl) { lastFocusedEl.focus(); }
  }

  document.getElementById('modal-close').addEventListener('click', closeModal);
  overlayEl.addEventListener('click', function (e) {
    if (e.target === overlayEl) { closeModal(); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !overlayEl.hidden) { closeModal(); }
  });

  /* Gegenstueck zu /api/fuer-dich (scoring.top_picks): die bestbewerteten acht
     Events der naechsten sieben Tage. Der Score kommt fertig aus den
     Tagesdateien, gerechnet auf dem Pi - hier wird nur sortiert. */
  function staticPicks() {
    return staticEvents(weekDays(), selectedCats).then(function (events) {
      events.sort(function (a, b) { return b.score - a.score; });
      return { events: events.slice(0, 8) };
    });
  }

  /* Liste und Empfehlungszeile holen ihre Events auf demselben Weg: im
     api-Modus von Flask, im static-Modus aus den Tagesdateien. Nur wo genau,
     unterscheidet sich - deshalb steht die Fallunterscheidung hier einmal und
     nicht in beiden Ladefunktionen. */
  function fetchJson(url) {
    return fetch(url).then(function (r) { return r.json(); });
  }

  function eventSource(what) {
    if (MODE === 'static') {
      if (what === 'picks') { return staticPicks(); }
      return staticEvents([selectedDate], selectedCats).then(function (events) { return { events: events }; });
    }
    if (what === 'picks') {
      return fetchJson('/api/fuer-dich?cat=' + encodeURIComponent(catQuery()));
    }
    return fetchJson('/api/events?date=' + selectedDate + '&cat=' + encodeURIComponent(catQuery()));
  }

  function loadPicks() {
    eventSource('picks').then(function (data) {
      pickRow.innerHTML = '';
      var picks = data.events.filter(passesFilters);
      if (!picks.length) {
        pickRow.innerHTML = CAN_HEART
          ? '<div class="loading">Noch keine Empfehlungen – herze ein paar Events.</div>'
          : '<div class="loading">Gerade keine Empfehlungen für diese Auswahl.</div>';
        return;
      }
      picks.forEach(function (e) {
        var card = document.createElement('div');
        card.className = 'pick-card';
        card.innerHTML = '<div class="pick-score">' + (CAN_HEART ? 'Für dich' : 'Empfehlung') + '</div>' +
          '<div class="pick-title"></div><div class="pick-meta"></div>';
        card.querySelector('.pick-title').textContent = e.title;
        card.querySelector('.pick-meta').textContent = whenLabel(e);
        card.style.cursor = 'pointer';
        card.addEventListener('click', function () { openModal(e); });
        pickRow.appendChild(card);
      });
    });
  }

  /* Beschriftet die Marke - oder nimmt sie aus der Zeile, wenn es nichts zu
     sagen gibt. rowClass faerbt zusaetzlich die ganze Zeile ein. */
  function mark(row, selector, text, rowClass) {
    var el = row.querySelector(selector);
    if (!text) { el.remove(); return; }
    el.textContent = text;
    if (rowClass) { row.classList.add(rowClass); }
  }

  /* Lange Serien am selben Tag zu einer Zeile falten - reine Anzeigesache
     (P5x). Die Daten dahinter aendern sich nicht: /api/events und die
     Tagesdateien liefern weiter jede einzelne Zeigung, hier wird nur
     zusammengefasst, WAS gezeichnet wird - nie in der SQL, nie mit DISTINCT
     (ein Query-Cut wuerde vier von fuenf echten Domfuehrungen von der Seite
     tilgen, siehe P5w-Bericht).
     Schluessel: gleicher Tag (kommt schon aus byDay) UND gleicher Ort UND
     exakt derselbe normalisierte Titel - der Ort ist Pflicht, sonst wuerden
     zwei Haeuser mit derselben "Fuehrung" am selben Tag verschmelzen.
     Gemessen an 5026 Gewinner-Zeilen (duplicate_of IS NULL, heute..+45 Tage,
     [V] 2026-09-12): 4394 Einzeltermine, 154 Gruppen zu zweit, 21 zu dritt,
     32 zu viert, 22 zu fuenft, 3 mit 6 oder mehr (7 bzw. 8 - Tuerme/Dom zu
     Meissen). Jede der 78 Gruppen ab Groesse 3 ist im Bestand eine
     Fuehrung/Tour mit identischem Titel und mehreren Uhrzeiten am selben Tag
     (Domfuehrung Meissen 5x, Turmfuehrung 4-8x, Wein-Fuehrung Wackerbarth 3x
     ...) - keine einzige ist ein zufaelliges Zusammentreffen zweier
     verschiedener Termine. Ab Groesse 2 ist das Bild gemischt (u.a. echte
     Doppelvorstellungen im Kindertheater), deshalb bleibt es dort bei zwei
     Zeilen - David's eigene Worte: "mehr als zwei oder drei mal".
     RUN_MIN_SIZE ist damit aus der Verteilung gewaehlt, nicht geraten. */
  var RUN_MIN_SIZE = 3;

  /* Dieselbe Transliteration wie normalize.slugify() in Python (Kleinschrift,
     Umlaute, Diakritika, Rest zu Bindestrichen) - aber OHNE Wortfilter.
     dedup.py._title_tokens() wirft Woerter unter drei Zeichen weg und macht
     z.B. "S.Y.N.T.H.E.T.I.C S.I.G.N.A.L.S" zu gar nichts (siehe P5w-Bericht) -
     fuer die Gruppierung hier zaehlt der volle normalisierte Text, nicht
     einzelne Woerter, also bleibt so ein Titel vergleichbar. */
  function runSlug(text) {
    return (text || '').toLowerCase()
      .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
      .normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  }

  /* Tag, Ort UND Titel - siehe Kommentar oben, warum der Ort nicht optional
     ist. Der TAG ist mit P5c dazugekommen und aendert an der Gruppierung der
     Liste NICHTS: gruppiert wird ohnehin nur innerhalb eines Tages (byDay in
     loadList), alle Mitglieder einer Gruppe tragen also denselben Tag.
     Gebraucht wird er fuer die Herzen: dort ist der Schluessel keine
     Gruppierungshilfe mehr, sondern eine gespeicherte Identitaet, und die muss
     ueber Tage hinweg eindeutig sein - "die Domfuehrung am 20.09." statt
     "jede Domfuehrung, die es je geben wird" (siehe P5c-Bericht).
     Das Gegenstueck auf dem Server ist normalize.run_key(); tests_smoke.py
     haelt beide mit einem Differenztest zusammen. */
  function runKey(e) { return e.date + '|' + runSlug(e.venue) + '|' + runSlug(e.title); }

  /* Eine einzelne Zeile - unveraendertes Verhalten von vor P5x, nur aus der
     Schleife herausgezogen, damit buildRunRow() dieselben Bausteine nutzen
     kann. */
  function buildEventRow(e) {
    var row = document.createElement('article');
    row.className = 'event';
    row.innerHTML = '<div class="event-time"></div><div class="event-cover"></div><div class="event-body"><p class="event-title"></p><div class="event-meta"><a class="event-venue-link"></a><span class="tag"></span><span class="tag-pick"></span><span class="tag-ongoing"></span><span class="tag-region"></span><span class="price-tag"></span></div></div><div class="event-actions"></div>';
    row.querySelector('.event-time').textContent = e.time || '--:--';
    fillCover(row.querySelector('.event-cover'), e, 'event-cover');
    row.querySelector('.event-title').textContent = e.title;
    var venueLink = row.querySelector('.event-venue-link');
    venueLink.textContent = e.venue || '';
    // Event -> Venue-Seite (decision #4), NICHT Kulturkalender. Nur ein
    // echter Link, wenn die Venue eine Seite hat (kein Treffpunkt, siehe
    // venueHref) - sonst bleibt es ein reiner Text wie vorher.
    var rowVenueHref = venueHref(e);
    if (rowVenueHref) {
      venueLink.href = rowVenueHref;
      venueLink.addEventListener('click', function (evt) { evt.stopPropagation(); });
    }
    row.querySelector('.tag').textContent = CAT_LABEL[e.category] || e.category;
    /* Die vier Marken an der Zeile. Jede steht im Rohbau schon da und
       wird entweder beschriftet oder wieder entfernt - eine leere Marke
       wuerde als kleiner Kasten sichtbar bleiben.
         Dauerangebot: laeuft die Reihe an vielen Tagen (db.ONGOING_MIN_DAYS),
           wird sie eingefaerbt und beschriftet - Farbe allein waere nicht
           lesbar.
         Top-Treffer: passt das Event zum gelernten Geschmack, bekommt die
           Zeile denselben Auftritt in Elbe-Tuerkis. Der Score kommt aus
           scoring.score_events() - im api-Modus aus /api/events, im
           statischen Modus vorgerechnet aus der Tagesdatei.
         Umland/Weiter weg: steht nur an Eintraegen, die ohne den Schalter
           "Auch Umland & Umgebung" gar nicht in der Liste waeren (P5b/
           decision #12: Standard ist jetzt nur Dresden, siehe passesFilters).
         Preis: nur, wenn die Quelle einen mitgeliefert hat. */
    mark(row, '.tag-ongoing', e.ongoing && 'Dauerangebot', 'ongoing');
    mark(row, '.tag-pick', Number(e.score) >= HIGHLIGHT_SCORE && 'Top-Treffer', 'top-pick');
    mark(row, '.tag-region', e.region && e.region !== 'dresden'
      && (e.region === 'weiter' ? 'Weiter weg' : 'Umland'));
    mark(row, '.price-tag', e.price_text);
    var actions = row.querySelector('.event-actions');
    if (CAN_HEART) {
      actions.appendChild(herzButton(e));
      if (heartedKeys[runKey(e)]) { row.classList.add('is-hearted'); }
    }
    // Statt eines eigenen Buttons oeffnet ein Klick auf die Zeile das
    // Popup. Der Herz-Knopf rechts stoppt sein Event zwar selbst, aber
    // sicherheitshalber wird hier geprueft, ob der Klick aus .event-actions kam.
    row.setAttribute('role', 'button');
    row.setAttribute('tabindex', '0');
    row.setAttribute('aria-haspopup', 'dialog');
    row.addEventListener('click', function (evt) {
      if (evt.target.closest('.event-actions')) { return; }
      openModal(e);
    });
    row.addEventListener('keydown', function (evt) {
      if (evt.key === 'Enter' || evt.key === ' ') { evt.preventDefault(); openModal(e); }
    });
    return row;
  }

  /* Eine zusammengefasste Zeile fuer eine lange Serie (>= RUN_MIN_SIZE
     Zeigungen). Titel/Ort/Kategorie stehen EINMAL (sie sind bei allen
     Mitgliedern identisch, sonst waeren sie nicht gruppiert worden), aber
     JEDE Uhrzeit ist ein eigener Knopf - ein Klick oeffnet das Popup genau
     dieser Zeigung mit ihrer eigenen uid und ihrer eigenen Quelle
     (openModal(m), nicht openModal(first)). Damit bleibt jede einzelne
     Zeigung erreichbar, auch nach dem Zusammenfalten.
     Bewusst OHNE Zeilen-Klick (waere mehrdeutig, welche Zeigung gemeint ist),
     aber MIT Herz-Knopf: P5x hatte hier noch keinen, weil die damaligen
     Daumen-Buttons am einzelnen Showing-uid hingen und eine zusammengefasste
     Zeile keinen einzelnen Uid mehr hat. Genau diese Frage hat David mit
     Entscheidung #26 beantwortet: ein Herz auf einer zusammengefassten Zeile
     gilt der GANZEN Serie. Der Knopf schickt die uid der ersten Zeigung mit,
     der Server loest daraus den Serien-Schluessel auf - alle Mitglieder sind
     damit geherzt, und die Zeile gilt als geherzt, sobald es die Serie ist. */
  function buildRunRow(members) {
    var first = members[0];
    var row = document.createElement('article');
    row.className = 'event event-run';
    row.innerHTML = '<div class="event-time event-time-list"></div><div class="event-cover"></div><div class="event-body"><p class="event-title"></p><div class="event-meta"><a class="event-venue-link"></a><span class="tag"></span><span class="tag-pick"></span><span class="tag-ongoing"></span><span class="tag-region"></span><span class="tag-run"></span><span class="price-tag"></span></div></div><div class="event-actions"></div>';

    var timeList = row.querySelector('.event-time-list');
    members.forEach(function (m) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'event-time-btn';
      btn.textContent = m.time || '--:--';
      btn.setAttribute('aria-haspopup', 'dialog');
      btn.addEventListener('click', function (evt) { evt.stopPropagation(); openModal(m); });
      timeList.appendChild(btn);
    });

    fillCover(row.querySelector('.event-cover'), first, 'event-cover');
    row.querySelector('.event-title').textContent = first.title;
    var venueLink = row.querySelector('.event-venue-link');
    venueLink.textContent = first.venue || '';
    var rowVenueHref = venueHref(first);
    if (rowVenueHref) {
      venueLink.href = rowVenueHref;
      venueLink.addEventListener('click', function (evt) { evt.stopPropagation(); });
    }
    row.querySelector('.tag').textContent = CAT_LABEL[first.category] || first.category;
    // Score/Dauerangebot/Ort sind bei einer echten Serie an allen Mitgliedern
    // gleich (gleicher Titel -> gleiches "ongoing", gleicher Ort -> gleiche
    // Region) - nur beim Score wird sicherheitshalber das Maximum genommen,
    // falls ein spaeteres Lernmodell einzelne Zeigungen doch unterschiedlich
    // bewertet.
    var maxScore = Math.max.apply(null, members.map(function (m) { return Number(m.score) || 0; }));
    mark(row, '.tag-ongoing', first.ongoing && 'Dauerangebot', 'ongoing');
    mark(row, '.tag-pick', maxScore >= HIGHLIGHT_SCORE && 'Top-Treffer', 'top-pick');
    mark(row, '.tag-region', first.region && first.region !== 'dresden'
      && (first.region === 'weiter' ? 'Weiter weg' : 'Umland'));
    mark(row, '.tag-run', members.length + ' Termine');
    var price = members.map(function (m) { return m.price_text; }).filter(Boolean)[0];
    mark(row, '.price-tag', price);
    if (CAN_HEART) {
      row.querySelector('.event-actions').appendChild(herzButton(first));
      if (heartedKeys[runKey(first)]) { row.classList.add('is-hearted'); }
    }
    return row;
  }

  function loadList() {
    listEl.innerHTML = '<div class="loading">Lädt …</div>';
    eventSource('list').then(function (data) {
      listEl.innerHTML = '';
      var byDay = {};
      data.events.filter(passesFilters).forEach(function (e) { (byDay[e.date] = byDay[e.date] || []).push(e); });
      var days = Object.keys(byDay).sort();
      if (!days.length) {
        var hint = data.events.length ? ' – die aktiven Filter blenden alles aus.' : '.';
        listEl.innerHTML = '<div class="empty-state">Keine Veranstaltungen gefunden' + hint + '</div>';
        return;
      }

      days.forEach(function (day, gi) {
        var section = document.createElement('section');
        section.className = 'day-group';
        var d = new Date(day + 'T00:00:00');
        var heading = document.createElement('div');
        heading.className = 'day-heading';
        heading.innerHTML = '<span class="name"></span><span class="date"></span>';
        heading.querySelector('.name').textContent = d.toLocaleDateString('de-DE', { weekday: 'long' });
        heading.querySelector('.date').textContent = d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
        section.appendChild(heading);

        var list = document.createElement('div');
        list.className = 'day-events';
        // Serien vorab zaehlen (siehe RUN_MIN_SIZE oben). byDay[day] ist
        // schon chronologisch sortiert (Server-/Export-Sortierung nach
        // date, time) - eine Serie wird deshalb an der Stelle ihrer
        // fruehesten Zeigung gezeichnet, renderedKeys verhindert, dass sie
        // bei ihren spaeteren Zeigungen ein zweites Mal auftaucht. Einzelne
        // Termine und Zweiergruppen durchlaufen unveraendert buildEventRow -
        // ihre Reihenfolge in der Liste aendert sich nicht.
        var membersByKey = {};
        byDay[day].forEach(function (e) { (membersByKey[runKey(e)] = membersByKey[runKey(e)] || []).push(e); });
        var renderedKeys = {};
        byDay[day].forEach(function (e) {
          var key = runKey(e);
          var members = membersByKey[key];
          if (members.length >= RUN_MIN_SIZE) {
            if (renderedKeys[key]) { return; }
            renderedKeys[key] = true;
            list.appendChild(buildRunRow(members));
            return;
          }
          list.appendChild(buildEventRow(e));
        });
        section.appendChild(list);
        listEl.appendChild(section);
      });
    });
  }

  // Wert in einer Auswahl umschalten: drin -> raus, draussen -> rein.
  function toggleIn(list, value) {
    var i = list.indexOf(value);
    if (i === -1) { list.push(value); } else { list.splice(i, 1); }
  }

  function onClick(selector, handler) {
    document.querySelectorAll(selector).forEach(function (el) {
      el.addEventListener('click', function () { handler(el); });
    });
  }

  // Liste und Empfehlungen haengen an derselben Auswahl - was die eine aendert,
  // aendert immer auch die andere. Die Herzen kommen VOR dem Zeichnen, sonst
  // baute die Liste ihre Knoepfe aus einem veralteten Stand.
  function refresh() {
    return loadHearts().then(function () { loadList(); loadPicks(); });
  }

  function applySelection() {
    syncChips();
    saveSelection();
    refresh();
  }

  function applyFilters() {
    syncFilterChips();
    saveFilters();
    refresh();
  }

  // Eine Reihe mit den naechsten sieben Tagen deckt den haeufigen Fall in
  // einem Klick ab; ein kleiner Kalender-Knopf daneben bleibt fuer alles
  // ausserhalb dieses Fensters (zurueckliegende Tage, mehr als eine Woche
  // voraus) - siehe die Entscheidung im Chat, den Reiter-Ersatz so
  // aufzuteilen statt nur den Kalender zu behalten.
  var dateStripEl = document.getElementById('date-strip');
  var dateBtn = document.getElementById('date-btn');
  var datePanel = document.getElementById('date-panel');
  var STRIP_DAYS = 7;

  function stripDates() {
    var today = new Date(); today.setHours(0, 0, 0, 0);
    var out = [];
    for (var i = 0; i < STRIP_DAYS; i++) {
      var d = new Date(today); d.setDate(d.getDate() + i);
      out.push(d);
    }
    return out;
  }

  function buildDateStrip() {
    dateStripEl.innerHTML = '';
    stripDates().forEach(function (d) {
      var iso = isoDay(d);
      var pill = document.createElement('button');
      pill.className = 'date-pill';
      pill.type = 'button';
      pill.dataset.date = iso;
      pill.setAttribute('aria-pressed', 'false');
      // Kurzform in der Reihe ("Mo"), das volle Datum steht in Titel/ARIA-Label
      // fuer Tooltip und Screenreader - siehe die Entscheidung im Chat.
      pill.textContent = d.toLocaleDateString('de-DE', { weekday: 'short' }).replace(/\.$/, '');
      var full = d.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: 'long' });
      pill.title = full;
      pill.setAttribute('aria-label', full);
      pill.addEventListener('click', function () {
        setSelectedDate(this.dataset.date);
        loadList();
      });
      dateStripEl.appendChild(pill);
    });
  }

  // Ob der gewaehlte Tag ueberhaupt in der sichtbaren Reihe steckt - sonst
  // zeigt keine Kachel den aktiven Zustand, dafuer bekommt der Kalender-Knopf
  // eine eigene Markierung (siehe .date-btn.is-active in app.css).
  function inStrip(iso) {
    return stripDates().some(function (d) { return isoDay(d) === iso; });
  }

  function syncDateStrip() {
    press('.date-pill', function (pill) { return pill.dataset.date === selectedDate; });
    dateBtn.classList.toggle('is-active', !inStrip(selectedDate));
  }

  // Der flatpickr-Kalender fuehrt seine eigene Vorstellung vom gewaehlten Tag -
  // die muss mitziehen, auch wenn die Auswahl aus der Reihe kommt, sonst zeigt
  // ein spaeter geoeffneter Kalender noch den alten Stand.
  var fpInstance = null;

  function setSelectedDate(iso) {
    selectedDate = iso;
    syncDateStrip();
    if (fpInstance) { fpInstance.setDate(iso, false); }
  }

  buildDateStrip();

  if (window.flatpickr) {
    if (window.flatpickr.l10ns && window.flatpickr.l10ns.de) {
      window.flatpickr.localize(window.flatpickr.l10ns.de);
    }
    fpInstance = window.flatpickr('#date-calendar', {
      inline: true,
      defaultDate: selectedDate,
      onChange: function (dates, dateStr) {
        setSelectedDate(dateStr);
        datePanel.hidden = true;
        dateBtn.setAttribute('aria-expanded', 'false');
        loadList();
      }
    });
  }

  if (window.ddRegisterMenu) { window.ddRegisterMenu(datePanel, dateBtn); }

  onClick('.chip[data-cat]', function (chip) {
    if (chip.dataset.cat === 'alle') { selectedCats = []; }
    else { toggleIn(selectedCats, chip.dataset.cat); }
    applySelection();
  });

  onClick('.chip-toggle', function (chip) {
    filters[chip.dataset.toggle] = !filters[chip.dataset.toggle];
    applyFilters();
  });

  onClick('.chip-tag', function (chip) {
    toggleIn(filters.tags, chip.dataset.tag);
    applyFilters();
  });

  onClick('.chip-src', function (chip) {
    toggleIn(filters.sources, chip.dataset.src);
    applyFilters();
  });

  onClick('#chip-reset', function () {
    selectedCats = [];
    applySelection();
  });

  /* Suche ueber Titel und Ort (P5b) - filtert client-seitig innerhalb des
     bereits geladenen Zeitraums, genau wie die Sichtbarkeits-Schalter oben.
     Eine kleine Verzoegerung reicht, damit nicht jeder Tastenanschlag sofort
     neu rendert. */
  var searchInput = document.getElementById('search-input');
  var searchTimer = null;
  if (searchInput) {
    searchInput.addEventListener('input', function () {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(function () {
        searchQuery = searchInput.value.trim().toLowerCase();
        refresh();
      }, 150);
    });
  }

  // Das Filter-Menue haengt sich in dieselbe Menue-Verwaltung wie Theme- und
  // Animationsmenue (registerMenu im Block darueber): ein Klick daneben oder
  // Escape schliesst alles, und ein Klick INS Panel schliesst es nicht.
  var filterPanel = document.getElementById('filter-panel');
  var filterBtn = document.getElementById('filter-btn');
  if (window.ddRegisterMenu) { window.ddRegisterMenu(filterPanel, filterBtn); }

  /* Der Verlauf am rechten Rand der Kategorienzeile soll nur da sein, wenn es
     wirklich weitergeht - sonst sieht die letzte Kategorie auf breiten
     Bildschirmen grundlos ausgeblichen aus. */
  var chipsEl = document.querySelector('.chips');
  function syncChipFade() {
    var overflow = chipsEl.scrollWidth - chipsEl.clientWidth;
    chipsEl.classList.toggle('is-scrollable', overflow > 4 && chipsEl.scrollLeft < overflow - 4);
  }
  chipsEl.addEventListener('scroll', syncChipFade);
  window.addEventListener('resize', syncChipFade);

  selectedCats = loadSelection();
  loadFilters();
  syncChips();
  syncFilterChips();
  syncChipFade();
  setSelectedDate(selectedDate);
  refresh();
})();

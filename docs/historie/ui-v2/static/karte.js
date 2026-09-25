/* Die Kartenansicht. Zeigt dieselben Events wie die Liste, nur nach Ort
   sortiert statt nach Zeit.

   Bauart-Entscheidungen, die man der Datei sonst nicht ansieht:

   - EIN TAG. Die Karte haengt an genau einem Datum, wie die Liste seit dem
     Kalender-Umbau auch. 4873 kommende Events auf 460 Nadeln gleichzeitig
     waeren keine Karte, sondern ein Farbfleck.
   - NADELN SIND ORTE, NICHT EVENTS. Koordinaten haengen an der Venue (siehe
     migrations/002_venue_geo.sql), nicht am Event. Fuenf Termine im
     Zentralwerk sind eine Nadel mit einer Fuenf, keine fuenf uebereinander.
   - DIE SEITENLISTE IST PFLICHT, nicht Zierde. Auf dem Telefon ist eine Nadel
     ein Punkt von zwoelf Pixeln; ohne Liste daneben ist nicht lesbar, was
     dahintersteckt.
   - ORTE OHNE KOORDINATEN FEHLEN HIER UND STEHEN IN DER LISTE. Ein Treffpunkt
     wie "Terrassenufer Dresden" hat keine Hausnummer. Das wird unten offen
     benannt statt stillschweigend weggelassen - dieselbe Haltung wie
     'sonstiges' bei den Kategorien. */
(function () {
  var DD = window.DD;
  var MODE = DD.mode;
  var EXCLUDED = DD.excluded || [];
  var DATA_V = DD.dataVersion;

  var mapEl = document.getElementById('karte');
  var sideList = document.getElementById('karte-side-list');
  var sideHead = document.getElementById('karte-side-head');
  var noteEl = document.getElementById('karte-note');
  var stripEl = document.getElementById('date-strip');
  var umlandToggle = document.getElementById('umland-toggle');
  // Chip statt Checkbox: aria-pressed ist hier der Zustand, nicht .checked.
  var umland = false;

  var CAT_LABEL = {};
  (DD.categories || []).forEach(function (c) { CAT_LABEL[c.slug] = c.label; });

  var selectedDate = isoDay(new Date());
  var selectedCats = [];
  var geo = null;
  var markers = {};
  var map = null;
  var layer = null;

  function isoDay(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
      + '-' + String(d.getDate()).padStart(2, '0');
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // --- Daten -------------------------------------------------------------
  // Dieselben Quellen wie app.js, damit Liste und Karte nie auseinanderlaufen:
  // im api-Modus Flask, im static-Modus die vorgerechneten Tagesdateien.
  var staticIndexPromise = null;
  function staticIndex() {
    if (!staticIndexPromise) {
      staticIndexPromise = fetch('data/index.json?v=' + encodeURIComponent(DATA_V))
        .then(function (r) { return r.json(); });
    }
    return staticIndexPromise;
  }

  function loadEvents(day) {
    if (MODE === 'static') {
      return staticIndex().then(function (idx) {
        var hit = null;
        idx.days.forEach(function (d) { if (d.date === day) { hit = d; } });
        if (!hit) { return []; }
        return fetch('data/days/' + day + '.json?v=' + encodeURIComponent(hit.v))
          .then(function (r) { return r.ok ? r.json() : []; })
          .catch(function () { return []; });
      }).then(function (events) {
        return events.filter(function (e) {
          if (selectedCats.length) { return selectedCats.indexOf(e.category) !== -1; }
          return EXCLUDED.indexOf(e.category) === -1;
        });
      });
    }
    var cat = selectedCats.length ? selectedCats.join(',') : '';
    return fetch('/api/events?date=' + day + '&cat=' + encodeURIComponent(cat))
      .then(function (r) { return r.json(); })
      .then(function (data) { return data.events || []; });
  }

  function loadGeo() {
    return fetch(DD.urls.geo).then(function (r) { return r.json(); });
  }

  // --- Karte -------------------------------------------------------------
  function initMap() {
    map = L.map(mapEl, { zoomControl: true, scrollWheelZoom: true })
      .setView([51.0504, 13.7373], 12);
    /* Dunkle Kacheln, weil alle fuenf Themes dunkel sind - die
       Standard-OSM-Kacheln leuchten in so einer Oberflaeche wie eine
       Taschenlampe. Die Daten sind dieselben (OpenStreetMap), nur der Stil
       kommt von CARTO; beide Nennungen sind Bedingung der Nutzung. */
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      subdomains: 'abcd',
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende, &copy; <a href="https://carto.com/attributions">CARTO</a>'
    }).addTo(map);
    layer = L.layerGroup().addTo(map);
  }

  function pin(count, active) {
    // Groesse waechst mit der Anzahl, aber gedeckelt - sonst verdeckt der Dom
    // zu Meissen mit 300 Terminen die halbe Karte.
    var size = Math.min(44, 24 + String(count).length * 7);
    return L.divIcon({
      className: 'karte-pin' + (active ? ' is-active' : ''),
      html: '<span>' + count + '</span>',
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2]
    });
  }

  function groupByVenue(events) {
    var groups = {};
    events.forEach(function (e) {
      var slug = e.venue_slug;
      if (!slug || !geo[slug]) { return; }
      /* Region kommt vom EVENT, nicht von der Venue - dieselbe Regel wie in
         app.js Zeile 103, damit Liste und Karte bei gleichem Schalter
         dasselbe zeigen. Fehlendes region-Feld heisst Dresden (der Exporter
         laesst es dann weg, siehe feed.slim_event). */
      if (e.region && e.region !== 'dresden' && !umland) { return; }
      if (!groups[slug]) { groups[slug] = { venue: geo[slug], slug: slug, events: [] }; }
      groups[slug].events.push(e);
    });
    return groups;
  }

  function render(events) {
    var groups = groupByVenue(events);
    var slugs = Object.keys(groups);
    layer.clearLayers();
    markers = {};

    slugs.forEach(function (slug) {
      var g = groups[slug];
      var m = L.marker([g.venue.lat, g.venue.lon], { icon: pin(g.events.length, false) })
        .addTo(layer);
      m.on('click', function () { select(slug, groups); });
      markers[slug] = m;
    });

    // Auf die tatsaechlich belegten Orte zoomen statt auf eine feste
    // Stadtmitte - an einem ruhigen Dienstag liegt sonst die halbe Karte leer.
    if (slugs.length) {
      var bounds = L.latLngBounds(slugs.map(function (s) {
        return [groups[s].venue.lat, groups[s].venue.lon];
      }));
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
    }

    renderSide(groups, null);
    note(events, groups);
  }

  function select(slug, groups) {
    Object.keys(markers).forEach(function (s) {
      markers[s].setIcon(pin(groups[s].events.length, s === slug));
    });
    renderSide(groups, slug);
    var row = document.getElementById('ort-' + slug);
    if (row) { row.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
  }

  function renderSide(groups, activeSlug) {
    var slugs = Object.keys(groups).sort(function (a, b) {
      var d = groups[b].events.length - groups[a].events.length;
      return d !== 0 ? d : groups[a].venue.n.localeCompare(groups[b].venue.n, 'de');
    });
    sideHead.textContent = slugs.length
      ? slugs.length + (slugs.length === 1 ? ' Ort' : ' Orte') + ' mit Terminen'
      : 'Keine Orte mit Terminen';
    sideList.innerHTML = slugs.map(function (slug) {
      var g = groups[slug];
      var rows = g.events.slice(0, 6).map(function (e) {
        return '<li><span class="karte-time">' + esc(e.time || '–') + '</span> '
          + esc(e.title) + '</li>';
      }).join('');
      var more = g.events.length > 6
        ? '<li class="karte-more">… und ' + (g.events.length - 6) + ' weitere</li>' : '';
      return '<div class="karte-ort' + (slug === activeSlug ? ' is-active' : '')
        + '" id="ort-' + esc(slug) + '" data-slug="' + esc(slug) + '">'
        + '<div class="karte-ort-head"><strong>' + esc(g.venue.n) + '</strong>'
        + '<span class="karte-count">' + g.events.length + '</span></div>'
        + '<ul class="karte-ort-events">' + rows + more + '</ul>'
        + '<a class="karte-ort-link" href="' + esc(DD.urls.venue.replace('__slug__', slug))
        + '">zur Ortsseite</a></div>';
    }).join('');

    Array.prototype.forEach.call(sideList.querySelectorAll('.karte-ort'), function (el) {
      el.addEventListener('click', function (ev) {
        if (ev.target.closest('.karte-ort-link')) { return; }
        var slug = el.dataset.slug;
        select(slug, groups);
        map.panTo([groups[slug].venue.lat, groups[slug].venue.lon]);
      });
    });
  }

  function note(events, groups) {
    // Was die Karte NICHT zeigt, steht offen darunter - ein Ort ohne
    // Koordinaten verschwaende sonst kommentarlos.
    var placed = 0;
    Object.keys(groups).forEach(function (s) { placed += groups[s].events.length; });
    var missing = events.length - placed;
    var txt = placed + ' von ' + events.length + ' Terminen an diesem Tag sind verortet.';
    if (missing > 0) {
      txt += ' ' + missing + ' ohne bekannte Adresse (Treffpunkte, Online-Termine, '
        + 'Orte ausserhalb der Auswahl) stehen nur in der Eventliste.';
    }
    noteEl.textContent = txt;
  }

  // --- Bedienung ---------------------------------------------------------
  function buildStrip() {
    var today = new Date(); today.setHours(0, 0, 0, 0);
    stripEl.innerHTML = '';
    for (var i = 0; i < 7; i++) {
      var d = new Date(today); d.setDate(d.getDate() + i);
      var iso = isoDay(d);
      var b = document.createElement('button');
      b.className = 'date-pill';
      b.type = 'button';
      b.dataset.date = iso;
      b.textContent = d.toLocaleDateString('de-DE', { weekday: 'short' }).replace(/\.$/, '');
      b.title = d.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: 'long' });
      b.setAttribute('aria-pressed', iso === selectedDate ? 'true' : 'false');
      b.addEventListener('click', function (e) {
        selectedDate = e.currentTarget.dataset.date;
        Array.prototype.forEach.call(stripEl.children, function (c) {
          c.setAttribute('aria-pressed', c.dataset.date === selectedDate ? 'true' : 'false');
        });
        refresh();
      });
      stripEl.appendChild(b);
    }
  }

  function buildCats() {
    var panel = document.getElementById('cat-panel');
    var btn = document.getElementById('cat-btn');
    var row = document.getElementById('cat-row');
    var badge = document.getElementById('cat-badge');

    (DD.categories || []).forEach(function (c) {
      var chip = document.createElement('button');
      chip.className = 'chip';
      chip.type = 'button';
      chip.dataset.cat = c.slug;
      chip.textContent = c.label;
      chip.setAttribute('aria-pressed', 'false');
      chip.addEventListener('click', function () {
        var on = chip.getAttribute('aria-pressed') !== 'true';
        chip.setAttribute('aria-pressed', on ? 'true' : 'false');
        selectedCats = Array.prototype.map.call(
          row.querySelectorAll('[aria-pressed="true"]'),
          function (el) { return el.dataset.cat; });
        badge.hidden = selectedCats.length === 0;
        badge.textContent = selectedCats.length;
        refresh();
      });
      row.appendChild(chip);
    });

    umlandToggle.addEventListener('click', function () {
      umland = umlandToggle.getAttribute('aria-pressed') !== 'true';
      umlandToggle.setAttribute('aria-pressed', umland ? 'true' : 'false');
      refresh();
    });

    // Die gemeinsame Klappmenue-Mechanik aus chrome.js mitbenutzen.
    if (window.ddRegisterMenu) { window.ddRegisterMenu(panel, btn); }
  }

  function refresh() {
    sideHead.textContent = 'Lädt …';
    loadEvents(selectedDate).then(render);
  }

  loadGeo().then(function (data) {
    geo = data;
    initMap();
    buildStrip();
    buildCats();
    refresh();
  }).catch(function (e) {
    sideHead.textContent = 'Karte konnte nicht geladen werden.';
    noteEl.textContent = String(e);
  });
})();

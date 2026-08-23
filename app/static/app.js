/* Bedienung der Seite: Aussehen (Theme, Hintergrund-Animation), Filter, Liste,
   Empfehlungszeile und Detail-Popup. Alles, was von Konfiguration abhaengt,
   kommt aus window.DD - gesetzt im Kopf der Vorlage (app/templates/index.html),
   sonst weiss diese Datei nichts von Jinja. */
(function () {
  var DD = window.DD;
  document.getElementById('today-label').textContent = new Date().toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' });

  // Aussehen: Farbschema und Hintergrund-Animation. Das Theme-Attribut steht
  // schon vor dem Stylesheet (Inline-Skript im <head>), hier werden nur die
  // beiden Menues gebaut und die Wahl persistiert. Jedes Theme bringt eine
  // Signatur-Animation mit; das Animationsmenue kann sie ueberstimmen.
  /* Im Privatmodus wirft schon der Zugriff auf localStorage. Statt das an
     jedem der sechs Lese- und Schreibpunkte einzeln abzufangen, steht es hier
     einmal: gelesen wird dann eben der Standardwert, geschrieben nichts. */
  function stored(key, fallback) {
    try { var raw = window.localStorage.getItem('dd-was-geht.' + key); return raw === null ? fallback : raw; }
    catch (e) { return fallback; }
  }
  function store(key, value) {
    try { window.localStorage.setItem('dd-was-geht.' + key, value); } catch (e) { /* s.o. */ }
  }
  // Schaltzustand fuer eine Gruppe gleichartiger Knoepfe (Chips, Farbpunkte,
  // Animationsliste) - alle melden ihn ueber aria-pressed.
  function press(nodes, isOn) {
    document.querySelectorAll(nodes).forEach(function (el) {
      el.setAttribute('aria-pressed', isOn(el) ? 'true' : 'false');
    });
  }

  var THEMES = [
    { key: 'elbe',      label: 'Elbe Dunkel',   swatch: '#4fc3ba', bg: '#14181a', anim: 'konstellation' },
    { key: 'dvb',       label: 'Dresden Gelb',  swatch: '#ffd400', bg: '#15140e', anim: 'wirbel' },
    { key: 'anthropic', label: 'Anthropic',     swatch: '#da7756', bg: '#1a1915', anim: 'nebel' },
    { key: 'semper',    label: 'Semperoper',    swatch: '#c9a227', bg: '#17111c', anim: 'staub' },
    { key: 'neustadt',  label: 'Neustadt Neon', swatch: '#ff3d8b', bg: '#0e0e12', anim: 'puls' }
  ];
  var ANIMS = [
    { key: 'auto',          label: 'Automatisch (zum Thema)' },
    { key: 'konstellation', label: 'Konstellation' },
    { key: 'wirbel',        label: 'Wirbel' },
    { key: 'nebel',         label: 'Nebel' },
    { key: 'staub',         label: 'Staub' },
    { key: 'puls',          label: 'Puls' },
    { key: 'zufall',        label: 'Zufall (bei jedem Laden)' },
    { key: 'aus',           label: 'Aus' }
  ];

  var themeBtn = document.getElementById('theme-btn');
  var themeMenu = document.getElementById('theme-menu');
  var bgBtn = document.getElementById('bg-btn');
  var bgMenu = document.getElementById('bg-menu');

  function themeByKey(key) {
    for (var i = 0; i < THEMES.length; i++) { if (THEMES[i].key === key) { return THEMES[i]; } }
    return THEMES[0];
  }

  function bgPref() { return stored('bg', 'auto') || 'auto'; }

  // Setzt data-bg auf die tatsaechlich zu zeichnende Animation und meldet die
  // Aenderung; das Hintergrund-Skript haengt an genau diesem Event.
  function applyAppearance() {
    var pref = bgPref();
    var active = themeByKey(document.documentElement.dataset.theme);
    document.documentElement.dataset.bg = pref === 'auto' ? active.anim : pref;
    syncThemeDots();
    syncBgOpts();
    window.dispatchEvent(new CustomEvent('dt-appearance-change'));
  }

  function setTheme(key) {
    document.documentElement.dataset.theme = key;
    store('theme', key);
    applyAppearance();
  }

  function setBg(key) {
    store('bg', key);
    applyAppearance();
  }

  function syncThemeDots() {
    var active = document.documentElement.dataset.theme;
    press('#theme-menu .theme-dot', function (dot) { return dot.dataset.theme === active; });
  }

  function syncBgOpts() {
    var pref = bgPref();
    press('#bg-menu .bg-opt', function (opt) { return opt.dataset.anim === pref; });
  }

  THEMES.forEach(function (t) {
    var dot = document.createElement('button');
    dot.className = 'theme-dot';
    dot.dataset.theme = t.key;
    dot.title = t.label;
    dot.style.background = 'linear-gradient(135deg,' + t.swatch + ' 50%,' + t.bg + ' 50%)';
    dot.innerHTML = '<span class="sr-only"></span>';
    dot.querySelector('.sr-only').textContent = t.label;
    dot.addEventListener('click', function () { setTheme(t.key); closeMenus(); });
    themeMenu.appendChild(dot);
  });

  ANIMS.forEach(function (a) {
    var opt = document.createElement('button');
    opt.className = 'bg-opt';
    opt.dataset.anim = a.key;
    opt.textContent = a.label;
    opt.addEventListener('click', function () { setBg(a.key); closeMenus(); });
    bgMenu.appendChild(opt);
  });

  /* Alle Klappmenues der Seite haengen an derselben Liste: Theme, Animation und
     - aus dem zweiten Skriptblock heraus angemeldet - das Filter-Menue. So gibt
     es nur EINEN Klick-daneben- und Escape-Handler, und ein neu geoeffnetes
     Menue schliesst die anderen automatisch. */
  var MENUS = [];

  function registerMenu(menu, btn) {
    MENUS.push({ menu: menu, btn: btn });
    btn.addEventListener('click', function (e) { e.stopPropagation(); toggleMenu(menu, btn); });
    menu.addEventListener('click', function (e) { e.stopPropagation(); });
  }

  function closeMenus() {
    MENUS.forEach(function (m) {
      m.menu.hidden = true;
      m.btn.setAttribute('aria-expanded', 'false');
    });
  }

  function toggleMenu(menu, btn) {
    var wasOpen = !menu.hidden;
    closeMenus();
    if (!wasOpen) { menu.hidden = false; btn.setAttribute('aria-expanded', 'true'); }
  }

  registerMenu(themeMenu, themeBtn);
  registerMenu(bgMenu, bgBtn);
  // Der Filterblock laeuft in einer eigenen IIFE und meldet sein Panel hier an.
  window.ddRegisterMenu = registerMenu;
  document.addEventListener('click', function () { closeMenus(); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closeMenus(); }
  });

  applyAppearance();

  var CAT_LABEL = DD.categories;

  var listEl = document.getElementById('list');
  var pickRow = document.getElementById('fuer-dich-row');
  var currentRange = 'heute';
  var selectedCats = [];  // leer = "Alle" (ohne die per EXCLUDED_CATEGORIES ausgeblendeten)

  // Sichtbarkeits-Schalter. Anders als die Kategorien laufen die NICHT gegen die
  // API: /api/events liefert ongoing, source und score ohnehin mit, deshalb wird
  // hier nach dem Laden gefiltert statt neu geholt.
  var SRC_LABEL = DD.sources;
  // Unter dieser Schwelle gilt ein Event als "wenig relevant" - dieselbe Zahl,
  // die frueher als Prozentwert an jeder Zeile stand.
  var LOW_SCORE = 40;
  // Gegenstueck nach oben (config.HIGHLIGHT_SCORE): ab hier wird die Zeile als
  // Treffer hervorgehoben. Kommt aus der .env, damit die Schwelle mitwachsen
  // kann, waehrend das Lernmodell noch wenig Bewertungen kennt.
  var HIGHLIGHT_SCORE = DD.highlightScore;
  /* umgebung=false ist der Standard: gezeigt wird Dresden samt Speckguertel
     (Radebeul, Freital, Pirna, Moritzburg ...). Was weiter weg liegt - Meissen,
     Saechsische Schweiz, Lausitz, Leipzig - traegt region='weiter' (siehe
     app/geo.py) und kommt erst mit dem Schalter dazu. */
  var filters = { ongoing: false, lowscore: false, umgebung: false, sources: Object.keys(SRC_LABEL) };

  function loadFilters() {
    try {
      var saved = JSON.parse(stored('filters', '') || 'null');
      if (!saved) { return; }
      filters.ongoing = !!saved.ongoing;
      filters.lowscore = !!saved.lowscore;
      filters.umgebung = !!saved.umgebung;
      if (Array.isArray(saved.sources)) {
        filters.sources = saved.sources.filter(function (s) { return s in SRC_LABEL; });
      }
    } catch (e) { /* kaputter Eintrag - Standardwerte bleiben */ }
  }

  function saveFilters() { store('filters', JSON.stringify(filters)); }

  function syncFilterChips() {
    press('.chip-toggle', function (chip) { return filters[chip.dataset.toggle]; });
    press('.chip-src', function (chip) { return filters.sources.indexOf(chip.dataset.src) !== -1; });
    syncFilterBadge();
  }

  /* Zaehlt, was vom Standard abweicht - zugeklappt sieht man dem Menue sonst
     nicht an, dass es gerade etwas ausblendet. Die beiden Schalter zaehlen im
     EIN-Zustand, weil sie standardmaessig aus sind; bei den Quellen zaehlt jede
     abgewaehlte. */
  function syncFilterBadge() {
    var badge = document.getElementById('filter-badge');
    var n = (filters.ongoing ? 1 : 0) + (filters.lowscore ? 1 : 0)
      + (filters.umgebung ? 1 : 0)
      + (Object.keys(SRC_LABEL).length - filters.sources.length);
    badge.textContent = n;
    badge.hidden = n === 0;
  }

  function passesFilters(e) {
    if (e.ongoing && !filters.ongoing) { return false; }
    // Nur "weiter" filtert hier aus - Dresden und Umland bleiben sichtbar.
    if (e.region === 'weiter' && !filters.umgebung) { return false; }
    if (!filters.lowscore && Number(e.score) < LOW_SCORE) { return false; }
    // Eine unbekannte Quelle (neuer Scraper, noch kein Label) bleibt sichtbar -
    // sonst verschwaende sie kommentarlos aus der Liste.
    if (e.source in SRC_LABEL && filters.sources.indexOf(e.source) === -1) { return false; }
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

  /* Bewerten steckt in rating.js und liegt nur auf der Flask-Seite. Von hier
     geht das Event hinein und der Weg zurueck: nach dem Speichern werden Liste
     und Empfehlungen neu gezeichnet, das offene Popup gleich mit. */
  function fbButtons(ev) {
    return window.ddFeedbackButtons(ev, function (rated) {
      refresh();
      if (currentModalEvent === rated) { renderModalFooter(); }
    });
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
    var host = document.getElementById('modal-fb');
    host.innerHTML = '';
    host.appendChild(fbButtons(currentModalEvent));
  }

  function renderModal() {
    var ev = currentModalEvent;
    if (!ev) { return; }

    document.getElementById('modal-title').textContent = ev.title;
    document.getElementById('modal-datetime').textContent = whenLabel(ev);
    document.getElementById('modal-venue').textContent = ev.venue || '';

    var tags = document.getElementById('modal-tags');
    tags.innerHTML = '';
    var catTag = document.createElement('span');
    catTag.className = 'tag';
    catTag.textContent = CAT_LABEL[ev.category] || ev.category;
    tags.appendChild(catTag);
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

  function fetchJson(url) {
    return fetch(url).then(function (r) { return r.json(); });
  }

  function eventSource(what) {
    return fetchJson(what === 'picks'
      ? '/api/fuer-dich?cat=' + encodeURIComponent(catQuery())
      : '/api/events?range=' + currentRange + '&cat=' + encodeURIComponent(catQuery()));
  }

  function loadPicks() {
    eventSource('picks').then(function (data) {
      pickRow.innerHTML = '';
      var picks = data.events.filter(passesFilters);
      if (!picks.length) {
        pickRow.innerHTML = '<div class="loading">Noch keine Empfehlungen – bewerte ein paar Events.</div>';
        return;
      }
      picks.forEach(function (e) {
        var card = document.createElement('div');
        card.className = 'pick-card';
        card.innerHTML = '<div class="pick-score">Für dich</div>' +
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
        byDay[day].forEach(function (e) {
          var row = document.createElement('article');
          row.className = 'event';
          row.innerHTML = '<div class="event-time"></div><div class="event-cover"></div><div class="event-body"><p class="event-title"></p><div class="event-meta"><span></span><span class="tag"></span><span class="tag-pick"></span><span class="tag-ongoing"></span><span class="tag-region"></span><span class="price-tag"></span></div></div><div class="event-actions"></div>';
          row.querySelector('.event-time').textContent = e.time || '--:--';
          fillCover(row.querySelector('.event-cover'), e, 'event-cover');
          row.querySelector('.event-title').textContent = e.title;
          row.querySelector('.event-meta span:first-child').textContent = e.venue || '';
          row.querySelector('.tag').textContent = CAT_LABEL[e.category] || e.category;
          /* Die vier Marken an der Zeile. Jede steht im Rohbau schon da und
             wird entweder beschriftet oder wieder entfernt - eine leere Marke
             wuerde als kleiner Kasten sichtbar bleiben.
               Dauerangebot: laeuft die Reihe an vielen Tagen (db.ONGOING_MIN_DAYS),
                 wird sie eingefaerbt und beschriftet - Farbe allein waere nicht
                 lesbar.
               Top-Treffer: passt das Event zum gelernten Geschmack, bekommt die
                 Zeile denselben Auftritt in Elbe-Tuerkis. Der Score kommt aus
                 scoring.score_events() über /api/events.
               Umgebung: steht nur an Eintraegen, die ohne den Schalter gar nicht
                 in der Liste waeren (siehe passesFilters).
               Preis: nur, wenn die Quelle einen mitgeliefert hat. */
          mark(row, '.tag-ongoing', e.ongoing && 'Dauerangebot', 'ongoing');
          mark(row, '.tag-pick', Number(e.score) >= HIGHLIGHT_SCORE && 'Top-Treffer', 'top-pick');
          mark(row, '.tag-region', e.region === 'weiter' && 'Umgebung');
          mark(row, '.price-tag', e.price_text);
          var actions = row.querySelector('.event-actions');
          actions.appendChild(fbButtons(e));
          // Statt eines eigenen Buttons oeffnet ein Klick auf die Zeile das
          // Popup. Die Daumen-Buttons rechts stoppen ihr Event selbst nicht,
          // deshalb hier pruefen, ob der Klick aus .event-actions kam.
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
          list.appendChild(row);
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
  // aendert immer auch die andere.
  function refresh() { loadList(); loadPicks(); }

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

  // Die Reiter melden ihren Zustand als aria-selected, nicht als aria-pressed:
  // eine Auswahl aus dreien, kein Schalter. Deshalb nicht ueber press().
  onClick('.tab', function (tab) {
    document.querySelectorAll('.tab').forEach(function (other) {
      other.setAttribute('aria-selected', other === tab ? 'true' : 'false');
    });
    currentRange = tab.dataset.range;
    loadList();
  });

  onClick('.chip[data-cat]', function (chip) {
    if (chip.dataset.cat === 'alle') { selectedCats = []; }
    else { toggleIn(selectedCats, chip.dataset.cat); }
    applySelection();
  });

  onClick('.chip-toggle', function (chip) {
    filters[chip.dataset.toggle] = !filters[chip.dataset.toggle];
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
  loadPicks();
  loadList();
})();

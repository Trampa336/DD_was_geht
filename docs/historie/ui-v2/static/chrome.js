/* Gemeinsame Bedienelemente aller Seiten: Datumszeile im Kopf, Farbschema,
   Hintergrund-Animation und die Klappmenue-Mechanik dahinter.

   Bis zur Kartenansicht stand das oben in app.js. Getrennt ist es, weil es
   seither vier Seiten gibt (Start, Liste, Karte, Orte) und nur eine davon die
   Liste ist - app.js komplett zu laden, nur damit der Theme-Knopf geht, hiesse
   auf der Startseite ueber fehlende Listen-Elemente zu stolpern.

   Wer ein eigenes Klappmenue hat, meldet es ueber window.ddRegisterMenu an -
   so gibt es weiterhin nur EINEN Klick-daneben- und Escape-Handler. */
(function () {
  var DD = window.DD || {};
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
    { key: 'industriegelaende', label: 'Industriegelände', swatch: '#d4652a', bg: '#17191a', anim: 'nebel' },
    { key: 'elbe',              label: 'Elbe Dunkel',      swatch: '#4fc3ba', bg: '#14181a', anim: 'konstellation' },
    { key: 'neustadt',          label: 'Neustadt Neon',    swatch: '#ff3d8b', bg: '#0e0e12', anim: 'wirbel' },
    { key: 'pappel',            label: 'Pappel',           swatch: '#7fb349', bg: '#12180f', anim: 'staub' },
    { key: 'prohlis',           label: 'Prohlis',          swatch: '#4fa8d8', bg: '#16181c', anim: 'puls' }
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

  /* Alle Klappmenues der Seite haengen an derselben Liste: Animation und
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
})();

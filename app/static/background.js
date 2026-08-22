/* Lebendiger Hintergrund. Jedes der fuenf Themes bringt genau eine
   Signatur-Animation mit, ueber das zweite Menue im Masthead laesst sie sich
   auf eine der anderen vier umstellen. Welche gerade laeuft, steht in data-bg
   am <html>-Element; die Farben kommen wie bisher aus den CSS-Variablen und
   folgen dem Theme deshalb automatisch. */
(function () {
  var canvas = document.getElementById('bg-canvas');
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext('2d');
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');

  var W = 0, H = 0, dpr = 1;
  var parts = [];
  var rings = [];
  var pointer = { x: -9999, y: -9999, active: false, burst: -9999, down: false };
  /* Die Scrollposition ist eine zweite Eingabe neben dem Zeiger: y laeuft der
     echten Position weich hinterher, v ist das dabei entstehende Tempo und
     klingt von selbst wieder ab. Flaechige Motive rechnen y in ihre
     Weltkoordinate (lueckenlos, anders als ein globales translate),
     Teilchenmodi nehmen v als kurzen Luftzug. */
  var scroll = { y: 0, target: 0, v: 0 };
  var accent = '31,111,107', muted = '139,126,104', bgRgb = '20,24,26';
  var raf = null, tick = 0, mode = 'konstellation';
  // 'zufall' wuerfelt genau einmal pro Seitenaufruf - sonst wechselte die
  // Animation bei jedem Theme-Klick.
  var diceRoll = null;

  function hexToRgb(hex) {
    hex = (hex || '').trim();
    var m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex);
    if (!m) {
      var n = /rgba?\(([^)]+)\)/i.exec(hex);
      if (n) return n[1].split(',').slice(0, 3).map(function (v) { return parseInt(v, 10); }).join(',');
      return null;
    }
    var h = m[1];
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var i = parseInt(h, 16);
    return [(i >> 16) & 255, (i >> 8) & 255, i & 255].join(',');
  }

  function readColors() {
    var cs = getComputedStyle(document.documentElement);
    accent = hexToRgb(cs.getPropertyValue('--elbe')) || accent;
    muted = hexToRgb(cs.getPropertyValue('--stone-dark')) || muted;
    bgRgb = hexToRgb(cs.getPropertyValue('--bg')) || bgRgb;
    puffs = {};
  }

  function rand(a, b) { return a + Math.random() * (b - a); }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

  // Einmal-Ausloeser: verbraucht den Klick, damit ein einzelner Tap auch bei
  // uebersprungenen Bildern genau eine Explosion ergibt - nicht mehrere.
  function takeBurst() {
    if (pointer.burst === -9999 || tick < pointer.burst) return false;
    pointer.burst = -9999;
    return true;
  }

  /* Ein weicher Lichtfleck, einmal je Farbe auf eine kleine Hilfsflaeche
     gezeichnet. Das Aufstempeln kostet dann nur noch eine Bildkopie statt
     eines frisch gebauten Farbverlaufs. */
  var puffs = {};
  var PUFF = 128;
  function puffPatch(rgb) {
    if (puffs[rgb]) return puffs[rgb];
    var c = document.createElement('canvas');
    c.width = c.height = PUFF * 2;
    var g2 = c.getContext('2d');
    var g = g2.createRadialGradient(PUFF, PUFF, 0, PUFF, PUFF, PUFF);
    g.addColorStop(0, 'rgba(' + rgb + ',0.16)');
    g.addColorStop(1, 'rgba(' + rgb + ',0)');
    g2.fillStyle = g;
    g2.fillRect(0, 0, PUFF * 2, PUFF * 2);
    puffs[rgb] = c;
    return c;
  }
  function stampPuff(rgb, x, y, r) {
    ctx.drawImage(puffPatch(rgb), x - r, y - r, r * 2, r * 2);
  }

  /* --- Bausteine, die sich mehrere Modi teilen ----------------------------
     Die Animationen sind Abwandlungen derselben Handgriffe: driften und am
     Rand umlaufen, nahe Teilchen verbinden, Punkte setzen, Ringe ausbreiten
     lassen. Die stehen hier einmal und werden mit Zahlen parametriert - was
     einen Modus ausmacht, sind genau diese Zahlen. */

  // Driften und am Rand wieder hereinkommen. drag = wie stark das Scrolltempo
  // mitzieht, m = wie weit ein Teilchen hinauslaufen darf, bevor es umschlaegt.
  function drift(p, drag, m) {
    p.x += p.vx; p.y += p.vy - scroll.v * drag;
    if (p.x < -m) p.x = W + m; else if (p.x > W + m) p.x = -m;
    if (p.y < -m) p.y = H + m; else if (p.y > H + m) p.y = -m;
  }

  // Striche zwischen allen Teilchen, die naeher als dist beieinander liegen;
  // je naeher, desto kraeftiger.
  function links(rgb, dist, alpha) {
    for (var i = 0; i < parts.length; i++) {
      var a = parts[i];
      for (var j = i + 1; j < parts.length; j++) {
        var b = parts[j];
        var dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
        if (d2 > dist * dist) continue;
        var t = 1 - Math.sqrt(d2) / dist;
        ctx.strokeStyle = 'rgba(' + rgb + ',' + (t * alpha).toFixed(3) + ')';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
    }
  }

  // Jedes Teilchen einzeln gefuellt (nicht in einem Pfad): wo zwei Punkte sich
  // ueberlappen, deckt das doppelt - genau so sieht die Konstellation aus.
  function soloDots(alpha) {
    ctx.fillStyle = 'rgba(' + accent + ',' + alpha + ')';
    for (var i = 0; i < parts.length; i++) {
      ctx.beginPath(); ctx.arc(parts[i].x, parts[i].y, parts[i].r, 0, Math.PI * 2); ctx.fill();
    }
  }

  // Ringe, die groesser werden und dabei verblassen; wer durch ist, fliegt raus.
  function ripples(rgb, grow, span, alpha, width) {
    for (var i = rings.length - 1; i >= 0; i--) {
      var ring = rings[i];
      ring.r += grow;
      var f = 1 - ring.r / span;
      if (f <= 0) { rings.splice(i, 1); continue; }
      ctx.strokeStyle = 'rgba(' + rgb + ',' + (f * alpha).toFixed(3) + ')';
      ctx.lineWidth = width;
      ctx.beginPath();
      ctx.arc(ring.x, ring.y, ring.r, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  /* Jede Animation beschreibt, wie viele Teilchen sie fuer die Flaeche braucht,
     wie ein Teilchen aussieht (make), wie es sich pro Bild bewegt (step) und wie
     das Gesamtbild gezeichnet wird (draw). Gefahren werden alle von derselben
     Schleife weiter unten (loop/step/draw). */
  var MODES = {

    /* Elbe Dunkel: driftende Punkte, die sich zu Linien verbinden - die
       urspruengliche Animation, unveraendert. */
    konstellation: {
      count: function () { return clamp(Math.round(W * H / 15000), 24, 110); },
      make: function () {
        return { x: rand(0, W), y: rand(0, H), vx: rand(-0.12, 0.12), vy: rand(-0.12, 0.12), r: rand(0.9, 2.4) };
      },
      step: function (p) { drift(p, 0.22, 20); },
      draw: function () {
        var POINTER = 168;
        links(muted, 132, 0.26);
        // Dazu die Faeden zum Zeiger - nur diese Animation hat sie.
        if (pointer.active) {
          for (var i = 0; i < parts.length; i++) {
            var p = parts[i], px = p.x - pointer.x, py = p.y - pointer.y;
            var pd = Math.sqrt(px * px + py * py);
            if (pd > POINTER) continue;
            ctx.strokeStyle = 'rgba(' + accent + ',' + ((1 - pd / POINTER) * 0.45).toFixed(3) + ')';
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(pointer.x, pointer.y); ctx.stroke();
          }
        }
        soloDots(0.5);
      }
    },

    /* Dresden Gelb: ein weiches Stroemungsfeld. Zwei ueberlagerte Sinuswellen
       ergeben Wirbel, durch die die Teilchen gleiten und dabei geschwungene
       Baender hinterlassen. Am Cursor bekommt die Stroemung einen Drall. */
    wirbel: {
      count: function () { return clamp(Math.round(W * H / 26000), 12, 44); },
      make: function () {
        var x = rand(0, W), y = rand(0, H);
        return { x: x, y: y, sp: rand(0.5, 1.35), age: rand(0, 260), life: rand(260, 760), trail: [{ x: x, y: y }] };
      },
      step: function (p) {
        var t = tick * 0.0016;
        var ang = Math.sin(p.y * 0.0075 + t) * 1.6 + Math.cos(p.x * 0.0061 - t * 1.3) * 1.6;
        var vx = Math.cos(ang) * p.sp, vy = Math.sin(ang) * p.sp;

        // Nahe am Cursor kommt eine tangentiale Komponente dazu - die
        // Stroemung dreht sich um den Zeiger, statt ihn nur zu streifen.
        if (pointer.active) {
          var dx = p.x - pointer.x, dy = p.y - pointer.y;
          var d = Math.sqrt(dx * dx + dy * dy);
          if (d < 190 && d > 1) {
            var pull = (1 - d / 190) * 0.9;
            vx += (-dy / d) * pull; vy += (dx / d) * pull;
          }
        }

        p.x += vx; p.y += vy - scroll.v * 0.25;
        p.age++;
        p.trail.push({ x: p.x, y: p.y });
        if (p.trail.length > 16) p.trail.shift();

        // Beim Neusetzen muss der Schweif mit weg, sonst zieht sich eine
        // gerade Linie quer ueber die Seite.
        if (p.age > p.life || p.x < -30 || p.x > W + 30 || p.y < -30 || p.y > H + 30) {
          p.x = rand(0, W); p.y = rand(0, H);
          p.age = 0; p.life = rand(260, 760);
          p.trail = [{ x: p.x, y: p.y }];
        }
      },
      draw: function () {
        // Der Schweif war frueher ein Strich je Segment (16 Zeichenaufrufe pro
        // Teilchen). Jetzt sind es zwei Pfade fuer den ganzen Schwarm: die
        // blasse hintere Haelfte und die kraeftigere vordere.
        var i, j, p, tr, half;
        ctx.lineCap = 'round';
        for (var pass = 0; pass < 2; pass++) {
          ctx.strokeStyle = 'rgba(' + accent + ',' + (pass ? 0.26 : 0.1) + ')';
          ctx.lineWidth = pass ? 1.5 : 0.7;
          ctx.beginPath();
          for (i = 0; i < parts.length; i++) {
            tr = parts[i].trail;
            half = tr.length >> 1;
            var from = pass ? half : 0, to = pass ? tr.length : half + 1;
            for (j = from + 1; j < to; j++) {
              ctx.moveTo(tr[j - 1].x, tr[j - 1].y);
              ctx.lineTo(tr[j].x, tr[j].y);
            }
          }
          ctx.stroke();
        }
        ctx.fillStyle = 'rgba(' + accent + ',0.6)';
        ctx.beginPath();
        for (i = 0; i < parts.length; i++) {
          p = parts[i];
          ctx.moveTo(p.x + 1.5, p.y);
          ctx.arc(p.x, p.y, 1.5, 0, Math.PI * 2);
        }
        ctx.fill();
        ctx.lineCap = 'butt';
      }
    },

    /* Anthropic: wenige grosse, weiche Schleier, die langsam durchs Bild
       wandern. Keine Linien, keine Punkte - nur Licht. */
    nebel: {
      count: function () { return clamp(Math.round(W * H / 130000), 4, 9); },
      make: function () {
        return {
          x: rand(0, W), y: rand(0, H), vx: rand(-0.09, 0.09), vy: rand(-0.07, 0.07),
          r: rand(90, 230), warm: Math.random() < 0.4
        };
      },
      step: function (p) { drift(p, 0.12, p.r); },
      draw: function () {
        // Frueher entstand pro Schleier und Bild ein neuer Farbverlauf. Jetzt
        // wird je Farbe genau ein Schleier vorgezeichnet (siehe puffPatch) und
        // nur noch skaliert aufgestempelt.
        ctx.globalCompositeOperation = 'lighter';
        for (var i = 0; i < parts.length; i++) {
          var p = parts[i];
          stampPuff(p.warm ? muted : accent, p.x, p.y, p.r);
        }
        if (pointer.active) stampPuff(accent, pointer.x, pointer.y, 140);
        ctx.globalCompositeOperation = 'source-over';
      }
    },

    /* Semperoper: feiner Staub, der langsam nach unten rieselt und dabei
       seitlich schwingt - Licht im Zuschauerraum. Der Cursor laesst ihn
       heller aufleuchten. */
    staub: {
      count: function () { return clamp(Math.round(W * H / 6500), 40, 190); },
      make: function () {
        return {
          x: rand(0, W), y: rand(-H, H), vy: rand(0.12, 0.55), sway: rand(0.15, 0.5),
          phase: rand(0, Math.PI * 2), r: rand(0.6, 1.9), a: rand(0.18, 0.62)
        };
      },
      step: function (p) {
        p.y += p.vy - scroll.v * 0.35;
        p.x += Math.sin(tick * 0.012 + p.phase) * p.sway * 0.35;
        if (p.y > H + 8) { p.y = -8; p.x = rand(0, W); }
        else if (p.y < -8) { p.y = H + 8; p.x = rand(0, W); }
      },
      draw: function () {
        for (var i = 0; i < parts.length; i++) {
          var p = parts[i], a = p.a;
          if (pointer.active) {
            var dx = p.x - pointer.x, dy = p.y - pointer.y;
            var d = Math.sqrt(dx * dx + dy * dy);
            if (d < 130) a = Math.min(1, a + (1 - d / 130) * 0.5);
          }
          ctx.fillStyle = 'rgba(' + accent + ',' + a.toFixed(3) + ')';
          ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
        }
      }
    },

    /* Neustadt Neon: schnellere Punkte mit kurzen, hellen Verbindungen, dazu
       Ringe, die sich ausbreiten und verblassen. */
    puls: {
      count: function () { return clamp(Math.round(W * H / 13000), 26, 110); },
      make: function () {
        return { x: rand(0, W), y: rand(0, H), vx: rand(-0.3, 0.3), vy: rand(-0.3, 0.3), r: rand(0.7, 2) };
      },
      step: function (p) { drift(p, 0.3, 20); },
      draw: function () {
        links(accent, 98, 0.38);
        if (tick % 70 === 0 || takeBurst()) {
          rings.push(pointer.active
            ? { x: pointer.x, y: pointer.y, r: 0 }
            : { x: rand(0, W), y: rand(0, H), r: 0 });
        }
        ripples(accent, 1.9, 190, 0.3, 1.2);
        soloDots(0.72);
      }
    }
  };

  function currentMode() {
    var m = document.documentElement.dataset.bg;
    if (m === 'aus') return 'aus';
    if (m === 'zufall') {
      if (!diceRoll) diceRoll = pick(Object.keys(MODES));
      return diceRoll;
    }
    return MODES[m] ? m : 'konstellation';
  }

  function build() {
    parts = []; rings = [];
    if (mode === 'aus') return;
    var def = MODES[mode], n = def.count();
    for (var i = 0; i < n; i++) parts.push(def.make());
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = canvas.clientWidth;
    H = canvas.clientHeight;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    build();
  }

  /* Modi mit .fade loeschen nicht, sondern uebermalen den letzten Frame leicht
     mit der Hintergrundfarbe - so bleiben Spuren stehen. */
  function draw() {
    var def = mode === 'aus' ? null : MODES[mode];
    if (def && def.fade && !reduce.matches) {
      ctx.fillStyle = 'rgba(' + bgRgb + ',' + def.fade + ')';
      ctx.fillRect(0, 0, W, H);
    } else {
      ctx.clearRect(0, 0, W, H);
    }
    if (!def) return;
    def.draw();
  }

  function step() {
    var def = MODES[mode];
    for (var i = 0; i < parts.length; i++) def.step(parts[i], i);
  }

  function loop() {
    tick++;
    scroll.v = (scroll.target - scroll.y) * 0.12;
    scroll.y += scroll.v;
    step();
    draw();
    raf = requestAnimationFrame(loop);
  }

  function start() {
    if (raf !== null) return;
    if (mode === 'aus') { draw(); return; }
    if (reduce.matches) { draw(); return; }
    raf = requestAnimationFrame(loop);
  }
  function stop() {
    if (raf !== null) { cancelAnimationFrame(raf); raf = null; }
  }

  // Theme- oder Animationswechsel: Farben neu lesen, Modus wechseln, neu saeen.
  function applyAppearance() {
    stop();
    readColors();
    mode = currentMode();
    build();
    draw();
    start();
  }
  window.addEventListener('dt-appearance-change', applyAppearance);

  var resizeTimer = null;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { resize(); if (reduce.matches || mode === 'aus') draw(); }, 150);
  });

  // Im Event wird nur gemerkt, wo die Seite steht - gerechnet wird in loop().
  window.addEventListener('scroll', function () {
    scroll.target = window.pageYOffset || document.documentElement.scrollTop || 0;
  }, { passive: true });

  // Klicks/Taps gelten fuer alle Geraete - auch ohne feinen Zeiger.
  window.addEventListener('pointerdown', function (e) {
    pointer.x = e.clientX; pointer.y = e.clientY;
    pointer.active = true; pointer.down = true; pointer.burst = tick + 1;
  }, { passive: true });
  window.addEventListener('pointerup', function () { pointer.down = false; }, { passive: true });

  if (window.matchMedia('(pointer: fine)').matches) {
    window.addEventListener('pointermove', function (e) {
      pointer.x = e.clientX; pointer.y = e.clientY; pointer.active = true;
    }, { passive: true });
    window.addEventListener('pointerleave', function () { pointer.active = false; }, { passive: true });
    document.addEventListener('mouseleave', function () { pointer.active = false; });
  }

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) stop(); else start();
  });

  var onReduce = function () { stop(); start(); };
  if (reduce.addEventListener) reduce.addEventListener('change', onReduce);
  else if (reduce.addListener) reduce.addListener(onReduce);

  readColors();
  scroll.target = scroll.y = window.pageYOffset || document.documentElement.scrollTop || 0;
  mode = currentMode();
  resize();
  draw();
  start();
})();

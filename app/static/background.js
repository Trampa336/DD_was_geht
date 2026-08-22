/* Lebendiger Hintergrund. Jedes Theme bringt eine eigene Signatur-Animation mit,
   ueber das zweite Menue im Masthead laesst sie sich ueberstimmen. Welche gerade
   laeuft, steht in data-bg am <html>-Element; die Farben kommen wie bisher aus
   den CSS-Variablen und folgen dem Theme deshalb automatisch. */
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
  var fontMono = 'ui-monospace,monospace';
  var dens = 1;
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
    fontMono = (cs.getPropertyValue('--font-mono') || '').trim() || fontMono;
    puffs = {};
  }

  function rand(a, b) { return a + Math.random() * (b - a); }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

  /* Handys und Touch-Geraete bekommen die halbe Teilchenzahl. Der Wert wird
     bei resize() einmal bestimmt, nicht pro Bild. */
  function density() { return dens; }
  function measureDensity() {
    dens = (W < 700 || window.matchMedia('(pointer: coarse)').matches) ? 0.5 : 1;
  }

  // Ein Klick liegt "frisch" an, solange er weniger als n Bilder her ist.
  function bursted(n) { var a = tick - pointer.burst; return a >= 0 && a < n; }
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

  /* Schnittpunkt einer Zellkante mit der Hoehenlinie - linear interpoliert,
     damit die Linien nicht wie Treppen aussehen. Kanten: 0 oben, 1 rechts,
     2 unten, 3 links. */
  function edgePoint(e, x, y, g, level, v0, v1, v2, v3) {
    var a, b;
    if (e === 0) { a = v0; b = v1; } else if (e === 1) { a = v1; b = v2; }
    else if (e === 2) { a = v3; b = v2; } else { a = v0; b = v3; }
    // Bei zwei gleichen Ecken gibt es keinen echten Schnittpunkt - dann die
    // Kantenmitte nehmen, statt durch Null zu teilen.
    var t = b === a ? 0.5 : (level - a) / (b - a);
    if (e === 0) return [x + g * t, y];
    if (e === 1) return [x + g, y + g * t];
    if (e === 2) return [x + g * t, y + g];
    return [x, y + g * t];
  }

  /* --- Bausteine, die sich mehrere Modi teilen ----------------------------
     Ein Dutzend der Animationen sind Abwandlungen derselben vier Handgriffe:
     driften und am Rand umlaufen, nahe Teilchen verbinden, Punkte setzen,
     Ringe ausbreiten lassen. Die stehen hier einmal und werden mit Zahlen
     parametriert - was einen Modus ausmacht, sind genau diese Zahlen. */

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

  // Ein Punkt in einen laufenden Pfad. moveTo davor, sonst zoege der Pfad einen
  // Strich vom letzten Punkt zum naechsten Kreis.
  function dot(x, y, r) { ctx.moveTo(x + r, y); ctx.arc(x, y, r, 0, Math.PI * 2); }

  // Jedes Teilchen einzeln gefuellt (nicht in einem Pfad): wo zwei Punkte sich
  // ueberlappen, deckt das doppelt - genau so sieht die Konstellation aus.
  function soloDots(alpha) {
    ctx.fillStyle = 'rgba(' + accent + ',' + alpha + ')';
    for (var i = 0; i < parts.length; i++) {
      ctx.beginPath(); ctx.arc(parts[i].x, parts[i].y, parts[i].r, 0, Math.PI * 2); ctx.fill();
    }
  }

  /* Punkte in drei Helligkeitsstufen. Alle Punkte einer Stufe liegen in einem
     Pfad - drei Zeichenaufrufe statt einem je Teilchen. plot() entscheidet je
     Teilchen und Stufe, ob und wo es gesetzt wird, und meldet das zurueck. */
  function bandedDots(base, step, plot) {
    for (var b = 0; b < 3; b++) {
      var any = false;
      ctx.beginPath();
      for (var i = 0; i < parts.length; i++) {
        if (plot(parts[i], b, b / 3, (b + 1) / 3)) any = true;
      }
      if (!any) continue;
      ctx.fillStyle = 'rgba(' + accent + ',' + (base + b * step).toFixed(3) + ')';
      ctx.fill();
    }
  }

  /* Ringe, die groesser werden und dabei verblassen; wer durch ist, fliegt raus.
     squash macht aus dem Kreis eine flache Ellipse (Pfuetzen im Regen). */
  function ripples(rgb, grow, span, alpha, width, squash) {
    for (var i = rings.length - 1; i >= 0; i--) {
      var ring = rings[i];
      ring.r += grow;
      var f = 1 - ring.r / span;
      if (f <= 0) { rings.splice(i, 1); continue; }
      ctx.strokeStyle = 'rgba(' + rgb + ',' + (f * alpha).toFixed(3) + ')';
      ctx.lineWidth = width;
      ctx.beginPath();
      if (squash) { ctx.ellipse(ring.x, ring.y, ring.r, ring.r * squash, 0, 0, Math.PI * 2); }
      else { ctx.arc(ring.x, ring.y, ring.r, 0, Math.PI * 2); }
      ctx.stroke();
    }
  }

  // Bahnkoerper: die neue Stelle merken und die vorige behalten, damit nur das
  // Stueck seit dem letzten Bild gezeichnet wird. Beim allerersten Mal gibt es
  // kein voriges - sonst zoege es einen Strich aus dem Nichts.
  function trail(p, x, y) {
    p.px = p.x; p.py = p.y;
    p.x = x; p.y = y;
    if (p.first) { p.px = x; p.py = y; p.first = false; }
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
    },

    /* Schwarm: Boids nach Reynolds - Ausrichtung, Zusammenhalt, Abstand. Die
       Nachbarsuche laeuft ueber ein Raster, nicht ueber alle Paare. Gezeichnet
       wird wie bei der Konstellation: duenne Striche, kleine Punkte, ein Ton. */
    schwarm: {
      count: function () { return clamp(Math.round(W * H / 24000 * density()), 14, 52); },
      make: function () {
        var a = rand(0, Math.PI * 2), sp = rand(0.5, 0.9);
        return { x: rand(0, W), y: rand(0, H), vx: Math.cos(a) * sp, vy: Math.sin(a) * sp };
      },
      step: function (p, i) {
        var R = 78, grid = this._grid;
        // Das Raster wird einmal pro Bild gebaut - beim ersten Teilchen.
        if (i === 0) {
          grid = this._grid = {};
          for (var k = 0; k < parts.length; k++) {
            var q = parts[k], key = ((q.x / R) | 0) + ':' + ((q.y / R) | 0);
            (grid[key] || (grid[key] = [])).push(q);
          }
        }
        var cx = (p.x / R) | 0, cy = (p.y / R) | 0;
        var ax = 0, ay = 0, sx = 0, sy = 0, mx = 0, my = 0, n = 0;
        for (var gx = cx - 1; gx <= cx + 1; gx++) {
          for (var gy = cy - 1; gy <= cy + 1; gy++) {
            var cell = grid[gx + ':' + gy];
            if (!cell) continue;
            for (var j = 0; j < cell.length; j++) {
              var o = cell[j];
              if (o === p) continue;
              var dx = o.x - p.x, dy = o.y - p.y, d2 = dx * dx + dy * dy;
              if (d2 > R * R || d2 === 0) continue;
              n++;
              ax += o.vx; ay += o.vy;              // Ausrichtung
              mx += o.x; my += o.y;                // Zusammenhalt
              if (d2 < 420) { sx -= dx / d2 * 60; sy -= dy / d2 * 60; }  // Abstand
            }
          }
        }
        if (n) {
          p.vx += (ax / n - p.vx) * 0.03 + (mx / n - p.x) * 0.0006 + sx * 0.012;
          p.vy += (ay / n - p.vy) * 0.03 + (my / n - p.y) * 0.0006 + sy * 0.012;
        }
        // Der Zeiger zieht nur leicht - kein Springen, kein Erschrecken.
        if (pointer.active) {
          var px = pointer.x - p.x, py = pointer.y - p.y;
          var pd = Math.sqrt(px * px + py * py) || 1;
          if (pd < 260) { p.vx += px / pd * 0.012; p.vy += py / pd * 0.012; }
        }
        var sp = Math.sqrt(p.vx * p.vx + p.vy * p.vy) || 1;
        var want = clamp(sp, 0.35, 1);
        p.vx = p.vx / sp * want; p.vy = p.vy / sp * want;
        drift(p, 0.2, 12);
      },
      draw: function () {
        // Alle Striche liegen in einem einzigen Pfad - ein Zeichenaufruf statt
        // einem pro Boid.
        var i, p;
        ctx.strokeStyle = 'rgba(' + muted + ',0.3)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (i = 0; i < parts.length; i++) {
          p = parts[i];
          ctx.moveTo(p.x - p.vx * 7, p.y - p.vy * 7);
          ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
        ctx.fillStyle = 'rgba(' + accent + ',0.5)';
        ctx.beginPath();
        for (i = 0; i < parts.length; i++) {
          p = parts[i];
          ctx.moveTo(p.x + 1.3, p.y);
          ctx.arc(p.x, p.y, 1.3, 0, Math.PI * 2);
        }
        ctx.fill();
      }
    },

    /* Funkenflug: alle paar Sekunden loest sich still eine Handvoll Funken und
       treibt aus. Keine Gradienten, kein Leuchten - nur Punkte, die verloeschen.
       Ein Klick loest den naechsten Funkenflug sofort aus. */
    feuerwerk: {
      count: function () { return Math.round(clamp(W * H / 16000, 40, 110) * density()); },
      make: function () { return { life: 0, max: 1, x: 0, y: 0, vx: 0, vy: 0 }; },
      step: function (p) {
        if (p.life <= 0) return;
        p.life--;
        p.vy += 0.014;                 // Schwerkraft, sehr sanft
        p.vx *= 0.992; p.vy *= 0.992;  // Luftwiderstand
        p.x += p.vx; p.y += p.vy - scroll.v * 0.3;
      },
      _boom: function (x, y) {
        var n = Math.round(rand(12, 20) * density()), fired = 0;
        var spread = rand(0.7, 1.4);
        for (var i = 0; i < parts.length && fired < n; i++) {
          var p = parts[i];
          if (p.life > 0) continue;
          var a = rand(0, Math.PI * 2), sp = spread * Math.sqrt(Math.random());
          p.x = x; p.y = y;
          p.vx = Math.cos(a) * sp; p.vy = Math.sin(a) * sp;
          p.max = p.life = Math.round(rand(120, 260));
          fired++;
        }
        rings.push({ x: x, y: y, r: 0 });
      },
      draw: function () {
        if (tick % 210 === 0) this._boom(rand(W * 0.15, W * 0.85), rand(H * 0.15, H * 0.7));
        if (takeBurst()) this._boom(pointer.x, pointer.y);

        // Eine einzige, langsam auslaufende Welle pro Funkenflug.
        ripples(muted, 1.1, 170, 0.16, 1);
        // Die Funken stuft die Restlebensdauer ein: frisch ist hell.
        bandedDots(0.12, 0.16, function (p, b, lo, hi) {
          if (p.life <= 0) return false;
          var f = p.life / p.max;
          if (f < lo || f >= hi) return false;
          dot(p.x, p.y, 1.5);
          return true;
        });
      }
    },

    /* Elbwelle: drei duenne Sinuslinien, die langsam gegeneinander laufen -
       eine Flusskante, kein Farbverlauf. Der Cursor druckt eine flache Delle
       hinein. Kosten: drei Striche pro Bild. */
    elbwelle: {
      count: function () { return density() < 1 ? 2 : 3; },
      make: function () { return {}; },
      step: function () { /* Die Wellen leben allein von tick. */ },
      draw: function () {
        var bands = parts.length, step = 22;
        for (var b = 0; b < bands; b++) {
          var f = b / (bands - 1 || 1);
          // Beim Scrollen kippt die Wellenlage sanft, ohne je zu springen.
          var base = H * (0.34 + f * 0.5) + Math.sin(scroll.y * 0.0016 + f) * (12 + f * 18);
          var amp = 14 + f * 26;
          var len = 0.0032 + f * 0.0018;
          var sp = tick * (0.004 + f * 0.003);
          ctx.beginPath();
          for (var x = -10; x <= W + 10; x += step) {
            var y = base
              + Math.sin(x * len + sp) * amp
              + Math.sin(x * len * 2.3 - sp * 1.7) * amp * 0.3;
            if (pointer.active) {
              var dx = x - pointer.x, dy = base - pointer.y;
              y -= 44 * Math.exp(-(dx * dx) / 26000 - (dy * dy) / 70000);
            }
            if (x < 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          }
          ctx.strokeStyle = 'rgba(' + (b % 2 ? muted : accent) + ',' + (0.12 + f * 0.1).toFixed(3) + ')';
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
    },

    /* Liniennetz: wenige Spalten mit langsam fallenden Linien- und
       Haltestellenkuerzeln. Kein Leuchten, kein Schlagschatten - nur Text in
       zwei Deckkraftstufen. */
    matrix: {
      _glyphs: ('3 4 6 7 8 9 10 11 12 13 61 62 63 64 66 75 S1 S2 S3 EC IC RE RB ' +
                'PIR RAD MEI HBF NST POS ALB SCH LOS BLA GOR PLA TRA').split(' '),
      count: function () { return clamp(Math.round(W / 96 * density()), 5, 14); },
      make: function () {
        return {
          x: 0, y: rand(-H, 0), sp: rand(0.35, 0.9), len: Math.round(rand(4, 8)),
          lit: 0, chars: []
        };
      },
      step: function (p, i) {
        var cols = parts.length;
        p.x = (i + 0.5) * (W / cols);
        p.y += p.sp - scroll.v * 0.4;
        if (p.lit) p.lit--;
        // Alle paar Bilder rutscht ein Zeichen nach.
        if (tick % 9 === 0) {
          p.chars.unshift(pick(this._glyphs));
          if (p.chars.length > p.len) p.chars.pop();
        }
        if (p.y - p.len * 20 > H) { p.y = rand(-H * 0.5, -20); p.sp = rand(0.35, 0.9); p.chars = []; }
        else if (p.y < -p.len * 20 - H) { p.y = rand(H * 0.5, H); p.chars = []; }
      },
      draw: function () {
        // Ein Klick hellt still die naechstgelegene Spalte auf.
        if (parts.length && takeBurst()) {
          var idx = clamp(Math.round(pointer.x / (W / parts.length) - 0.5), 0, parts.length - 1);
          parts[idx].lit = 70;
        }
        ctx.font = '500 13px ' + fontMono;
        ctx.textAlign = 'center';
        for (var i = 0; i < parts.length; i++) {
          var p = parts[i];
          for (var j = 0; j < p.chars.length; j++) {
            var y = p.y - j * 20;
            if (y < -20 || y > H + 20) continue;
            var fade = 1 - j / (p.chars.length || 1);
            if (j === 0) {
              ctx.fillStyle = 'rgba(' + accent + ',' + (p.lit ? 0.6 : 0.42) + ')';
            } else {
              ctx.fillStyle = 'rgba(' + (p.lit ? accent : muted) + ',' + (fade * 0.22).toFixed(3) + ')';
            }
            ctx.fillText(p.chars[j], p.x, y);
          }
        }
        ctx.textAlign = 'start';
      }
    },

    /* Kaleidoskop: zwei wandernde Zeichenkoepfe, sechsfach um die Bildmitte
       gespiegelt. Statt zu loeschen wird pro Bild leicht mit der
       Hintergrundfarbe uebermalt - daher die langen, weichen Schleifen. */
    kaleidoskop: {
      fade: 0.035,
      count: function () { return 2; },
      make: function () {
        return {
          a: rand(0, Math.PI * 2), r: rand(40, 200), da: rand(0.004, 0.011) * (Math.random() < 0.5 ? -1 : 1),
          dr: rand(0.25, 0.7), phase: rand(0, Math.PI * 2), px: 0, py: 0, first: true
        };
      },
      step: function (p) {
        var cx = W / 2, cy = H / 2;
        var boost = 1, reach = Math.min(W, H) * 0.42;
        if (pointer.active) {
          // Cursor-Abstand zur Mitte steuert Radius und Drehtempo - sanft.
          var dx = pointer.x - cx, dy = pointer.y - cy;
          var pd = clamp(Math.sqrt(dx * dx + dy * dy) / (Math.min(W, H) / 2 || 1), 0, 1.2);
          reach *= 0.7 + pd * 0.5;
          boost = 1 + pd * 0.6;
        }
        p.a += p.da * boost;
        p.r += Math.sin(tick * 0.007 + p.phase) * p.dr * boost;
        p.r = clamp(p.r, 20, reach);
        trail(p, cx + Math.cos(p.a) * p.r + Math.cos(p.a * 3.4 + p.phase) * p.r * 0.2,
                 cy + Math.sin(p.a) * p.r + Math.sin(p.a * 2.7 - p.phase) * p.r * 0.2);
      },
      draw: function () {
        var cx = W / 2, cy = H / 2;
        var arms = density() < 1 ? 4 : 6;
        ctx.save();
        ctx.translate(cx, cy);
        ctx.lineCap = 'round';
        ctx.lineWidth = 1;
        for (var i = 0; i < parts.length; i++) {
          var p = parts[i];
          ctx.strokeStyle = 'rgba(' + (i ? muted : accent) + ',' + (i ? 0.16 : 0.24) + ')';
          // Ein Pfad je Kopf: alle Arme und ihre Spiegelung liegen darin.
          ctx.beginPath();
          for (var k = 0; k < arms; k++) {
            var ang = Math.PI * 2 * k / arms, c = Math.cos(ang), sn = Math.sin(ang);
            var x0 = p.px - cx, y0 = p.py - cy, x1 = p.x - cx, y1 = p.y - cy;
            ctx.moveTo(x0 * c - y0 * sn, x0 * sn + y0 * c);
            ctx.lineTo(x1 * c - y1 * sn, x1 * sn + y1 * c);
            ctx.moveTo(x0 * c + y0 * sn, x0 * sn - y0 * c);
            ctx.lineTo(x1 * c + y1 * sn, x1 * sn - y1 * c);
          }
          ctx.stroke();
        }
        ctx.lineCap = 'butt';
        ctx.restore();
      }
    },

    /* Regen: schraege Striche in einem einzigen Pfad. Der Zeiger gibt die
       Windrichtung vor, unten bleiben ein paar Pfuetzenringe zurueck. */
    regen: {
      count: function () { return clamp(Math.round(W * H / 17000 * density()), 18, 64); },
      make: function () {
        return { x: rand(0, W), y: rand(-H, H), len: rand(9, 24), sp: rand(2.6, 5.4) };
      },
      step: function (p, i) {
        // Der Wind wird einmal pro Bild bestimmt, nicht einmal pro Tropfen.
        if (i === 0) {
          var want = pointer.active ? (pointer.x - W / 2) / W * 2.2 : 0.45;
          this._wind = (this._wind || 0) * 0.94 + want * 0.06;
        }
        p.x += this._wind * p.sp * 0.5;
        p.y += p.sp - scroll.v * 0.5;
        if (p.y > H + p.len) {
          if (rings.length < 5) rings.push({ x: p.x, y: H - rand(0, 12), r: 0 });
          p.y = -p.len - rand(0, H * 0.4); p.x = rand(-40, W + 40);
        } else if (p.y < -p.len - H) {
          p.y = H + rand(0, 40); p.x = rand(-40, W + 40);
        }
        if (p.x < -60) p.x = W + 40; else if (p.x > W + 60) p.x = -40;
      },
      draw: function () {
        var w = this._wind || 0, i;
        ctx.strokeStyle = 'rgba(' + accent + ',0.2)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (i = 0; i < parts.length; i++) {
          var p = parts[i];
          ctx.moveTo(p.x - w * p.len * 0.5, p.y - p.len);
          ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
        // Die Pfuetzen unten: flach gedrueckte Ringe.
        ripples(muted, 0.7, 34, 0.22, 1, 0.3);
      }
    },

    /* Raster: ein fluchtendes Bodengitter. Braucht keine Teilchen - Horizont,
       Fluchtpunkt und Tiefe ergeben sich aus tick und Scrollposition. */
    raster: {
      count: function () { return 0; },
      make: function () { return {}; },
      step: function () { },
      draw: function () {
        var horizon = H * 0.46;
        var vx = W / 2, depth = H - horizon;
        if (pointer.active) vx += (pointer.x - W / 2) * 0.12;
        // Die Tiefenphase laeuft mit der Zeit und zusaetzlich mit dem Scrollen.
        var phase = (tick * 0.0035 + scroll.y * 0.0011) % 1;
        var lines = density() < 1 ? 9 : 14, i;
        ctx.strokeStyle = 'rgba(' + muted + ',0.16)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (i = 1; i <= lines; i++) {
          var t = i - phase;
          var y = horizon + depth / t;
          if (y > H + 2) continue;
          ctx.moveTo(0, y); ctx.lineTo(W, y);
        }
        for (i = -8; i <= 8; i++) {
          ctx.moveTo(vx, horizon);
          ctx.lineTo(vx + i * W * 0.19, H);
        }
        ctx.stroke();
        // Der Horizont selbst bekommt einen Hauch mehr Kontur.
        ctx.strokeStyle = 'rgba(' + accent + ',0.16)';
        ctx.beginPath(); ctx.moveTo(0, horizon); ctx.lineTo(W, horizon); ctx.stroke();
      }
    },

    /* Hoehenlinien: Marching Squares ueber ein langsam atmendes Feld. Die
       Feldwerte werden einmal pro Bild in ein wiederverwendetes Array
       geschrieben, beide Hoehenstufen lesen daraus - jede Stufe ist dann ein
       einziger Pfad. */
    hoehenlinien: {
      _cases: [[], [[0, 3]], [[0, 1]], [[1, 3]], [[1, 2]], [[0, 1], [2, 3]], [[0, 2]], [[2, 3]],
               [[2, 3]], [[0, 2]], [[0, 3], [1, 2]], [[1, 2]], [[1, 3]], [[0, 1]], [[0, 3]], []],
      count: function () { return 0; },
      make: function () { return {}; },
      step: function () { },
      draw: function () {
        var G = density() < 1 ? 62 : 44;
        var cols = Math.ceil(W / G) + 2, rows = Math.ceil(H / G) + 2;
        if (this._cols !== cols || this._rows !== rows) {
          this._cols = cols; this._rows = rows;
          this._f = new Float32Array(cols * rows);
        }
        var f = this._f, t = tick * 0.0026, oy = scroll.y * 0.35, gx, gy;
        for (gy = 0; gy < rows; gy++) {
          var wy = gy * G - G + oy;
          for (gx = 0; gx < cols; gx++) {
            var wx = gx * G - G;
            f[gy * cols + gx] = Math.sin(wx * 0.0052 + t)
              + Math.sin(wy * 0.0068 - t * 0.8)
              + Math.sin((wx + wy) * 0.0035 + t * 1.4);
          }
        }
        var cases = this._cases;
        for (var lv = 0; lv < 2; lv++) {
          var level = lv ? 0.55 : -0.55;
          ctx.strokeStyle = 'rgba(' + (lv ? accent : muted) + ',' + (lv ? 0.2 : 0.13) + ')';
          ctx.lineWidth = 1;
          ctx.beginPath();
          for (gy = 0; gy < rows - 1; gy++) {
            for (gx = 0; gx < cols - 1; gx++) {
              var i0 = gy * cols + gx;
              var v0 = f[i0], v1 = f[i0 + 1], v2 = f[i0 + cols + 1], v3 = f[i0 + cols];
              var idx = (v0 >= level ? 1 : 0) | (v1 >= level ? 2 : 0) | (v2 >= level ? 4 : 0) | (v3 >= level ? 8 : 0);
              var segs = cases[idx];
              if (!segs.length) continue;
              var x0 = gx * G - G, y0 = gy * G - G;
              for (var sIdx = 0; sIdx < segs.length; sIdx++) {
                var a = edgePoint(segs[sIdx][0], x0, y0, G, level, v0, v1, v2, v3);
                var b = edgePoint(segs[sIdx][1], x0, y0, G, level, v0, v1, v2, v3);
                ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]);
              }
            }
          }
          ctx.stroke();
        }
      }
    },

    /* Trabanten: drei Koerper auf driftenden Bahnen. Gezeichnet wird nur das
       Stueck seit dem letzten Bild - die Spur entsteht ueber fade. */
    trabanten: {
      fade: 0.028,
      count: function () { return 3; },
      make: function () {
        return {
          a: rand(0, Math.PI * 2), da: rand(0.008, 0.02) * (Math.random() < 0.5 ? -1 : 1),
          r: rand(60, 190), ca: rand(0, Math.PI * 2), cda: rand(0.0012, 0.0031),
          cr: rand(60, 170), px: 0, py: 0, first: true
        };
      },
      step: function (p) {
        // Der Mittelpunkt jeder Bahn wandert selbst auf einer langsamen Bahn.
        p.ca += p.cda;
        var cx = W / 2 + Math.cos(p.ca) * p.cr;
        var cy = H / 2 + Math.sin(p.ca * 1.3) * p.cr * 0.6 - scroll.y * 0.06;
        p.a += p.da;
        trail(p, cx + Math.cos(p.a) * p.r, cy + Math.sin(p.a) * p.r);
      },
      draw: function () {
        ctx.lineCap = 'round';
        ctx.lineWidth = 1.2;
        for (var i = 0; i < parts.length; i++) {
          var p = parts[i];
          ctx.strokeStyle = 'rgba(' + (i ? muted : accent) + ',' + (i ? 0.2 : 0.3) + ')';
          ctx.beginPath();
          ctx.moveTo(p.px, p.py); ctx.lineTo(p.x, p.y);
          ctx.stroke();
        }
        ctx.lineCap = 'butt';
      }
    },

    /* Radar: ein Strahl wandert aus der unteren linken Ecke ueber die Flaeche.
       Die Blips stehen fest und leuchten auf, wenn er sie streift. */
    radar: {
      count: function () { return clamp(Math.round(W * H / 42000 * density()), 6, 22); },
      make: function () { return { x: rand(0, W), y: rand(0, H), lit: 0 }; },
      // Beim Scrollen wandern die Blips durchs Bild; Schritt und Zeichnen
      // muessen dieselbe Position sehen, sonst leuchten die falschen auf.
      _wy: function (p) {
        var y = (p.y - scroll.y * 0.08) % H;
        return y < 0 ? y + H : y;
      },
      _beam: function () { return -(tick * 0.0038) % Math.PI; },
      step: function (p) {
        p.lit *= 0.982;
        var a = Math.atan2(this._wy(p) - H * 0.94, p.x - W * 0.06);
        var d = Math.abs(a - this._beam());
        if (d < 0.05) p.lit = 1;
      },
      draw: function () {
        var ox = W * 0.06, oy = H * 0.94, reach = Math.sqrt(W * W + H * H);
        var beam = this._beam();
        // Zwei Bogen als Entfernungsringe, dann der Strahl mit zwei Echos.
        ctx.strokeStyle = 'rgba(' + muted + ',0.1)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(ox, oy, reach * 0.34, -Math.PI, 0);
        ctx.moveTo(ox + reach * 0.66, oy);
        ctx.arc(ox, oy, reach * 0.66, 0, -Math.PI, true);
        ctx.stroke();
        for (var e = 2; e >= 0; e--) {
          ctx.strokeStyle = 'rgba(' + accent + ',' + (e ? 0.05 / e : 0.22) + ')';
          ctx.beginPath();
          ctx.moveTo(ox, oy);
          ctx.lineTo(ox + Math.cos(beam + e * 0.09) * reach, oy + Math.sin(beam + e * 0.09) * reach);
          ctx.stroke();
        }
        // Frisch gestreifte Blips leuchten am hellsten und klingen dann ab.
        var self = this;
        bandedDots(0.08, 0.18, function (p, b, lo, hi) {
          if (p.lit < lo || (b < 2 && p.lit >= hi)) return false;
          dot(p.x, self._wy(p), 2);
          return true;
        });
      }
    },

    /* Dresdner Silhouette: eine einmal gewuerfelte Dachlinie mit Kuppel und
       spitzem Turm, in zwei Tiefen. Beim Scrollen laufen die Ebenen
       unterschiedlich schnell - das ist die eigentliche Parallaxe. */
    silhouette: {
      count: function () { return 2; },
      make: function () {
        // Wird nur beim Aufbau gerufen, nicht pro Bild.
        var far = parts.length === 0;
        var span = W * 1.6, x = 0, pts = [], top = H * (far ? 0.62 : 0.72);
        while (x < span) {
          var w = rand(38, 118), r = Math.random();
          var h = top + rand(-40, 40);
          if (r < 0.1) {
            // Kuppel
            var cx = x + w / 2, rad = w / 2;
            pts.push([x, h + rad * 0.5]);
            for (var k = 0; k <= 8; k++) {
              var ang = Math.PI + Math.PI * (k / 8);
              pts.push([cx + Math.cos(ang) * rad, h + rad * 0.5 + Math.sin(ang) * rad * 0.9]);
            }
          } else if (r < 0.18) {
            // Spitzer Turm
            pts.push([x, h]);
            pts.push([x + w * 0.5, h - rand(40, 90)]);
            pts.push([x + w, h]);
          } else if (r < 0.34) {
            // Giebel
            pts.push([x, h]);
            pts.push([x + w * 0.5, h - rand(12, 30)]);
            pts.push([x + w, h]);
          } else {
            pts.push([x, h]); pts.push([x + w, h]);
          }
          x += w;
        }
        return { pts: pts, span: span, far: far };
      },
      step: function () { },
      draw: function () {
        for (var i = 0; i < parts.length; i++) {
          var p = parts[i];
          var par = p.far ? 0.05 : 0.14;
          var dx = -((tick * (p.far ? 0.02 : 0.05)) % (p.span - W)) - scroll.y * par;
          // Der Versatz bleibt in einem Streifen, damit nie eine Kante auftaucht.
          dx = -(((-dx) % (p.span - W)) + (p.span - W)) % (p.span - W);
          ctx.beginPath();
          ctx.moveTo(dx, H + 4);
          for (var j = 0; j < p.pts.length; j++) ctx.lineTo(p.pts[j][0] + dx, p.pts[j][1]);
          ctx.lineTo(dx + p.span, H + 4);
          ctx.closePath();
          ctx.fillStyle = 'rgba(' + (p.far ? muted : accent) + ',' + (p.far ? 0.055 : 0.075) + ')';
          ctx.fill();
          ctx.strokeStyle = 'rgba(' + (p.far ? muted : accent) + ',' + (p.far ? 0.1 : 0.16) + ')';
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
    },

    /* Bildfahrplan: waagerechte Haltestellenlinien, schraege Zuglinien. Die
       Haltestellen liegen gleichmaessig, deshalb kann ihr Scrollversatz ohne
       sichtbaren Sprung umlaufen. */
    bildfahrplan: {
      count: function () { return clamp(Math.round(W / 190 * density()), 3, 9); },
      make: function () {
        return {
          x: rand(-W, W), y: rand(0.1, 0.9) * H, dy: rand(-0.5, 0.5),
          len: rand(W * 0.3, W * 0.9), sp: rand(0.25, 0.75)
        };
      },
      step: function (p) {
        p.x -= p.sp;
        if (p.x + p.len < -20) {
          p.x = W + rand(0, W * 0.5); p.y = rand(0.1, 0.9) * H;
          p.dy = rand(-0.5, 0.5); p.len = rand(W * 0.3, W * 0.9); p.sp = rand(0.25, 0.75);
        }
      },
      draw: function () {
        var rows = 7, gap = H / rows, off = (tick * 0.03 + scroll.y * 0.18) % gap, i;
        ctx.strokeStyle = 'rgba(' + muted + ',0.13)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (i = -1; i <= rows; i++) {
          var y = i * gap + off;
          ctx.moveTo(0, y); ctx.lineTo(W, y);
        }
        ctx.stroke();
        ctx.strokeStyle = 'rgba(' + accent + ',0.24)';
        ctx.beginPath();
        for (i = 0; i < parts.length; i++) {
          var p = parts[i];
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(p.x + p.len, p.y + p.dy * p.len * 0.35);
        }
        ctx.stroke();
      }
    },

    /* Sternenhimmel: die Sterne stehen fest zueinander und drehen sich
       aeusserst langsam um einen Punkt ausserhalb des Bildes. Kein Verbinden,
       kein Leuchten - nur Funkeln ueber die Deckkraft. */
    sterne: {
      count: function () { return clamp(Math.round(W * H / 11000 * density()), 40, 140); },
      make: function () {
        var reach = Math.sqrt(W * W + H * H);
        return {
          a: rand(0, Math.PI * 2), r: rand(H * 0.3, reach * 0.85),
          phase: rand(0, Math.PI * 2), base: rand(0.14, 0.5), size: rand(0.7, 1.6)
        };
      },
      step: function (p) { p.a += 0.00028; },
      draw: function () {
        var cx = W * 0.5, cy = H * 1.35 - scroll.y * 0.1;
        // Nicht die Lebensdauer stuft hier ein, sondern das Funkeln selbst.
        bandedDots(0.12, 0.16, function (p, b) {
          var a = p.base * (0.55 + 0.45 * Math.sin(tick * 0.022 + p.phase));
          if (clamp(Math.floor(a * 6), 0, 2) !== b) return false;
          var x = cx + Math.cos(p.a) * p.r, y = cy + Math.sin(p.a) * p.r;
          if (x < -4 || x > W + 4 || y < -4 || y > H + 4) return false;
          dot(x, y, p.size);
          return true;
        });
      }
    },

    /* Moire: zwei Scharen paralleler Linien, die sich minimal unterschiedlich
       drehen. Jede Schar ist ein Pfad - das Muster entsteht allein aus der
       Ueberlagerung. */
    moire: {
      count: function () { return 0; },
      make: function () { return {}; },
      step: function () { },
      draw: function () {
        var D = Math.sqrt(W * W + H * H) * 0.62;
        var gap = density() < 1 ? 30 : 22;
        for (var f = 0; f < 2; f++) {
          var ang = (f ? -1 : 1) * (tick * (f ? 0.00055 : 0.00082) + scroll.y * 0.00035) + f * 0.06;
          ctx.save();
          ctx.translate(W / 2, H / 2);
          ctx.rotate(ang);
          ctx.strokeStyle = 'rgba(' + (f ? muted : accent) + ',0.085)';
          ctx.lineWidth = 1;
          ctx.beginPath();
          for (var x = -D; x <= D; x += gap) {
            ctx.moveTo(x, -D); ctx.lineTo(x, D);
          }
          ctx.stroke();
          ctx.restore();
        }
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
    measureDensity();
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

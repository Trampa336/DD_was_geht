/* Herzen. Diese Datei liegt NUR auf der Flask-Seite im Heimnetz: die Vorlage
   bindet sie im static-Modus nicht ein (app/templates/index.html), sie steht
   nicht in web.PUBLIC_ASSETS, und tools/export_static.py loescht eine Altkopie
   aktiv wieder. In der oeffentlichen Kopie gibt es also nicht einen
   abgeschalteten Knopf, sondern gar keinen Code dafuer - dieselbe Bauart, die
   bis P5c fuer rating.js galt.

   EIN Herz gilt der ganzen Serie (Entscheidung #26). Welche Zeigungen dazu
   gehoeren, entscheidet der Server: der Browser schickt nur die uid der
   angeklickten Zeile, /api/herz antwortet mit dem Serien-Schluessel. Dieselbe
   Antwort taugt fuer Einzeltermine, da ist die Serie eben einelementig.

   app.js reicht beim Aufbau einer Zeile den Serien-Schluessel, eine Zeigung der
   Serie und eine Funktion herein, die nach dem Umschalten neu zeichnet. */
(function () {
  function post(uid, an, runKey) {
    return fetch('/api/herz', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uid: uid, an: an, run_key: runKey })
    }).then(function (res) { return res.json(); });
  }

  function label(btn, an) {
    btn.setAttribute('aria-pressed', an ? 'true' : 'false');
    btn.title = an ? 'Herz entfernen' : 'Zu deinen Herzen hinzufügen';
    btn.setAttribute('aria-label', btn.title);
  }

  /* Der Knopf fuer eine Zeile in der Liste. runKey ist der Schluessel, den
     app.js aus der Zeile rechnet (runKey()); uid ist die Zeigung, an der der
     Server die Serie aufloest. */
  window.ddHerzButton = function (runKey, uid, an, done) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'herz';
    btn.textContent = '♥';
    label(btn, an);
    btn.addEventListener('click', function (evt) {
      evt.stopPropagation();
      var naechster = btn.getAttribute('aria-pressed') !== 'true';
      btn.disabled = true;
      post(uid, naechster, runKey).then(function (data) {
        btn.disabled = false;
        // Der Server hat das letzte Wort darueber, welcher Schluessel getroffen
        // wurde: zeigte die Zeile auf eine ausgeblendete Doppelung, herzt er
        // den Eintrag, den die Liste an ihrer Stelle zeigt.
        label(btn, !!data.an);
        if (done) { done(data); }
      }).catch(function () { btn.disabled = false; });
    });
    return btn;
  };

  /* Die kuratierte Seite (app/templates/herzen.html) rendert ihre Knoepfe
     serverseitig. Ein Klick entfernt das Herz und nimmt die Zeile gleich mit -
     ein Neuladen waere ehrlicher, aber die Zeile stehen zu lassen waere
     falsch. */
  document.querySelectorAll('.herz-entfernen').forEach(function (btn) {
    label(btn, true);
    btn.addEventListener('click', function () {
      btn.disabled = true;
      post(btn.dataset.uid, false, btn.dataset.runKey).then(function () {
        var row = btn.closest('.herz-row');
        if (row) { row.remove(); }
      }).catch(function () { btn.disabled = false; });
    });
  });
})();

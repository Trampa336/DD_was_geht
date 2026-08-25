/* Bewerten mit 👍/👎. Diese Datei liegt NUR auf der Flask-Seite im Heimnetz:
   die Vorlage bindet sie im static-Modus nicht ein und tools/export_static.py
   kopiert sie nicht mit. In der oeffentlichen Kopie gibt es also nicht einen
   abgeschalteten Knopf, sondern gar keinen Code dafuer.

   app.js reicht beim Aufbau einer Zeile das Event und eine Funktion herein, die
   nach der gespeicherten Bewertung Liste und Empfehlungen neu zeichnet. */
window.ddFeedbackButtons = function (ev, done) {
  var wrap = document.createElement('div');
  wrap.className = 'fb';
  ['like', 'skip'].forEach(function (r) {
    var btn = document.createElement('button');
    btn.textContent = r === 'like' ? '👍' : '👎';
    btn.dataset.active = ev.reaction === r ? 'true' : 'false';
    btn.addEventListener('click', function () {
      fetch('/api/feedback', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uid: ev.uid, reaction: r })
      }).then(function (res) { return res.json(); }).then(function () {
        ev.reaction = r;
        done(ev);
      });
    });
    wrap.appendChild(btn);
  });
  return wrap;
};

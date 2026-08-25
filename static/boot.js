/* Umbenennung von "Dresden Takt" zu "DD was geht": die gespeicherten Einstellungen
   lagen unter dresden-takt.* . Einmalig umtragen, sonst stuende jeder Browser
   wieder auf Standardtheme und mit zurueckgesetzten Filtern da. Kann weg, sobald
   alle Geraete die Seite einmal geladen haben. */
(function () {
  try {
    ['bg', 'cats', 'filters'].forEach(function (name) {
      var alt = window.localStorage.getItem('dresden-takt.' + name);
      if (alt !== null && window.localStorage.getItem('dd-was-geht.' + name) === null) {
        window.localStorage.setItem('dd-was-geht.' + name, alt);
      }
      window.localStorage.removeItem('dresden-takt.' + name);
    });
    // Bewertet wird nur noch im Heimnetz: die Gast-Bewertungen der oeffentlichen
    // Kopie sind Altlast und werden beim naechsten Besuch entsorgt.
    ['dd-was-geht.guest.reactions', 'dd-was-geht.guest.weights',
     'dresden-takt.guest.reactions', 'dresden-takt.guest.weights']
      .forEach(function (key) { window.localStorage.removeItem(key); });
  } catch (e) { /* Privatmodus o.ae. - dann eben Standardwerte */ }
})();
document.documentElement.dataset.theme = 'industriegelaende';

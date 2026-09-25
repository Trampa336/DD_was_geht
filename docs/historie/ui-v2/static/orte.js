/* Suche auf der "Alle Orte"-Seite (app/templates/venues.html). Die Liste
   steht komplett im HTML (bis zu ~730 Zeilen, Server- bzw. Export-gerendert -
   siehe app/web.py:venues_index/tools/export_static.py) - hier wird nur nach
   Namen gefiltert, kein Nachladen noetig. */
(function () {
  var input = document.getElementById('venue-search');
  var table = document.getElementById('venues-table');
  var empty = document.getElementById('venue-search-empty');
  if (!input || !table) { return; }
  var rows = Array.prototype.slice.call(table.querySelectorAll('.venue-row'));

  input.addEventListener('input', function () {
    var q = input.value.trim().toLowerCase();
    var visible = 0;
    rows.forEach(function (row) {
      var match = !q || row.dataset.name.indexOf(q) !== -1;
      row.hidden = !match;
      if (match) { visible += 1; }
    });
    empty.hidden = visible !== 0;
  });
})();

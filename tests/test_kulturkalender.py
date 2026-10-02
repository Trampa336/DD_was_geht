"""Kulturkalender: Titel ohne den angehängten Untertitel (Aufbau vom 02.10.2026)."""
from datetime import date

from ddwg.quellen import kulturkalender

SEITE = """
<div class="list-events">
  <section class="component-event">
    <div class="component-card"><span>20:00</span><span>Musik</span>
      <h3 class="title-event">
        <a href="https://www.kulturkalender-dresden.de/veranstaltung/sotiria">Sotiria</a>
        <span>
         Meine Liebe ist Gift - Tour 2026 + special guest             </span>
      </h3>
      <a href="/ort/beatpol">Beatpol</a></div>
  </section>
  <section class="component-event">
    <div class="component-card"><span>19:30</span><span>Musik</span>
      <h3 class="title-event">
        <a href="https://www.kulturkalender-dresden.de/veranstaltung/x">4. Fotowalk 2026 - Mit der Kamera</a>
      </h3>
      <a href="/ort/zwinger">Zwinger</a></div>
  </section>
</div>
"""


def test_titel_ohne_untertitel():
    events = kulturkalender._parse(SEITE, date(2026, 10, 17), "https://kk.example/heute")
    titel = sorted(e["title"] for e in events)
    assert titel == ["4. Fotowalk 2026 - Mit der Kamera", "Sotiria"]

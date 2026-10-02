"""objekt-klein-a-Scraper ohne Netz, gekürzter Aufbau der echten Seite (02.10.2026)."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg.quellen import objektkleina  # noqa: E402

NAV = """
<nav class="off-canvas off-canvas--left"><div class="off-canvas__inner"><ul>
  <li><a href="https://objektkleina.com/"><i data-feather="chevron-right"></i>Oktober 2026</a></li>
  <li><a href="https://objektkleina.com/september-2026-2/"><i data-feather="chevron-right"></i>September 2026</a></li>
  <li><a href="https://objektkleina.com/juni-2026-2-2/"><i data-feather="chevron-right"></i>Juli 2026</a></li>
</ul></div></nav>
"""

OKTOBER = NAV + """
<main>
<article class="child scroll-section" data-permalink="https://objektkleina.com/oktober-2026/comedy-flash-2/">
  <div class="child__header"><h2>Comedy Flash</h2></div>
  <div class="child__body">
    <div class="child__visual fitting--contain"><div class="scaled-image__inner">
      <img src="https://objektkleina.com/content/uploads/objektkleina-cf2.png" data-sizes="auto" class="media-element lazyload">
    </div></div>
    <div class="child__info">
      <dl>
        <dt class="is-hidden">Title:</dt><dd>
          Comedy Flash                  </dd>
        <dt>Type:</dt><dd>Comedy</dd>
        <dt>Date:</dt><dd>02 10 26</dd>
        <dt>Start:</dt><dd>19:00</dd>
      </dl>
      <div class="text text-size--large">
        <p>Comedyflash – Die Stand Up Comedy Show</p>
<p>Ein Abend im objekt klein a mit Live-Comedy? Witzig!</p>
      </div>
      <div class="text text-size--small">
        <p><a href="https://standup-republic.de/events/comedyflash-dresden-open-air_6759">Tickets im VVK</a></p>
      </div>
      <h2>Lineup</h2>
      <div class="text text-size--large">
        <p>Maja Stinnen<br>
Matti Mauro<br>
Luisa Tamm</p>
      </div>
    </div>
  </div>
</article>
<article class="child scroll-section" data-permalink="https://objektkleina.com/oktober-2026/routine/">
  <div class="child__header"><h2>ROUTINE w/ Das Beat &amp;&nbsp;Hyperaktivist</h2></div>
  <div class="child__body">
    <div class="child__info">
      <dl>
        <dt>Type:</dt><dd>Club</dd>
        <dt>Date:</dt><dd>03 10 26</dd>
        <dt>Start:</dt><dd>23:00</dd>
      </dl>
      <div class="text text-size--large">
        <p>Ich vermiss noch immer mein Cap, das ich auf der vorletzten ROUTINE vergessen hab.</p>
<p>Flo | 36 | Hat inzwischen ein neues Cap</p>
      </div>
      <div class="text text-size--small">
        <p>10€ bis 0000<br>
15€ ab 0000</p>
<p>⊘ no hate – just love ♡</p>
      </div>
      <h2>Lineup</h2>
      <div class="text text-size--large">
        <p>Das Beat<br>
Hyperaktivist</p>
<p><iframe title="Das Beat" src="https://w.soundcloud.com/player/"></iframe></p>
      </div>
    </div>
  </div>
</article>
<article class="child scroll-section" data-permalink="https://objektkleina.com/oktober-2026/traum-a/">
  <div class="child__header"><h2>Traum A</h2></div>
  <div class="child__body">
    <div class="child__info">
      <dl>
        <dt>Type:</dt><dd>Club</dd>
        <dt>Date:</dt><dd>17 10 26</dd>
        <dt>Start:</dt><dd>23:00</dd>
      </dl>
      <div class="text text-size--large">
        <p>lorem ipsum</p>
      </div>
      <div class="text text-size--small"><div>
<p>10€ bis 0000<br>
15€ ab 0000<br>
10€ ab 0400</p>
</div></div>
      <h2>Lineup</h2>
      <div class="text text-size--large">
        <p><a href="https://soundcloud.com/agilyagily">Agily</a><br>
<a href="https://soundcloud.com/bephaal">Bephål</a> ( SAFT )</p>
      </div>
    </div>
  </div>
</article>
<article class="child scroll-section" data-permalink="https://objektkleina.com/oktober-2026/symptoms/">
  <div class="child__header"><h2>SYMPTOMS</h2></div>
  <div class="child__body">
    <div class="child__info">
      <dl>
        <dt>Type:</dt><dd>Club</dd>
        <dt>Date:</dt><dd>24 10 26</dd>
        <dt>Start:</dt><dd>23:00</dd>
      </dl>
      <div class="text text-size--large">
      </div>
      <div class="text text-size--small">
      </div>
    </div>
  </div>
</article>
</main>
"""

SEPTEMBER = NAV + """
<article class="child scroll-section" data-permalink="https://objektkleina.com/september-2026-2/x/">
  <div class="child__header"><h2>Ende September</h2></div>
  <div class="child__info"><dl><dt>Date:</dt><dd>30 09 26</dd><dt>Start:</dt><dd>22:00</dd></dl></div>
</article>
"""


def test_menue_monate():
    seiten = objektkleina._monatsseiten(OKTOBER)
    assert seiten[(2026, 10)] == "https://objektkleina.com/"
    assert seiten[(2026, 7)] == "https://objektkleina.com/juni-2026-2-2/"


def test_parse_felder():
    ev = {e["title"]: e for e in objektkleina._parse(OKTOBER)}
    assert set(ev) == {"Comedy Flash", "ROUTINE w/ Das Beat & Hyperaktivist", "Traum A", "SYMPTOMS"}
    cf = ev["Comedy Flash"]
    assert cf["date"] == "2026-10-02" and cf["time"] == "19:00" and cf["venue"] == "objekt klein a"
    assert cf["raw_category"] == "Comedy"
    assert cf["url"] == "https://objektkleina.com/oktober-2026/comedy-flash-2/"
    assert cf["image_url"] == "https://objektkleina.com/content/uploads/objektkleina-cf2.png"
    assert cf["description"].startswith("Comedyflash – Die Stand Up Comedy Show\n")
    assert cf["description"].endswith("Lineup: Maja Stinnen, Matti Mauro, Luisa Tamm")
    assert cf["price_text"] is None  # nur ein Ticket-Link, kein Preis
    ro = ev["ROUTINE w/ Das Beat & Hyperaktivist"]
    assert ro["price_text"] == "10€ bis 0000 · 15€ ab 0000"
    assert ro["category"] == "musik"
    assert ro["image_url"] is None


def test_platzhalter_und_leer():
    ev = {e["title"]: e for e in objektkleina._parse(OKTOBER)}
    assert ev["Traum A"]["description"] == "Lineup: Agily, Bephål ( SAFT )"
    assert ev["SYMPTOMS"]["description"] is None and ev["SYMPTOMS"]["price_text"] is None


def test_scrape_range_holt_monate_laut_menue(monkeypatch):
    seiten = {objektkleina.URL: OKTOBER, "https://objektkleina.com/september-2026-2/": SEPTEMBER}
    geholt = []

    def fetch(url, **kw):
        geholt.append(url)
        return seiten[url]
    monkeypatch.setattr(objektkleina.base, "fetch_html", fetch)
    monkeypatch.setattr(objektkleina.base, "REQUEST_DELAY_SECONDS", 0)
    ev = objektkleina.scrape_range(date(2026, 9, 29), date(2026, 10, 10))
    assert geholt == [objektkleina.URL, "https://objektkleina.com/september-2026-2/"]
    assert [e["title"] for e in sorted(ev, key=lambda e: e["date"])] == [
        "Ende September", "Comedy Flash", "ROUTINE w/ Das Beat & Hyperaktivist"]

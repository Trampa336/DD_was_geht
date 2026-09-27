"""Hole-of-Fame-Scraper ohne Netz, mit dem Aufbau der echten Seiten (27.09.2026)."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddwg.quellen import holeoffame  # noqa: E402

UEBERSICHT = """
<table><tbody>
<tr> <td colspan="3"><h2 class="title">September</h2></td> </tr>
<tr> <td class="date">Mittwoch</td> <td> <span class="type badge">talk</span> </td> <td class="event_title"> <a href="/events/droht-ein-neuer-faschismus">Droht ein neuer Faschismus?</a> </td> </tr>
<tr class="additional_info"> <td></td> <td></td> <td> Vortrag und Diskussion mit Prof. Dr. Klaus Neumann<br> 19:00 Uhr </td> </tr>
<tr> <td colspan="3"><h2 class="title">Oktober</h2></td> </tr>
<tr> <td class="date">Donnerstag</td> <td> <span class="type badge">ausstellung</span> </td> <td class="event_title"> <a href="/events/vernissage-my-german-is-abstract">My German Is Abstract</a> </td> </tr>
<tr class="additional_info"> <td></td> <td></td> <td> Arbeiten von Nina Piatrouskaya und Nina Suptel<br> bis 16. Oktober </td> </tr>
<tr> <td class="date">Do. 15.</td> <td> <span class="type badge">film</span> </td> <td class="event_title"> <a href="/events/politkino-of-fame-wohin-mit-mir">PolitKino of Fame #04: Wohin mit mir?</a> </td> </tr>
<tr class="additional_info"> <td></td> <td></td> <td> Gemeinsam politisches Kino gucken<br> 19:00 Uhr </td> </tr>
<tr> <td colspan="3"><h2 class="title">November</h2></td> </tr>
<tr> <td class="date">Sa. 07.</td> <td> <span class="type badge">konzert</span> </td> <td class="event_title"> <a href="/events/tinted-house-ida-the-young">SUPERFEST: Tinted House</a> </td> </tr>
<tr class="additional_info"> <td></td> <td></td> <td> Indie </td> </tr>
</tbody></table>
"""


def detail(tag, beginn, preis="Eintritt frei"):
    return f"""<div class="card"><div class="s12"> <div class="col s4">{tag}</div>
    <div class="col s4">Begin: {beginn}</div> <div class="col s4">{preis}</div> </div></div>
    <div class="card"><div class="trix-content"><div><p>Text zu {tag}.</p></div></div></div>"""


DETAILS = {
    "https://holeoffame.de/events/droht-ein-neuer-faschismus": detail("30. September", "19:00"),
    "https://holeoffame.de/events/politkino-of-fame-wohin-mit-mir": detail("15. Oktober", "19:00", "Eintritt frei, Spende willkommen"),
    "https://holeoffame.de/events/tinted-house-ida-the-young": detail("07. November", "00:00"),
}
BEZUG = date(2026, 9, 27)


def test_uebersicht_monat_tag_und_ausstellung_weg():
    t = {x["title"]: x for x in holeoffame._parse_uebersicht(UEBERSICHT, BEZUG)}
    assert "My German Is Abstract" not in t
    assert t["Droht ein neuer Faschismus?"]["date"] is None
    assert t["Droht ein neuer Faschismus?"]["time"] == "19:00"
    assert t["PolitKino of Fame #04: Wohin mit mir?"]["date"] == date(2026, 10, 15)
    assert t["PolitKino of Fame #04: Wohin mit mir?"]["art"] == "film"
    assert t["SUPERFEST: Tinted House"]["untertitel"] == "Indie"


def test_detail_datum_und_null_uhr():
    tag, zeit, preis, text = holeoffame._parse_detail(DETAILS["https://holeoffame.de/events/tinted-house-ida-the-young"], BEZUG)
    assert tag == date(2026, 11, 7) and zeit is None and preis == "Eintritt frei"
    assert text == "Text zu 07. November."


def test_scrape_range(monkeypatch):
    seiten = dict(DETAILS, **{holeoffame.URL: UEBERSICHT})
    monkeypatch.setattr(holeoffame.base, "fetch_html", lambda url, **kw: seiten[url])
    monkeypatch.setattr(holeoffame, "DETAIL_DELAY_SECONDS", 0)
    ev = {e["title"]: e for e in holeoffame.scrape_range(BEZUG, date(2026, 10, 28))}
    assert set(ev) == {"Droht ein neuer Faschismus?", "PolitKino of Fame #04: Wohin mit mir?"}
    talk = ev["Droht ein neuer Faschismus?"]
    assert talk["date"] == "2026-09-30" and talk["time"] == "19:00" and talk["venue"] == "Hole of Fame"
    assert talk["description"].startswith("Vortrag und Diskussion")


def test_ohne_detail_und_ohne_tag_faellt_weg(monkeypatch):
    def fetch(url, **kw):
        if url == holeoffame.URL:
            return UEBERSICHT
        raise RuntimeError("weg")
    monkeypatch.setattr(holeoffame.base, "fetch_html", fetch)
    monkeypatch.setattr(holeoffame, "DETAIL_DELAY_SECONDS", 0)
    ev = {e["title"] for e in holeoffame.scrape_range(BEZUG, date(2026, 10, 28))}
    assert ev == {"PolitKino of Fame #04: Wohin mit mir?"}

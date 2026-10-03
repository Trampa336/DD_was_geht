"""Vorschau-Seiten zum Teilen: Bild, Titel und Ort in der Link-Vorschau (03.10.2026)."""
import os

from ddwg import ausgabe

EV = {"u": "abc123", "d": "2026-10-03", "t": "19:30", "ti": 'Konzert "A" & <B>', "o": "ostpol",
      "img": "https://example.org/bild.jpg"}
ORT = {"n": "Ostpol", "c": "https://example.org/ort.jpg"}


def test_vorschau_hat_og_angaben_und_leitet_weiter():
    h = ausgabe._vorschau_html(EV, ORT)
    assert '<meta property="og:title" content="Konzert &quot;A&quot; &amp; &lt;B&gt;">' in h
    assert '<meta property="og:description" content="Sa 3. Okt, 19:30 · Ostpol">' in h
    assert '<meta property="og:image" content="https://example.org/bild.jpg">' in h
    assert 'location.replace("../#t=abc123~2026-10-03~ostpol")' in h
    assert 'name="robots" content="noindex"' in h


def test_vorschau_bild_ersatz_und_ohne_uhrzeit():
    ev = dict(EV, img=None, t="00:00")
    h = ausgabe._vorschau_html(ev, ORT)
    assert 'og:image" content="https://example.org/ort.jpg"' in h
    assert 'og:description" content="Sa 3. Okt · Ostpol"' in h
    h = ausgabe._vorschau_html(dict(ev, o=None, **{"or": "Irgendwo"}), None)
    assert 'og:image" content="' + ausgabe.SEITE_URL + 'icon-512.png"' in h
    assert "~2026-10-03~" in h and "Irgendwo" in h


def test_vorschau_seiten_ersetzt_alte(tmp_path):
    alt = tmp_path / "t"
    alt.mkdir()
    (alt / "weg.html").write_text("alt")
    n = ausgabe.vorschau_seiten({"events": [EV], "orte": {"ostpol": ORT}}, str(tmp_path))
    assert n == 1
    assert sorted(os.listdir(alt)) == ["abc123.html"]

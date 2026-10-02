"""Bildgrößen: kleine Fassungen statt der größten (Scrollen am Handy, 02.10.2026)."""
from ddwg import ausgabe
from ddwg.quellen import base


def test_srcset_kleinste_ab_500():
    s = "https://kk/a_1920.jpg 1920w, https://kk/a_1200.jpg 1200w, https://kk/a_800.jpg 800w, https://kk/a_588.jpg 588w, https://kk/a_400.jpg 400w"
    assert base.srcset_waehlen(s) == "https://kk/a_588.jpg"


def test_srcset_keine_gross_genug_nimmt_breiteste():
    assert base.srcset_waehlen("https://kk/k.jpg 200w, https://kk/m.jpg 450w") == "https://kk/m.jpg"


def test_srcset_ohne_breiten_und_leer():
    assert base.srcset_waehlen("https://kk/x.jpg") == "https://kk/x.jpg"
    assert base.srcset_waehlen("") is None


def test_bild_youtube_klein_und_kk_platzhalter_weg():
    assert ausgabe._bild("https://i.ytimg.com/vi/ABC/maxresdefault.jpg") == "https://i.ytimg.com/vi/ABC/hqdefault.jpg"
    assert ausgabe._bild("https://i.ytimg.com/vi/ABC/hqdefault.jpg") == "https://i.ytimg.com/vi/ABC/hqdefault.jpg"
    assert ausgabe._bild("https://www.kulturkalender-dresden.de/img/fallback.jpg") is None
    assert ausgabe._bild("javascript:alert(1)") is None
    assert ausgabe._bild("https://example.org/b.jpg") == "https://example.org/b.jpg"

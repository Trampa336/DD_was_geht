"""Richtungen: Flavours (Orte) und Kategorien in einer Liste.

Ein Termin gehoert zu einer Richtung, wenn
  - sein Ort den passenden Flavour hat (orte/flavours.json, nur "haupt"),
  - ein Stichwort im Titel passt, oder
  - die Kategorie der Quelle passt (Demos, Familie, Feste, Sport).
Ort und Stichwort zaehlen nur, wenn die Kategorie nicht klar etwas anderes sagt:
Eine Lesung in der Chemiefabrik (Flavour Rock) ist Lesung, nicht Rock.

Bereiche (Musik, Kultur) fassen mehrere Richtungen zusammen. Ein Termin mit einer
Richtung bekommt auch den Schluessel seines Bereichs, ein Termin der Kategorie
"musik" ohne genauere Richtung nur "musik".

Stichworte werden auf dem Slug gesucht (normalize.slugify: klein, Umlaute
ausgeschrieben, Bindestriche als Wortgrenze). Neue Stichworte bitte mit einem
Test in tests/test_richtungen.py, auch fuer Fehlgriffe.
"""
import re

from .normalize import _SPORT_FALSE_FRIENDS_RE, _SPECTATOR_SPORT_RE, _SPORT_TITLE_RE, _is_film_venue, slugify

# Reihenfolge = Reihenfolge im Filter-Blatt. "fl" = Flavour aus orte/flavours.json.
BEREICHE = [
    {"k": "musik", "n": "Musik", "sub": [
        {"k": "club", "n": "Club & Party", "fl": "club"},
        {"k": "rock", "n": "Rock, Punk & Metal", "fl": "rock"},
        {"k": "indie", "n": "Indie & Bars", "fl": "indie"},
        {"k": "jazz", "n": "Jazz, Blues & Swing", "fl": "jazz"},
        {"k": "klassik", "n": "Klassik & Chor", "fl": "klassik"},
    ]},
    {"k": "kultur", "n": "Kultur", "sub": [
        {"k": "buehne", "n": "Theater & Bühne", "fl": "buehne"},
        {"k": "film", "n": "Kino & Film"},
        {"k": "wort", "n": "Lesung & Vortrag"},
        {"k": "kunst", "n": "Ausstellungen & Museen", "fl": "museum"},
    ]},
    {"k": "demo", "n": "Demos"},
    {"k": "familie", "n": "Familie", "fl": "familie"},
    {"k": "outdoor", "n": "Feste & Märkte"},
    {"k": "sport", "n": "Sport"},
]

_W = r"(?:^|-)"      # Wortanfang im Slug
_E = r"(?=-|$)"      # Wortende im Slug

STICHWORTE = {
    "club": re.compile(
        _W + r"(?:techno|[a-z]*house|rave|[a-z]*party|partys|dj|djs|djane|dj-?set|electro|elektro"
        r"|electronic|drum-(?:and|n)-bass|dnb|disco|hip-?hop|rap|dancehall|clubnacht|bass|trance"
        r"|psytrance|goa|afrobeats?|reggaeton|ebm|darkwave|minimal)" + _E),
    "rock": re.compile(
        _W + r"(?:[a-z]*rock|[a-z]*punk|[a-z]*metal|hardcore|grunge|ska|rockabilly|rock-n-roll"
        r"|stoner|doom|thrash|emo|garage)" + _E),
    "indie": re.compile(
        _W + r"(?:indie|indiepop|singer-songwriter|songwriter|folk|pop|acoustic|akustik|unplugged"
        r"|liedermacher|chanson)" + _E),
    "jazz": re.compile(
        _W + r"(?:[a-z]*jazz|blues|swing|soul|funk|dixie|dixieland|bebop|bigband|big-band"
        r"|jam-?session|jamsession)" + _E),
    "klassik": re.compile(
        r"klassik|orchester|sinfoni|symphon|philharmon|kammermusik|kantate|oratorium|liederabend"
        r"|requiem|motette|kirchenmusik|klavierabend|streichquartett|orgel"
        + r"|" + _W + r"(?:chor|choere|chorkonzert|quartett|bach|mozart|beethoven|haendel)" + _E),
    "buehne": re.compile(
        r"theater|kabarett|comedy|comedian|operette|ballett|musical|schauspiel|revue|poetry|slam"
        r"|zirkus|variete|kleinkunst|improtheater|lesebuehne|stand-?up"
        + r"|" + _W + r"(?:oper|impro|show|musical)" + _E),
    "film": re.compile(
        _W + r"(?:film|filme|kino|doku|dokumentarfilm|kurzfilm|kurzfilme|filmnacht|filmabend"
        r"|kinoabend|filmreihe|filmvorfuehrung|sneak)" + _E),
    "wort": re.compile(
        r"lesung|vortrag|vortraege|gespraech|diskussion|podium|literatur|buchpremiere"
        r"|buchvorstellung|erzaehlcafe"),
    "kunst": re.compile(
        r"ausstellung|vernissage|finissage|museum|galerie|atelier" + r"|" + _W + r"kunst" + _E),
}

# Fehlgriffe, die ein Stichwort sonst einsammelt
FALSCHE_FREUNDE = {
    "rock": re.compile(r"barock|rocky|minirock|(?:^|-)[a-z]*punkt" + _E),
    "club": re.compile(r"kinderparty|kinder-party|(?:^|-)house-of" + _E),
    "indie": re.compile(r"popcorn|pop-up|popup"),
}

# Sport: Mitmachen (Yoga, Laufen, Team-Challenge), nicht Zuschauen. Senioren- und
# Familienangebote zaehlen ausdruecklich nicht (Davids Entscheidung, 29.09.2026).
_SPORT_EXTRA_RE = re.compile(
    r"team-?challenge|firmenlauf|spendenlauf|stadtlauf|volkslauf|fun-?run|(?:^|-)run" + _E
    + r"|" + _W + r"(?:yoga|lauf|laufen)" + _E)
_SPORT_AUSGESCHLOSSEN_RE = re.compile(
    r"senior|(?:^|-)ue-?(?:50|55|60|65|70)" + _E + r"|(?:^|-)(?:50|60|65)-?plus" + _E
    + r"|kinder|kids|familie|eltern|baby|babys|kleinkind|mutter-kind|vater-kind|kita|seniorenheim"
    r"|schueler|(?:^|-)jugend")

# Welche Kategorien ein Stichwort oder Flavour "ueberschreiben" darf
_BEREICH_KAT = {"musik": "musik", "kultur": "kultur"}


def _sub_von(k):
    for b in BEREICHE:
        for s in b.get("sub", []):
            if s["k"] == k:
                return b["k"], s
    return None, None


def _ist_sport(slug, kategorie, ort_slug=""):
    if kategorie in ("familie", "demo"):
        return False
    # Senioren/Familie auch am Ort erkennen ("Yoga mit Pat" in einer Kindertagesstaette)
    if _SPECTATOR_SPORT_RE.search(slug) or _SPORT_AUSGESCHLOSSEN_RE.search(slug + "-" + ort_slug):
        return False
    if kategorie == "sport":
        return True
    treffer = _SPORT_TITLE_RE.search(slug) or _SPORT_EXTRA_RE.search(slug)
    return bool(treffer) and not _SPORT_FALSE_FRIENDS_RE.search(slug)


def fuer(titel, kategorie, ort=None, ort_name=None, flavour_von_ort=None):
    """Liste der Richtungs-Schluessel eines Termins, Bereiche eingeschlossen.

    flavour_von_ort: {ort_slug: flavour_key} aus orte/flavours.json (nur haupt)."""
    slug = slugify(titel)
    flavour = (flavour_von_ort or {}).get(ort)
    rt = []
    for b in BEREICHE:
        for s in b.get("sub", []):
            k = s["k"]
            if kategorie not in (b["k"], "sonstiges"):
                continue
            ueber_ort = bool(s.get("fl")) and s["fl"] == flavour
            ueber_wort = bool(STICHWORTE[k].search(slug)) and not (
                k in FALSCHE_FREUNDE and FALSCHE_FREUNDE[k].search(slug))
            # Kino als Ort nur ohne eigenen Flavour: Die Schauburg ist als Buehne
            # eingetragen und zeigt in den Kalendern vor allem Kabarett und Lesungen.
            if k == "film" and not flavour and _is_film_venue(ort_name):
                ueber_ort = True
            if ueber_ort or ueber_wort:
                rt.append(k)
        if any(_sub_von(k)[0] == b["k"] for k in rt) or kategorie == b["k"] and "sub" in b:
            rt.append(b["k"])
    if kategorie == "demo":
        rt.append("demo")
    if kategorie == "familie" or (flavour == "familie" and kategorie in ("familie", "sonstiges")):
        rt.append("familie")
    if kategorie == "outdoor":
        rt.append("outdoor")
    if _ist_sport(slug, kategorie, slugify(ort_name)):
        rt.append("sport")
    # Bereich ohne Richtung: Reihenfolge stabil, keine Doppelten
    return list(dict.fromkeys(rt))


def fuer_ausgabe():
    """Aufbau fuer die Seite: Bereiche mit Richtungen (ohne interne Felder)."""
    return BEREICHE

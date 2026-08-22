"""Normalisierung von Rohdaten aus den Scrapern: Kategorien, Schlüsselwörter, IDs."""
import hashlib
import re
import unicodedata

# Rohe Kategorie-/Genre-Bezeichnungen der Quellseiten -> unsere Buckets.
# Wird als erstes versucht; greift das nicht, entscheidet _classify_by_keywords().
RAW_CATEGORY_MAP = {
    "musik": "musik", "konzert": "musik", "konzerte": "musik", "party": "musik",
    "club": "musik", "dj": "musik", "rave": "musik",
    # "festival" stand hier bewusst und ist bewusst wieder raus: die Quellseite
    # benutzt das Label als Sammelbecken. Von 200 so markierten Einträgen waren
    # (gemessen am 21.08.2026) nur ~17% wirklich Musik - der Rest sind Vorträge,
    # Workshops, Führungen, ein Board-Game-Abend und das komplette Open-Air-
    # Kinoprogramm. Ohne diesen Eintrag entscheidet der Titel (und bei Kinos der
    # Ort, siehe _is_film_venue).
    "buehne": "kultur", "bühne": "kultur", "theater": "kultur", "oper": "kultur",
    "ballett": "kultur", "kunst": "kultur", "ausstellung": "kultur",
    "lesung": "kultur", "vortrag": "kultur", "gespraech": "kultur", "kabarett": "kultur",
    "film": "kultur", "kino": "kultur", "diskussion": "kultur",
    "literatur": "kultur",
    "kinder": "familie", "familie": "familie",
    "fuehrung": "fuehrungen", "fuehrungen": "fuehrungen",
    "rundgang": "fuehrungen", "entdeckungen": "fuehrungen",
    "markt": "outdoor",
    "sport": "sport", "fitness": "sport", "bewegung": "sport",
    # Bewusst NICHT hier: "Fest". Die Schluessel werden per Teilstring geprueft,
    # "fest" wuerde also auch auf "Festival" passen und damit die oben bewusst
    # entfernte Zuordnung durch die Hintertuer wieder einfuehren (gemessen:
    # "Festival"/"Board-Game-Abend" landete damit in outdoor). CyberSAX-
    # Festzeilen heissen ohnehin fast immer "...fest" im Titel und werden von
    # KEYWORD_CATEGORY_MAP eingefangen.
    #
    # Bewusst NICHT hier: "Workshops", "Aktionen" und "Treff". Das sind die
    # restlichen Abschnittsueberschriften von CyberSAX, und alle drei
    # beschreiben die Form der Veranstaltung, nicht ihr Thema - derselbe Grund,
    # aus dem "festival" oben wieder rausgeflogen ist. Der "Offene DJ*-Treff"
    # im AZ Conni laeuft dort unter "Workshop" und ist trotzdem Musik. Ein
    # Titel-Stichwort entscheidet hier besser; "workshop" steht deshalb nur in
    # KEYWORD_CATEGORY_MAP, wo es erst zieht, wenn der Titel nichts Besseres
    # hergibt ("Manifestation Workshop 1" -> kultur).
}

# Fallback: Schlüsselwörter im Titel, falls die Quelle keine brauchbare
# Kategorie liefert oder eine, die nicht in RAW_CATEGORY_MAP steckt.
KEYWORD_CATEGORY_MAP = {
    # Kino zuerst: "Radeberger Filmnacht" enthält sonst "nacht" und landete über
    # das Nightlife-Vokabular weiter unten in musik. "filmmusik" muss wiederum
    # vor "film" stehen - erste Teilstring-Übereinstimmung gewinnt.
    "filmmusik": "musik",
    "film": "kultur", "kino": "kultur",
    "konzert": "musik", "musik": "musik", "party": "musik", "dj": "musik",
    "disco": "musik", "band": "musik", "sound": "musik", "session": "musik",
    "jam": "musik",
    # Nightlife-Vokabular, wie es auf Rauze vorkommt (viele davon in Titeln
    # von Events, die dort nur als "Sonstiges" oder "Außerhalb" gelistet sind)
    "rave": "musik", "techno": "musik", "openair": "musik", "open-air": "musik",
    # "nachtwaechter" muss vor "nacht" stehen: die Nachtwaechter-Rundgaenge sind
    # kostuemierte Stadtfuehrungen und haben mit Nightlife nichts zu tun.
    "nachtwaechter": "kultur",
    "nacht": "musik", "night": "musik", "invites": "musik", "vinyl": "musik",
    # Klassik und Genre-Namen: ohne diese landeten die "Wiener Philharmoniker"
    # und "Drei Joker des Jazz" in sonstiges, seit "Festival" nichts mehr
    # entscheidet. "tanztheater" muss vor "tanz" stehen (erster Treffer gewinnt).
    "tanztheater": "kultur",
    "philharmon": "musik", "sinfoni": "musik", "orchester": "musik",
    "klassik": "musik", "jazz": "musik", "blues": "musik", "swing": "musik",
    "soul": "musik", "chor": "musik", "liederabend": "musik", "tanz": "musik",
    "theater": "kultur", "oper": "kultur", "ballett": "kultur", "buehne": "kultur",
    "figurentheater": "kultur", "kabarett": "kultur", "revue": "kultur",
    "ausstellung": "kultur", "galerie": "kultur", "vernissage": "kultur",
    "schauspiel": "kultur", "premiere": "kultur", "komoedie": "kultur",
    "zirkus": "kultur", "kulturtage": "kultur",
    "kinder": "familie", "familie": "familie",
    "fuehrung": "fuehrungen", "rundgang": "fuehrungen",
    "stadtrundfahrt": "fuehrungen",
    # Die größten Gruppen, die bisher ohne Rohkategorie in "sonstiges" landeten
    # (aus 1734 sonstiges-Titeln der Live-DB ausgezählt): Elbdampfer und
    # Stadtrundfahrten, Werks- und Schlossbesichtigungen, Museumsangebote.
    # Die Schiffsfahrten stehen hier bei den Führungen und nicht bei den
    # Festen: eine Schlösserfahrt ist eine geführte Tour mit Abfahrtszeit,
    # kein Termin zum Hingehen-wann-man-will.
    "schiff": "fuehrungen", "schloesserfahrt": "fuehrungen",
    "stadtfahrt": "fuehrungen", "elbfahrt": "fuehrungen",
    "dampfer": "fuehrungen", "besichtigung": "fuehrungen",
    "audioguide": "fuehrungen", "stadtrundgang": "fuehrungen",
    "schauwerkstatt": "kultur", "museum": "kultur", "sonderausstellung": "kultur",
    "vortrag": "kultur", "lesung": "kultur",
    "workshop": "kultur", "matinee": "kultur",
    "fest": "outdoor", "markt": "outdoor",
}

# --- Sport (Mitmachen, nicht Zuschauen) ---------------------------------
# Gemeint sind Termine zum Selbstbewegen: Yoga, Pilates, offene Radausfahrten,
# Lauftreffs, Klettern. Ausdruecklich NICHT gemeint ist Zuschauersport
# (Fussball, Ligaspiele, Heimspiele) - der bleibt aussen vor.
#
# Warum eigene Regexe statt Eintraegen in den Maps oben: die Maps matchen per
# Substring und werden erst nach RAW_CATEGORY_MAP befragt. Beides passt hier
# nicht. "Yoga im Alaunpark" laeuft auf der Quellseite unter der Rohkategorie
# "Festival" und landete damit in musik, ohne dass der Titel je geprueft wurde.
# Deshalb wird Sport als Titel-Vorpruefung VOR den Maps ausgewertet - und mit
# Wortgrenzen, damit "Weinbergswanderung" oder "Der Wanderer" nicht mitkommen.
#
# Bewusst NICHT hier: Kampfsport ("karate", "judo", "aikido"). Die Treffer im
# Bestand sind durchweg "Karate Anfaengerkurse fuer Kinder" und stehen richtig
# in familie - und familie steht in EXCLUDED_CATEGORIES, ein Umzug haette sie
# zusaetzlich in den Newsletter gespuelt.
_SPORT_TITLE_RE = re.compile(
    r"yoga|pilates|qi-?gong|tai-?chi|taiji|zumba|aerobic|gymnastik|faszien"
    r"|calisthenics|crossfit|bootcamp|workout|fitness|nordic-walking"
    r"|marathon|triathlon|duathlon|jogging|schwimmkurs|schwimmen"
    # Yoga-Stile ohne das Wort "Yoga" im Titel - die Studios kuendigen ihre
    # Kurse oft nur unter dem Stil an ("Kundalini-Aktivierung").
    r"|hatha|vinyasa|kundalini|ashtanga|iyengar|(?:^|-)asana"
    # Tanz nur als Kurs/Workshop/Treff, NIE als "-abend": "SALSA Tanzabend"
    # und "Saloppe SalsaTanzAbend" sind Nightlife und gehoeren in musik.
    r"|(?:^|-)(?:tanzkurs|tanzworkshop|tanzstunde|tanztreff|tanzschule)"
    r"|meditat"
    # Bewusst nur die Komposita, nicht das blanke "atem": das faengt sonst das
    # Ensemble "Sospiratem" (Konzert). Aus demselben Grund steht "achtsam"
    # nirgends hier - es wuerde die Krimikomoedie "ACHTSAM MORDEN" einsammeln.
    r"|(?:^|-)atem(?:workshop|kurs|uebung|training|reise)"
    r"|feldenkrais|alexandertechnik|(?:^|-)entspannungs(?:kurs|training)"
    r"|rueckbildung|beckenboden|wassergymnastik|aquafitness|aquajogging"
    r"|(?:^|-)(?:tischtennis|badminton|federball|slackline|parkour|discgolf)"
    r"|(?:^|-)(?:stadtradeln|radtreff|feierabendrunde)|(?:^|-)bogenschiessen"
    r"|(?:^|-)(?:rueckenfit|rueckenschule|lauftreff|laufgruppe|laufkurs)"
    r"|(?:^|-)(?:fahr)?rad(?:tour|touren|ausfahrt|fahrt|rundfahrt|korso|nacht|demo)"
    r"|(?:^|-)(?:radeln|critical-mass|sternfahrt)"
    r"|(?:^|-)wander(?:ung|ungen|n|tour|touren)(?:-|$)"
    r"|(?:^|-)(?:klettern|kletterkurs|klettertreff|bouldern|boulder-)"
    r"|(?:^|-)(?:kanu|kajak|paddeln|paddel-|rudern|drachenboot)"
    r"|(?:^|-)(?:skaten|skate-|inline|inliner|rollschuh)"
    r"|(?:^|-)sport(?:fest|tag|treff|kurs|angebot|abzeichen)"
    r"|(?:^|-)(?:mitmachsport|breitensport|volkssport)"
    r"|(?:^|-)[a-z]*lauf(?:e|s)?(?=-|$)"
)

# Gegenprobe: "...lauf" faengt sonst Alltagswoerter, und ein Vortrag ueber das
# Wandern ist eine Lesung und kein Wanderausflug.
_SPORT_FALSE_FRIENDS_RE = re.compile(
    r"(?:^|-)(?:ab|ver|durch|ein|aus|zu|an|um|rund|spiel)lauf(?:e|s)?(?=-|$)"
    r"|lesung|vortrag|buchvorstellung|buchpremiere|ausstellung|vernissage"
)

# Zuschauersport - blockt den Sport-Bucket, auch wenn die Quelle "Sport" sagt.
_SPECTATOR_SPORT_RE = re.compile(
    r"fussball|handball|eishockey|basketball|volleyball"
    r"|heimspiel|auswaertsspiel|punktspiel|testspiel|spieltag|laenderspiel"
    # "liga" bewusst NICHT als [a-z]*liga: das fing im Bestand ausschliesslich
    # den Nachnamen im "Yoga | Simon Scheliga"-Kurs ein und schob den Termin aus
    # dem Sport-Bucket. Echte Ligazeilen heissen mit Praefix oder allein "Liga".
    r"|(?:^|-)(?:\d-)?(?:bundes|kreis|landes|ober|nord|sued|regional|verbands"
    r"|bezirks|stadt|amateur|profi|damen|herren|jugend|champions|euro)?liga(?:-|$)"
    r"|(?:^|-)pokal|(?:^|-)derby|public-viewing"
    r"|(?:^|-)(?:dynamo|dsc|monarchs|titans)(?:-|$)|(?:^|-)vs(?:-|$)"
)


def _is_sport(slug):
    """Mitmach-Sport im Titel? Zuschauersport zaehlt ausdruecklich nicht."""
    if _SPECTATOR_SPORT_RE.search(slug):
        return False
    if not _SPORT_TITLE_RE.search(slug):
        return False
    return not _SPORT_FALSE_FRIENDS_RE.search(slug)


# --- Kino als Ort ----------------------------------------------------------
# Die Filmnächte am Elbufer laufen auf der Quellseite unter "Festival", und die
# Filmtitel selbst ("Sonnenallee", "Zoomania 2", "In the Grey") enthalten kein
# einziges Genre-Wort. Der einzige verlässliche Hinweis ist der Ort.
#
# Das ist NICHT die Ortsnamen-Falle aus dem README: dort ging es darum, dass
# Ortsnamen zufällig Genre-Wörter enthalten ("Jazzclub Tonne", "Landesbühnen
# Sachsen") und deshalb nicht in die allgemeine Stichwortsuche dürfen. Hier
# steht eine ausdrückliche, kurze Liste Dresdner Spielstätten, die nichts
# anderes zeigen als Filme.
_FILM_VENUE_RE = re.compile(
    r"filmnaechte|rundkino|kristallpalast|schauburg|programmkino|zentralkino"
    r"|lichtspiel|cinemaxx|thalia-kino|kino-im-kasten"
)


def _is_film_venue(venue):
    return bool(venue and _FILM_VENUE_RE.search(slugify(venue)))


_STOPWORDS = {
    "der", "die", "das", "und", "mit", "von", "im", "in", "am", "auf", "ein",
    "eine", "einer", "einen", "zum", "zur", "an", "bei", "fuer", "für", "des",
    "dem", "den", "vom", "als", "auch", "ist", "sind", "open", "air", "tour",
}


def slugify(text):
    """Stabiler, ASCII-only Schlüssel: Kleinbuchstaben, ohne Umlaute/Sonderzeichen."""
    if not text:
        return ""
    text = text.strip().lower()
    replacements = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


def classify_category(raw_category, title, venue=None):
    """Ordnet eine rohe Quellkategorie + Titel einem unserer Buckets zu.

    venue ist optional und wird ausschließlich für die Kino-Erkennung benutzt
    (siehe _is_film_venue) - nicht für die allgemeine Stichwortsuche.
    """
    slug = slugify(title)
    if _is_sport(slug):
        return "sport"
    key = slugify(raw_category).replace("-", "")
    for raw_key, bucket in RAW_CATEGORY_MAP.items():
        if raw_key.replace("-", "") in key:
            # Quelle sagt "Sport", Titel ist ein Ligaspiel: nicht unser Bucket.
            if bucket == "sport":
                return "sonstiges" if _SPECTATOR_SPORT_RE.search(slug) else "sport"
            return bucket
    # Erst NACH der Rohkategorie, anders als der Sport-Vorabcheck: sagt die
    # Quelle ausdrücklich "Konzert", ist es auch am Kino-Ort ein Konzert
    # (Wincent Weiss und Clueso spielen live bei den Filmnächten). Die Regel
    # greift genau dann, wenn die Quelle nichts Brauchbares geliefert hat - und
    # das ist beim Filmprogramm der Normalfall, seit "Festival" nicht mehr zählt.
    if _is_film_venue(venue):
        return "kultur"
    return _classify_by_keywords(title)


def _classify_by_keywords(title):
    slug = slugify(title)
    for keyword, bucket in KEYWORD_CATEGORY_MAP.items():
        if keyword in slug:
            return bucket
    return "sonstiges"


def extract_keywords(title, max_n=3):
    """Grobe Schlüsselwörter aus dem Titel (für die Scoring-Feature-Keys)."""
    slug = slugify(title)
    words = [w for w in slug.split("-") if len(w) >= 4 and w not in _STOPWORDS]
    # Längste/markanteste Wörter zuerst, stabil sortiert.
    words = sorted(set(words), key=lambda w: (-len(w), w))
    return words[:max_n]


def normalize_time(raw_time):
    """Extrahiert die Startzeit HH:MM aus Strings wie '19:00-20:30' oder '19 Uhr'."""
    if not raw_time:
        return None
    match = re.search(r"(\d{1,2})[:.](\d{2})", raw_time)
    if not match:
        return None
    hour, minute = int(match.group(1)), match.group(2)
    return f"{hour:02d}:{minute}"


def make_event_uid(date, time, title, venue):
    """Stabile ID, damit dasselbe Event aus mehreren Quellen zusammenfällt
    (z.B. ein Konzert, das sowohl im Kulturkalender als auch auf Rauze steht)."""
    basis = f"{date}|{time or ''}|{slugify(title)}|{slugify(venue)}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]

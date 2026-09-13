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
    "disco": "musik",
    # "band" hat denselben Fehlerfreund-Fehler wie "rave"/"jam" unten
    # (faengt "Bundesverbands"/"Chorverband", P4e 2026-09-11: 1 Fall im
    # Bestand real falsch - "Jahrestagung des Bundesverbands
    # Museumspaedagogik" landet in musik statt kultur), aber OHNE saubere
    # Grenzregel: "Bigband" und "Banda Comunale" (echte Treffer im Bestand)
    # haben exakt dieselbe Form wie "Verband"/"Bandscheibenvorfall"
    # (Praefix/Suffix ohne Bindestrich) - eine Bindestrich-Regel wie bei
    # "-rave" wuerde die echten Treffer mit rauswerfen. Bewusst NICHT
    # gefixt (ein Konferenztitel, keine Sperrliste gebaut) - siehe P4e-Bericht.
    "band": "musik", "sound": "musik", "session": "musik",
    # NICHT das blanke "jam": das faengt den Vornamen "Benjamin" ueberall dort,
    # wo er in einem Titel auftaucht (3 Faelle im Bestand, u.a. eine
    # Podiumsdiskussion und zwei "Tatortreiniger"-Theaterabende - alle drei
    # faelschlich musik, P4e 2026-09-11). Alle echten Treffer im Bestand
    # heissen "Jamsession" (mit oder ohne Leerzeichen) - "jamsession" faengt
    # sie unveraendert und "Benjamin" nicht mehr.
    "jamsession": "musik",
    # Nightlife-Vokabular, wie es auf Rauze vorkommt (viele davon in Titeln
    # von Events, die dort nur als "Sonstiges" oder "Außerhalb" gelistet sind)
    # NICHT das blanke "rave": das faengt "Travestie", "Gravestone" und
    # "Ravenshope" (4 Faelle im Bestand, P4e 2026-09-11) - u.a. eine
    # Travestie-Revue, die dadurch nie bis zum treffenderen "revue"-Schluessel
    # weiter unten kam. Beide echten Treffer im Bestand stehen als letztes
    # Wort des Titels ("... Coffee Rave", "...90er Rave") - "-rave" (mit
    # Bindestrich) faengt genau das und keins der vier Fehltreffer.
    "-rave": "musik", "techno": "musik", "openair": "musik", "open-air": "musik",
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
    # "fuehrung" faengt die Substantiv-Form, aber nicht die gebeugten
    # Partizip-Formen ("geführter", "geführte", "geführten") - "Geführter
    # Kuppelaufstieg" oder "...an kostenlosen geführten Rundgängen teil"
    # enthalten "fuehrung" nirgends im Slug. "gefuehrt" faengt alle Beugungen
    # in einem Rutsch; keine Kollisionen im Bestand gefunden (P4e, 2026-09-11).
    "gefuehrt": "fuehrungen",
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
    # Orgel: muss NACH "fuehrung"/"rundgang" stehen. "Wort & Orgelklang mit
    # zentraler Kirchenführung" enthaelt beides ("orgelklang" und
    # "kirchenfuehrung") - stuende orgel frueher im Dict, kaeme der erste
    # Treffer aus der falschen Zeile und das (bewusst so belassene) Fuehrungs-
    # Ergebnis kippte nach musik. Ohne Fuehrungswort im Titel ist eine
    # Orgel-Zeile fast immer ein Konzert (gemessen: 23 von 30 Orgel-Titeln im
    # Bestand liefen schon vorher ueber "konzert" in musik, P4e 2026-09-11).
    "orgel": "musik",
    # "Messe" ist zweideutig: kirchenmusikalisches Werk ("BACH - Messe in
    # h-Moll") vs. Verkaufs-/Fachmesse ("Messe für Alleinerziehende"). Die
    # Werk-Form steht im Bestand ausnahmslos als "Messe in <Ton>-Moll/Dur" -
    # "messe-in" muss deshalb VOR dem blanken "messe" stehen, sonst gewinnt
    # immer die Messe-als-Markt-Lesart. Nur 2 Beispiele im Bestand (P4e,
    # 2026-09-11), aber beide Frauenkirche-Konzerte, kein Fehlklassifikations-
    # Risiko erkennbar.
    "messe-in": "musik",
    "messe": "outdoor",
    "fest": "outdoor", "markt": "outdoor",
}

# --- "Tour" -----------------------------------------------------------------
# Bewusst NICHT als einfacher Dict-Eintrag: "Tour" heisst im Bestand sowohl
# "gefuehrte Besichtigung" (Elbschloesser-Tour, Weinerlebnis-Tour, Guided
# Tour im Residenzschloss) als auch "Konzerttournee" (Kilminister Tour 25,
# Vanessa Mai Traumfabrik Tour 2026) - ein blankes "tour"-Schluesselwort waere
# darum haeufiger falsch als richtig. Gemessen an den sonstiges-Titeln mit
# "tour" im Slug (Stand 2026-09-11, volle Reclassify-Probe): von 16 dadurch
# neu getroffenen Titeln waren 12 echte Fuehrungen/Touren und 4 Konzert-
# tourneen. Zwei Filter dagegen:
#   1. Wortmuster, die eine Tournee-Ankuendigung fast sicher verraten:
#      Jahreszahl/Zaehlnummer nach "Tour", "Jubilaeumstour", "Anniversary
#      Tour", "auf/on Tour", "Tournee", "Deutschlandtour" (Lese-/Promotour).
#   2. Eine kurze Sperrliste reiner Live-Musik-Venues: alle 4 der so
#      gemessenen Fehltreffer ("Uwe Kotteck - 50 Jahre Buehne Tour
#      Rockballaden", "Sebastian Wappler STILL HOPE TOUR", "POINTS OF
#      CONCEPTION ... The Light Inside Tour", "THE GARDENER & THE TREE (CH)
#      SOLE TOUR") standen an genau diesen vier Adressen und nirgends sonst -
#      keins davon zeigt je eine echte Fuehrung. "Tante JU Liveclub" steht mit
#      dabei, auch wenn seine beiden Tour-Titel schon ueber Filter 1 fallen
#      (Verteidigung in der Tiefe fuer kuenftige Ankuendigungen ohne Jahr).
#      Diese Liste ist NICHT dieselbe Mechanik wie venues.kind (Schritt 3) -
#      sie ist eine reine Namensliste, genau wie _FILM_VENUE_RE oben.
_TOUR_TITLE_RE = re.compile(r"tour(?:-|$)")
_TOUR_FALSE_FRIENDS_RE = re.compile(
    r"tour-?(?:19|20)\d{2}|tour-\d{1,2}(?:-|$)"
    r"|jubilaeumstour|anniversary|tournee|deutschlandtour"
    r"|(?:^|-)auf-tour|(?:^|-)on-tour"
)
_TOUR_MUSIC_VENUE_RE = re.compile(
    r"chemiefabrik-dresden|theater-am-wettiner-platz|beatpol-dresden"
    r"|dixiebahnhof-dresden|tante-ju-liveclub"
)


def _is_guided_tour(slug, venue=None):
    """Letzter Fallback in _classify_by_keywords, siehe Kommentar oben."""
    if not _TOUR_TITLE_RE.search(slug):
        return False
    if _TOUR_FALSE_FRIENDS_RE.search(slug):
        return False
    return not _TOUR_MUSIC_VENUE_RE.search(slugify(venue) if venue else "")


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


# --- Serien-Schluessel (P5x im Frontend, P5c auf dem Server) ---------------
# EINE Vorstellung davon, was eine "Serie"/ein "Lauf" ist - zwei
# Implementierungen, weil die Liste im Browser gruppiert und die Herzen auf dem
# Server gespeichert werden. Das Gegenstueck heisst runSlug()/runKey() in
# app/static/app.js; tests_smoke.py haelt beide mit einem Differenztest ueber
# genau die Zeichen zusammen, an denen sie auseinanderlaufen KOENNTEN.
#
# Bewusst NICHT slugify(): das wirft ueber encode("ascii", "ignore") alles weg,
# was nach der NFKD-Zerlegung kein ASCII ist ("Køb Ø" -> "kb"), waehrend
# JavaScript dieselbe Stelle ueber [^a-z0-9]+ zu einem Bindestrich macht
# ("k-b"). Fuer einen Schluessel, der auf beiden Seiten GLEICH herauskommen
# muss, ist dieser Unterschied kein Detail, sondern ein Herz, das in der Liste
# nicht mehr als geherzt erkannt wird.
def run_slug(text):
    """Wie runSlug() in app/static/app.js: Kleinschrift, Umlaute ausgeschrieben,
    Diakritika entfernt, alles Uebrige zu Bindestrichen - und ohne den
    Wortfilter von dedup.py._title_tokens() (siehe P5w: ein gepunkteter Titel
    bliebe sonst schluessellos)."""
    text = (text or "").lower()
    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def run_key(date, venue, title):
    """Der Schluessel einer Serie: Tag + Ort + normalisierter Titel.

    Der TAG gehoert dazu (Entscheidung P5c, siehe Bericht): app.js gruppiert
    ohnehin nur innerhalb eines Tages (byDay), der Schluessel wird durch das
    Datum also nicht enger - er wird nur ueber Tage hinweg eindeutig. Genau das
    braucht ein Herz: "die Domfuehrung am 20.09." und nicht "jede Domfuehrung,
    die es je geben wird".

    venue ist der ROHE Ortsstring (events.raw_venue, im Event-Dict "venue") -
    dasselbe Feld, das app.js benutzt. Dass zwei Schreibweisen derselben Venue
    ("Ostpol" / "Ostpol Dresden") verschiedene Schluessel ergeben, ist damit
    uebernommen und nicht neu; aufgefangen wird es beim Wiederanknuepfen ueber
    die Doppelungs-Buchung (db.relink_hearts).
    """
    return f"{date}|{run_slug(venue)}|{run_slug(title)}"


def run_key_for_event(event):
    """run_key() aus einem Event-Dict, wie es db.events_for_range() liefert."""
    return run_key(event["date"], event.get("venue"), event.get("title"))


def classify_category(raw_category, title, venue=None):
    """Ordnet eine rohe Quellkategorie + Titel einem unserer Buckets zu.

    venue ist optional. Genutzt fuer die Kino-Erkennung (_is_film_venue) UND,
    als letzter Fallback in _classify_by_keywords, fuer die Musikclub-
    Sperrliste des Tour-Erkenners (_is_guided_tour) - nicht fuer die
    allgemeine Stichwortsuche selbst.
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
    return _classify_by_keywords(title, venue)


def _classify_by_keywords(title, venue=None):
    slug = slugify(title)
    for keyword, bucket in KEYWORD_CATEGORY_MAP.items():
        if keyword in slug:
            return bucket
    # Letzter Fallback, absichtlich NACH der Dict-Schleife: eine echte
    # Keyword-Traefferzeile soll immer gewinnen, auch wenn der Titel
    # nebenbei "Tour" enthaelt (siehe _is_guided_tour-Kommentar oben).
    if _is_guided_tour(slug, venue):
        return "fuehrungen"
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


# ===========================================================================
# Tags (Kontext, nicht Kategorie) - P4e
# ===========================================================================
# David: Kategorie = WAS ein Event IST (Musik, Theater, Fuehrung), Tag =
# KONTEXT (Kirche, Museum, Open Air, Klassik, Techno). Beispiel: ein
# Orgelkonzert in einer Kirche ist Kategorie Musik mit Tags Kirche + Klassik -
# ueber beide Filter auffindbar, ohne dass irgendwas um einen einzigen Slot
# konkurriert (siehe migrations/001_schema_v2.sql §2, Tabellen tags/event_tags,
# die die Schema-Datei schon vorsieht).
#
# Bewusst ein KLEINER, verteidigbarer Startsatz - keine ausufernde Taxonomie:
# genau die fuenf Tags, die David selbst als Beispiele genannt hat. Bewusst
# NICHT dabei: ein Tag pro Musikgenre (jazz/blues/swing/soul/... gibt es alle
# schon als KEYWORD_CATEGORY_MAP-Eintraege, aber daraus automatisch zehn Tags
# zu machen waere genau die Sprawl-Falle, vor der die Aufgabe warnt), kein
# "kostenlos"/"barrierefrei" (kein verlaessliches Datenfeld dafuer - price_text
# ist nur duenn gefuellt, siehe DDL §3 - ein Tag ohne verlaessliche Grundlage
# waere schlimmer als keiner), kein Venue-Typ-Tag fuer club/theater/kino
# (deckungsgleich mit der Kategorie, liefert keine zusaetzliche Information).
TAG_LABELS = {
    "kirche": "Kirche",
    "museum": "Museum",
    "open-air": "Open Air",
    "klassik": "Klassik",
    "techno": "Techno",
}

# Dieselbe kurze Woertliste wie tools/seed_venues.py._KEYWORD_KIND fuer
# kirche/museum - eine zweite, unabhaengige Liste wuerde ueber die Zeit
# auseinanderlaufen. NICHT identisch uebernommen: seed_venues.py wendet seine
# Liste nur auf die Top-120-Venues an (kuratierte kind-Spalte), hier gilt sie
# fuer ALLE Venues, weil ein Tag additiv und nicht die einzige Kategorie-
# Entscheidung ist - geringeres Fehlerrisiko als bei kind.
_TAG_KIRCHE_WORDS = ("kirche", "dom", "kloster", "kathedrale", "kapelle", "kreuzkirche")
_TAG_MUSEUM_WORDS = ("museum", "sammlung", "ausstellungshaus", "gedenkstaette", "schloss")
# "schloss" faengt neben echten Schloessern auch "Schloßplatz" (ein Platz,
# keine Spielstaette - 32 Events im Bestand) und "KulturSchlosserei" (eine
# Schlosser-Werkstatt, kein Schloss) - beide gemessen, P4e 2026-09-11.
_TAG_MUSEUM_FALSE_FRIENDS = ("schlossplatz", "schlosserei")
_TAG_KLASSIK_WORDS = (
    "klassik", "philharmon", "sinfoni", "orchester", "kammermusik", "orgel",
    "oper", "chor",
)


def derive_tags(title, venue_name=None, venue_kind=None):
    """Kontext-Tags aus Titel + Venue, siehe Modul-Kommentar oben.

    venue_kind ist die kuratierte venues.kind-Spalte (siehe migrations/
    001_schema_v2.sql §1), NICHT der freie Rohstring - Aufrufer ohne
    Venue-Aufloesung (die 10 Scraper) lassen es schlicht weg; Kirche/Museum
    greifen dann nur ueber den Venue-NAMEN, was bei den meisten Haeusern
    bereits reicht (Kirchen/Museen tragen ihre Art fast immer im Namen).
    """
    tags = set()
    tslug = slugify(title)
    vslug = slugify(venue_name or "")

    if any(w in vslug for w in _TAG_KIRCHE_WORDS) or venue_kind == "kirche":
        tags.add("kirche")

    is_museumish = any(w in vslug for w in _TAG_MUSEUM_WORDS) or venue_kind == "museum"
    if is_museumish and not any(ff in vslug for ff in _TAG_MUSEUM_FALSE_FRIENDS):
        tags.add("museum")

    if "open-air" in tslug or "openair" in tslug:
        tags.add("open-air")

    if any(w in tslug for w in _TAG_KLASSIK_WORDS):
        tags.add("klassik")

    # Dieselbe "-rave"-Schreibweise wie in KEYWORD_CATEGORY_MAP (siehe
    # Kommentar dort) - sonst faengt der Tag dieselben Fehlerfreunde
    # (Travestie, Gravestone, Ravenshope) wieder ein.
    if "techno" in tslug or "-rave" in tslug:
        tags.add("techno")

    return sorted(tags)

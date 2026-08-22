"""Wo findet ein Event statt: Dresden, Speckguertel oder weiter weg?

Hintergrund: der Kulturkalender heisst zwar "Dresden", listet aber die ganze
Region mit - gemessen am 22.08.2026 liegen rund 29% aller Eintraege ausserhalb
der Stadtgrenze, allein Meissen (Dom, Erlebniswelt) stellt ~440 Zeilen. Fuer
"was geht heute in Dresden" ist das Rauschen; als Ausflugstipp ist es
willkommen. Deshalb gibt es im Web-UI den Schalter "Umgebung einschliessen",
und im Newsletter bleibt das Entfernte aussen vor.

Datenlage: mehr als der Ortsname im venue-Feld ist nicht da. Die Detailseiten
des Kulturkalenders nennen KEINE Adresse (geprueft: <address> enthaelt nur
denselben Ortsnamen wie die Tagesliste), Geokoordinaten liefert keine Quelle.
Die Zuordnung laeuft deshalb ueber ausdrueckliche Listen - dieselbe Bauart wie
cybersax.BIG_VENUE_SLUGS und normalize._FILM_VENUE_RE, und aus demselben Grund:
"liegt das in Dresden" sieht man einem Namen nicht an, das muss jemand wissen.

Drei Stufen:
    dresden - Stadtgebiet inkl. aller Ortsteile (Pillnitz, Langebrueck,
              Schoenfeld-Weissig, Cossebaude ...)
    umland  - Speckguertel, rund 20 km: Radebeul, Freital, Pirna, Coswig,
              Heidenau, Moritzburg, Radeberg, Radeburg, Dohna ...
    weiter  - alles andere: Meissen, Kamenz, Bautzen, Saechsische Schweiz,
              Leipzig, Cottbus ...
Der Schalter im Web-UI und der Newsletter-Filter trennen zwischen "weiter" und
dem Rest - Umland zaehlt also bewusst als "nah bei Dresden" und bleibt immer
sichtbar.
"""
from .normalize import slugify

REGION_DRESDEN = "dresden"
REGION_UMLAND = "umland"
REGION_WEITER = "weiter"

# Ortsnamen werden gegen die WOERTER des Slugs geprueft, nicht per Teilstring.
# Das ist der ganze Trick gegen die Strassennamen-Falle: Dresden ist voller
# Strassen, die nach dem Nachbarort heissen, und die tragen im Deutschen
# zuverlaessig die abgeleitete Form - "Bautzner Strasse", "Meissner
# Landstrasse", "Pirnaer Landstrasse", "Koenigsbruecker", "Radeberger
# Biertheater", "Riesaer Strasse", "Leipziger Bahnhof". Als eigenes Wort
# ("pirnaer" != "pirna") faellt keine davon durch.
#
# Aus demselben Grund steht "neustadt" NIRGENDS in diesen Listen: Neustadt in
# Sachsen liegt 40 km weg, die Dresdner Neustadt ist das Zentrum des
# Nachtlebens. Ein Treffer haette die halbe Musikkategorie versteckt.
NEARBY_TOWNS = {
    "radebeul", "freital", "coswig", "heidenau", "moritzburg", "radeberg",
    "pirna", "radeburg", "weinboehla", "bannewitz", "kreischa", "wilsdruff",
    "arnsdorf", "dohna", "klipphausen", "tharandt", "possendorf", "graupa",
    "pesterwitz", "friedewald", "serkowitz", "zuschendorf", "grosssedlitz",
    "sonnenstein", "boxdorf", "reichenberg", "ottendorf-okrilla",
    "duerrroehrsdorf", "wachau", "seifersdorf", "mohorn", "unkersdorf",
    "constappel",
}

FAR_TOWNS = {
    "meissen", "kamenz", "pulsnitz", "bautzen", "goerlitz", "leipzig",
    "cottbus", "hoyerswerda", "zittau", "chemnitz", "weimar", "berlin",
    "riesa", "grossenhain", "zabeltitz", "nossen", "doebeln", "torgau",
    "freiberg", "rammenau", "grossroehrsdorf", "elstra", "ohorn", "burkau",
    "stolpen", "hohnstein", "sebnitz", "neukirch",
    # Saechsische Schweiz und Osterzgebirge - Ausflugsziele, keine Nachbarorte
    "koenigstein", "rathen", "gohrisch", "struppen", "wehlen", "lohmen",
    "bad-schandau", "bad-gottleuba", "berggiesshuebel", "rosenthal-bielatal",
    "papstdorf", "reinhardtsdorf", "krippen", "porschdorf", "rauenstein",
    "dippoldiswalde", "altenberg", "lauenstein", "geising", "schmiedeberg",
    "glashuette", "weesenstein", "maxen", "liebstadt", "kipsdorf", "rabenau",
    "hermsdorf-erzgebirge", "seiffen", "olbernhau", "annaberg",
    # Oberlausitz, Brandenburg, Erzgebirge - kommen ueber den Kulturkalender
    # vereinzelt mit herein
    "herrnhut", "weisswasser", "knappenrode", "finsterwalde", "cunewalde",
    "schirgiswalde", "marienberg", "mortka", "domsdorf", "hinterhermsdorf",
    "kleinhennersdorf", "niederau", "proschwitz", "jahnishausen", "altdoebern",
    "tiefenau", "gostewitz", "mahlitzsch", "goedelitz", "saechsische-schweiz",
}

# Haeuser, deren Name den Ort nicht verraet. Ohne diese Liste laege der
# groesste Einzelposten falsch: Schloss Wackerbarth (139 Eintraege) steht in
# Radebeul, nicht in Dresden.
#
# Geprueft per Teilstring gegen den Slug, weil die Quellen denselben Ort in
# vielen Schreibweisen nennen ("Hoflößnitz", "Weingut Hoflößnitz Radebeul").
#
# Erweitern, wenn ein Ausflugsziel als Dresden durchrutscht - der lange
# Ausklang mit ein bis drei Terminen je Haus ist bewusst nicht vollstaendig
# erfasst (siehe classify_region: im Zweifel Dresden):
#   SELECT venue, count(*) c FROM events WHERE duplicate_of IS NULL
#     GROUP BY 1 ORDER BY c DESC;
VENUE_REGIONS = (
    # --- Speckguertel ---
    ("schloss-wackerbarth", REGION_UMLAND),      # Radebeul
    ("hofloessnitz", REGION_UMLAND),             # Radebeul
    ("landesbuehnen", REGION_UMLAND),            # Landesbuehnen Sachsen, Radebeul
    ("weingut-aust", REGION_UMLAND),             # Radebeul
    ("haus-steinbach", REGION_UMLAND),           # Radebeul
    ("tom-pauls", REGION_UMLAND),                # Tom-Pauls-Theater, Pirna
    ("schloss-batzdorf", REGION_UMLAND),         # Klipphausen
    ("saxstall", REGION_UMLAND),                 # Bosewitz bei Dohna
    ("zentralgasthof", REGION_UMLAND),           # Weinboehla
    # --- weiter weg ---
    ("hochstift", REGION_WEITER),                # Dom zu Meissen
    ("albrechtsburg", REGION_WEITER),            # Meissen
    ("erlebniswelt-meissen", REGION_WEITER),
    ("porzellan-manufaktur", REGION_WEITER),     # Meissen
    ("kulturinsel", REGION_WEITER),              # Zentendorf bei Goerlitz
    ("turisede", REGION_WEITER),                 # dieselbe Kulturinsel
    ("terra-mineralia", REGION_WEITER),          # Freiberg
    ("roedersaal", REGION_WEITER),               # Grossroehrsdorf
    ("felsenbuehne", REGION_WEITER),             # Rathen
    ("robert-sterl", REGION_WEITER),             # Struppen
    ("osterzgebirgsmuseum", REGION_WEITER),
    ("naturbuehne-maxen", REGION_WEITER),
    ("kloster-altzella", REGION_WEITER),         # Nossen
    ("barockschloss-rammenau", REGION_WEITER),
    ("deutsch-sorbisches", REGION_WEITER),       # Volkstheater Bautzen
    ("alte-wasserkunst", REGION_WEITER),         # Bautzen
    ("stadthalle-krone", REGION_WEITER),         # Bautzen
    ("museum-der-westlausitz", REGION_WEITER),   # Kamenz
    ("kunsthalle-lausitz", REGION_WEITER),
    ("gerhart-hauptmann-theater", REGION_WEITER),  # Goerlitz/Zittau
    ("martin-moller", REGION_WEITER),            # Goerlitz
    ("gunzenhauser", REGION_WEITER),             # Chemnitz
    ("schlossbergmuseum", REGION_WEITER),        # Chemnitz
    ("grassi", REGION_WEITER),                   # Leipzig
    ("gladhouse", REGION_WEITER),                # Cottbus
    ("weimarhalle", REGION_WEITER),
    ("kirms-krackow", REGION_WEITER),            # Weimar
    ("kulturweberei", REGION_WEITER),            # Finsterwalde
    ("danner-halle", REGION_WEITER),             # Telux-Gelaende, Weisswasser
    ("energiefabrik", REGION_WEITER),            # Knappenrode
    ("brikettfabrik-louise", REGION_WEITER),     # Domsdorf
    ("naturerlebniszentrum-hebelei", REGION_WEITER),  # Saechsische Schweiz
    ("heymannbaude", REGION_WEITER),             # Kleinhennersdorf
    ("karrasburg", REGION_UMLAND),               # Coswig
    ("adams-gasthof", REGION_UMLAND),            # Moritzburg
)

# Gegenprobe: Dresdner Haeuser, deren Name trotz der Wortregel oben einen
# fremden Ortsnamen als eigenes Wort enthaelt. Kurz halten - jeder Eintrag hier
# ist eine Ausnahme von der Ausnahme.
DRESDEN_VENUES = (
    "riesa-efau",        # Kultur Forum an der Adlergasse, Dresden-Friedrichstadt
    "motorenhalle",      # gehoert zum riesa efau
    "leipziger-bahnhof", # Alter Leipziger Bahnhof, Dresden-Neustadt
)


def classify_region(venue):
    """venue -> 'dresden' | 'umland' | 'weiter'.

    Im Zweifel Dresden: ein unbekannter Name ist viel wahrscheinlicher ein
    Dresdner Laden als ein Ausflugsziel, und ein falsch als "weiter" gewerteter
    Eintrag verschwaende kommentarlos aus Liste und Newsletter.
    """
    slug = slugify(venue or "")
    if not slug:
        return REGION_DRESDEN
    if any(name in slug for name in DRESDEN_VENUES):
        return REGION_DRESDEN
    for name, region in VENUE_REGIONS:
        if name in slug:
            return region
    if "dresden" in slug.split("-"):
        return REGION_DRESDEN
    town = _town_region(slug)
    if town:
        return town
    return REGION_DRESDEN


def _town_region(slug):
    """Ortsname im Slug? Einwortnamen als eigenes Wort (siehe NEARBY_TOWNS),
    zusammengesetzte ("bad-schandau") als Teilstring."""
    words = set(slug.split("-"))
    for towns, region in ((FAR_TOWNS, REGION_WEITER), (NEARBY_TOWNS, REGION_UMLAND)):
        for name in towns:
            if "-" in name:
                if name in slug:
                    return region
            elif name in words:
                return region
    return None

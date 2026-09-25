"""Die Orte - kuratiert, in git, als orte/orte.json.

Warum eine Datei und keine Tabelle: alles, was jemand von Hand pflegt oder was
nur mit vielen Requests wiederzubeschaffen ist (Herz, Art, Homepage, Cover,
Adresse, Koordinaten, Aliase), soll einen Neuaufbau der Datenbank ueberleben
und in git nachvollziehbar sein. Die Events dagegen sind nach vier Wochen
ohnehin veraltet und werden bei jedem Lauf neu gebaut (ddwg/db.py).

Aufbau der Datei: ein Objekt {slug: ort}, nach slug sortiert. Leere Felder
werden weggelassen, damit die Datei lesbar bleibt. Felder eines Ortes:

    name              Anzeigename
    aliase            alle Schreibweisen, unter denen Quellen den Ort liefern
    region            dresden | umland | weiter (ddwg/geo.py)
    art               club, museum, theater ... (fehlt = sonstiges)
    herz              true = Davids Ort: seine Events kommen auf der
                      Startseite nach vorn
    treffpunkt        true = kein Haus, sondern ein Treffpunkt (Stadtfuehrung)
    homepage, cover, beschreibung, adresse, telefon, oeffnungszeiten,
    lat, lon, geo_quelle
    erstmals          Datum, an dem ein Scrape den Ort zum ersten Mal sah
                      (nur bei Orten, die nach dem Umzug auf v3 dazukamen)

Aufloesung einer Schreibweise (resolve):
    1. exakt als Alias bekannt
    2. ihr Kollaps-Schluessel (venue_slug) trifft den eines bekannten Alias
    3. sonst: neuer Ort mit dieser Schreibweise als Name und einzigem Alias
"""
import json
import os
import re
from datetime import date

from . import geo, normalize

ORTE_PATH = os.environ.get(
    "DDWG_ORTE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "orte", "orte.json"),
)

FELDER = (
    "name", "aliase", "region", "art", "herz", "treffpunkt", "homepage", "cover",
    "beschreibung", "adresse", "telefon", "oeffnungszeiten", "lat", "lon",
    "geo_quelle", "erstmals", "notiz",
)

# Woerter, die beim Kollaps-Schluessel verschwinden - dieselbe gemessene Regel
# wie in v2 (Kleinschreibung, Umlaute, Klammerzusaetze, "Dresden"/"e.V."/"GmbH"
# raus - das und NICHT MEHR, sonst kollabieren echte, verschiedene Orte).
_PAREN_RE = re.compile(r"\([^)]*\)")
_DROP_WORDS = {"dresden", "e", "v", "gmbh"}


def venue_slug(raw_venue):
    """Kollaps-Schluessel einer Schreibweise."""
    if not raw_venue:
        return ""
    slug = normalize.slugify(_PAREN_RE.sub(" ", raw_venue))
    parts = [p for p in slug.split("-") if p and p not in _DROP_WORDS]
    return "-".join(parts) or slug


def _clean(ort):
    """Feste Feldreihenfolge, leere Felder raus."""
    out = {}
    for key in FELDER:
        value = ort.get(key)
        if value in (None, "", [], False):
            continue
        if key == "art" and value == "sonstiges":
            continue
        out[key] = value
    return out


class Orte:
    def __init__(self, data, path=None):
        self.path = path
        self.by_slug = {slug: dict(ort) for slug, ort in data.items()}
        self.neu = []          # slugs, die in diesem Lauf dazukamen
        self._reindex()

    # --- Laden / Speichern ---------------------------------------------------

    @classmethod
    def load(cls, path=None):
        path = path or ORTE_PATH
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh), path)

    def save(self, path=None):
        path = path or self.path or ORTE_PATH
        data = {slug: _clean(self.by_slug[slug]) for slug in sorted(self.by_slug)}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        os.replace(tmp, path)

    def _reindex(self):
        self._exact = {}
        self._collapsed = {}
        for slug, ort in self.by_slug.items():
            names = [ort.get("name")] + list(ort.get("aliase") or [])
            for raw in names:
                if not raw:
                    continue
                self._exact.setdefault(raw, slug)
                key = venue_slug(raw)
                if key:
                    self._collapsed.setdefault(key, slug)
            self._collapsed.setdefault(slug, slug)

    # --- Zugriff -------------------------------------------------------------

    def __getitem__(self, slug):
        return self.by_slug[slug]

    def get(self, slug):
        return self.by_slug.get(slug)

    def __iter__(self):
        return iter(self.by_slug.values())

    def __len__(self):
        return len(self.by_slug)

    def items(self):
        return self.by_slug.items()

    def lookup(self, raw_venue):
        """Schreibweise -> slug, ohne etwas anzulegen. None, wenn unbekannt."""
        if not raw_venue:
            return None
        if raw_venue in self._exact:
            return self._exact[raw_venue]
        return self._collapsed.get(venue_slug(raw_venue))

    def resolve(self, raw_venue, heute=None):
        """Schreibweise -> slug. Legt unbekannte Orte an (siehe Modul-Docstring).
        Leere Schreibweise -> None."""
        if not raw_venue or not raw_venue.strip():
            return None
        raw_venue = raw_venue.strip()
        slug = self.lookup(raw_venue)
        if slug:
            ort = self.by_slug[slug]
            if raw_venue not in (ort.get("aliase") or []) and raw_venue != ort.get("name"):
                ort.setdefault("aliase", []).append(raw_venue)
                self._exact[raw_venue] = slug
            return slug

        slug = venue_slug(raw_venue) or normalize.slugify(raw_venue) or "ort"
        base, n = slug, 2
        while slug in self.by_slug:
            slug, n = f"{base}-{n}", n + 1
        self.by_slug[slug] = {
            "name": raw_venue,
            "aliase": [raw_venue],
            "region": geo.classify_region(raw_venue),
            "erstmals": (heute or date.today()).isoformat(),
        }
        self.neu.append(slug)
        self._exact[raw_venue] = slug
        self._collapsed.setdefault(venue_slug(raw_venue), slug)
        self._collapsed.setdefault(slug, slug)
        return slug

    def suche(self, text):
        """Orte, deren slug, Name oder Alias den Text enthaelt (ohne Umlaute/Case)."""
        needle = normalize.slugify(text)
        if needle in self.by_slug:
            return [needle]
        hits = []
        for slug, ort in self.by_slug.items():
            hay = [slug, ort.get("name") or ""] + list(ort.get("aliase") or [])
            if any(needle in normalize.slugify(h) for h in hay):
                hits.append(slug)
        return sorted(hits)

    def herz_orte(self):
        return sorted(slug for slug, ort in self.by_slug.items() if ort.get("herz"))

    def set_herz(self, slug, an=True):
        ort = self.by_slug[slug]
        if an:
            ort["herz"] = True
        else:
            ort.pop("herz", None)

    def zusammenlegen(self, ziel, *weitere):
        """Orte zu einem zusammenlegen: Aliase und fehlende Felder wandern zu
        `ziel`, die anderen Eintraege verschwinden. Fuer doppelt angelegte
        Haeuser (Paula / Club Paula)."""
        target = self.by_slug[ziel]
        aliase = list(target.get("aliase") or [])
        for slug in weitere:
            other = self.by_slug.pop(slug)
            for raw in [other.get("name")] + list(other.get("aliase") or []):
                if raw and raw not in aliase:
                    aliase.append(raw)
            for key in FELDER:
                if key in ("name", "aliase"):
                    continue
                if target.get(key) in (None, "", [], "sonstiges") and other.get(key) not in (None, "", []):
                    target[key] = other[key]
        target["aliase"] = aliase
        self._reindex()

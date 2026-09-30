"""Was gar nicht erst auf die Seite kommt - weder in den Zeitstrahl noch auf die Karte.

Davids Entscheidungen vom 29./30.09.2026: Die Seite ist fuer Club, Konzerte und
Subkultur. Diese Termine verwirft build() nach der Kategorie-Vergabe, sie stehen
dann auch nicht in ausgabe/index.html:

  - Orte mit Feld "raus" in orte/orte.json (Grund als Text), z. B. Haus der
    Bruecke, TimeRide, Erlwein Forum (Titanic-Show), Dampfschifffahrt.
  - Hotels und Gasthoefe: jeder Ort, dessen Name "Hotel" oder "Gasthof" enthaelt
    (so fallen auch neue Hotels von allein raus).
  - Familie und Kinder: alles, was die Richtung "familie" bekaeme (Kategorie
    familie, oder Ort mit Flavour familie und sonst keine Kategorie).
  - Senioren: Titel mit Senior, 60+, Ue60, "aeltere Menschen".
  - Abgesagt: Titel mit abgesagt, faellt aus, entfaellt, cancelled.
  - Touristen-Angebote: Candlelight, Babykonzerte, Stadtabenteuer,
    Weinwanderungen, Weinproben und -verkostungen.

grund() gibt den Grund als kurzen Text zurueck (fuer das Log) oder None.
Umland bleibt ausdruecklich drin (Sternwarte, Ausflugsziele).
"""
import json
import os
import re

from . import richtungen
from .normalize import slugify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLAVOURS_PATH = os.path.join(ROOT, "orte", "flavours.json")

_HOTEL_RE = re.compile(r"hotel|gasthof")
# Auf dem kleingeschriebenen Titel (nicht dem Slug): "60+" und "Ü60" ueberlebt
# slugify nicht.
_SENIOREN_RE = re.compile(r"senior|\b60 ?\+|\bü ?60\b|ältere[nr]? menschen|aeltere[nr]? menschen")
_ABGESAGT_RE = re.compile(r"abgesagt|fällt aus|faellt aus|entfällt|entfaellt|cancel+ed")
_TOURISTEN_RE = re.compile(
    r"candlelight|babykonzert|stadtabenteuer|wein(?:bergs?)?wanderung|weinverkostung"
    r"|weinprobe|verkostung von \d+ .*weinen")


def flavour_von_ort(pfad=None):
    """{ort_slug: flavour} aus orte/flavours.json, nur "haupt", ohne "unklar"."""
    pfad = pfad or FLAVOURS_PATH
    if not os.path.exists(pfad):
        return {}
    with open(pfad, encoding="utf-8") as fh:
        roh = json.load(fh)
    return {slug: z["haupt"] for slug, z in roh.get("orte", {}).items()
            if z.get("haupt") and z["haupt"] != "unklar"}


def grund(titel, kategorie, ort_slug=None, ort=None, flavours=None):
    """Warum ein Termin raus soll, oder None.

    ort: der Eintrag aus orte.json (dict) oder None; flavours: flavour_von_ort()."""
    ort = ort or {}
    if ort.get("raus"):
        return "Ort: " + str(ort["raus"])
    if _HOTEL_RE.search(slugify(ort.get("name") or "")):
        return "Hotel/Gasthof"
    t = (titel or "").lower()
    if _ABGESAGT_RE.search(t):
        return "abgesagt"
    if _SENIOREN_RE.search(t):
        return "Senioren"
    if _TOURISTEN_RE.search(t):
        return "Touristen-Angebot"
    if "familie" in richtungen.fuer(titel, kategorie, ort_slug, ort.get("name"), flavours or {}):
        return "Familie"
    return None

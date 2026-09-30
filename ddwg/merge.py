"""Aus einer Gruppe von Eintraegen EIN Event machen - Feld fuer Feld.

v2 kuerte je Doppelung einen Gewinner und fuellte bei ihm nur leere Felder
auf. v3 verschmilzt ausdruecklich: jede Angabe kommt von der ranghoechsten
Quelle, die sie ueberhaupt hat (Rang siehe ddwg/quellen/__init__.py). Ein
Konzert, das rauze und der Kulturkalender beide fuehren, bekommt so Titel,
Beschreibung und Preis von rauze und notfalls das Bild vom Kulturkalender.

Die Gruppe kommt aus dedup.cluster() schon sortiert, der ranghoechste Eintrag
zuerst. Datum und Titel stammen immer von ihm. Die Uhrzeit auch - nur wenn er
keine hat, kommt sie von der naechsten Quelle, die eine hat (seit 30.09.2026:
die Ostpol-Seite nennt oft keine, cybersax und der Kulturkalender schon).

Der Link soll auf die Seite des Termins zeigen. Eine Startseite (ost-pol.de/)
oder eine Tagesuebersicht (cybersax /terminal/day/) zaehlt nur, wenn keine
Quelle einen eigenen Link hat. Im Preisfeld bleibt nur der Preis, ein
angehaengtes "Quelle: Museen der Stadt Dresden" faellt weg.
"""
import re
from urllib.parse import urlparse

from . import dedup, quellen

KEINE_BESCHREIBUNG = "Keine weitere Beschreibung verfügbar."


def _first(members, field):
    for member in members:
        value = member.get(field)
        if isinstance(value, str):
            value = value.strip()
        if value and value != KEINE_BESCHREIBUNG:
            return value
    return None


def ist_einzellink(url):
    """False fuer Startseiten und Tagesuebersichten, die fuer viele Termine gleich sind."""
    if not url:
        return False
    teile = urlparse(url)
    pfad = teile.path.rstrip("/")
    if not pfad or pfad in ("/index.php", "/index.html"):
        return False
    return "/terminal/day/" not in teile.path


_PREIS_QUELLE_RE = re.compile(r"\s*\|?\s*quelle:.*$", re.IGNORECASE | re.DOTALL)


def preis_bereinigen(text):
    """"frei | Ohne Anmeldung Quelle: Bibliothek" -> "frei | Ohne Anmeldung";
    "Quelle: Museen der Stadt Dresden" -> None."""
    if not text:
        return None
    text = _PREIS_QUELLE_RE.sub("", text).strip(" |")
    return text or None


def merge(members, detail=None):
    """members: Eintraege EINER Gruppe, ranghoechster zuerst (dedup.cluster).
    detail: optional {url: {description, price_text, image_url}} aus der
    details-Tabelle - nachgeladene Detailseiten zaehlen wie die Quelle, deren
    URL sie sind.

    Gibt ein Event-dict zurueck (ohne region/laufend, das setzt pipeline.py)."""
    if detail:
        members = [_with_detail(m, detail) for m in members]
    head = members[0]

    # Ort: der erste echte, Platzhalter ("Location siehe Beschreibung") zaehlen
    # nicht - die liefert rauze gern, obwohl cybersax den Ort kennt.
    ort_member = next((m for m in members if not dedup.is_unknown_venue(m.get("ort_roh"))), head)

    # Kategorie: die erste Quelle, die eine echte Kategorie weiss.
    category = next((m["category"] for m in members
                     if m.get("category") and m["category"] != "sonstiges"), "sonstiges")

    sources = []
    for member in sorted(members, key=lambda m: quellen.rang(m["source"])):
        if member["source"] not in sources:
            sources.append(member["source"])

    return {
        # event_uid: die stabile uid der Quelle (normalize.make_event_uid);
        # "uid" ist in der Gruppe nur der Zeilenschluessel fuer dedup.
        "uid": head.get("event_uid") or head["uid"],
        "date": head["date"],
        "time": head.get("time") or _first(members, "time"),
        "title": head["title"],
        "ort": ort_member.get("ort"),
        "ort_roh": ort_member.get("ort_roh"),
        "category": category,
        "url": next((m["url"] for m in members if ist_einzellink(m.get("url"))), None)
               or _first(members, "url"),
        "image_url": _first(members, "image_url"),
        "description": _first(members, "description"),
        "price_text": next((p for p in (preis_bereinigen(m.get("price_text")) for m in members) if p), None),
        "sources": ",".join(sources),
    }


def _with_detail(member, detail):
    found = detail.get(member.get("url") or "")
    if not found:
        return member
    out = dict(member)
    for field in ("description", "price_text", "image_url"):
        if not (out.get(field) or "").strip() and found.get(field):
            out[field] = found[field]
    return out

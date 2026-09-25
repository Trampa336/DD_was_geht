"""Aus einer Gruppe von Eintraegen EIN Event machen - Feld fuer Feld.

v2 kuerte je Doppelung einen Gewinner und fuellte bei ihm nur leere Felder
auf. v3 verschmilzt ausdruecklich: jede Angabe kommt von der ranghoechsten
Quelle, die sie ueberhaupt hat (Rang siehe ddwg/quellen/__init__.py). Ein
Konzert, das rauze und der Kulturkalender beide fuehren, bekommt so Titel,
Beschreibung und Preis von rauze und notfalls das Bild vom Kulturkalender.

Die Gruppe kommt aus dedup.cluster() schon sortiert, der ranghoechste Eintrag
zuerst. Datum, Uhrzeit und Titel stammen immer von ihm - sonst koennte ein
Event aus Titel der einen und Uhrzeit der anderen Quelle zusammengesetzt
werden, und das waere eine Angabe, die keine Quelle so gemacht hat.
"""
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
        "time": head.get("time"),
        "title": head["title"],
        "ort": ort_member.get("ort"),
        "ort_roh": ort_member.get("ort_roh"),
        "category": category,
        "url": _first(members, "url"),
        "image_url": _first(members, "image_url"),
        "description": _first(members, "description"),
        "price_text": _first(members, "price_text"),
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

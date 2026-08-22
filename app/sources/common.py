"""Gemeinsame LLM-Plumbing für API-Quellen: Schema, Prompt, Batch-Aufruf.

Bewusst quellenunabhängig gehalten: der Aufrufer liefert nur Textschnipsel mit
einem Bezugsdatum, hier passiert die Klassifizierung ("ist das überhaupt eine
Veranstaltung?") plus Extraktion der Felder, die app/db.py erwartet.
"""
import json
import logging

from .. import config

logger = logging.getLogger("dd-was-geht.sources.common")

# Das Schema erzwingt gültiges JSON in der Antwort (siehe output_config unten),
# damit hier kein Freitext geparst werden muss.
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "is_event": {"type": "boolean"},
                    "confidence": {"type": "number"},
                    "date": {"type": ["string", "null"]},
                    "time": {"type": ["string", "null"]},
                    "title": {"type": ["string", "null"]},
                    "venue": {"type": ["string", "null"]},
                    "raw_category": {"type": ["string", "null"]},
                },
                "required": [
                    "id", "is_event", "confidence",
                    "date", "time", "title", "venue", "raw_category",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """Du analysierst Beiträge aus sozialen Netzwerken und erkennst darin \
Veranstaltungen in Dresden (Konzerte, Partys, Raves, Lesungen, Ausstellungen, Festivals, \
Märkte, Sportveranstaltungen und Ähnliches).

Für jeden Beitrag entscheidest du:
1. is_event: true nur, wenn der Beitrag eine KONKRETE, zeitlich datierbare Veranstaltung \
ankündigt oder erwähnt. false bei allgemeinen Fragen ("Was kann man am Wochenende machen?"), \
Rückblicken auf vergangene Veranstaltungen, Diskussionen, Suchanzeigen und Meta-Beiträgen.
2. confidence: 0.0 bis 1.0, wie sicher du dir bei is_event und den extrahierten Feldern bist.
3. date: das Veranstaltungsdatum als YYYY-MM-DD. Relative Angaben ("morgen", "nächsten \
Freitag", "diesen Samstag") löst du anhand des angegebenen Bezugsdatums des Beitrags auf. \
Wenn sich kein eindeutiges Datum bestimmen lässt: null.
4. time: Startzeit als HH:MM (24h) oder null, wenn keine genannt wird.
5. title: kurzer, sprechender Veranstaltungstitel - NICHT der komplette Beitragstext und \
nicht der Reddit-Titel mit Zusätzen wie "[Frage]". Ohne Emojis.
6. venue: Ort/Location (Clubname, Adresse, Veranstalter) oder null.
7. raw_category: Genre/Art in einem Wort, wenn erkennbar (z.B. Konzert, Party, Rave, Techno, \
Lesung, Ausstellung, Festival, Film, Markt), sonst null.

Gib zu jedem Beitrag genau ein Ergebnis mit der jeweiligen id zurück. Erfinde nichts: \
Felder, die im Text nicht stehen und sich nicht sicher ableiten lassen, sind null."""

_client = None


def get_llm_client():
    """Lazy angelegt (wie get_bot() in app/bot.py), damit der reine Import des
    Moduls ohne gesetzten API-Key funktioniert - z.B. in den Smoke-Tests."""
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _format_items(items):
    lines = []
    for item in items:
        lines.append(
            f"--- Beitrag id={item['id']} (verfasst am {item['reference_date']}) ---\n"
            f"{item['text']}"
        )
    return "\n\n".join(lines)


def extract_events(items, client=None):
    """items: Liste von dicts mit id/text/reference_date.
    Gibt eine Liste von Ergebnis-dicts zurück (Schlüssel siehe EXTRACTION_SCHEMA),
    zugeordnet über das Feld 'id'."""
    if not items:
        return []

    client = client or get_llm_client()
    response = client.messages.create(
        model=config.REDDIT_LLM_MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _format_items(items)}],
        output_config={"format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA}},
    )

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        logger.warning("LLM-Antwort enthielt keinen Text-Block.")
        return []
    return json.loads(text).get("results", [])

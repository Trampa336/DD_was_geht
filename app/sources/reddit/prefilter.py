"""Billiger Vorfilter, bevor ein Post Geld kostet.

Wichtig: das ist KEIN Ersatz für die LLM-Klassifizierung, sondern nur eine
Kostenbremse. Deshalb bewusst großzügig - ein durchgelassener Nicht-Event
kostet einen Bruchteil eines Cents, ein aussortiertes echtes Event ist weg.
"""
import re

# Datums-/Zeitangaben, wie sie in Posts vorkommen. Bewusst mehrere Muster
# statt einer großen Alternative: die Wochentagskürzel (Mo, Di, ...) müssen
# eng gefasst werden, weil "so", "do" und "mi" auch ganz normale deutsche
# Wörter sind - "Warum ist die Elbe so voll" ist kein Veranstaltungshinweis.
DATE_PATTERNS = [
    # 21.08. / 21.08.2026 / 21:00
    re.compile(r"\b\d{1,2}\.\d{1,2}\.(\d{2,4})?|\b\d{1,2}:\d{2}\b"),
    # Ausgeschriebene Wochentage und Monate
    re.compile(
        r"\b(montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonnabend|sonntag"
        r"|januar|februar|maerz|märz|april|mai|juni|juli|august|september"
        r"|oktober|november|dezember)\b",
        re.IGNORECASE,
    ),
    # Relative Angaben; ohne \b am Ende, damit "nächsten"/"nächstes" mitgeht
    re.compile(r"\b(heute|morgen|übermorgen|uebermorgen|wochenende|nächst|naechst)",
               re.IGNORECASE),
    # Kürzel nur, wenn eine Zahl folgt: "Sa 22.", "Fr. 21"
    re.compile(r"\b(mo|di|mi|do|fr|sa|so)\.?\s+\d", re.IGNORECASE),
]


def _has_date(text):
    return any(pattern.search(text) for pattern in DATE_PATTERNS)

# Vokabular, das auf eine Veranstaltung hindeutet (ergänzt die Kategorie-
# Stichwörter aus app/normalize.py um Ankündigungs-Wortschatz).
EVENT_WORDS = {
    "event", "veranstaltung", "konzert", "party", "rave", "techno", "dj",
    "lineup", "line-up", "festival", "club", "gig", "show", "openair",
    "open air", "tickets", "ticket", "einlass", "eintritt", "location",
    "venue", "flyer", "vvk", "vorverkauf", "afterparty", "release",
    "lesung", "ausstellung", "vernissage", "kino", "film", "markt",
    "aufführung", "auffuehrung", "premiere", "jam", "session", "soli",
}

# Beiträge, die klar keine Ankündigung sind.
QUESTION_PATTERN = re.compile(
    r"\b(wer kennt|weiß jemand|weiss jemand|kennt (wer|jemand)|suche|gesucht"
    r"|does anyone know|looking for|empfehlung(en)?\?|wo kann man)\b",
    re.IGNORECASE,
)
SKIP_FLAIRS = {"frage", "question", "meta", "diskussion", "discussion", "hilfe"}


def looks_event_ish(title, selftext="", flair=None):
    if flair and flair.strip().lower() in SKIP_FLAIRS:
        return False

    text = f"{title}\n{selftext}"
    if not title.strip():
        return False

    lowered = text.lower()
    has_date = _has_date(text)
    has_event_word = any(word in lowered for word in EVENT_WORDS)

    if not (has_date or has_event_word):
        return False
    # Reine Fragen ohne Datum sind fast nie eine Ankündigung.
    if QUESTION_PATTERN.search(text) and not has_date:
        return False
    return True

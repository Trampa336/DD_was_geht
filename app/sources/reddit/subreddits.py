"""Welche Subreddits beobachtet werden - bewusst von Hand gepflegt.

Die Liste steht in einer Textdatei (config/reddit_subreddits.txt) statt im Code,
damit sie ohne Neubau des Containers änderbar ist und kommentiert werden kann.
Vorschläge liefert tools/discover_subreddits.py; eingetragen wird von Hand.
"""
import logging
import os

from ... import config

logger = logging.getLogger("dd-was-geht.sources.reddit")


def _clean(name):
    name = name.strip()
    if name.startswith("r/"):
        name = name[2:]
    elif name.startswith("/r/"):
        name = name[3:]
    return name.strip().strip("/")


def _parse_lines(lines):
    names = []
    for line in lines:
        line = line.split("#", 1)[0]
        name = _clean(line)
        if name and name.lower() not in [n.lower() for n in names]:
            names.append(name)
    return names


def load_active_subreddits(path=None, extra=None):
    """Liest die gepflegte Liste. Fehlt die Datei, ist das kein Fehler -
    die Reddit-Quelle bleibt dann einfach still (siehe pipeline.poll_recent)."""
    path = path if path is not None else config.REDDIT_SUBREDDITS_FILE
    extra = extra if extra is not None else config.REDDIT_SUBREDDITS_EXTRA

    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    else:
        logger.warning("Subreddit-Liste %s nicht gefunden.", path)

    lines.extend(extra.split(","))
    return _parse_lines(lines)

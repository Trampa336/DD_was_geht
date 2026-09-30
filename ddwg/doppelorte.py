"""Verdacht auf doppelte Orte: derselbe Ort unter zwei Schreibweisen.

dedup.cluster() legt Termine nur am selben Ort zusammen. Steht ein Haus unter
zwei slugs in orte/orte.json, erscheinen seine Termine doppelt im Zeitstrahl.
Diese Pruefung meldet Orts-Paare, an denen mehrmals am selben Tag ein Termin
mit gleichem Titelanfang steht. Sie aendert nichts; zusammengelegt wird von
Hand mit Orte.zusammenlegen() (siehe CLAUDE.md). Laeuft in `python -m ddwg status`.
"""
from collections import defaultdict

from . import normalize

# So viele Treffer braucht ein Paar. Einer allein ist oft Zufall
# (Tourneen, Demos mit gleichem Aufruf an zwei Plaetzen).
MIN_TREFFER = 2
_WOERTER = 3


def titel_schluessel(titel):
    """Die ersten Woerter des Titels ohne kurze Fuellwoerter, als Slug."""
    teile = [w for w in normalize.slugify(titel or "").split("-") if len(w) > 2]
    return "-".join(teile[:_WOERTER])


def verdacht(events, raus=(), min_treffer=MIN_TREFFER):
    """events: dicts mit date, title, ort. Liefert [(ort_a, ort_b, treffer, beispiel)],
    meiste Treffer zuerst."""
    raus = set(raus)
    orte_je = defaultdict(set)
    beispiel = {}
    for e in events:
        ort = e.get("ort")
        key = titel_schluessel(e.get("title"))
        if not ort or ort in raus or not key:
            continue
        orte_je[(e["date"], key)].add(ort)
        beispiel.setdefault((e["date"], key), e.get("title"))
    paare = defaultdict(list)
    for tk, orte in orte_je.items():
        orte = sorted(orte)
        for i, a in enumerate(orte):
            for b in orte[i + 1:]:
                paare[(a, b)].append(tk)
    out = [(a, b, len(t), beispiel[t[0]]) for (a, b), t in paare.items() if len(t) >= min_treffer]
    return sorted(out, key=lambda x: (-x[2], x[0], x[1]))

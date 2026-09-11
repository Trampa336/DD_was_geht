"""Auswertung des P4-Anreicherungslaufs: prueft die beiden Annahmen aus dem Paket.

Annahme A: "Jede KK-Venue-Seite traegt genau EINEN auswaertigen Link, und der
           ist die offizielle Homepage."
Annahme B: "venues.kind auf ~120 Venues zu pflegen loest das Kategorieproblem
           besser als jede Titel-Heuristik pro Event."

Liest ausschliesslich data/venue_cache/enrichment.json - kein Netzzugriff.

Aufruf: ../.venv/bin/python tools/enrich_report.py <db>
"""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CACHE = Path(__file__).resolve().parent.parent / "data" / "venue_cache" / "enrichment.json"

# Aus Homepage-Titel + Description erschlossene Art. Bewusst eine ANDERE
# Evidenzquelle als P3s guess_kind (das nur den Venue-Slug ansieht) - sonst
# waere der Vergleich zirkulaer.
_EVIDENCE_KIND = (
    (("weingut", "winzer", "sektmanufaktur", "weinberg", "rebe"), "weingut"),
    (("museum", "sammlung", "ausstellung", "schatzkammer", "galerie der",
      "gedenkstätte", "gedenkstaette"), "museum"),
    (("kirche", "dom", "kathedrale", "kloster", "kapelle", "gemeinde",
      "gottesdienst", "pfarr"), "kirche"),
    (("kino", "lichtspiel", "filmtheater", "programmkino", "filmnächte"), "kino"),
    (("theater", "oper", "schauspiel", "kabarett", "puppentheater",
      "ballett", "komödie", "komoedie"), "theater"),
    (("club", "diskothek", "nightlife", "techno", "party", "konzerte",
      "livemusik", "live-musik", "tanzbar"), "club"),
    (("galerie", "kunstverein", "kunsthaus", "atelier"), "galerie"),
    (("bühne", "buehne", "konzertsaal", "kulturpalast", "philharmonie",
      "veranstaltungssaal"), "buehne"),
    (("park", "garten", "zoo", "tierpark", "botanisch"), "park"),
)


def evidence_kind(rec):
    meta = rec.get("meta") or {}
    text = " ".join(filter(None, [meta.get("meta_title"),
                                  meta.get("meta_description")])).lower()
    if not text:
        return None
    for words, kind in _EVIDENCE_KIND:
        if any(w in text for w in words):
            return kind
    return None


def main():
    db = sys.argv[1] if len(sys.argv) > 1 else "data/dd-was-geht-v2.db"
    recs = json.loads(CACHE.read_text("utf-8"))
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    ranks = {str(r["id"]): i for i, r in enumerate(conn.execute(
        """SELECT v.id FROM venues v JOIN events e ON e.venue_id = v.id
           GROUP BY v.id ORDER BY COUNT(e.uid) DESC"""), 1)}

    items = sorted(recs.items(), key=lambda kv: ranks.get(kv[0], 9999))
    print(f"{len(items)} Venues im Lauf.\n")

    # ---------- Annahme A ----------
    print("=== ANNAHME A: genau ein auswaertiger Link = Homepage ===")
    with_kk = [r for _, r in items if r.get("status") != "kein_kk_link"]
    status = Counter(r["status"] for r in with_kk)
    print(f"Venues mit KK-Venue-Seite: {len(with_kk)} "
          f"(ohne KK-Link: {len(items) - len(with_kk)})")
    for s, n in status.most_common():
        print(f"  {s:16} {n:4}  ({n / len(with_kk) * 100:.1f}%)")

    # Wie oft stimmt die WOERTLICHE Fassung ("genau ein auswaertiger Link")?
    literal_ok = exactly_one_hp = 0
    outbound_hist = Counter()
    for r in with_kk:
        if "n_homepage" not in r:
            continue
        total = r["n_homepage"] + r["n_social"] + r["n_other"]
        outbound_hist[total] += 1
        if total == 1 and r["n_homepage"] == 1:
            literal_ok += 1
        if r["n_homepage"] == 1:
            exactly_one_hp += 1
    measured = sum(outbound_hist.values())
    print(f"\nAuswaertige Links je Venue-Seite (ohne KK-eigene Social-Buttons):")
    for k in sorted(outbound_hist):
        print(f"  {k} Link(s): {outbound_hist[k]:4}")
    print(f"\nWOERTLICH (genau 1 auswaertiger Link, und der ist die Homepage): "
          f"{literal_ok}/{measured} = {literal_ok / measured * 100:.1f}%")
    print(f"VERFEINERT (genau 1 Link mit Domain-Beschriftung): "
          f"{exactly_one_hp}/{measured} = {exactly_one_hp / measured * 100:.1f}%")

    # Wie oft liefert die Homepage dann auch brauchbare Metadaten?
    ok_meta = [r for _, r in items if (r.get("meta") or {}).get("status") == "ok"]
    with_img = [r for r in ok_meta if (r["meta"] or {}).get("og_image_url")]
    with_desc = [r for r in ok_meta if (r["meta"] or {}).get("meta_description")]
    print(f"\nHomepage erreichbar + HTML: {len(ok_meta)}/{len(items)}")
    print(f"  davon og:image (Cover):   {len(with_img)} "
          f"({len(with_img) / max(len(ok_meta), 1) * 100:.1f}%)")
    print(f"  davon meta description:   {len(with_desc)} "
          f"({len(with_desc) / max(len(ok_meta), 1) * 100:.1f}%)")

    # ---------- Tail ----------
    print("\n=== TAIL: wo sterben die Ertraege? ===")
    for lo in range(0, len(items), 20):
        chunk = items[lo:lo + 20]
        good = sum(1 for _, r in chunk if (r.get("meta") or {}).get("status") == "ok")
        img = sum(1 for _, r in chunk
                  if (r.get("meta") or {}).get("og_image_url"))
        nokk = sum(1 for _, r in chunk if r.get("status") == "kein_kk_link")
        print(f"  Rang {lo + 1:3}-{lo + len(chunk):3}: Homepage+Meta {good:2}/{len(chunk)}, "
              f"og:image {img:2}, ohne KK-Link {nokk}")

    # ---------- Annahme B ----------
    print("\n=== ANNAHME B: venues.kind traegt die Kategorien ===")
    agree = disagree = p3_blank = no_evidence = 0
    disagreements = []
    for key, r in items:
        if (r.get("meta") or {}).get("status") != "ok":
            continue
        p3 = r.get("kind")
        ev = evidence_kind(r)
        if ev is None:
            no_evidence += 1
            continue
        if p3 == "sonstiges":
            p3_blank += 1
            disagreements.append((ranks.get(key), r["name"], p3, ev, r["n"]))
        elif p3 == ev:
            agree += 1
        else:
            disagree += 1
            disagreements.append((ranks.get(key), r["name"], p3, ev, r["n"]))
    checked = agree + disagree + p3_blank
    print(f"Venues mit Homepage-Evidenz: {checked} (ohne verwertbare Evidenz: {no_evidence})")
    print(f"  P3 stimmt mit Evidenz ueberein: {agree}")
    print(f"  P3 sagt 'sonstiges', Evidenz nennt eine Art: {p3_blank}")
    print(f"  P3 und Evidenz widersprechen sich: {disagree}")
    print(f"  -> Abweichungsquote: {(p3_blank + disagree)}/{checked} = "
          f"{(p3_blank + disagree) / max(checked, 1) * 100:.1f}%")

    print("\n  Abweichungen (Rang | Venue | P3 -> Evidenz | Events):")
    for rank, name, p3, ev, n in sorted(disagreements)[:45]:
        print(f"   {rank:4} {name[:44]:44} {p3:10} -> {ev:9} {n:4}")


if __name__ == "__main__":
    main()

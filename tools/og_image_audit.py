"""Aufloesung des og:image-Widerspruchs aus P4 / P4b (Paket P4c, Aufgabe 1).

Liest NUR data/venue_cache/enrichment.json. Kein Netzzugriff.

Der Widerspruch: P4 meldete "praktisch kein og:image", P4b meldete 35,8%.
Beide Zahlen stammen aus DEMSELBEN Lauf, gemessen an verschiedenen Stellen:

  * og:image ist bei den GROSSEN Haeusern selten und bei den kleinen haeufig.
    Die Quote waechst monoton mit dem Rang: 0,0% nach 10 Venues, 8,3% nach 15,
    35,8% nach 90, 39,5% am Ende. P4 sah die ersten ~15 (0-1 Treffer), P4b las
    den Bericht bei ~90 Datensaetzen, waehrend der Lauf noch schrieb.
  * Nenner: P4b teilt durch "Homepage erfolgreich geholt" (86), nicht durch
    alle 114 Datensaetze.

Die Quote ist aber die falsche Frage. Von 34 Treffern sind nur 13 als Cover
brauchbar - der Rest sind Logos, Favicons, CMS-Standardbilder, Portalfotos
des falschen Motivs oder tote Links. Die Einstufung unten ist Handarbeit,
gestuetzt auf HEAD-Proben (Status, Content-Type, Groesse) und Bildmasse.
"""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "data" / "venue_cache" / "enrichment.json"

# rang -> (verdikt, begruendung). Handgepruefte Einstufung der 34 Treffer.
VERDICT = {
    15:  ("tot", "logo.png -> 404"),
    16:  ("brauchbar", "Pressefoto des Hauses, 1150K, (c) Fotograf"),
    22:  ("brauchbar", "eigens gebautes OG-Bild 1200x630"),
    26:  ("brauchbar", "facebook-og-img.jpg, hausbezogen, 178K"),
    29:  ("logo", "header_tile.png 1000x256 - Kopfstreifen, kein Motiv"),
    31:  ("tot", "logo.png -> 404 (gleiche Datei wie Rang 15)"),
    33:  ("brauchbar", "superfly.jpg 275K"),
    34:  ("falsches_motiv", "Sterl-Selbstbildnis 1007x1024, Hochformat, Gemaelde statt Haus"),
    41:  ("logo", "favImage.png 298x298 quadratisch"),
    44:  ("cms_default", "kupa_default_meta.jpg - Standardbild des CMS"),
    45:  ("falsches_motiv", "Puppentheater-Ensemble 1920x2560 Hochformat, Inszenierung statt Haus"),
    46:  ("logo", "cropped-favicon-sowieso.png - WordPress-Site-Icon"),
    49:  ("brauchbar", "Kreuzkirche-Dresden-c-Frank-Walther 1024x576"),
    52:  ("brauchbar", "Kettenkarussell-Foto 355K"),
    53:  ("brauchbar", "Marktplatz Pirna 1281x670, echtes Querformat-Foto"),
    56:  ("brauchbar", "Landhaus - das Museumsgebaeude selbst"),
    61:  ("logo", "AEM-clientlib-Static 20K PNG"),
    67:  ("portal", "dresden.de-Pressebild - Stadtportal, wechselt"),
    69:  ("portal", "dresden.de/media/bilder/auslaender/DSC_0374 - Stadtportal"),
    81:  ("brauchbar", "Technische_Sammlungen 230K"),
    82:  ("logo", "wixstatic 256x256 trotz w_2500-Anforderung"),
    84:  ("logo", "logo_only.jpg"),
    85:  ("logo", "icons/icon-300x300.png - App-Icon"),
    88:  ("brauchbar", "theaterkahn.jpg 2208x1368"),
    91:  ("brauchbar", "og-image.jpg 232K"),
    92:  ("portal", "dresden.de-Hochwasserfoto der Elbschloesser - falsches Motiv"),
    95:  ("brauchbar", "og-image-2025.jpg 289K"),
    100: ("brauchbar", "SLUB-Foto 55K"),
    103: ("logo", "SGDynamoDD_Logo_Outline-RGB.png"),
    105: ("tot", "Banner-scaled.jpg -> 404"),
    108: ("tot", "logo.png -> 404"),
    109: ("logo", "logo_astroclub_...facebook.png"),
    110: ("tot", "zeigt auf eine SEITE, nicht auf ein Bild; Host-SSL kaputt"),
    112: ("cms_default", "kupa_default_meta.jpg - dieselbe Datei wie Rang 44, falsches Haus"),
}
USABLE = "brauchbar"


def main():
    db = sys.argv[1] if len(sys.argv) > 1 else "data/dd-was-geht-v2.db"
    recs = json.loads(CACHE.read_text("utf-8"))
    conn = sqlite3.connect(db)
    ranks = {str(r[0]): i for i, r in enumerate(conn.execute(
        """SELECT v.id FROM venues v JOIN events e ON e.venue_id = v.id
           GROUP BY v.id ORDER BY COUNT(e.uid) DESC"""), 1)}
    items = sorted(recs.items(), key=lambda kv: ranks.get(kv[0], 9999))

    meta_ok = [r for _, r in items if (r.get("meta") or {}).get("status") == "ok"]
    hits = [(ranks.get(k, 9999), r) for k, r in items
            if (r.get("meta") or {}).get("og_image_url")]

    print("=== NENNER ===")
    print(f"  alle Datensaetze                 : {len(hits)}/{len(items)} = {len(hits)/len(items)*100:.1f}%")
    print(f"  mit homepage_url                 : {len(hits)}/{sum(1 for _, r in items if r.get('homepage_url'))}"
          f" = {len(hits)/sum(1 for _, r in items if r.get('homepage_url'))*100:.1f}%")
    print(f"  Homepage erfolgreich geholt      : {len(hits)}/{len(meta_ok)} = {len(hits)/len(meta_ok)*100:.1f}%  <- P4bs Nenner")

    print("\n=== QUOTE WAECHST MIT DEM RANG (darum beide Zahlen) ===")
    ok = im = 0
    for i, (k, r) in enumerate(items, 1):
        m = r.get("meta") or {}
        if m.get("status") == "ok":
            ok += 1
            im += bool(m.get("og_image_url"))
        if i in (10, 15, 20, 30, 50, 69, 90, 114):
            mark = "  <- P4 sah hier" if i == 15 else ("  <- P4bs 35,8%" if i == 90 else "")
            print(f"  nach {i:3} Venues: {im:2}/{ok:2} = {im/max(ok,1)*100:5.1f}%{mark}")

    print("\n=== BRAUCHBARKEIT DER 34 TREFFER ===")
    cnt = Counter(VERDICT.get(rk, ("unbekannt", ""))[0] for rk, _ in hits)
    for v, n in cnt.most_common():
        print(f"  {v:16} {n:3}")
    usable = [(rk, r) for rk, r in hits if VERDICT.get(rk, ("?",))[0] == USABLE]
    print(f"\n  ALS COVER BRAUCHBAR: {len(usable)}/{len(hits)} Treffer"
          f" = {len(usable)}/{len(meta_ok)} der geholten Homepages ({len(usable)/len(meta_ok)*100:.1f}%)"
          f" = {len(usable)/len(items)*100:.1f}% aller {len(items)} Venues")
    top = [rk for rk, _ in usable if rk <= 14]
    print(f"  davon unter den Top 14 nach Eventzahl: {len(top)}")

    kk = [r for _, r in items if r.get("kk_cover_url")]
    withkk = [r for _, r in items if r.get("status") != "kein_kk_link"]
    print(f"\n=== VERGLEICH: KK-Medienslider ===")
    print(f"  kk_cover_url: {len(kk)}/{len(withkk)} Venues mit KK-Seite = {len(kk)/len(withkk)*100:.1f}%")
    print(f"  verschiedene URLs: {len(set(r['kk_cover_url'] for r in kk))} (keine Dubletten)")
    print(f"  mit alt-Text:      {sum(1 for r in kk if r.get('kk_cover_alt'))}")

    print("\n=== EINZELURTEILE ===")
    for rk, r in hits:
        v, why = VERDICT.get(rk, ("unbekannt", ""))
        print(f"  {rk:4} {r['name'][:34]:34} {v:15} {why}")


if __name__ == "__main__":
    main()

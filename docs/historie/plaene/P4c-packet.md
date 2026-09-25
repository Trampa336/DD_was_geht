# P4c — venue enrichment: resolve, load, finish, verify

**Model: Opus 5.** Open-ended measurement plus a contradiction between two prior workers; the load step is mechanical but the verification is not. Run this packet and nothing else. If a premise below turns out to be wrong, **stop and report** rather than working around it — the supervisor re-scopes.

Working tree: `/home/admin/dd-was-geht/backend`. venv: `../.venv/bin/python` (do not build another). Repo code/comments/UI are German; this planning doc is English.

## Why

The venue enrichment sweep (P4b) reached **114 of 160 venues** and was then stopped deliberately by David. Its results are on disk but **not in the database**, its verification step never ran, and it left a direct contradiction with the packet before it. Nothing here needs re-fetching what is already cached. This packet closes out venue enrichment so P5 can render venue pages.

## Standing facts you need (all measured, do not re-derive)

- DB to work against: **`backend/data/dd-was-geht-v2.db`** (schema v2, gitignored, not deployed). The live CT103 DB is separate and is **not** in scope — see follow-up 3.
- Schema v2 gives `venues` slug/name/region/kind/parent_venue_id plus **homepage and meta slots specifically for this packet**. `venue_aliases` exists so merges are data, not code.
- 709 venues / 744 aliases seeded. **`kind` was curated by P3 for the top 120 by event count**; the remaining ~590 sit at `sonstiges` by design.
- Event counts have three distinct meanings and get crossed constantly — **run-seen** (`scrape_runs.event_count`), **reach** (`event_sources` rows), **winner** (`events`, `duplicate_of IS NULL`, future = **5239**). Always name which one you mean.
- Today's baseline: **~35% of events classify as `sonstiges`**.
- Tool: `tools/enrich_venues.py`, invoked as
  `../.venv/bin/python -u tools/enrich_venues.py data/dd-was-geht-v2.db --limit=160`
- Cache: `backend/data/venue_cache/enrichment.json` — **114 records, 88 with a homepage**. Fields per record include `homepage_url`, `kk_cover_url`, `kk_cover_alt`, `all_homepage`, `all_social`, `all_other`, `kind`, `meta`.
- `venues.homepage_url` is currently **0 populated**.
- Measured pacing: **3.5 s/venue** (an earlier 35 s/venue estimate was wrong).
- Link rule, measured on the partial sweep: literal "the venue page's one outbound link" = **37.5%** success; the refined rule — **the homepage is the link whose anchor text is its own bare domain** (`zentralwerk.de`, `www.skd.museum`) — = **81.2%**. Kulturkalender venue pages carry 3+ outbound links (KK's own footer socials, YouTube embeds, in-description links).
- Kulturkalender **event** pages serve no JSON-LD and no `og:` tags. Venue **homepages** are third-party sites and are a separate question — that is task 1.
- Venue-kind categorisation ceilings at **73.8%** on the top 120 (only 19 are single-category, 67 span 3+).

## The assumption to test

> **"The og:image contradiction is a measurement artefact that the data already on disk can settle — no refetching required."**

State plainly whether it held. If the cached data cannot settle it, say so and say exactly what minimum fetch would, **before** fetching anything beyond the 46 venues in task 3.

## Do — in this order

**1. Resolve the og:image contradiction. This comes first; tasks 2–4 must not overwrite the evidence.**

Two workers measured the same sweep and disagree:
- **P4** reported venue homepages carry "essentially no `og:image`", stated as verified against raw HTML, not just a selector. Decision #5 ("cover from the homepage's og:image") and the whole "use the Kulturkalender media-slider photo instead" fallback rest on this number.
- **P4b**, running the same sweep, measured `og:image` at **35.8%**.

35.8% is a usable cover source; "essentially none" is not. Both figures are currently **inferred, not verified**. Settle it from `enrichment.json` and any cached raw HTML the tool kept. Specifically determine:
- **What each number's denominator was** — all 114 records, only the 88 with a homepage, only successfully-fetched pages, or something else. A denominator mismatch alone could produce both figures from one dataset.
- **What was being measured** — the venue's own homepage vs. the Kulturkalender venue page; `og:image` vs. `twitter:image` vs. a bare `<img>`; parse-time failures counted as absent.
- **Whether the hits are usable as covers** — how many are distinct, non-placeholder, venue-specific images rather than logos, social-badge sprites or CMS defaults. A 35.8% hit rate of logos is not a cover source. This judgement is the point of the packet, not the raw percentage.

Report one number with its denominator, plus the usable-cover count. Then say which source P5 should render from: homepage `og:image`, `kk_cover_url`, or both with a fallback order.

**2. Load `enrichment.json` into `venues` — do not re-fetch those 114.**

Write the loader **idempotently** (re-running after task 3 must not duplicate or clobber), joining cache records to `venues` rows explicitly — do not assume the JSON's keys match `venues.slug`. Report how many of the 114 matched a venue row and what you did with any that did not.

Do **not** silently overwrite P3's curated `kind` with the tool's inferred `kind`. Keep the curated value and record the disagreement — that is task 4's number.

**3. Finish the remaining ~46 venues** of the 160, resuming rather than restarting (~46 × 3.5 s ≈ 3 minutes). **Respect the existing request delay** — it is mandated, do not lower it. Then load those results the same way as task 2.

**4. Run the verification P4b never reached.** Three numbers:
- **Hand-check 20 venues against their real homepages. Report the FAILURE rate, not the success count** — and for each failure, what went wrong (wrong site, social page, aggregator page, dead link, empty). 20 is the sample size; say how you chose them.
- **`kind` disagreement rate**: tool-inferred `kind` vs. P3's curated `kind`, over the venues where both exist. Report the rate and characterise the disagreements — which direction, and which is right where you can tell.
- **Category headroom.** Quantify what venue `kind` alone would do to today's **~35% `sonstiges`**: over the 5239 winner events, what share lands in a non-`sonstiges` category once `kind` is populated for the enriched venues, against the 73.8% theoretical ceiling. This number decides a live question David is waiting on — whether 73.8% is good enough or a second per-event classification layer is warranted. **Do not answer that question yourself; produce the number.**

## Done when

- The og:image question has one verified number with a stated denominator, plus a usable-cover count and a recommended cover source for P5.
- `venues.homepage_url` is populated for all enriched venues that have one, from cache plus the finished sweep — no venue fetched twice.
- All four verification numbers are reported: failure rate (20 hand-checked), `kind` disagreement rate, category headroom, and the enriched-venue count.
- `../.venv/bin/python tests_smoke.py` is **green** (380 checks, 0 failures at last run).
- Work is **committed locally**. **Never push** — write access is unverified from this tree. Commit messages end with:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`

## Report back — head first, short enough to paste

1. **result** — one paragraph: what is now true.
2. **the one finding that matters** — including, explicitly, whether the assumption above held or was disproven. Every analysis packet in this project so far has disproved something; if nothing broke, say that and say what you checked.
3. **the numbers** — og:image (with denominator) · usable covers · recommended cover source · venues loaded · venues still unenriched · hand-check failure rate out of 20 · `kind` disagreement rate · category headroom vs. 35% `sonstiges`.
4. **follow-ups** — anything the supervisor must fold in, including:
   - whether the ~590 long-tail venues need anything before P5 renders their (fetch-free) pages;
   - whether the refined bare-domain-anchor link rule held at 160 venues or degraded past 114;
   - **how this enrichment reaches the live CT103 database at cutover** — the v2 DB is a local verification copy. Describe the path; do **not** implement it or touch CT103 in this packet.

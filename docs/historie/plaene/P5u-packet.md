# P5u — cybersax address-page enrichment for the 74 bare venues

**Model: Opus 5.** Open-ended: an untested page structure, new fetcher logic, and writes into an
enrichment path other tools already depend on.

Tree `/home/admin/dd-was-geht/backend`. Python `../.venv/bin/python`. **Commit locally. NEVER push.
NEVER touch CT103 or the live database.** Work against `backend/data/dd-was-geht-v2.db`. A root cron
publishes publicly at 15 1,7,13,19.

**Why this packet exists:** P5t proved the 74 bare venue pages cannot be fixed by the existing tool —
all 74 come from `cybersax`, which by design covers only venues Kulturkalender does *not* carry, and
`enrich_venues.py` requires a KK venue page to exist. 0/74, full 32-day census. David was offered
"accept them", "try cybersax first", "close it out permanently" and chose **try cybersax first.
Hearts waits.**

## The assumption to test

> **"cybersax's own `/terminal/adressen/address/<ort>/` pages exist for these 74 venues and carry
> outbound links to the venue's homepage."**

**This is [I] and rests on ONE piece of evidence: a docstring in `app/scrapers/cybersax.py`.**

**A docstring in this codebase has already been proven to lie.** `enrich_venues.py`'s docstring claims
it caches raw HTML; **it never writes any**, and a previous packet's "verified against raw HTML" claim
was therefore unsupportable. **Do not trust this docstring either. Verify against actually fetched
pages before building anything on it.**

## Fail fast, and say so

**Sample ~10 of the 74 first.** Report: how many have an address page at all, how many of those carry
an outbound link, and what the links actually point at (homepage? Facebook? Instagram? the venue's
own subpage?). **If the first 10 yield zero usable homepages, stop and report — do not grind through
the remaining 64.** A fast structural "no" is a complete result and the second-best outcome here.

If the sample is non-zero, continue to all 74. **[V]** measured pace elsewhere is 3.5s/venue;
**respect the mandated 1.2s request delay.**

## Rules on what you may write

**A venue description may ONLY come from fetched meta text. NEVER write one from your own knowledge,
and never infer one from the venue's name.** This publishes to a public website about real Dresden
businesses — small bars, cafés and clubs. An invented sentence is a factual claim David never made
and cannot check. No scrapable description means **no description**. A short honest page is fine.

**Same for `kind`.** P5t left **9 of the 74 at `sonstiges` on purpose** and named them:
`tonkunstraum`, `riesa efau, Motorenhalle`, `Trinitatishaus`, `Sächs. Akademie der Künste`,
`Sachsensofa`, `Richard-Wagner-Stätten`, `Katy's Garage`, `Elbe-Schleppkahn "Waltraut"`,
`Bahnbetriebswerk Dresden-Altstadt`. **If newly scraped text gives real evidence for one, set it and
cite the text. If not, it stays `sonstiges`.** That worker declined to use outside knowledge of what
`riesa efau, Motorenhalle` actually is — **hold that same line.** Also re-check P5t's one
moderate-confidence call: `Puppentheatersammlung` → `museum`, inferred from "Sammlung", not a keyword.

**Link quality matters more than link count.** P4c found homepage `og:image` hits that were logos,
dead links, CMS defaults and a city-portal image that mutated into a photo of a flood. **Hand-check
what you store.** Report a *failure* rate, not just a success count.

## Also fix a trap P5t found

**`tools/venue_readiness_report.py` section 4 now prints "0/726 truly bare". That is FALSE** — it
scopes to `meta_status IS NULL`, and P5t moved the 74 to `'not_found'`. The real figure is 74. **Fix
the scoping so the report stops printing a false zero**, and state the corrected number before and
after your run.

## Mechanics

- **Do not corrupt the existing cache.** `enrich_venues.py` skips anything already in
  `enrichment.json`, and these 74 are cached there as `kein_kk_link`. P5t handled this by writing to a
  **separate cache file**; do the same.
- Write into the existing venue fields (`homepage_url`, `homepage_root`, `og_image_url`,
  `meta_description`) so the venue page picks them up with no template change. **Record provenance in
  `cover_source`** — a cybersax-sourced cover is not a Kulturkalender one and must not claim to be.
- **Do not invert the cover fallback order** (`kk_cover_url` first, homepage `og:image` second) — two
  stored og:image URLs are already dead.
- **Do not touch** the image fallback P5b added (borrow the nearest upcoming event's image). It is why
  the number is 74 and not 277.

## Out of scope

Hearts, visitor likes, retiring `reactions`/`apply_reaction`/`/api/feedback`, `score`. Next packet.
Do not enrich beyond these 74.

## Gates

- `../.venv/bin/python tests_smoke.py` green — stands at 425 checks / 0 failures. Name any assertion
  you change and why.
- `git status --short` clean, committed locally. Commits end
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Repo code, comments and UI are **German**. Planning docs English.
- Mark every fact **[V]** (say how) or **[I]**. **Any rate needs its denominator**, and its depth if
  it came from a ranked sweep. **Five figures in this project have failed to reproduce** — if one you
  are handed does not reproduce, report that rather than smoothing it over.

## Report — head first

1. **result** — how many of the 74 are no longer bare, and the corrected residual over all 726.
2. **the one finding that matters** — what this changes for hearts.
3. **follow-ups** — including every venue left `sonstiges`, and the failure rate of what you stored.

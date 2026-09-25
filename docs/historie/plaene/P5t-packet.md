# P5t — fill in the 74 bare venue pages (runs between P5b and hearts)

**Model: Sonnet 5.** Tree `/home/admin/dd-was-geht/backend`. Python `../.venv/bin/python`.
**Commit locally. NEVER push. NEVER touch CT103 or the live database.** Work against
`backend/data/dd-was-geht-v2.db`. A root cron publishes publicly at 15 1,7,13,19.

**Why this packet exists:** P5b shipped venue pages and measured that **74 of 726 (10.2%)** are still
a bare dead end — one event, no photo, no description, `kind` uncurated (`sonstiges` for all 74).
David was given four options and chose **"fill them in first"**, ahead of hearts. A hearted event
leading to a dead-end page is precisely the hand-off decision #4 exists to kill.

Reproduce the list with the existing `tools/venue_readiness_report.py` — do not re-derive it by eye.

## The assumption to test

> **"These 74 venues are bare because nobody ever tried them, not because there is nothing to find."**

**[V]** they sit inside the 569 venues never attempted for enrichment — the sweep ran on the top 160
by event count and these are single-event venues at the bottom of the tail. So the cheap mechanical
route has never been run on them.

**[V]** and encouraging: P4c measured that the bare-domain-anchor link rule **improved** with depth —
83.7% at ranks 1–114, **92.1% at ranks 115–160**, 85.9% overall. It did not degrade going down the
tail. **[I]** whether that holds all the way to single-event venues is unknown; ranks 115–160 are
still far above the bottom. **Do not assume it holds. Measure it and report the rate with its
denominator and its depth** — this project has had four figures fall apart under recomputation, one
of them a rate carried to a narrower population without re-deriving it.

## Do the cheap thing first

1. **Run the existing `tools/enrich_venues.py` on these 74 venues only.** Do not write a new tool.
   **[V]** measured pace is 3.5s/venue, so 74 venues is roughly 5 minutes — this is the one packet
   where network requests are expected and correct. **Respect the mandated 1.2s request delay.**
   Then load results with `tools/load_enrichment.py` as P4c/P5a established.
2. **Re-measure and report:** of the 74, how many now have a cover, a homepage, a meta description.
   How many are still bare. **Denominators on everything.**
3. **Only then hand-curate what is left** — `kind` at minimum. All 74 are currently `sonstiges`, so
   this is a small categorisation win as well as a page-quality one.

## Hard rule on descriptions — read this twice

**A venue description may ONLY come from a fetched `meta description` or equivalent scraped text.
NEVER write one from your own knowledge or imagination, and never infer one from the venue's name.**

This content is published to a public website about real businesses and institutions in Dresden. An
invented sentence about a real venue is a factual claim David did not make and cannot check. If a
venue has no scrapable description, **it has no description** — leave it empty and let the page be
short. A short honest page is fine. A plausible-sounding invented one is not.

The same applies to `kind`: infer it from the venue **name** and its **event titles**, which are real
data. If a name gives you no confident read, **leave it `sonstiges` and list it in your report as
uncertain.** `sonstiges` is a real answer in this project (decision #14) — do not launder a guess
into a label to make a number look better.

## Then re-measure the whole thing

Report the **bare-page count over all 726 addressable venues**, before and after. P5b's fallback
(borrow the nearest upcoming event's `image_url` when the venue has no `og_image_url`) is already in
place and is the reason the figure is 74 and not 277 — **leave that fallback alone.**

**Cover order is `kk_cover_url` first, homepage `og:image` second. DO NOT INVERT IT.** **[V]** two
stored og:image URLs are already dead; inverting surfaces broken images immediately.

## One check before you start

**[I], unverified:** the state file separately defers "curating `kind` on the **70** already-enriched
venues P3 left unset (706 residual `sonstiges` events)". Those are high-event-count venues *with*
covers; these 74 are single-event venues *without*. **They should be disjoint sets — confirm that
they are** and say so, so nobody conflates the two later. If they overlap, report the overlap.

## Out of scope

Hearts, visitor likes, retiring `reactions`/`apply_reaction`/`/api/feedback`, `score`. All next packet.
Do not curate beyond the 74 — the 70-venue set above is a separate deferred packet and is not this one.

## Gates

- `../.venv/bin/python tests_smoke.py` green (P5b left it at 425 checks / 0 failures). If you change
  an assertion, name which and why.
- `git status --short` clean, committed locally. Commits end
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Repo code, comments and UI are **German**. Planning docs English.
- Mark every fact **[V]** (say how you verified) or **[I]**. Any rate needs its denominator, and its
  depth if it came from a ranked sweep.

## Report — head first

1. **result** — how many of the 74 are no longer bare, and the residual over all 726.
2. **the one finding that matters** — what this changes for hearts.
3. **follow-ups**, including every venue you left `sonstiges` because you were not confident.

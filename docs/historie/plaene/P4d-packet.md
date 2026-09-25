# P4d — how far do German title-keyword rules actually get?

**Model: Sonnet 5.** Fully specified measurement work with a known shape. If a premise below turns out to be wrong, **stop and report** rather than working around it — the supervisor re-issues on Opus.

**Do not start this while P4c is still running.** Both touch `backend/data/dd-was-geht-v2.db`. P4c writes to it; you only read.

Working tree: `/home/admin/dd-was-geht/backend`. venv: `../.venv/bin/python` (do not build another). Repo code/comments/UI are German; this planning doc is English.

## Why

Event categorisation is the weakest part of the catalog: **~35% of events sit in `sonstiges`** today. The obvious fix — curate a `kind` per venue and inherit it — was measured and capped: a *perfect* venue→category map ceilings at **73.8%** on the top 120 venues, because only 19 of them are single-category and **67 span three or more**. Those 67 are the high-volume venues, so venue kind is weakest exactly where it matters most.

David has ruled (decision #14) that a second layer goes **above** venue kind, and that it is **German title-keyword rules, not a classifier**. Reason: for a filter UI a wrong category is worse than an absent one — `sonstiges` is merely unhelpful, but a techno night filed under Theater makes the filter lie.

This packet does not build that layer. It measures whether it can carry the weight, so P5 knows how much to lean on it.

## Standing facts you need (measured, do not re-derive)

- DB: **`backend/data/dd-was-geht-v2.db`** (schema v2, gitignored, not deployed). **Read-only in this packet.** The live CT103 DB is out of scope.
- Event counts have three distinct meanings and get crossed constantly — **run-seen** (`scrape_runs.event_count`), **reach** (`event_sources` rows), **winner** (`events`, `duplicate_of IS NULL`, future = **5239**). Always name which one you mean.
- **For 85% of the catalog, title + venue are the only signals.** `raw_category` is filled 30.5% overall but only **20.6% for kulturkalender**, which is 85% of the corpus. `description` is 9.1% overall, **2.5% for kulturkalender**. URL path is useless (3862/4472 under `/veranstaltung/`).
- **~1179 winner events are guided tours.** Expect `Führung` to be the single largest rule. Frauenkirche runs tours *and* concerts — this is precisely the signal venue kind cannot express.
- `venues.kind` was curated by P3 for the top 120 by event count; the remaining ~590 sit at `sonstiges` by design.
- Venue shape: 709 venues, **38% have exactly 1 event, 56% have ≤2, ~120 carry the catalog.**
- Category taxonomy lives in the `categories` table (schema v2). Map to **existing** slugs — do not invent new categories in this packet.

## The assumption to test

> **"German title keywords resolve the majority of events at multi-category venues — a rule layer, not a classifier, is the whole fix."**

Say plainly whether it held. Every analysis packet in this project has disproved something; if nothing broke, say so and say what you checked.

## Do

**1. Identify the multi-category venues from the DB — do not trust the number 67.** Recompute which venues span 3+ distinct categories among their events, and report how many there are and how many winner events they carry. If the recomputed figure disagrees with 67, that disagreement is a finding: report it rather than reconciling it silently.

**2. Derive the keyword list from the real titles — do not invent it.** Run a frequency analysis over the German event titles at those venues (tokens and short phrases, case-folded, umlaut-aware). Build the candidate rule list from what actually appears. A list written from imagination will score well on itself and badly on the catalog.

**3. Sample ~200 events from those venues.** State how you sampled — random, stratified by venue, or by volume — and why. Keep the sample reproducible (fix the seed, record the uids).

**4. Measure coverage AND precision separately. This is the point of the packet.**
- **Coverage**: what share of the 200 does the rule list assign a category to at all?
- **Precision**: of those assignments, what share is *correct*? Hand-check them against the title (and the venue where the title alone is ambiguous).

A list that resolves 80% at 60% precision is **worse** than one resolving 50% at 95% — the first fills the UI with confident lies, the second leaves honest gaps. Report both numbers for the list as a whole, and for the top ~10 individual rules, so weak rules can be dropped rather than the whole layer judged by them.

**5. Report the `Führung` case on its own.** Is it really one rule? What precision does it reach, and what does it misfire on?

**6. Characterise the residue.** Of the sampled events the rules do not resolve: what would it actually take? Group them — needs the description (which is 2.5% filled on kulturkalender), needs outside knowledge of the act, genuinely ambiguous, or simply a missing keyword. This is the evidence for or against ever adding a classifier, so be concrete and quote example titles.

## Done when

- Multi-category venue count recomputed and reported against the expected 67.
- Keyword list derived from real title frequencies, with its provenance shown.
- Coverage and precision reported **separately**, overall and per top-10 rule.
- The `Führung` rule reported on its own.
- The unresolved residue characterised with real example titles.
- **Nothing ships into the write path.** Do not modify `db.py`'s categorisation, the `categories` table, or any event row. A throwaway analysis script under `tools/` or the scratchpad is fine; a behaviour change is not — that is P5's call, gated on these numbers.
- `../.venv/bin/python tests_smoke.py` is **green** (380 checks, 0 failures at last run).
- Work is **committed locally**. **Never push** — write access is unverified from this tree. Commit messages end with:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`

## Report back — head first, short enough to paste

1. **result** — one paragraph: what is now true.
2. **the one finding that matters** — including whether the assumption above held or was disproven.
3. **the numbers** — multi-category venue count (vs 67) · winner events they carry · sample size and method · coverage % · precision % · per-rule table for the top 10 · `Führung` coverage and precision · unresolved residue %.
4. **follow-ups** — anything the supervisor must fold in, especially: which rules are strong enough for P5 to ship, which should be dropped, and whether the residue is a keyword-list gap (cheap, keep extending) or a genuine signal gap (expensive, needs a decision from David).

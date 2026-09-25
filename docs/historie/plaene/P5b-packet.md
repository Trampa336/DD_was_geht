# P5b — the read surfaces: searchable list + venue pages

**Model: Sonnet 5.** Tree `/home/admin/dd-was-geht/backend`. Python `../.venv/bin/python`.
**Commit locally. NEVER push. NEVER touch CT103 or the live database.** A root cron publishes
publicly at 15 1,7,13,19. Everything you do stays in the local tree and the local verification DB
`backend/data/dd-was-geht-v2.db` (gitignored, not deployed).

**This is the first packet David will actually SEE.** Everything before it was plumbing. He chose
to split the frontend into two stages so he can look at something real sooner. Stage two (hearts)
is a separate packet — do not start it.

## The assumption to test

> **"Every event resolves to a venue page, and a venue page built only from data already held is
> worth landing on — including for the ~569 venues with no cover and no homepage, 38% of which
> have exactly one event."**

This is the project's core feature (decision #4: an event leads to a venue page *inside the app*,
not out to Kulturkalender). If a typical venue page turns out to be a name and a single event with
no photo and no description, then landing there is **worse** than the Kulturkalender page it
replaces, and the design needs a fallback before it ships — not after.

**Test it with real numbers before you finish the templates.** Report:
- how many of the 5239 winner events resolve to a venue row (and how many do not — say what happens
  to those);
- the distribution of what a venue page can actually show: how many venues have a cover, a homepage,
  a meta description, ≥3 upcoming events, exactly 1 event;
- your honest read on whether the thin ones are worth landing on, and what you did about it.

**If the assumption is false, say so and propose the fallback. Do not quietly ship thin pages.**

## Build

**Decision #7: the old frontend is replaced, not extended.** But P5a established **[V]** that the
export renders the *live Jinja templates in-process* (`tools/export_static.py:160-172`, `mode="static"`),
so whatever you build must render correctly in **both** modes from one template set. Verify both.

1. **Searchable list** — the main surface, as today but working. Filters for **category** and
   **tag** (both are real tables; 5 tags are seeded: `kirche`, `museum`, `open-air`, `klassik`,
   `techno`). Search over title and venue.
2. **Region toggle, default Dresden-only** (decision #12). Region lives on the **venue** row. Nothing
   is dropped — Meissen/Umland is one switch away.
3. **Venue pages** for all ~729 venues. Enriched ones (160) show cover, homepage button, meta
   description, upcoming events. Unenriched ones (~569) show name, kind, region, upcoming events —
   **no cover, no fetch, no network requests anywhere in this packet.**
4. **Event → venue page**, not Kulturkalender. Keep the per-event link to the event's own official
   page as well (decision #11) — both links exist, they are different things.
5. **Homepage button uses `venues.homepage_root`** (the `scheme://netloc` column P5a added), because
   a chunk of stored `homepage_url` values are deep links into the venue's own event listing. Keep
   `homepage_url` available; do not delete it.
6. **Covers: `kk_cover_url` first, homepage `og:image` second. DO NOT INVERT THIS ORDER** — **[V]**
   two stored og:image URLs are dead, and inverting surfaces broken images immediately. P5a measured
   the live split as 142× kulturkalender / 0× homepage; `venues.cover_source` records which won.

## Two specific checks

- **`score` is a constant.** **[V]** P2: `reactions` and `weights` have 0 rows, `score` was never a
  column, and all ~5235 exported events carry `score: 50.0`. Find out whether anything actually
  consumes it (sorting, display, the export payload). **If nothing does, stop exporting it.** If
  something does, leave it and report what. Do not touch `scoring.py`, `reactions` or
  `/api/feedback` — those retire in the next packet, together.
- **Schema declaration.** **[I], unverified by anyone:** `venues.homepage_root` and
  `venues.cover_source` are added by `ALTER TABLE` inside `tools/load_enrichment.py`, not declared in
  `migrations/001_schema_v2.sql`. Confirm where they are declared and whether a fresh DB built from
  the DDL would be missing them. Report; fix only if it is trivial and safe.

## Explicitly OUT of scope — next packet

Hearts, the visitor `localStorage` like, retiring `reactions`/`apply_reaction`/`/api/feedback`,
`rating.js`. The curated page: **David ruled it ships empty and he fills it** — so build no
curated page and no shortlist/proposer in this packet.

## Let David look at it

He must be able to open this himself. **Do not use port 1111** (that is the live app on CT103).
Run the app locally against the verification DB on a free port bound so he can reach it from his
LAN, confirm it serves, then **give him one copy-pasteable command** to start it himself, and the
exact URL. Also build the static export locally and confirm it renders — but publish nothing.

## Gates

- `../.venv/bin/python tests_smoke.py` green before reporting done. If your rebuild legitimately
  changes what the smoke suite asserts about the frontend, **say exactly which assertions you
  changed and why** — a previous packet's red smoke test blocked everything for a day.
- `git status --short` clean, changes committed locally. Commits end
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Repo code, comments and UI are **German**. Planning docs English.

## Evidence discipline

Mark every fact **[V]** (you verified it, say how) or **[I]** (inferred). **Any rate needs its
denominator.** Three figures in this project have failed to reproduce under recomputation — most
recently P4c's "45 of 123 homepages are deep links", which gives 49 or 21 depending on the rule.
**Do not cite 45.** If a number you are handed does not reproduce, report that rather than
smoothing it over.

## Report — head first

1. **result** — what you built, and the answer to the assumption, with numbers.
2. **the one finding that matters** — the single thing that changes the hearts packet.
3. **follow-ups.**

# P5w — duplicated entries in the event list (diagnose first, then fix)

**Model: Opus 5.** Open-ended diagnosis across the query path, the template and the dedup data.

Tree `/home/admin/dd-was-geht/backend`. Python `../.venv/bin/python`. **Commit locally. NEVER push.
NEVER touch CT103 or the live database.** Work against `backend/data/dd-was-geht-v2.db`.

**A dev server is already running on port 8090** against that DB (`WEB_PORT=8090`). Use it. If you
restart it, put it back afterwards — **David is actively looking at it.** Do not take port 1111.

**Why this packet exists:** David opened the new frontend and reported **"there are a lot entries
doubled"**. That is the whole bug report; treat it as a symptom, not a diagnosis. He has not yet said
which entries or on which view — if a detail arrives mid-packet it will be forwarded to you.

## Diagnose before you touch anything

**The single most important distinction, and your report must answer it explicitly:**

> **Is the same event rendering twice (one `uid`, two rows), or are there two different `uid`s for
> what is really one event?**

These are completely different bugs with completely different fixes, and **one of them must not be
fixed with `DISTINCT`.** A row fan-out in a query is cosmetic and `DISTINCT`-able; a genuine dedup
failure in the data is a real defect, and hiding it behind `DISTINCT` would suppress the evidence
while leaving the bad rows in the database. **Name which one you found before you change a line.**

## The assumption to test

> **[I] "The duplication is a query-level row fan-out introduced when category/tag filtering was
> joined into the list — an event with N tags yields N rows — not a data-level duplicate in
> `events`."**

**This is the supervisor's hypothesis and it is inferred, not verified.** The supervisor has authored
two false premises in this project and both were caught by workers. **If the evidence points
elsewhere, say so plainly and follow the evidence.** Tag filtering and the tag join are recent
(P4e seeded 5 tags and 2154 `event_tags` rows; P5b wired a tag filter into the list), which is what
makes this the first thing to look at — **not proof that it is the cause.**

## Rule these in or out explicitly, with counts

1. **Join fan-out** — `event_tags`, `categories`, `venues`, `event_sources` or any other join
   multiplying rows per event.
2. **`duplicate_of` not applied.** **[V]** the winner filter in this project is
   `duplicate_of IS NULL` **and** future-dated. **[V]** counts are three different things and get
   crossed constantly here: **run-seen** (`scrape_runs.event_count`), **reach** (`event_sources`),
   **winner** (`events`). **Say which you are quoting, every time.**
3. **Genuine dedup miss** — the same real event ingested from two sources (kulturkalender and
   cybersax both carry it) that `event_duplicates` failed to match. **[V]** `uid =
   sha1(date|time|slug(title)|slug(venue))[:16]`, so a venue-string or title difference across
   sources produces two uids for one event. **[V]** `registry.EXTRA_VENUE_ALIASES` is live
   dedup-matching code — **understand it before touching it, and do not remove it.**
4. **Legitimately repeating events** — a run that genuinely happens on many dates is **not** a
   duplicate. **[V]** P2 measured uid collisions at 31/8468 = 0.37%, "only on generic repeating
   titles". Do not "fix" a real repeat into invisibility.
5. **Venue alias resolution** producing two venues for one house, splitting one event into two.

## Required numbers, with denominators

- How many rendered list rows are duplicates, **out of how many rows on that view**.
- How many distinct `uid`s are affected.
- Whether the rate differs between the **live Flask view** and the **static export** — **[V]** both
  render from the same Jinja templates in-process (`tools/export_static.py:160-172`), so a template
  or query bug appears in both and an export-only bug is a different animal. **Check both.**
- Whether it differs by filter state (no filter / category selected / tag selected / region toggled).

## Fix

Only after the cause is named. **Fix the cause, not the symptom.** If you find genuine duplicate data,
report it and say what a data fix would involve — **do not mass-delete rows in this packet.**

## Do not touch

Hearts, visitor likes, `reactions`/`apply_reaction`/`/api/feedback`, `score`. The cover fallback order.
P5b's event-image fallback. `enrichment.json`.

## Gates

- `../.venv/bin/python tests_smoke.py` green — **stands at 485 checks / 0 failures.** **Add a
  regression test that fails on the bug and passes on the fix.** Name any assertion you change and why.
- `git status --short` clean, committed locally. Commits end
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Repo code, comments and UI are **German**. Planning docs English.
- Mark every fact **[V]** (say how) or **[I]**. **Six figures in this project have failed to
  reproduce** — report any that does not. **Do not trust a tool's printed summary without re-deriving
  the predicate**; one reporting tool was caught printing a false zero.
- **`meta_status` being *set* and being `'ok'` are different facts** — P5v fixed a live bug caused by
  conflating them. Do not repeat it.

## Report — head first

1. **result** — which of the two bugs it is, the cause, and the numbers.
2. **the one finding that matters** — what this changes for hearts.
3. **follow-ups.**

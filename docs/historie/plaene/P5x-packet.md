# P5x — collapse long same-day runs in the list (display layer only)

**Model: Sonnet 5.** Fully specified: one measurement, then a presentation change.

Tree `/home/admin/dd-was-geht/backend`. Python `../.venv/bin/python`. **Commit locally. NEVER push.
NEVER touch CT103 or the live database.** Work against `backend/data/dd-was-geht-v2.db`.

**A dev server is running on port 8090 and David is using it.** If you restart it, put it back. Never
take port 1111.

**Why this packet exists:** David reported "a lot entries doubled". P5w proved **[V]** that almost all
of it is correct data — the Frauenkirche really does run five separate bookable Domführungen in a day,
and Kulturkalender lists them as five cards. **437 rows beyond the first / 5026 winner rows = 8.7%**
share a day and title with another row. Offered three presentations, David chose **"collapse only long
runs"** (#24): a double-bill stays two rows; an hourly tour run folds into one row listing its times.

## The assumption to test

> **"A threshold exists in the group-size distribution that separates hourly tour runs from genuine
> double-bills — and collapsing at it removes the noise David saw without hiding any real showing."**

**[I].** Nobody has looked at the distribution. **Measure it before you pick a number.**

**Step 1, measurement, before any UI change:** the group-size histogram over winner rows — how many
groups of exactly 2, 3, 4, 5, 6+; how many rows each bucket accounts for; **denominators stated**.
Then pick the threshold **from that data** and **say why**. **[I]** the supervisor's starting guess is
collapse at **3+** (groups of 2 stay as two rows) — David's words were "more than two or three times".
**If the distribution argues for a different cut, take the data and explain it.**

## The grouping key — get this right or you will merge unrelated events

Group only on **same date + same venue + same normalised title**. **Venue is not optional:** two
different houses each running a "Führung" on the same day are **not** one run. State exactly what
normalisation you apply to the title, and **[V]** it against real rows.

**Beware:** P5w found `_title_tokens` drops words under three characters, which made
`S.Y.N.T.H.E.T.I.C S.I.G.N.A.L.S` tokenise to nothing. **Do not reuse a normaliser with that property
for grouping** without checking what it does to dotted and short titles.

## Display layer ONLY — this is the hard constraint

**The grouping happens in the rendering path (`loadList` in `app/static/app.js` and whatever the
template needs), NEVER in the SQL and NEVER with `DISTINCT`.**

P5w established **[V]** that there are **zero** duplicate uids anywhere — every row is a real,
separately bookable showing. **A query-level change would delete four of the five Domführungen from
the page.** The API must keep returning every showing; only the presentation folds them.

A collapsed row must:
- show **all** its times, in order;
- keep **every** underlying showing reachable — each has its own `uid` and its own source URL;
- be visibly a run, not a single event at an odd time.

## Must keep working

- The **client-side tag filter** (`app/static/app.js:247-250`) and the category, region and
  Dauerangebote filters. **Check every filter state** — a collapsed row must behave correctly when a
  filter hides some of its members.
- **Both render modes.** **[V]** live Flask and the static export share the templates in-process
  (`tools/export_static.py:160-172`). **Verify both**; P5w confirmed they behave identically today.
- `score`, the top-pick badge and the "wenig relevant" filter — **[V]** three live consumers. Do not
  break them; do not touch them.

## Report, do not build: the hearts consequence

**[V]** P5w found a heart lands on a *showing*, not an event, and no code path relates the five
Domführung uids. Collapsing makes that visible: **what should hearting a collapsed row mean?**
**Say what you recommend and why — the next packet builds hearts. Do not implement any of it here.**

## Do not touch

Hearts, visitor likes, `reactions`/`apply_reaction`/`/api/feedback`, `score`, `dedup.py`, the cover
fallback order, P5b's event-image fallback, `enrichment.json`. The 22 known cross-source misses and
the 3 split venue rows are **separate deferred packets** — not this one.

## Gates

- `../.venv/bin/python tests_smoke.py` green — **stands at 489 checks / 0 failures.** **Add a
  regression test that a real multi-showing run still exposes every showing after collapsing.** Name
  any assertion you change and why.
- `git status --short` clean, committed locally. Commits end
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Repo code, comments and UI are **German**. Planning docs English.
- Mark every fact **[V]** (say how) or **[I]**. **Any rate needs its denominator**, and **name which
  event count you are quoting** — run-seen (5948), reach (5880) and winner (5026, `duplicate_of IS
  NULL`, today…+45d) are three different things and get crossed constantly here.
- **Six figures in this project have failed to reproduce.** Report any that does not.
- **Do not trust a tool's printed summary without re-deriving the predicate.**

## Report — head first

1. **result** — the distribution, the threshold you chose and why, and the before/after row count on
   the default view.
2. **the one finding that matters** — including your recommendation for hearting a collapsed run.
3. **follow-ups.**

# P5a — export-render recon + fetch-free data fixes

**Model: Sonnet 5.** Working tree `/home/admin/dd-was-geht/backend`. venv `../.venv/bin/python`.
**Commit locally. Never push. Never touch CT103 or the live database.** A root cron publishes
publicly at 15 1,7,13,19 — a bad deploy is visible to the world 45 minutes after a scrape.

## The assumption to test

> **"The static export renders through the same Flask templates the live app serves, so keeping
> heart/write routes out of the export is a matter of route separation."**

This is P5's whole design premise and **no worker has verified it.** It is marked **[I] inferred**
and inferred facts have a bad record in this project. If it is false — if the export is built by a
separate generator that never touches the live templates, or conversely if it renders by walking
live routes — then P5's frontend design changes before a line of it is written.

**Report what you find even if it makes P5 bigger. Especially then.**

## What is established (do not re-derive)

- **[V]** P1: cron `15 1,7,13,19 * * *` → `/opt/dd-was-geht/tools/publish_site.sh`; exports to
  `/app/data/site` in-container → rsync to `/root/dd-was-geht-site` → commit + push.
- **[V]** P1: export shape is a pre-rendered `index.html` + `data/index.json` + one JSON per day,
  69 files, ~2.8 MB. Every event already carries `uid` and `score`.
- **[V]** P2: `reactions` and `weights` have **0 rows**; all 5235 events export the constant
  `score: 50.0`, computed at serve time by `scoring.py`. `score` was never a column.
- **[V]** P3: `reactions` is alive and load-bearing — `tests_smoke.py`, `scoring.apply_reaction`
  and `/api/feedback` all depend on it today. It is hearts' predecessor, not a parallel system.
- **[I]** Nothing is established about *what code generates the export's `index.html`.* That is
  question 1 below. Do not assume.

## Deliverables, in order

### 1. Answer the gating question (recon, no changes)

- **What renders the export's `index.html`?** Name the file and the function. Does it import and
  render the live Flask templates, run a second generator, or drive the live app over HTTP?
- **Given that answer: how would a LAN-only heart button be kept out of the published export?**
  Route separation alone, a build-time template flag, a separate template, or something else?
  Say which, with the evidence from the code — not the tidiest option.
- **Does the export currently emit anything that would become a write endpoint or a call back to
  `192.168.178.91`?** Grep the built output if one is available locally; say if it is not.

### 2. Settle one arithmetic ambiguity left by P4e

P4e reported keyword extension taking `sonstiges` from **1834 (35.0%) → 1715 (32.7%)** among 5239
winner events, and separately reported `venues.kind` stage 3 gaining **24 events / 0.46 pp**.
**It does not state whether the 1715 already includes those 24.** Answer it. Give the current
`sonstiges` count with and without the venue-kind stage, denominators stated.

### 3. Fetch-free data fixes carried in from P4c — no network requests

- **Deep-link defect.** **[V]** 45 of 123 stored homepages (36.6%) are not site roots — they are
  `/veranstaltungen/`, `/programm/`, `/spielplan/` paths the venue submitted to Kulturkalender.
  A "Homepage" button landing on a venue's own event listing is poor UX. Store
  `scheme://netloc` **alongside** the full URL; keep both, drop neither. Name the column you add.
- **Cover attribution.** **[V]** `og_image_url` holds whichever source won with no record of
  which. Add a `cover_source` column and populate it from `enrichment.json` — no refetching.
- **Do NOT invert the cover fallback order.** **[V]** KK cover first, homepage og:image second.
  Two dead og:image URLs are stored as covers for venues that also have a KK cover; inverting
  surfaces 5 broken images immediately.

## Out of scope

Frontend work, hearts, retiring `reactions`, the `score: 50.0` export — all P5b. Do not start them.
If recon says P5b must be split differently, say so; do not act on it yourself.

## Gates

- `../.venv/bin/python tests_smoke.py` green (380 checks / 0 failures) before reporting done.
- `git status --short` clean at report time, changes committed locally.
- Commits end `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Repo code/comments/UI are German; this planning doc is English.

## Report shape — head first

1. **result** — what changed, what the gating question's answer is.
2. **the one finding that matters** — the single thing that changes P5b's shape.
3. **follow-ups.**

Mark every fact **[V]** verified by you against the live system or **[I]** inferred.
Any rate needs its denominator, and its sample depth if it came from a ranked sweep.

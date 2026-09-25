# P6a — rebuild the publish path and verify it LOCALLY. No cutover.

**Model: Opus 5.** Cross-cutting, container-coupled, and the only part of this rework whose blast
radius is public.

Tree `/home/admin/dd-was-geht/backend`. Python `../.venv/bin/python`. **Dev server is UP on :8090 and
David uses it — if you restart it, put it back. Never port 1111.**

## The line you must not cross

**P6a touches NOTHING outside the local tree.**

- **NEVER push.** **NEVER touch CT103.** **NEVER touch the live database.**
- **Do NOT change any GitHub Pages setting.**
- **Do NOT delete, archive or modify the `DD_was_geht` repo** — **[V]** P1 established that repo **IS
  the live public site** (build output, not source). Touching it takes David's site down.
- **Do NOT modify the root cron**, which publishes at `15 1,7,13,19`.
- **Do NOT touch `/root/dd-was-geht-site`** on CT103.

The cutover is **P6b**, a separate packet that runs only on David's explicit go. **Your job is to make
P6b safe and boring.**

## The assumption to test

> **"The new publish path can be fully verified locally — the only thing that genuinely cannot be
> tested without CT103 is the `git push` itself."**

**[I], and there is a concrete reason to doubt it: `publish_site.sh` exports to `/app/data/site`
*in-container*** (**[V]** P1), so the script is coupled to the Docker layout. **If parts of it cannot
be exercised outside the container, say exactly which parts and what P6b will therefore be testing
for the first time in production.** That list is the most valuable thing this packet can produce.

## Established, do not re-derive [V] — all from P1

- **Three repos, not two.** `backend` → `github.com/Trampa336/dd-was-geht` (`main`). `frontend` →
  `github.com/Trampa336/DD_was_geht`, **which is the Pages site itself**. Plus a third clone on CT103
  at `/root/dd-was-geht-site` that the cron pushes to.
- Pages serves from **`main` of the frontend repo. There is no `gh-pages` branch.**
- Cron → `/opt/dd-was-geht/tools/publish_site.sh`: export to `/app/data/site` in-container → rsync to
  `/root/dd-was-geht-site` → commit + push. **Deploy key `~/.ssh/dd-was-geht-deploy`.** No force-push;
  commits only on change.
- **`/opt/dd-was-geht` is a plain copy, not a git repo**, and is now ~14 commits behind local HEAD.
- **P1 disproved "merging to one repo is a config change."** This is a rebuild. Do not re-litigate it.

## Build

1. **Rewrite `tools/publish_site.sh`** so the export target lives in the **single** repo instead of the
   separate Pages repo. Decide and document where the built site sits in that repo, and why.
2. **The export must emit the curated page** — **decision #27, David ruled it public.** Read-only
   output only: **the heart button must never appear in the export** (decision #8). **[V]** P5c's
   pattern is the one to reuse — template `mode` guard, `PUBLIC_ASSETS` allowlist, `CAN_HEART` client
   gate — and P5c deliberately named the read endpoint `/api/geherzt` so that **`"/api/herz"` is an
   unambiguous grep for the write route.** Keep that property.
3. **Do not revive any old frontend template.** Decision #7 retired them; P5b replaced them.

## Measure the export churn — it is an operational question, not a detail

**[V]** P5b warned that each venue page bakes its upcoming-events list into static HTML, so **most of
the ~746 venue files rewrite on most cron runs**. At **4 pushes/day**, that is a large recurring diff
in a git repo that grows forever. **Measure it:** build twice with a scrape in between, and report how
many files actually change, total bytes, and what a year of that looks like. **Then say whether it
needs fixing and what the fix would cost.** Do not fix it in this packet unless it is trivial.

## Verify locally, and say what you could not verify

- **Build the export from the real dev DB and diff the file list against the currently published
  site** (`/root/dd-was-geht-site` content is on CT103 — **do not fetch it from there**; use the
  public site or the last known export shape, and say which you used).
- **Grep every built file** for: any write route (`/api/herz`, `/api/feedback`), `192.168.178.91`,
  `:1111`, and any heart-button asset. **There must be none.** **[V]** P5c's export passed exactly
  this check — reproduce it, do not assume it still holds.
- **Confirm the curated page is present and read-only.**
- **State plainly which steps of the publish path you could NOT exercise locally.**

## Write the cutover runbook — this is a deliverable, not a footnote

A numbered, ordered runbook for P6b that David could follow himself, including:
- the **exact order**: new path green locally → deploy → verify published output → repoint Pages →
  **only then** retire the old repo;
- **how to preserve the deploy key** `~/.ssh/dd-was-geht-deploy`;
- **how to roll back at each step**, and the point of no return;
- what is **destructive and irreversible**, named explicitly.

## Out of scope

**P5d (visitor `localStorage` likes)** — separate small packet, may run before cutover. The venue-page
collapse (**#25 — David deferred it and did NOT confirm which surface he saw**). The 22 cross-source
dedup misses. The 3 split venue rows. `raw_venue`-vs-`venue_slug` run keys.

## Gates

- `../.venv/bin/python tests_smoke.py` green — **stands at 550 checks / 0 failures.** Name any
  assertion you change and why.
- `git status --short` clean, committed locally, **nothing pushed**. Commits end
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Repo code, comments and UI are **German**. Planning docs English.
- Mark every fact **[V]** (say how) or **[I]**. **Any rate needs its denominator**, and name which
  event count. **Seven figures in this project have failed to reproduce** — report any that does not.
- **Do not trust a tool's printed summary without re-deriving the predicate.**

## Report — head first

1. **result** — the new publish path, what you verified locally, and **what you could not**.
2. **the one finding that matters** — what P6b will be doing for the first time in production.
3. **follow-ups**, plus the cutover runbook.

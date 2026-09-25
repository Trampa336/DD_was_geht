# P6a2 — re-target the publish path after decision #29, and fix the runbook

**Model: Sonnet 5.** Mechanical and fully specified: undo one design choice, keep the rest, correct a document.

Tree `/home/admin/dd-was-geht/backend`. Python `../.venv/bin/python`.
**NEVER push. NEVER touch CT103. NEVER touch the live database. Do not change any GitHub setting.
Do not touch the `DD_was_geht` repo or `/root/dd-was-geht-site`.**
**Dev server is UP on :8090 and David uses it — if you restart it, put it back. Never port 1111.**

## Why this packet exists

P6a (commit `59b91cc`) built the publish path for a **consolidated** repo: site under `docs/`, because
GitHub Pages' branch-deploy only knows `/` and `/docs`. **David then chose a different shape entirely
(decision #29): GitHub keeps ONLY the public site — the existing `DD_was_geht` repo, unchanged URL,
Pages settings untouched — and the source moves to Forgejo.**

**So the `docs/` subdirectory targeting is now wrong.** The site repo stays a separate,
build-output-only repo serving from its root, exactly as today. **There is no consolidation.**

## What to change

**Re-target the publish path from `$SITE_REPO/docs/` back to the site repo's root**, i.e. the shape
that exists in production today. Keep everything else P6a built.

## What to KEEP — these are real improvements and must survive [V], all from P6a

- **The six failure guards** (bad `SITE_SUBDIR`, non-repo, wrong origin, missing `herzen.html`,
  missing `.nojekyll`, 0 day files) — each exits 1 with a message and leaves the clone untouched.
  Re-scope any that referenced `docs/`; **do not delete them.**
- **The `data/days` silent-failure fix.** `set -o pipefail` + `find` on a missing directory aborted the
  script with **no line in the cron log at all** — present in the pre-P6a script too, and it would
  fire on cutover day.
- **The byte-wise write comparison.** `_write` read back in text mode, so a title containing a literal
  CRLF made `orte/boulevardtheater.html` count as rewritten on **every** export. Keep the fix and its
  regression test.
- **`EXPORT_MODE=lokal` and `DRY_RUN=1`**, so the path can be exercised off CT103 at all.
- **The curated page in the export** (`herzen.html`, decision #27) and every check that keeps the
  heart button out of it. **Do not loosen those.**
- **`fetch` + `reset --hard origin/main` before writing.** **[I]** its original justification (a second
  writer after consolidation) no longer applies — under #29 the cron is the only writer, as today.
  **Keep it anyway as cheap defence, and say in the header that the justification changed.** Do not
  silently keep a comment that is now false.

## One thing to reconsider, not assume

**[V]** P6a found `https://trampa336.github.io/DD_was_geht/README.md` returns **404** although
`README.md` is tracked at the old clone's HEAD — an earlier cron's `rsync --delete` into the repo root
ate it. **Under #29 the site repo is pure build output, so deleting non-export files at the root is
now correct, intended behaviour, not the accident P6a called it.** **Say whether David loses anything
he would miss** (e.g. a README on the public repo) and, if so, how the script could preserve a small
allow-list. **Report it; do not build it unless it is trivial.**

## Fix the runbook — it is now wrong in its most important places

`/home/admin/.claude/plans/P6b-cutover-runbook.md` was written for the consolidated shape. Rewrite it
for #29. Specifically:
- **STEP 0's blocker is GONE.** The private-repo/Pages problem does not exist under #29. Say so.
- **Repointing GitHub Pages is GONE.** Nothing about Pages changes.
- **Deleting `DD_was_geht` is GONE — it stays, untouched, serving the same URL.**
- **The public URL does NOT change**, so no redirect-stub question.
- **What remains** is: deploy the new code to CT103, verify the published output, and the separate
  Forgejo move (its own packet).
- **Deleting `github.com/Trampa336/dd-was-geht` is now the only irreversible action**, it happens
  **after** Forgejo has the source and a clone is verified, and it is **not part of the cutover.**
- Keep the format: numbered steps, rollback on each, the point of no return named, irreversible
  actions listed individually.

## Out of scope

The Forgejo move (own packet). P5d visitor likes. The venue-page collapse (#25 — David deferred it and
did **not** confirm which surface he saw). The cross-source dedup misses. The split venue rows.

## Gates

- `../.venv/bin/python tests_smoke.py` green — **stands at 568 checks / 0 failures.** Assertions that
  encode `docs/` **will** need changing — **name every one and why.** Count by grepping `[OK]`/`[FAIL]`,
  **not** the trailing banner (P6a found the banner unreliable).
- Re-run P6a's verification on the re-targeted path: **build the export and byte-read every file** for
  `/api/herz`, `/api/feedback`, `192.168.178.91`, `:1111`, `herz-entfernen`, `data-run-key`,
  `ddHerzButton =` — **there must be zero hits.** Confirm `static/` still equals `PUBLIC_ASSETS`, links
  still all relative, `herzen.html` present with **0 `<button>`**. **Reproduce, do not assume.**
- `git status --short` clean, committed locally, **nothing pushed**. Commits end
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Repo code, comments and UI are **German**. Planning docs English.
- Mark every fact **[V]** (say how) or **[I]**. **Eight figures in this project have failed to
  reproduce** — report any that does not. Note the published site is **43 files**, not P1's "69".

## Report — head first

1. **result** — the re-targeted path, what you re-verified, and what changed in the runbook.
2. **the one finding that matters.**
3. **follow-ups.**

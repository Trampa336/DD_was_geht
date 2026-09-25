# P6b — cutover runbook (rewritten by P6a2 under decision #29, 2026-09-15)

**This is a much smaller cutover than the previous version of this document described.** The previous
version was written for a *consolidated* repo (source + site together, site under `docs/`). David chose
a different shape (decision #29): **GitHub keeps only the public site** — the existing `DD_was_geht`
repo, same URL, Pages settings untouched, nothing about it deleted — and the source code moves to a
Forgejo server instead. There is no consolidation.

**What that removes from this runbook, concretely:**
- **The old STEP 0 blocker is gone.** It existed only because a consolidated repo holding both source
  and site would need to be public (or paid) for Pages to serve `/docs` from it. `DD_was_geht` already
  serves Pages today, unchanged, so there is nothing to decide here.
- **Repointing GitHub Pages is gone.** Pages keeps serving `DD_was_geht` from its root, exactly as now.
- **Deleting `DD_was_geht` is gone.** It stays, forever, serving the same URL.
- **The public URL does not change** (`https://trampa336.github.io/DD_was_geht/`), so there is no
  redirect-stub question either.

**What is left:** deploy the new code (venue pages, curated page, the hardened `publish_site.sh`) to
CT103, and verify the published output. The Forgejo move is a separate, later packet and is not in this
document.

**There is no point of no return in this runbook.** Every step below is reversible — restore the backed
up script (step 1) and either run it once or wait for the next cron tick. The **one** irreversible
action anywhere in this project is deleting `github.com/Trampa336/dd-was-geht` (the source repo that
briefly held the consolidated build during P6a) — and that happens **later**, as part of the Forgejo
packet, only **after** Forgejo has the source and a clone from it has been verified. It is explicitly
**not** part of this cutover; do not fold it into the steps below.

---

## STEP 1 — preserve the escape hatch (do this first, it is cheap)

On CT103, as root:

```bash
cp /opt/dd-was-geht/tools/publish_site.sh /root/publish_site.sh.vor-P6b
crontab -l > /root/crontab.vor-P6b
ls -l /root/.ssh/dd-was-geht-deploy /root/.ssh/dd-was-geht-deploy.pub
ls -d /root/dd-was-geht-site
```

**There is no new deploy key and no new clone this time.** Under decision #29 the new script targets
the *same* repo through the *same* clone (`/root/dd-was-geht-site`) with the *same* key
(`~/.ssh/dd-was-geht-deploy`) as today — that is the whole point of undoing the consolidation. Do not
create a second key or a second clone; there is nothing for them to separate any more.

*Rollback:* n/a — nothing has been touched yet.

---

## STEP 2 — pause the cron while you work

```bash
crontab -e
# comment out the publish_site.sh line
```

**Why this step exists, and did not exist in the same form before:** under the old (consolidated) plan,
a half-finished deploy would publish to a URL nobody was looking at yet (`dd-was-geht`, not
`DD_was_geht`) — harmless by construction. Under #29 there is only **one** repo and **one** URL, and it
is already live. The new `export_static.py` produces `herzen.html` and `orte/*.html`; the *currently
deployed* `publish_site.sh` on CT103 is the old, pre-P6a script, which already does a bare
`rsync -a --delete --exclude '.git'` into the repo root with no per-surface completeness guard. That
means **step 3 alone (deploying the new `export_static.py`, before you even touch `publish_site.sh`) is
enough to make the next cron tick publish venue pages and the curated page for real** — the old script
does not know to refuse an incomplete pairing, it will simply rsync whatever the new exporter wrote.
Pausing the cron here turns that from an unplanned surprise into something you trigger on purpose in
step 5.

*Rollback:* uncomment the line again; nothing else changed.

---

## STEP 3 — deploy the new code to CT103

`/opt/dd-was-geht` is a plain copy, not a git repo. **It is 8–14 commits behind local HEAD**, pinned
from the live site rather than assumed (P6a established this without reading CT103 — it comes from what
the *public* site does and does not have, all **[V]**):

- the published `index.html` loads flatpickr → deployed ≥ `c27a84a`;
- it has no `site-nav` / "Alle Orte", and `static/orte.js` is 404 → deployed < `2b37172` (P5b);
- its `static/` holds exactly the 7 files `PUBLIC_ASSETS` had before P5b.

So deployed ∈ `c27a84a … b68c680`, i.e. **14 commits behind at worst, 8 at best**. This packet did not
touch CT103 and cannot narrow that further; confirm on CT103 with
`diff -rq --exclude data --exclude .env /opt/dd-was-geht <checkout>` before you deploy.

```bash
# from the workstation
rsync -a --delete --exclude data --exclude .git --exclude .env \
      /home/admin/dd-was-geht/backend/ root@<ct103>:/opt/dd-was-geht/
# on CT103
cd /opt/dd-was-geht && docker compose up -d --build
docker exec dd-was-geht python3 -c "import tools.export_static as e; print('export_static neu:', 'herzen.html' in open(e.__file__).read())"
```

*Rollback:* restore the previous tree and `docker compose up -d --build` again. The cron is paused
(step 2), so nothing publishes on its own either way.

---

## STEP 4 — dry run against a throwaway clone of the SAME repo

Do **not** point this at `/root/dd-was-geht-site` yet — clone a second, disposable copy so a mistake
here costs nothing:

```bash
git clone git@github-dd:Trampa336/DD_was_geht.git /root/dd-was-geht-site-test
cd /opt/dd-was-geht
DRY_RUN=1 SITE_REPO=/root/dd-was-geht-site-test tools/publish_site.sh
```

**Expect `Export (container) ...`, then `DRY_RUN=1: kein Commit, kein Push. Anstehen wuerden N
Dateien`.**

**N as observed today (2026-09-14/15), against a byte-exact offline copy of the actual live repo
[V — re-derived this packet, not carried over from P6a]:** 791 files touched — **755 added** (752 venue
pages, `orte/index.html`, `static/orte.js`, `herzen.html`), **35 modified** (`index.html`,
`data/index.json`, `static/app.css`, `static/app.js`, and day files whose event lists changed), **1
deleted** (`data/days/2026-09-14.json` — that day aged out of the 45-day window; this happens every day
regardless of this cutover, it is not specific to #29). Resulting file count: 43 − 1 + 755 = **797**.

P6a's own dry run a day earlier measured **798** with **0 deletions** — the difference is exactly one
day-rollover between when each of us measured, not a discrepancy in the mechanism. **Expect your own
number on cutover day to differ from both of ours by roughly this much, for the same reason** — this is
one of the figures in this project that does not hold still, by design (new events are scraped
continuously), not because of a bug.

If it aborts, it says why — the completeness guard names the missing file. An abort here has changed
nothing (`/root/dd-was-geht-site` was never touched).

*Rollback:* `rm -rf /root/dd-was-geht-site-test`.

---

## STEP 5 — first real publish (manual, not via cron)

This is the step that actually changes the public site — do it deliberately, not by re-enabling the
cron and waiting.

```bash
cd /opt/dd-was-geht
SITE_REPO=/root/dd-was-geht-site tools/publish_site.sh
```

This commits and **pushes to `DD_was_geht`** — the live repo, the live URL, immediately. There is no
staging repo to hide behind this time (that was the point of steps 2 and 4).

Verify on GitHub straight after: `index.html`, `herzen.html`, `orte/index.html`, `.nojekyll` and ~750
files under `orte/` exist in the `main` branch.

*Rollback:* restore `/root/publish_site.sh.vor-P6b` and the old `export_static.py` to
`/opt/dd-was-geht`, then run once manually (or wait for the next cron tick). The old script's
`rsync --delete --exclude '.git'` at the repo root removes everything the old exporter would not have
written — `herzen.html`, `orte/`, `static/orte.js` — which restores the 43-file baseline. This is the
same mechanism that already deleted `README.md` from this repo once before (see "Where the facts come
from" below); it is not new here, only pointed at more files.

---

## STEP 6 — verify the live site

Check **`https://trampa336.github.io/DD_was_geht/`**:

- the list loads and shows events;
- "Alle Orte" opens `orte/index.html`, and a venue page opens from there;
- "Handverlesen" opens `herzen.html`;
- **no heart buttons anywhere** — on the list, on a venue page, on the curated page;
- the browser console shows no 404s (a single wrong relative path shows up here and nowhere else).

*Rollback:* same as step 5.

---

## STEP 7 — re-enable the cron

```bash
crontab -e
# uncomment the publish_site.sh line again
```

**No env var change is needed here** — unlike the consolidated plan, the new script's defaults
(`SITE_REPO=$HOME/dd-was-geht-site`, `SITE_SUBDIR` empty = repo root) already match what step 5 just
ran by hand. The cron line does not change at all from what it is today.

**Watch two full cron cycles** (≥12 h). Check `data/publish.log` for `Veroeffentlicht: <sha> (N Dateien)`
and no `FEHLER:`. **Expect N to drop to roughly 20–90 after the first run** — the 755 new files were a
one-time backfill; day-to-day, only day files with new/changed events, and the handful of venue pages
that changed, get rewritten. This range is **[I]**, carried over from P6a's own measured 70–150 for the
*old* (docs/) shape and not independently re-measured this packet across a real multi-run window — if it
turns out to be badly off, that would be a ninth figure in this project that failed to reproduce; note it
if so.

*Rollback:* `crontab -l` → restore `/root/crontab.vor-P6b`, and restore
`/root/publish_site.sh.vor-P6b` to `/opt/dd-was-geht/tools/publish_site.sh`.

---

## Not part of this cutover

**The Forgejo move** (its own packet): moving the source tree off GitHub onto David's own Forgejo
server. Nothing in this runbook depends on it, and this runbook does not touch `github.com/Trampa336/
dd-was-geht` at all.

**The one irreversible action in this project:** deleting `github.com/Trampa336/dd-was-geht`. It
destroys the source repo's history — the same repo P6a briefly pointed at for the consolidated plan,
now just a plain GitHub mirror of the source tree with no special role. Do this only after Forgejo holds
the source and a clone made *from Forgejo* has been verified against it. It is independent of
`DD_was_geht` (the *site* repo), which this runbook never proposes deleting.

---

## Where the facts come from

- **[V], re-verified this packet (2026-09-14/15), read-only** — `DD_was_geht` currently publishes
  **43 files**: confirmed both by cloning `https://github.com/Trampa336/DD_was_geht.git` directly and by
  GitHub's tree API (`git/trees/main?recursive=1`), independently of P6a's earlier count. This matches
  P6a's "43", **not** the "69" an early packet (P1) claimed.
- **[V], re-verified this packet** — `/README.md` on the live site is still **404** (checked via HTTP,
  and confirmed the file is genuinely absent from the current clone, not merely un-rendered). `.nojekyll`
  is present, so Jekyll is not the explanation. Same finding as P6a; it has not been fixed and this
  runbook does not fix it either (see the judgement call below).
- **[V], re-verified this packet** — `herzen.html`, `orte/index.html`, `static/orte.js` are all still
  404 on the live site; `index.html` and `data/index.json` are 200. The live site is still pre-P5b/P5c
  in shape, exactly as P6a found.
- **[V], re-verified this packet** — live site is current and healthy: `data/index.json`
  `generated_at` `2026-09-14T21:15:02` (Berlin), matching the latest commit `3f7026b` at
  `2026-09-14T19:15:02Z` (UTC) exactly — the cron is running on schedule, roughly 3 hours before this
  check, well inside its normal ≤6-hour cadence. No stall.
- **[V], re-derived this packet against a byte-exact offline mirror of the current live repo, not
  assumed from P6a's numbers** — the first real publish under the new (root-target) shape touches 791
  files: 755 added, 35 modified, 1 deleted. See step 4 for the breakdown and the caveat that this number
  moves day to day by design.
- **[I], carried over from P6a, not independently re-measured this packet** — the cron's four times
  (`1,7,13,19`) are UTC on the host, matching the observed Berlin `generated_at` values via
  `TZ=Europe/Berlin` inside the container. Worth reconfirming during step 7; does not change anything in
  this runbook.
- **[V], from P6a, unchanged and not re-checked this packet (would require touching CT103)** —
  `/opt/dd-was-geht` is a plain copy, not a git repo; deploy key at `~/.ssh/dd-was-geht-deploy`; cron
  `15 1,7,13,19` → `/opt/dd-was-geht/tools/publish_site.sh` — all from P1, and still the basis for
  step 3's commit-window estimate.

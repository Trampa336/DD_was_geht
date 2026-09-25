# P7 — move the source to Forgejo, keep GitHub for the public site

**Model: Sonnet 5.** Mechanical and fully specified, but it **pushes**, which every other packet in this project was forbidden from doing. Read the boundaries twice.

Tree `/home/admin/dd-was-geht/backend`. Python `../.venv/bin/python`.
**Dev server may be UP on :8090 and David uses it — if you restart it, put it back. Never port 1111.**

## What you may and may not push

- **You MAY push to Forgejo** — `ssh://git@192.168.178.98:2222/erwin/dd-was-geht.git`. That is the point of this packet.
- **You MUST NOT push to GitHub.** Not to `dd-was-geht`, not to `DD_was_geht`. **[V]** `DD_was_geht` **is the live public website.**
- **You MUST NOT delete any repository anywhere.** Deleting the GitHub source repo is David's call, separately, after he has seen your verification.
- **NEVER touch CT103, the live database, the root cron, or any GitHub setting.**

## Established [V] — verified by the supervisor 2026-09-15, re-verify rather than trust

- SSH auth works: `ssh -T -p 2222 git@192.168.178.98` → *"Hi there, erwin!"* with key `claude-migration@leo` (`/home/admin/.ssh/id_ed25519`).
- **The push is a clean fast-forward.** Forgejo `erwin/dd-was-geht` main = `a3eefcf`, 23 commits, **an ancestor of local HEAD**; local is 24 ahead. **`git merge-base --is-ancestor a3eefcf HEAD` returns true.** **Re-run that check yourself before pushing. If it is false, STOP and report — do not force.**
- **`erwin/dd-was-geht` also carries an open PR #1** on branch `claude/event-calendar-ui-research-rnnkxv`, one commit `34d2802` touching only `app/static/app.css`. **[V]** it is in neither local main nor GitHub `origin/main`. **Do not merge it, do not cherry-pick it, do not delete the branch** — decision #31 gives it its own packet.
- Local `origin` currently points at `git@github.com:Trampa336/dd-was-geht.git`.

## Do, in this order

1. **Re-verify the ancestry.** If not a fast-forward, stop.
2. **Add Forgejo as a remote.** Decide and state whether Forgejo becomes `origin` and GitHub is renamed/dropped, or Forgejo gets its own name. **Say what you chose and why** — David will be typing `git push` here for years.
3. **Push `main` to Forgejo.** Report what moved.
4. **VERIFY BY CLONING BACK.** Clone fresh from Forgejo into the scratchpad — **not** by re-reading the repo you just pushed from. Confirm HEAD matches, commit count matches, and **spot-check that real file content survived** (not just that refs match). **A push reporting success is not evidence the data is there** — this project has been bitten three times by trusting a tool's own report.
5. **Grep the whole tree for hard-coded references to the GitHub source repo** (`Trampa336/dd-was-geht`, `github.com/Trampa336`) — README, scripts, docs, CI, `publish_site.sh`. **That repo is going to be deleted.** Report every hit and fix the ones that are genuinely wrong. **Be careful to distinguish the SOURCE repo from `DD_was_geht`, the public site repo, which STAYS** — a reference to the public site is correct and must not be "fixed".
6. **Close open registration** on Forgejo — `DISABLE_REGISTRATION` is unset, so anyone on the LAN can create an account. Set it, restart the service, confirm the setting took **and that the web UI still answers 200**.

## Do NOT do

Delete anything. Touch the `DD_was_geht` repo. Merge or cherry-pick PR #1. Deploy to CT103. Change Pages settings. Build visitor likes. Touch the venue-page collapse (**#25 — David deferred it and did NOT confirm which surface he saw**).

## Gates

- `../.venv/bin/python tests_smoke.py` green. **Baseline moved — P6a2 landed just before you; establish the current count yourself and report it.** Count by grepping `[OK]`/`[FAIL]`, **not** the trailing banner, which P6a found unreliable.
- `git status --short` clean at report time. Any code change committed locally. Commits end
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Repo code, comments and UI are **German**. Planning docs English.
- Mark every fact **[V]** (say how) or **[I]**. **Eight figures in this project have failed to reproduce** — report any that does not.

## Report — head first

1. **result** — is the source on Forgejo and independently verified, and what is the remote layout now.
2. **the one finding that matters** — specifically: **is it safe to delete the GitHub source repo, and what would break if it were deleted today?**
3. **follow-ups.**

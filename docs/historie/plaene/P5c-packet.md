# P5c — editorial hearts, retire `reactions`, re-feed `score`

**Model: Opus 5.** Re-routed up from the original Sonnet call. P5a confirmed route separation holds,
which was the original condition — **but the packet has since grown three subtle cross-file
requirements** (run-keyed hearts, the `duplicate_of` tracking trap, and a `score` re-feed with three
live consumers) **plus the retirement of a working production mechanism.** That is Opus work.

Tree `/home/admin/dd-was-geht/backend`. Python `../.venv/bin/python`. **Commit locally. NEVER push.
NEVER touch CT103 or the live database.** Work against `backend/data/dd-was-geht-v2.db`.
**A dev server is UP on port 8090 and David uses it — if you restart it, put it back. Never port 1111.**

**This is the packet the whole rework exists for.** Decision #3: *curation = hearts*, a one-way
positive signal; hearted events are the curated page.

## The assumption to test

> **"Hearts can reuse the existing three-mechanism live/static gating unchanged, and retiring
> `reactions` leaves no gap in `scoring.py`."**

**[V]** the gating pattern exists and is production-proven (P5a): template `{% if mode != 'static' %}`,
the `web.PUBLIC_ASSETS` allowlist excluding `rating.js` (and the exporter deleting stale copies), and
`app.js`'s `CAN_RATE = MODE === 'api'`. **[I]** that hearts drop into it unchanged. **[V]** `reactions`
is **live and load-bearing** — `tests_smoke.py`, `scoring.apply_reaction` and `/api/feedback` all
depend on it today, and P3 refused to delete it for exactly that reason. **If the second half is
false, say so before you rip anything out.**

## Three requirements that are already known [V] — do not rediscover them the hard way

### 1. Hearts must track the WINNER predicate, not row existence
`hearts.link_status = 'ok'` means *"uid points at a living event row"*. **That is NOT what the list
shows.** The list requires `duplicate_of IS NULL`. `dedup.link_duplicates` runs after **every** scrape
over today…+31d and moves rows between winner and duplicate — **P5w produced exactly that transition
in-packet**: `15a4e9d368071799` is a perfectly live row that is now invisible in every view. **A heart
on it would report `'ok'` and silently vanish from the curated page.**

**`event_duplicates` already maps `duplicate_uid → canonical_uid`, so relinking is free.** Use it.

**This is the project's recurring failure mode, now seen three times: a status field being *set* is
not the same fact as the thing being *true*.** P5v fixed it in `meta_status`; P5w found it waiting
here. **Check every status field against the predicate its consumer actually needs.**

### 2. A heart lands on a RUN, not a showing — decision #26
**[V]** `hearts.event_uid` is a PRIMARY KEY on a single showing; `identity_key` only re-links the
*same* showing across scraper churn. **Nothing relates the 5–8 sibling uids of one run.**
David ruled: **hearting a folded row hearts the whole run.** Key hearts by the run group key; render
the row hearted if any member is hearted. **Reuse P5x's grouping key** (`runKey`/`runSlug` in
`app/static/app.js`, `RUN_MIN_SIZE = 3`) — **do not invent a second, divergent notion of a run.**

**THE SUB-DECISION DAVID HAS NOT MADE — state which you chose and why, do not bury it:**
does the run key include the **date**? P5x's wording (venue_slug + normalised title) **omits** it,
which hearts the tour across *all* days. Plausible for "I like this tour" — but **the curated page is
date-bearing**, and a dateless key would put every future Domführung on it forever. **Pick one,
implement it, and put the trade-off in your report in one short paragraph so David can overrule.**

### 3. `score` must be RE-FED, not merely unexported
**[V]** three live consumers: the top-pick badge, the "wenig relevant" filter, and `/api/fuer-dich`
sorting. **[V]** `reactions` and `weights` have **0 rows**, so every event exports the constant
`score: 50.0` and all three consumers are no-ops today. **Deleting `reactions` without re-feeding
`score` turns three working features into broken ones.** Feed scoring from hearts, or remove the
consumers cleanly — **not half of each.** Say which you did.

## Build

1. **Editorial heart, LAN-only, DB-backed.** A one-way positive signal — **not** approve/reject
   (decision #3). Write routes exist only on `:1111` and **must never appear in the static export**
   (decision #8). No login, no auth code — route separation plus the existing gating.
2. **Retire `reactions` / `apply_reaction` / `/api/feedback` IN THIS PACKET.** **[V]** David's own
   words were *"a heart or like system **instead of** a dislike and like"*. P3 established hearts are
   the **predecessor's replacement**, not a parallel system, and that this pairing **must not be
   split.** Remove `rating.js` and its asset entry too.
3. **The curated page ships EMPTY** (decision #19). No shortlist, no proposer, no seeding. David fills
   it. Nothing publishes publicly until he has seen it locally.

## Out of scope — deliberately split off

**Visitor `localStorage` likes are NOT in this packet.** They only affect the public export, which
does not go live until P6, and keeping them out shrinks the riskiest packet in the rework. They are
**P5d** — small, non-blocking, may ride with P6. Do not build them here.

Also out: the venue-page collapse (**decision #25 — David deferred it and did NOT confirm which
surface he saw; do not assume**), the 22 cross-source dedup misses, the 3 split venue rows.

## Acceptance test — this is the test for the whole rework

**Heart an event → re-run a scrape → confirm the heart survives.** Run it and report the result.
Then **grep the built static export for any write route and for `192.168.178.91` — there must be
none.** Verify in **both** render modes; **[V]** they share templates in-process
(`tools/export_static.py:160-172`).

## Gates

- `../.venv/bin/python tests_smoke.py` green — **stands at 505 checks / 0 failures.** Retiring
  `reactions` **will** require changing assertions that cover it — **name every one and why.**
- `git status --short` clean, committed locally. Commits end
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Repo code, comments and UI are **German**. Planning docs English.
- Mark every fact **[V]** (say how) or **[I]**. **Any rate needs its denominator**, and **name which
  event count** — run-seen (5948), reach (5880), winner (5026, `duplicate_of IS NULL`, +45d).
- **Seven figures in this project have failed to reproduce**, the most recent because a grouping key
  omitted venue. Report any that does not reproduce.
- **Do not trust a tool's printed summary without re-deriving the predicate.**

## Report — head first

1. **result** — hearts working, `reactions` gone, `score` re-fed, and the acceptance-test outcome.
2. **the one finding that matters** — including the date-in-run-key trade-off for David.
3. **follow-ups.**

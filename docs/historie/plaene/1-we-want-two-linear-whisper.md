# dd-was-geht — structural rework (supervisor state file)

---

## HANDOFF — read this first if you are a fresh supervisor session

**Written 2026-09-15 at David's request. This file is your entire state. Do not read the codebase — if you need a fact, that is a packet for a worker, not work for you.**

### Your role
You orchestrate workers, you ask David questions, you maintain this file. **One packet at a time, one worker at a time** — they share a working tree and will interleave commits otherwise. **Brief every packet by naming the assumption to test**, not just the change; nearly every packet briefed that way here has disproved something, including four of the supervisor's own claims.

### Non-negotiables
- **Mark every fact [V] verified by a worker or [I] inferred.** Inferred facts have a bad record here.
- **Any rate needs its denominator**, and its depth if it came from a ranked sweep. **Carrying a [V] rate to a narrower population makes it [I] until re-derived** — the supervisor broke this rule itself.
- **Never state that something does or does not exist in the code unless a worker verified it.**
- **Model routing, named in every handout:** mechanical + fully specified → Sonnet 5; open-ended diagnosis or subtle cross-file correctness → Opus 5; lookups and status chores → Haiku 4.5.
- **Workers commit locally and NEVER push.** Never touch CT103 or the live database. A root cron publishes publicly at `15 1,7,13,19`.
- **Reports head-first:** `result` → `the one finding that matters` → `follow-ups`.
- **Repo code, comments and UI are German.** Planning docs English.

### STATE AT THE PAUSE

**Local HEAD `59b91cc`, tree clean, 16 commits ahead of `origin/main`, NOTHING pushed. Smoke 568 checks / 0 failures. CT103, the live DB and the public site are all untouched by this entire rework.**

**ONE PACKET IS IN FLIGHT AND MAY HAVE LANDED UNATTENDED: P6a2** (Sonnet 5, packet at `P6a2-packet.md`). **On resume, first:**
1. `cd /home/admin/dd-was-geht/backend && git log --oneline -3`. **A commit after `59b91cc` means P6a2 landed and its results are NOT recorded below — recover them from the commit and fold them in.**
2. `../.venv/bin/python tests_smoke.py` — was 568/0. A different count means P6a2 changed assertions; it was told to name every one.
3. Check `P6b-cutover-runbook.md` — **P6a2's main job was rewriting it. Until that is confirmed done, the runbook on disk is WRONG and dangerous: it still says to repoint GitHub Pages and delete `DD_was_geht`, which is the live public site. Decision #29 killed both of those steps.**

**Dev server:** `http://192.168.178.88:8090/` — David uses it. Not a service. Restart from `backend/`:
```
DB_PATH=./data/dd-was-geht-v2.db WEB_PORT=8090 ../.venv/bin/python -c "from app.web import run_web; run_web()"
```
**Never port 1111.**

### WHAT IS DONE
P1–P5a, P5b, P5t, P5u, P5v, P5w, P5x, P5c, P6a — all complete and folded in below. **The rework's acceptance test PASSED (P5c):** heart an event → real scrape against all 10 live sources → heart survives, re-derived rather than trusted. Hearts ship, `reactions`/`apply_reaction`//api/feedback are retired, `score` is re-fed from hearts. Venue pages exist for ~726 venues. Categorisation is closed at 32.7% `sonstiges`.

### WHAT IS LEFT, IN ORDER
1. **P6a2** — in flight. Re-target the publish path to the separate site repo's root (decision #29 killed the `docs/` consolidation shape) and **rewrite the runbook.**
2. **P5d** — visitor `localStorage` likes on the public site. Small, local, never sent to the server (decision #3b). Split out of P5c deliberately to shrink the riskiest packet.
3. **P6b — the cutover.** Now much smaller: deploy the new code to CT103 and verify the published output. **Pages settings never change. The public URL never changes. `DD_was_geht` is never deleted.** Runs only on David's explicit go, and it is the first time this rework touches CT103.
4. **P7 — move the source to Forgejo (CT108).** **BLOCKED-ish: the supervisor's notes say Forgejo has no admin user yet — David was asked to check and has not answered.** Verify before building on it.
5. **Delete `github.com/Trampa336/dd-was-geht`** — the only irreversible action left, and **not part of the cutover.** Happens only after Forgejo has the source and a clone has been verified.

### OPEN WITH DAVID
- **Forgejo admin user** — asked 2026-09-15, unanswered. Gates P7.
- **#25: the "doubled entries"** — he said *"We will Note for later to Check for duplicates"* and **did NOT confirm which surface he saw them on.** Do not assume it was the venue pages. A future packet reproduces first, fixes second.
- Nothing else is blocking.

### THE THREE THINGS THIS PROJECT KEEPS TEACHING
1. **A status field being *set* is not the same fact as the thing being *true*.** Caught three times: `meta_status` non-NULL ≠ success (false on 43 of 74 pages); `hearts.link_status='ok'` means "row exists", not "row is a winner"; and hearts now track `duplicate_of IS NULL` because of it.
2. **Do not trust a tool's printed summary — re-derive the predicate.** `venue_readiness_report.py` printed a false "0/726 truly bare"; the exporter's `venues_written` was wrong by exactly 1 on every run for years; the smoke suite's trailing banner is unreliable. Each was caught by recomputation, never by reading the output.
3. **Fabrication risk outranks correctness risk in any curation packet.** This publishes to a public site about real Dresden businesses. Descriptions come only from scraped text; an unconfident `kind` stays `sonstiges`. Four workers have held that line — one refused to use its own knowledge of a venue it recognised, and another rejected a church description whose opening paragraph would have told readers the church is still a ruin.

### THE SUPERVISOR'S OWN RECORD — four false premises, all caught by workers
A "42-venue-scraper dead code" that never existed; decision #14's claim that title-keyword rules needed building when they had been live since `54d52ff`; "38% of the 569 venues have one event" (38% is over all 726; over the 569 it is 48.7%); and P5w's fan-out hypothesis (tags are not joined into the list at all — the filter is client-side). **Naming a hypothesis as the assumption to test is correct. Stating it as fact is not.**

### EIGHT FIGURES THAT FAILED TO REPRODUCE — none may be cited as load-bearing
P4c's "45 of 123 homepages are deep links" (49 broad / 21 literal) · P4e's baseline 1834 (recomputes 1843) · the supervisor's "38% of the 569" (48.7%) · "70 venues / 706 events" (84/1368 or 61/1044) · `feed.venue_cover`'s "569 / 67.7%" (385/495 = 77.8%) · P5w's "437 rows / 8.7%" (400 / 8.0% under the correct venue-bearing key) · P1's "69 files" (the published site is **43**) · P5x's "78 runs over 5026" vs P5c's "78 over 5092" (same count, different denominator — a coincidence, flagged as such).
**The one figure deliberately verified twice by two independent code paths:** the date-in-run-key measurement — 3057 of 5092 winner rows (60.0%) sit under a dateless key spanning more than one day.

---

Owner: supervisor session. Workers do not edit this file; they report, I fold.
Status legend: **[V]** verified by a worker against the live system · **[I]** inferred — poor record in this project, treat as suspect.

## Context

`dd-was-geht` scrapes 10 Dresden event sources every 6h into SQLite and serves a Flask app on CT103 (`192.168.178.91:1111`), with a root cron publishing a static export to a public GitHub Pages site. It works, but it grew around a strategy that its own measurements killed: 42 bespoke venue scrapers meant to outrank the aggregators, when 98.7% of future events are aggregator-only. What is left is an app with 5234 events, 744 unnormalised venue strings, 35% of events in category `sonstiges`, no venue identity, and a UI that hands the user off to Kulturkalender — the ugly page David is trying to get away from.

This rework replaces the data model and the frontend, keeps the one part that demonstrably works (the 10 scrapers), and deletes the abandoned venue-scraper apparatus outright. The intended outcome is two surfaces over one database: a searchable categorised index, and a curated page of events David has hearted — plus venue pages inside the app, so an event leads to the venue, not to an aggregator.

## Decisions (David, 2026-09-11) — all **[V]** as statements of intent

1. **Purpose.** Two surfaces, one DB: (a) searchable categorised list, as today; (b) a curated page in the spirit of Resident Advisor — big/nice events only.
2. **Audience.** Local-first on `:1111`, shared publicly via the Pages site. Both matter.
3. **Curation = hearts.** Not approve/reject. A one-way positive signal: David hearts an event, hearted events are the curated page. Rules may *propose* candidates (shortlist/scoring); the heart is the only thing that publishes.
3b. **Two distinct likes, do not conflate them.** *Editorial hearts* live in the DB, are written LAN-only by David, and build the curated page. *Visitor likes* on the public site are per-browser (`localStorage`) only — everyone can like, their likes persist for them, nothing is aggregated, nothing is sent to the server, and they never influence what is featured. This is what keeps the Pages site fully static and the homelab free of any internet-facing write endpoint.
4. **The core feature.** An event leads to a **venue page inside the app** — cover, info, that venue's upcoming events — instead of redirecting to Kulturkalender.
5. **Venue content.** Hot-link + light one-off scrape of the venue's official homepage (title, meta description). Nothing copied into the DB beyond a cached summary. Covers stay hot-linked. **AMENDED by P4c (2026-09-11): the cover source is `kk_cover_url` — the Kulturkalender venue page's media slider — NOT the homepage `og:image`.** Homepage og:image yielded only 13 usable covers out of 34 hits and **zero in the top 14 venues**; the rest were logos, dead links, mutating city-portal images and CMS defaults. KK covers exist for 142/142 venues with a KK page, all distinct. Homepage og:image is kept only as a second-position fallback that in practice never fires.
6. **Schema.** Fresh schema. Old DB ripped out, frozen on disk as a dead rollback copy. No migration.
7. **Retirement.** Delete the old frontend and everything left of the 42-venue-scraper plan. Keep and adapt the 10 working scrapers.
8. **Admin.** LAN-only, no login. Heart/write routes exist only on `:1111` and must never appear in the static export.
9. **Repos.** ~~Merge to one repo; delete the separate Pages repo.~~ **SUPERSEDED by #29 (2026-09-15)** — GitHub keeps only the public site (`DD_was_geht`, unchanged URL); the source goes to Forgejo; the private GitHub source repo is deleted. Public site survives, and now survives *untouched*.
10. **Forgejo (CT108).** Git remote only. Deploy stays copy-to-CT103.
11. Carried over: keep everything in the DB, but Kultur/Musik/Nightlife surface and the tourism tail is one toggle away. Build both the venue-homepage link and the per-event official link.
12. **Region toggle, default Dresden-only** (2026-09-11, decided on P2 evidence). Everything stays in the DB and nothing is dropped at scrape time. The default view is Dresden; Meissen/Umland is one switch. Region lives on the **venue** row, computed once via `geo.py`, not per event. The app is `dd-was-geht` — defaulting to Dresden is honest.
13. **Venue pages: top venues by event count get a scraped page** (2026-09-11). **DONE — 160 venues enriched** (the walk ran past the original ~120 because the bare-domain link rule *improved* with depth). The remaining **569** long-tail venues still get a venue page, built only from data already held (name, kind, region, event list) — no cover, no fetch. They need nothing before P5.

14. **Categorisation: title-rule layer above venue kind; `sonstiges` stays a real answer** (2026-09-11, David ruled on the supervisor's reframe). The 73.8% ceiling and the 35% `sonstiges` baseline measure different things — **accuracy** vs **coverage**. Venue kind alone does not lift coverage to 73.8%; it converts honest unknowns into confident guesses, ~26% of them wrong, concentrated on the highest-volume venues (the 67 spanning 3+ categories). For a filter UI a wrong category is worse than an absent one: `sonstiges` is unhelpful, but a techno night filed under Theater makes the filter lie and the user cannot tell which rows to distrust. Ruling: **a second layer is warranted, and it is German title keyword rules — not a classifier.** Precedence: (1) source `raw_category` where present, (2) per-event title rule, (3) venue `kind` only where the venue is single-category or the title rule is silent and a prior is explicitly accepted, (4) `sonstiges`. **Do not force every event into a bucket.** Supporting evidence already in hand: ~1179 of ~5239 winner events are guided tours and "Führung" in the title is a one-line rule that no venue kind can express — Frauenkirche runs tours *and* concerts.

15. **Decision #14 CORRECTED (2026-09-11), after P4d proved its premise false.** #14 ruled to "add" a German title-keyword layer. **That layer already existed** — `app/normalize.py::classify_category`, live since commit `54d52ff`, called by all 10 scrapers. The 35% `sonstiges` figure is its *output*. #14's stages 1+2 are therefore already built; only **stage 3 (`venues.kind`) was ever missing**. The reasoning in #14 stands — accuracy over coverage, `sonstiges` remains a real answer, no classifier — only its premise about what existed was wrong. **The supervisor authored that false premise.**

16. **Venue-kind fallback: YES, but only for single-category venues** (2026-09-11, David, in plain terms: *"guess from the venue only where the venue does one thing"*). Wire `venues.kind` into `classify_category` as stage 3, below the title rules, above `sonstiges`. **Venues spanning multiple categories are skipped and keep `sonstiges`** — a wrong label is worse than an honest unknown, because with `sonstiges` the user knows to look. Expected gain: most of the measured 13.0 pp (35.0% → 22.0%), without mislabelling the ~2199 events at mixed venues.

17. **Tags alongside categories — not more categories** (2026-09-11, David's idea, reframed and accepted). **Category = what an event IS** (Musik, Theater, Führung). **Tag = context** (Kirche, Museum, Open Air, Klassik, Techno). An organ concert in a church is category `Musik` + tags `Kirche`, `Klassik` — found by either filter, with nothing competing for a single slot. A flat category list would force it to pick one and drop it from the other filter. **The `tags` table already exists in schema v2, so this needs no schema work.** David's trigger example: *"kirche rather than orgelkonzert missmatching the music category"*.

18. **Category work is CLOSED at 32.7% `sonstiges`** (2026-09-11, David, after being told the supervisor's #16 estimate was wrong by ~28×). He was offered four routes on measured numbers — accept 0.46 pp; curate `kind` on 70 more venues (ceiling 13.5 pp **[V]**, realistic ~3 pp **[I]**); guess at mixed venues after all (~26% wrong at the highest-volume venues **[V]**); or keep mining keywords (unmeasured residue **[I]**). **He chose accept and move to P5.** His #16 reasoning — accuracy over coverage, `sonstiges` stays a real answer — is reaffirmed, not overturned. The 70-venue curation and further keyword mining are **deferred, not cancelled**; they are standalone packets available any time and gate nothing.

19. **The curated page ships EMPTY** (2026-09-12). David expressed no preference; the supervisor decided and told him. It matches decision #3 exactly — the heart is the only thing that publishes. No shortlist, no proposer, no seeding in the first frontend packets. Nothing publishes publicly until he has seen it locally, so the empty state is never public. Reversible later; the rule-based proposer decision #3 permits remains available and gates nothing.
20. **The frontend ships in TWO stages** (2026-09-12, David, asked in plain terms which he preferred). **P5b = read surfaces** (searchable list, venue pages, region toggle, category + tag filters) — read-only, nothing retired, so he sees something real sooner and can say it looks wrong before more is built on it. **P5c = hearts + visitor likes + retiring `reactions`/`apply_reaction`//api/feedback**, which stay together in one packet as P3 required. The split is between read and write, not through the hearts↔reactions pairing.

21. **Fill in the 74 bare venue pages BEFORE hearts** (2026-09-12, David, offered four options after P5b measured them). He rejected accepting 10% dead-end pages, rejected linking back out to the source for them, and rejected looking before deciding. **Hearts wait.** Rationale is decision #4's: a hearted event leading to a name-and-one-event page is exactly the hand-off this project exists to kill, and the 74 are all uncurated `sonstiges`, so curating them is a small categorisation win too. Sequenced as **P5t**, between P5b and hearts.

22. **Try the cybersax address-page route before hearts** (2026-09-12, David, re-decided after P5t disproved the cheap route). Offered "accept them", "try cybersax first", "close it out permanently" — he chose **try first**. Consistent with #21: he has now twice ranked filling the pages in above accepting them. **Hearts waits a second time.** The lever is cybersax's own `/terminal/adressen/address/<ort>/` pages, **[I]** untested, evidenced only by a docstring. Sequenced as **P5u**, Opus 5. If it also fails, the honest terminal state is (a) accept — and that should then be put to him as a closing decision, not assumed.

23. **Store the cybersax contact-card data before hearts** (2026-09-12, David, third time he has ranked filling the venue pages in above moving on — see #21, #22). P5u settled that the 62 remaining bare pages **can never get a photo**; David chose to give them *information* instead: postal address, phone, opening hours, already fetched. **No new photo work will be proposed for these venues again — that question is closed [V].** Sequenced as **P5v**, Sonnet 5. **Supervisor note: the photo thread is closed, the contact thread is closed after this. If a fourth venue-quality idea appears, it needs a positive reason to come before hearts, not just availability.**

24. **Collapse only LONG same-day runs in the list** (2026-09-12, David, after P5w proved the "doubled entries" were overwhelmingly correct data). A double-bill stays two rows; an hourly tour run folds into one row listing its times. **Display layer only — never in the query, never `DISTINCT`:** P5w verified **[V]** there are zero duplicate uids, so a query-level collapse would delete four of the five real Domführungen from the page. **The threshold is to be measured from the group-size distribution, not guessed** — supervisor's starting guess is 3+, David's words were "more than two or three times". Sequenced as **P5x**, Sonnet 5. **Consequence he has not yet ruled on: what hearting a collapsed run means. P5x reports a recommendation; it does not build it.**

25. **The "doubled entries" question is DEFERRED, not answered** (2026-09-13). Asked where he saw them — main list or venue page — David answered: *"We will Note for later to Check for duplicates."* **He did not confirm either surface.** So: **do not build the venue-page collapse on the assumption that was it.** What is known **[V]**: the main list is folded and measurably clean at his default filters; `/orte/<slug>` has **no** category/region/Dauerangebote/date filtering and shows Dom zu Meißen 307 rows, 273 of them two tour names repeated. **A future duplicate-check packet should reproduce what he saw before fixing anything.** Nothing blocks on this.
26. **Hearting a folded run hearts the WHOLE RUN** (2026-09-13, David, on P5x's recommendation). Seeing "Domführung, 5 Termine" the mental model is *"I like this tour"*, not *"I like the 12:30 slot"*; hearting one sibling and leaving four unhearted would read as a bug. Requires a schema/lookup change — hearts keyed by the run group key rather than a single `event_uid`. **Sub-question David has NOT ruled on and the supervisor must not silently decide: whether the run key includes the DATE.** P5x's wording (venue_slug + normalised title) **omits it**, which would heart the tour across all days — plausible for "I like this tour", but the curated page is date-bearing and would then carry every future Domführung. **P5c must state which it implemented and why, so David can overrule.**

27. **The curated page GOES PUBLIC** (2026-09-14). P5c built `/herzen` as Flask-only and correctly deferred the question. David ruled it public — it is the Resident-Advisor half of decision #1, and #2 already said both surfaces are shared publicly. **Only the read-only result publishes; the heart button itself never appears in the export** (decision #8 unchanged). He hearts things before the first publish so it does not go up empty (#19 unchanged — it ships empty, he fills it, and nothing publishes until he has seen it locally).
28. **P6 is SPLIT: build-and-verify (P6a) then cutover (P6b)** (2026-09-14, supervisor, on the project's own verification rule — *"new publish path green locally first, cutover second, delete third"*). **P6a touches nothing outside the local tree.** **P6b is the first time this rework touches CT103 or anything public, and it runs only on David's explicit go.** Rationale: **[V]** P1 found the `DD_was_geht` repo **is the live Pages site** (build output, not source), so retiring it deletes the public site until the new path works; **[V]** the deploy key `~/.ssh/dd-was-geht-deploy` on CT103 root must survive or the first push fails silently; and **[V]** `/opt/dd-was-geht` is a plain copy, now ~14 commits behind local HEAD.

29. **DECISION #9 IS SUPERSEDED. GitHub keeps only the public site; the source moves to Forgejo** (2026-09-15, David — his own fourth option, not one of the three offered). **`DD_was_geht` stays exactly as it is**: public, Pages-serving, **same URL, no Pages setting changed, no link broken.** The source repo moves to **Forgejo on CT108**, and **`github.com/Trampa336/dd-was-geht` is DELETED once Forgejo has it and the clone is verified.** This **dissolves the private-repo blocker entirely** — the source never needs to be public because it is not on GitHub at all — and it **removes the two most dangerous steps from the cutover** (repointing Pages, deleting the live site's repo). #9's spirit survives: one source repo, one published-artefact repo, on different hosts with different jobs.
30. **Source living only on the homelab is accepted** (2026-09-15, David, asked directly). GitHub is currently an off-site copy of the code; after #29 the only copies are on `leo`. The Proxmox backup job covers CT108 — **the same protection Nextcloud, Immich and Paperless already run on**, which he has judged sufficient there. **Decided on purpose, not discovered later.** Revisit only if he asks.

31. **The orphaned Forgejo PR gets its IDEA evaluated, not its diff applied** (2026-09-15). `erwin/dd-was-geht` carries an open **PR #1** from branch `claude/event-calendar-ui-research-rnnkxv` — one commit `34d2802`, *"Kompakteres Mobile-Layout: kleines Thumbnail statt ausgeblendetem Cover"*, **+9/−4, `app/static/app.css` only**. **[V]** it is in **neither** local main **nor** GitHub `origin/main` — never merged anywhere. It predates the rework and targets CSS that P5b replaced wholesale. David ruled: **read what it did, check whether the rebuilt mobile layout already handles it; close the PR if so, re-implement the idea properly against the new CSS if not.** Own packet, after the repo move. **Do not cherry-pick the commit.**

32. **Restore a README on the public site repo** (2026-09-15, David: *"its trivial"*). **[V]** `DD_was_geht`'s `README.md` is genuinely gone (404, absent from the tree, last touched at `fe7d638`) — an old cron's root-level `rsync --delete` ate it, and under #29 that repo is **pure build output**, so deleting stray files there is now *correct* behaviour rather than a bug. But it is the only human-readable context for anyone landing on the GitHub repo page instead of the site. **Implement it by having `export_static.py` EMIT the README** alongside `robots.txt`/`.nojekyll` — **not** by adding an `rsync --exclude`. Reason: an emitted file is versioned in source, regenerated every run, and survives a fresh clone; an excluded file survives only by exception and silently disappears the first time someone re-clones. Content is the four lines it had: title, one-line description, link to the live Pages URL, and a note that the content is auto-exported from a private instance. **Lands with the cutover packet (P6b) — it is a publish-path change.**

**Deferred, not cancelled:** map view. The `<address>` block carries a venue name only, no street — a map needs a geocoding pass and is not free. Revisit once venue identity exists, since geocoding 744 venues is far cheaper than 5234 events.

**Do not reopen:** venue sources are a quality upgrade on a slice, never a coverage layer. Aggregators are permanent.

## Standing facts

Verified read-only 2026-09-11; see also §7 of `sorted-strolling-lagoon.md` (still valid verbatim — send a worker with a specific question, do not read wholesale).

- **[V]** 5234 future events. `time`/`venue`/`url` 100%, `image_url` 89%, `description` 9%, `price_text` 3%. 744 distinct venue strings. 85% of URLs → kulturkalender.de, 10% → cybersax.de.
- **[V]** Every Kulturkalender event page links out to the venue's own page (15/15 sampled). Each event's `<address>` links to a Kulturkalender venue page holding exactly one outbound link: the official homepage. Venue homepages therefore cost ~744 one-off requests, not 5234 recurring ones. **[I]** that this holds for all 744 — P4 tests it.
- **[V]** Kulturkalender serves no JSON-LD and no `og:` tags. Any queued "generic JSON-LD adapter" work rests on a false premise and is cancelled.
- **[V]** Host `leo` ~1.3 GB RAM free. No headless browser, ever. Respect the existing request delay.
- **[V]** A bad deploy is publicly visible: cron publishes 45 min after each scrape.
### P1 results (Haiku, 2026-09-11) — all **[V]**

- **Three** repos, not two. `backend` → `github.com/Trampa336/dd-was-geht`, `main`, clean, **2 commits ahead**. `frontend` → `github.com/Trampa336/DD_was_geht`, which **is the Pages site itself — build output, not source**. Plus a third clone on CT103 at `/root/dd-was-geht-site` that the cron pushes to.
- Pages serves from `main` of the frontend repo. No `gh-pages` branch.
- Cron on CT103: `15 1,7,13,19 * * *` → `/opt/dd-was-geht/tools/publish_site.sh`. Exports to `/app/data/site` in-container → rsync to `/root/dd-was-geht-site` → commit + push. Deploy key `~/.ssh/dd-was-geht-deploy`. No force-push; commits only on change.
- Pipeline **healthy**. Last run 2026-09-11 07:15:04, 5235 events over 32 days, ~2.8 MB, no errors.
- Export shape: pre-rendered `index.html` + `data/index.json` + one JSON per day. Each event carries **`uid`** and **`score`** fields already. Pure static, 69 files.
- `/opt/dd-was-geht` ~25 min behind local backend HEAD.

**Assumption "merging to one repo is a config change" — DISPROVEN.** The export targets a *separate repo by design*; consolidation means rewriting `publish_site.sh` and reconfiguring the Pages source. P6 is a rebuild of the publish step, not a config edit. Re-scoped accordingly.

- Three event counts exist and get crossed constantly — run-seen (`/api/health`), reach (`event_sources`), winner (`events.source`). Always name which.

### P2 results (Opus, 2026-09-11) — all **[V]**, measured

- **`uid` is STABLE. The hearts premise holds.** `uid = sha1(date|time|slug(title)|slug(venue))[:16]` — a content hash. Measured across 12 published snapshots in `/root/dd-was-geht-site` git history (2026-08-22 → 09-11), matching on `(source,url,date)`: **40 changes in 38,558 same-event comparisons = 0.104%**. Zero churn between consecutive 6h runs — churn tracks *source edits over elapsed time*, not re-scrapes. Causes: venue 19, title 14, time 6, both 1. Collisions 31/8468 = 0.37%, only on generic repeating titles.
- Practical exposure: **~3–4% for a heart held 30 days**. Absorbed by design, not by inventing a new key.
- Schema at `backend/migrations/001_schema_v2.sql` — 12 tables, 17 indexes, validated, `foreign_key_check` clean. `events.uid` PK + non-unique `identity_key = sha1(source|url|date)` as a re-attachment handle. `venues` (slug/name/region/kind/parent_venue_id + homepage & meta slots for P4) + `venue_aliases` so merges are data, not code. **`hearts` stores an event snapshot and deliberately has NO FK to events** — a heart must never cascade away. `categories`/`tags` as tables; `default_visible` puts the tourism tail one UPDATE away. Cutover at `backend/migrations/CUTOVER.md`. Committed locally `23a79be`, not pushed.
- **Venue collapse is small: ~4.7%.** 744 strings → ~710 canonical venues (35 merges). The strings are genuinely distinct, not sloppy. Real shape is the tail: **38% of venues have exactly 1 event, 56% have ≤2; ~120 venues carry the catalog.**
- **Category signal is thin and now measured.** `raw_category` filled 30.5% overall, **20.6% for kulturkalender (85% of corpus)**. `description` 9.1% overall, 2.5% for kulturkalender. URL path useless (3862/4472 under `/veranstaltung/`). **For 85% of the catalog, title + venue are the only signals.**
- **`score` is dead weight today.** Never a column; computed at serve time by `scoring.py` from `weights`. `reactions` and `weights` both have **0 rows** — all 5235 events export `score: 50.0`. Keep the mechanism, feed it from hearts, stop exporting the constant before P5 sorts by it.
- **Frozen interface:** `make_event_uid`. Any change to slugify or time normalization breaks every uid and every heart.
- **Do not delete in P3:** `event_sources`, `event_duplicates`, `scrape_runs` — they are the only way to tell a source with a broken selector from a quiet day. Carried into v2 unchanged.

### Blocker carried into P3
**`tests_smoke.py` is RED at HEAD and predates this work: 296 OK, 1 FAIL.** Unpushed commit `c27a84a` (flatpickr calendar) added 3 static assets; `index.html` now has 8 `static/` refs while the assertion demands exactly 5. Green at `HEAD~1`. This blocks every "tests green" gate until fixed.

### P3 results (Sonnet, 2026-09-11) — all **[V]**

- **Assumption held: none of the 10 scrapers needed changes.** All emit plain dicts with free-text `venue`/`category`; all resolution (alias lookup/auto-create, `identity_key`, `category_slug` FK with `sonstiges` fallback) lives in `db.py`'s write path. Verified by inspection *and* a real scrape run with zero exceptions.
- Counts from a real cycle against seeded v2, labelled: **run-seen 5948** (Sum of `scrape_runs.event_count`) - **reach 5880** (`event_sources` rows) - **winner 5239** (`events`, `duplicate_of IS NULL`, future). Sane against the 5235 baseline.
- **97% of v1 uids reappear unchanged in v2** — direct evidence hearts survive the cutover.
- Venues seeded: 744 raw strings -> **709 venues / 744 aliases**. Region via unmodified `geo.py`. `kind` curated for the top 120 by event count; remaining ~590 sit at `sonstiges` by design.
- Old DB frozen at `/opt/dd-was-geht/data/backups/v1-frozen-2026-09-11.db` (inside CT103, outside `backup.py`'s rotation glob).
- Deleted: v1's incremental `_migrate_schema`/`ALTER TABLE` machinery in `db.py`, obsolete under a fresh-start schema.
- `tests_smoke.py` **380 checks, 0 failures**. Publish cron confirmed restored. Live app HTTP 200, unaffected. Commits local only: `54d6eae` (smoke fix), `9472205` (v2 write path).
- Verification DB at `backend/data/dd-was-geht-v2.db` (gitignored, not deployed) — hand to P4 or discard.

### Two premises corrected by P3 — one of them the supervisor's

1. **The "42-bespoke-venue-scraper dead code" does not exist.** Checked commit history, `tools/`, requirements.txt and `sorted-strolling-lagoon.md`: packet P4b never advanced past `todo`. Nothing was ever written, so there is nothing to delete. **This was a supervisor-invented premise carried into this file from the project's history — exactly the failure mode this session is meant to avoid.** Correction: the abandoned strategy left *planning* residue, not code residue. `registry.EXTRA_VENUE_ALIASES` superficially resembles it but is live dedup-matching code — **do not remove**.
2. **`CUTOVER.md` section 4.5 said drop `reactions`. Following that would have deleted David's only working like/skip mechanism with nothing to replace it.** `tests_smoke.py`, `scoring.apply_reaction` and `/api/feedback` all depend on it today. P3 correctly refused and kept `reactions` alive as an addendum table created in `db.py:init_db()` — P2's DDL file untouched. A deviation from CUTOVER's letter, not from schema v2.

**Consequence for P5:** `reactions` (like/skip) is the *predecessor* of hearts, not a parallel system. David's own words were "a heart or like system **instead of** a dislike and like". So P5 ships hearts and retires `reactions` in the same packet — that is the retirement pairing, and it must not be split.

### P4 interim (Opus, 2026-09-11) — session ended mid-sweep; findings below were already in hand

- **Assumption A FALSE as stated; refined version holds.** KK venue pages carry **3+ outbound links**, not one: Kulturkalender's own footer social buttons (`kukadresden`), YouTube embeds, in-description links. The real rule: the homepage is the link whose **anchor text is its own bare domain** (`zentralwerk.de`, `www.skd.museum`). A naive "take the only outbound link" picks a `youtube-nocookie.com` embed. **[V]**
- **The planned cover source is empty.** Venue homepages publish essentially **no `og:image`** — verified against raw HTML, not just a selector. Covers cannot come from where decision #5 assumed. Better source found on a page already fetched: the **KK venue page's media slider** carries the venue's own photo, alt text naming the venue. **[V]**
- **Assumption B substantially WRONG.** Only **19 of the top 120** venues are single-category; **67 span three or more**. A *perfect* venue→category map ceilings at **73.8%** on the top 120. Venue-level kind is therefore a strong partial signal, not the fix. **[V]**
- Pacing ~35s/venue (large KK pages + mandated 1.2s delay); 160 venues ≈ 80 min.

### P4b partial (Opus, 2026-09-11) — STOPPED by David mid-sweep, results preserved

- Sweep reached **114 of 160 venues**, then was killed deliberately. **Nothing was lost.**
- **Results are in `backend/data/venue_cache/enrichment.json`, NOT in the database.** `venues.homepage_url` is still **0 populated**. 114 records, **88 with a homepage**, fields include `homepage_url`, `kk_cover_url`, `kk_cover_alt`, `all_homepage`/`all_social`/`all_other`, `kind`, `meta`. The tool is `tools/enrich_venues.py`, run as `../.venv/bin/python -u tools/enrich_venues.py data/dd-was-geht-v2.db --limit=160`. **The next packet must load this JSON into `venues` rather than re-fetching 114 venues.**
- Link-rule verdict on partial data: **literal "one outbound link" rule 37.5% success; refined bare-domain-anchor rule 81.2%.** Confirms the refined rule.
- Pacing measured at **3.5s/venue**, not the 35s P4 estimated.

### P4c results (Opus, 2026-09-11) — venue enrichment CLOSED OUT, all **[V]**

**Assumption HELD** — the cached data settled the og:image contradiction with no refetching. First packet in this project whose stated assumption survived. Verified three ways: denominator sweep, rank-cumulative replay, per-hit inspection.

**The contradiction was not a mistake by either worker.** `og:image` availability **rises monotonically as venue prominence falls**: 0.0% at 10 venues, 8.3% at 15, 35.8% at ~90, 39.5% at 114. P4 sampled the head and correctly saw nothing; P4b read a partially-written cache mid-sweep and correctly saw 35.8%. Same dataset, same code, different depth. **Lesson for this project: a rate measured on a rank-ordered sweep is meaningless without its depth.**

**Decision #5's cover source FALLS — but P4's conclusion was right for the wrong reason.** Of 34 og:image hits, only **13 are usable covers**: 9 logos/favicons, 5 dead on arrival (404/broken SSL), 3 `dresden.de` city-portal images that mutate (Neues Rathaus served a photo of a *flood*), 2 the same `kupa_default_meta.jpg` CMS default, 2 portrait production artwork. **Zero usable covers in the top 14 venues by event count.**

**→ Cover source for P5: `kk_cover_url` first, homepage `og:image` second.** KK covers: **142/142** venues that have a KK page, all 142 URLs distinct, 141 with venue-naming alt text. The fallback never actually fires — every og:image venue also has a KK cover.

**Numbers:** 160/160 venues enriched and loaded (**123 homepages, 142 covers**), joined by `venues.id` with name verification, 0 unmatched. **569 venues still unenriched**, carrying 1206 of 5239 winner events (23.0%). Hand-check **1 failure in 20 = 5%** (Schloss Pillnitz, transient HTTP 500; URL correct, returns 200 now) — no wrong sites, no social pages, no aggregator pages. Smoke suite 380/0, loader idempotent (re-run touches 0 rows), nothing pushed.

**Category headroom: 35.0% → 22.0% `sonstiges` — 13.0 percentage points**, moving 680 of 1834 sonstiges events. Needed no enrichment; `kind` was already populated by P3.

### Three sub-premises P4c broke

1. **P4's "verified against raw HTML" cannot be true.** `enrich_venues.py`'s docstring claims it caches raw HTML; **it never writes any**. Nothing on disk could have supported that claim. Treat "verified against raw HTML" in P4's report as unsupported.
2. **There is no "tool-inferred `kind`".** `enrichment.json`'s `kind` is P3's curated value read back out of the DB (differs in 0 of 160 rows). The clobber P4c's packet warned about was never possible. The only inferred kind is `enrich_report.evidence_kind`.
3. **DB drift from the standing facts: 729 venues / 792 aliases, not 709/744.** Correct this wherever it appears.

### Applying decision #14's own criterion (not a new decision)

Decision #14 set the test: *"If venue kind only moves 35% → ~30%, it drops below the title rules to a tiebreaker rather than a layer."* Measured move is **35.0% → 22.0%**, well clear of that line. **Venue kind stays a real layer in the precedence order**, below the title rules as #14 already ruled, not demoted to tiebreaker. No new ruling from David required.

**Caution when comparing:** the 73.8% ceiling is *accuracy* of venue→dominant-category; 78.0% non-`sonstiges` is *coverage*. Different quantities — **do not subtract them.**

### Carried into P5 from P4c

- **Deep-link defect: 45 of 123 homepages (36.6%) are not site roots** — `/veranstaltungen/`, `/programm/`, `/spielplan/`. The rule finds the right *site* but keeps the path the venue submitted to Kulturkalender. A "Homepage" button landing on the venue's own event listing is poor UX. **Fetch-free fix: store `scheme://netloc` and keep the full URL alongside.**
- **Cover attribution has nowhere to live.** `og_image_url` holds whichever source won, with no record of which. P5 may want a `cover_source` column.
- Two dead og:image URLs are stored as covers for venues that also have a KK cover. Harmless while KK wins the `or`; **inverting the fallback order would surface 5 broken images immediately.**
- The ~590 long-tail venues need **nothing** before P5 renders their fetch-free pages (name/kind/region/events, no cover).
- **The bare-domain-anchor link rule improved with depth**, it did not degrade: ranks 1–114 = 83.7%, ranks 115–160 = **92.1%**, overall **85.9%**. Literal "one outbound link" rule stays broken at 35.2%.

### Cutover path for the enrichment (described by P4c, not implemented; CT103 untouched)

Enrichment is venue-level metadata keyed by `venues.id`, which is **local to each DB — it cannot be copied by id**. The path is to re-run `tools/load_enrichment.py` against the live v2 DB *after* the live venue seed: it re-joins by id **and verifies the name**, refusing any row whose id points at a different house. That name check is what makes the cache portable. No refetching. **`enrichment.json` is the artefact that carries over, not the table.**

### P4d results (Sonnet, 2026-09-11) — PREMISE FALSE, packet stopped, nothing changed

**P4d's premise — and decision #14's — is false. German title-keyword rules are not an unbuilt layer. They are the current production categorisation mechanism.**

- `app/normalize.py::classify_category(raw_category, title, venue)` has been live **since the project's second commit `54d52ff`**. **Every one of the 10 scrapers calls it at ingest.** It already performs decision #14's stages 1+2: `raw_category` map, then a German title-keyword map (`KEYWORD_CATEGORY_MAP`, ~90 entries), then falls straight to `sonstiges`.
- **The 35.0% / 1834-event `sonstiges` baseline is the output of those keyword rules, not a pre-keyword baseline.** Everything sized against it must be read as *marginal* gain.
- **`venues.kind` appears nowhere in the categorisation path** — not in `classify_category`, not in the write path. It is unused curated metadata. Decision #14's stage 3 is the part that genuinely does not exist.
- `tools/reclassify.py` exists precisely because "changing the rules in `normalize.py` only affects newly-inserted events" — extending the map and backfilling is an **established, repeated workflow**, not new territory. Comments in `normalize.py` cite prior rounds of keyword mining "counted out of 1734 sonstiges titles".
- Dry-run check: current `category_slug` matches live rule output for **5769/5784 events (99.7%)**, drift 15 events (0.26%). Not stale.
- **Consequence: P4c's 13.0 pp (35.0% → 22.0%) is the marginal gain from wiring `venues.kind` in as stage 3 *on top of* the existing keyword rules.** That reading is now the correct one.

**Second disagreement, unreconciled — do not size P5 off the old figure until settled.** Recomputing directly from `dd-was-geht-v2.db` gives **120 multi-category venues** (3+ distinct `category_slug` among 5239 winner events), not the 67 carried since P4. P4d does not assert which is right, only that direct recomputation gives 120. The two numbers may use different populations or category sources. **This matters because multi-category venues are exactly where venue-kind guessing goes wrong — 120 is a materially worse exposure than 67.**

Supporting numbers (denominators stated): winner events at those 120 venues = **2199**; currently `sonstiges` among them = **781 (35.5%)** — so multi-category venues are **not** disproportionately worse than the 35.0% catalog-wide figure. `raw_category` filled among those 781 = **134 (17.2%)**.

**Cheap misses found in the existing map** (eyeballed 40 of the 781, not a full protocol): inflected `führ-` stems not caught by the substring `fuehrung` (e.g. "Geführter Kuppelaufstieg"), plain **"Tour"** absent from the map ("Elbschlösser-Tour" ×3), **"Orgel"** absent (organ recitals), **"Messe"** absent (fairs). Genuinely hard residue is festival umbrella titles ("Interkulturelle Tage", "Tag des offenen Denkmals"), named series with no genre word, and talk-show formats.

**Nothing was touched.** `git status --short` empty throughout, `tests_smoke.py` green, nothing to commit.

### P4e results (Sonnet, 2026-09-11) — DONE, committed `c059149`, smoke 380/0 throughout

**Two pre-existing LIVE bugs found and fixed, unrelated to anything any packet flagged.** Bare substring keywords in `KEYWORD_CATEGORY_MAP` were silently mislabelling real events as `musik`: `"rave"` caught *Travestie* / *Gravestone* / *Ravenshope*; `"jam"` caught the first name *Benjamin*. Victims included a drag revue, an academic panel and two comedy-theatre shows. Fixed to `-rave` and `jamsession`. **One of these had already corrupted P4e's own step-3 computation** — "Carte Blanche Travestie-Revue-Theater" looked falsely single-category until the fix; re-ran and it self-corrected. `band`/*"Verband"* found but deliberately left (1 event, no clean boundary rule) — chip `task_8380148b`.

**67 vs 120 reconciled — BOTH were correct, different populations.** Identical test (≥3 distinct `category_slug` incl. `sonstiges` among a venue's winner events). **P4d's 120 = all 729 venues. P4's 67 = same test restricted to the ~125 venues with ≥10 winner events.** Category source, event filter and threshold did not differ. No one was wrong.

**Keyword extension + backfill.** Added `gefuehrt` (inflected *führung*), `orgel`, a `messe-in`/`messe` disambiguation pair (Bach/Mozart *Mass* vs trade fair), and a conservative regex `Tour` detector with a word blocklist + 5-venue music-club blocklist. **A bare `"tour"` keyword was tested and rejected first — 4 of 16 raw matches were concert tours, not guided tours.** Net: `sonstiges` among 5239 winners **1834 (35.0%) → 1715 (32.7%)**, −119 events / **−2.3 pp**. **PHRASING CORRECTED by P5a: the 1715 already includes stage 3's 24 events — it is the post-venue-kind figure, not a keyword-only one.** Keyword-only is **1739 (33.19%)**. The chain is **1834 → 1739 → 1715**. Subtracting the separately-reported 24 from 1715 gives 1691, a number that exists nowhere in the pipeline.

**`venues.kind` as stage 3 — realised gain is 0.46 pp, not 13.0 pp.** Implemented in `db.venue_category_hints()`, called from `db.upsert_events` at insert and from `tools/reclassify.py` at backfill — **not** inside `normalize.classify_category`, because all 10 scrapers call that before `venue_id` is resolved; signature untouched. **Of 76 venues with a curated `kind`, only 17 are single-category** (55 multi-category, correctly kept at `sonstiges`; 4 no evidence). Gain: **24 winner events / 0.46 pp**. This is the conservative design working as specified, not a shortfall — but see the correction below.

**Tags seeded — exactly 5**, David's own named examples: `kirche`, `museum`, `open-air`, `klassik`, `techno`. 2154 `event_tags` rows. Winner coverage: museum 1174/5239 (22.4%), kirche 620/5239 (11.8%), klassik 305/5239 (5.8%), open-air 11/5239 (0.2%), techno 2/5239 (0.04%). Deliberately excluded: per-genre tags (sprawl), `kostenlos`/`barrierefrei` (no reliable field). **David's trigger example verified end-to-end: organ concert at a church venue → category `musik`, tags `{kirche, klassik}`.**

Files: `app/normalize.py`, `app/db.py`, `tools/reclassify.py`, `tools/tag_events.py` (new).

### Correction owed to David — the supervisor oversold decision #16 — **DELIVERED 2026-09-11, ruled as decision #18**

When David chose "venue guess, single-category venues only", the supervisor told him it would get **"most of the 13 points"**. **Measured reality: 0.46 pp of the 13.0 pp ceiling.** The reason is now known and was not known then: only **17 of 76** curated venues are single-category. The 13.0 pp ceiling assumed guessing at *every* venue, including the 55 mixed ones David deliberately excluded. His reasoning (accuracy over coverage) is untouched and the design is doing exactly what he asked — but the payoff estimate given to him was wrong by an order of magnitude. ~~He must be told and offered the choice again on real numbers.~~ **Done — he accepted 0.46 pp (#18).** Note the `open-air`/`techno` tag coverage (0.2% / 0.04%) is separately thin and may want the same scrutiny.

### P5a results (Sonnet, 2026-09-11) — DONE, committed `b68c680`, smoke 380/0

**Assumption HELD.** Second packet in this project whose stated assumption survived (after P4c). **P5b's design premise is safe.**

- **[V] The export renders the live Jinja templates in-process.** `tools/export_static.py:160-172` imports the Flask app and calls `flask_app.jinja_env.get_template("index.html").render(..., mode="static", ...)` inside a `test_request_context`. Not a second generator, not an HTTP crawl. The live route `app/web.py::index()` renders the same template with `mode="api"`.
- **[V] Write capability is kept out of the export by three independent mechanisms, not route separation alone.** (1) template `{% if mode != 'static' %}` omits the `rating.js` script tag; (2) `web.PUBLIC_ASSETS` excludes `rating.js` and the exporter actively deletes a stale copy; (3) `app.js` sets `CAN_RATE = MODE === 'api'` and guards its one live-only fetch with `if (MODE === 'static') return;`.
- **[V] The built export at `data/site/` (2026-09-11 02:34) contains no `192.168` reference, no active `/api/` call, and no `rating.js`.** `app.js` ships a dead reference to `window.ddFeedbackButtons` — undefined in static mode, every call site gated by `CAN_RATE`.
- **Consequence for P5b: the LAN-only pattern already exists and is proven — it is exactly how like/skip is kept off the public site today. Hearts extend it; they do not need a new mechanism.**

**Arithmetic settled [V]** (5239 winner events, `duplicate_of IS NULL`, local verification DB): stage 1+2 only = **1739 (33.19%)**; stage 1+2+3 = **1715 (32.74%)**, matching the live `category_slug` column exactly. Marginal stage-3 gain **24 events**, confirming P4e's 0.46 pp.

**Fetch-free fixes shipped**, DB-layer only, zero network requests, sourced entirely from the on-disk `enrichment.json`:
- `venues.homepage_root` (`scheme://netloc`), added **alongside** `homepage_url` — neither replaces the other.
- `venues.cover_source` (`'kulturkalender' | 'homepage' | NULL`). Populated **142× kulturkalender / 0× homepage**, confirming P4c's finding that the og:image fallback never fires. Fallback order untouched.
- Both via an idempotent `--apply`-gated extension of `tools/load_enrichment.py`. Re-run touches 0 rows. A SQLite DDL-autocommit quirk defeated the probe-mode rollback until an explicit `BEGIN` was added — found and fixed by the worker.

**Two numbers that did not reproduce — neither load-bearing, both recorded:**
1. **P4c's "45 of 123 homepages are deep links" could not be reproduced.** Broad rule (any non-root path) gives **49/123**; the three literal keywords cited (`/veranstaltungen/|/programm/|/spielplan/`) give **21/123**. P4c's classification method was never preserved as a script. The `homepage_root` fix does not depend on the count — it applies unconditionally to all 123 rows — so nothing is blocked. **Do not cite 45 as load-bearing again without re-deriving it.**
2. **Pre-P4e baseline recomputes to 1843/5239 (35.18%), not the reported 1834 (35.0%)** — 9 events / 0.18 pp, from identical code at commit `d45e2b3` against today's rows. **[I]** cause: snapshot drift from the 4×/day scrape cron rotating winners. Internal chain stays self-consistent (−95 keyword, −24 venue-kind = −119, matching P4e).

**Open question for P5b [I] — not verified by anyone:** `homepage_root` and `cover_source` are added by `ALTER TABLE` inside `tools/load_enrichment.py`, not declared in `migrations/001_schema_v2.sql`. P3 deleted v1's incremental ALTER machinery as obsolete under a fresh-start schema, though P3 itself kept `reactions` as an addendum table created in `db.py:init_db()` — so addendum-outside-the-DDL has precedent here. P4c's cutover path does re-run `load_enrichment.py` against the live DB after the venue seed, which would create the columns. **P5b should confirm where these two columns are declared and that a fresh DB built from the DDL is not missing them.**

### P5b results (Sonnet, 2026-09-12) — DONE, smoke 425/0, committed locally, nothing pushed

**Assumption MOSTLY HELD — but only after the worker built a fallback that was not in the packet.** Third packet whose assumption survived, and the first that survived *conditionally*.

- **[V] 5239/5239 winner events resolve to a venue row** — 0 NULL, 0 dangling refs. The core feature is reachable for every event.
- **[V] 3 of 729 venues are `is_meeting_point`** (city-tour meeting points) and get no page by schema design. **201 upcoming events** therefore get only their source link, no venue link. **726 venues are addressable.**
- **[V] The worker built an unrequested fallback and it is the reason this packet ships:** a venue with no `og_image_url` now falls back to the nearest upcoming event's own `image_url`. **Truly bare pages (one event, no image, no description) fell from 277 to 74 of 726 = 10.2%.**
- **[V] 74 pages are still a bare dead end** — one event, no photo, no description, `kind` uncurated (`sonstiges` for all 74). Worse than the Kulturkalender page they replace. **This is a design decision, deliberately not solved in-packet.** Reproducible via the new `tools/venue_readiness_report.py`.
- Built: searchable list (client-side title/venue search), category filter from the real `categories` table, tag filter over the seeded `tags`, region toggle default-Dresden. Venue pages at `/orte` and `/orte/<slug>`. **One Jinja template set verified rendering in BOTH Flask and static-export mode against the real DB, not fixtures.**

**A real, silent production drift found and fixed:** `config.EXCLUDED_CATEGORIES` (`familie`, `fuehrungen`) had disagreed with `categories.default_visible` (`familie` → visible) ever since P2 created the table. The UI now uses the table, the documented source of truth. **`familie` is visible by default from now on — a user-visible behaviour change, flagged not buried.**

**Two [I] concerns from earlier packets, both resolved [V]:**
1. `venues.homepage_root` and `cover_source` **are** declared in `migrations/001_schema_v2.sql` (P5a, `b68c680`). The supervisor's worry that they were ALTER-only was **stale — a fresh DB from the DDL has both columns.** No fix needed.
2. **`score` IS consumed** — the top-pick badge, the "wenig relevant" filter and `/api/fuer-dich` sorting. Left untouched per the packet's own rule. Not a contradiction of P2: it is consumed *and* constant, so the consumption is a no-op while `reactions`/`weights` sit at 0 rows. **P5c must replace the feed, not just delete the field.**

**Smoke: 425 checks, 0 failures.** Three assertion groups changed, each for a real behaviour change and each named in the commit message: asset paths now absolute in Flask (new nested routes), `index.json`'s `excluded` now sourced from `categories.default_visible`, region-toggle label/condition per decision #12.

### The fourth figure that failed to reproduce — and this one is the supervisor's

**The P5b packet said "~569 venues with no cover and no homepage, 38% of which have exactly one event." The 38% is attached to the wrong denominator.** **[V]** 38.0% is the rate over **all 726 addressable venues**; over the **569 unenriched** ones it is **48.7%** — about 11 points worse. P2's original finding was correct and correctly marked; **the supervisor re-attached it to a narrower population without re-deriving it.**

This is the project's **fourth** reproduction failure (after P4c's 45/123, P4e's 1834 baseline, and this), and the first the supervisor authored directly. **It is a violation of this file's own standing rule — "any rate needs its denominator."** The rule exists, was written down, and was still broken by the person enforcing it. **Carrying a [V] fact to a new population makes it [I] until re-derived.** Add that to the operating instructions.

### Carried into P5c from P5b

- **The 74 bare venue pages are a blocker-by-choice for hearts.** Hearts link straight into these same pages; a hearted event leading to a dead end is exactly the hand-off decision #4 exists to kill. **Close the gap or explicitly accept it before hearts ships.** David's call — put to him 2026-09-12.
- **`score` must be re-fed, not merely unexported.** Three live consumers.
- The worker tried to file the thin-venue follow-up as a background task; **the spawn tool errored (host-side hook timeout), so it is NOT in any queue.** It lives here only.
- **[I] Probable curation gap:** `"Treffpunkt: Molenbrücke Pieschen, Skulptur 'Undine kommt'"` reads like a tour meeting point but is not flagged `is_meeting_point` (only 3 are). Data curation, untouched.
- **Export churn warning:** each venue page bakes its upcoming-events list into static HTML, so most of the 726 files rewrite on most cron runs — a much larger per-push diff than the day-file approach. Acceptable, but P6 should know before this goes live.
- README was already stale on schema v2 before this packet; targeted fixes only.

**Run it locally (never port 1111):**
```
cd /home/admin/dd-was-geht/backend && DB_PATH=./data/dd-was-geht-v2.db WEB_PORT=8090 ../.venv/bin/python -c "from app.web import run_web; run_web()"
```
→ `http://192.168.178.88:8090/`

### P5t results (Sonnet, 2026-09-12) — ASSUMPTION DISPROVEN, structural cause found, smoke 425/0

**"These 74 venues are bare because nobody ever tried them" is FALSE. 0 of 74 gained a photo or a description. The residual is unchanged at 74/726 = 10.2%.**

**[V] The cause is structural, not depth.** All 74 venues' single event comes from exactly one source: **`cybersax`**. `app/scrapers/cybersax.py` exists *by design* to cover only venues Kulturkalender does **not** carry — the small Läden that never appear in KK. `enrich_venues.py`'s entire mechanism (day page → KK venue page → bare-domain homepage link → meta tags) depends on a KK venue page existing. **A cybersax-only venue structurally cannot have one.** 0/74 resolved, on a **full 32-day census of every distinct event date**, not a sample — necessary because a single-event venue surfaces on exactly one day.

**This retires the depth question, it does not lose to it.** P4c's 83.7% → 92.1% curve measured the domain-anchor link rate *among venues with a resolved KK page*. Here that precondition has **zero** instances. **The curve's domain does not reach this population.** Do not cite the depth curve against these venues again.

- **[V]** Site-wide totals bit-for-bit unchanged: cover 139/726, homepage 123/726, meta_description 79/726.
- **[I]** 20 of the 74 gained a curated `kind` from unambiguous name text (all were `sonstiges`). A real categorisation win — **not** a bareness fix, since `kind` is not photo-or-description.
- **9 left `sonstiges` deliberately and named** as uncertain rather than guessed — incl. `tonkunstraum`, `Katy's Garage`, `Trinitatishaus`, `Richard-Wagner-Stätten`, `Bahnbetriebswerk Dresden-Altstadt`. The worker explicitly declined to use outside knowledge of what `riesa efau, Motorenhalle` actually is. **That is the anti-fabrication rule working as intended.**
- **1 moderate-confidence call flagged for review:** `Puppentheatersammlung` → `museum` (linguistic inference from "Sammlung", not a keyword hit).
- Tools: `enrich_venues.py` gained an `--ids=` selector + full-census mode in a **separate cache file**, default behaviour byte-identical. New `tools/curate_kind_p5t.py` documents all 20 assignments with per-row justification.

### A TRAP left in the tooling — read before trusting the readiness report

**`tools/venue_readiness_report.py` section 4 now prints "0/726 truly bare". That is FALSE.** After `load_enrichment.py` moved the 74 from `meta_status IS NULL` to `'not_found'`, section 4's own `meta_status IS NULL` scoping excludes them. **The real figure is still 74.** The worker caught this by re-deriving the predicate without the scoping rather than trusting the tool's printed number. **Anyone citing that report's bare-count must re-derive it.**

**[V] Second tool note:** `enrich_venues.py`'s cache-skip (`if key in results: continue`) means these 74 — now cached as `kein_kk_link` — will never be auto-retried by a future default top-N sweep, even if one later picks up a second, KK-covered event.

### The fifth figure that failed to reproduce

**The deferred "70 already-enriched venues with `kind` unset, 706 residual `sonstiges` events" does not reproduce under any reading tried.** `meta_status NOT NULL` → **84 venues / 1368 events**; `meta_status='ok'` → **61 venues / 1044 events**. Neither is 70/706. **[V] Disjointness from P5t's 74 holds under every reconstruction — 0 overlap.** Re-derive 70/706 fresh when that packet runs; do not carry it.

### The real choice P5t hands to David

The 74 are a **closed set under the current source mix**, not a backlog to grind down. Any future cybersax-only venue lands in the same state. Two levers, no third:
- **(a)** Accept a short honest page as the terminal state — it still names the venue, the event and the date.
- **(b)** **[I], untested:** a different enrichment path for cybersax venues specifically. Their own `/terminal/adressen/address/<ort>/` pages carry outbound links *per the scraper's own docstring*. Requires writing new fetcher logic — out of scope for P5t by its own brief. **Yield unknown. Do not size it.**

### P5u results (Opus, 2026-09-12) — PARTIAL YIELD, lever exhausted, committed `53eccdc`, smoke 454/0

**Assumption HELD but thinly. 12 of 74 are no longer bare. Corrected residual: 62 of 726 = 8.5%** (from 74/726 = 10.2%).

**The docstring was right this time — 74/74 address pages exist [V].** Full census, denominator 74 on every line, no sampling depth:

| | count |
|---|---|
| address page exists | **74/74** |
| carries a `Web:` link (in the *Kontakt* block) | 34/74 |
| → real homepage (1 was Facebook-only) | 33/74 |
| → **homepage answers 200 + HTML** | **31/74** |
| og:image found | 16/74 → **4 stored, failure rate 12/16 = 75%** |
| description candidates | 23/74 → **10 stored, rejection rate 13/23 = 56.5%** |
| `kind` set from fetched text | 2/74 |

**Fail-fast sample honoured:** 10 of 74 across 4 day pages, before any tool was written — 10/10 address pages, 4/10 usable homepage. Non-zero, so it continued; the full run reproduced the sample rate (45% vs 40%).

**Not captured by the bare count: 31 venues gained a working Homepage button they did not have.** The bare predicate is photo-or-description, so a homepage alone does not clear it.

**THE LEVER IS EXHAUSTED — and the reason is structural, again [V].** A cybersax address page is a **contact card, not a venue page**: postal address, phone, opening hours, and **no `<img>` at all** (`n_images == 0` on every page fetched). So a cover can only ever come from the venue's own homepage `og:image` — the path P4c already measured as mostly junk, and it failed here at the **same 75% rate**. **There is no third image source for the remaining 62.** `cover_source` is `'homepage'` for all 4 and that is literally true; no cover claims Kulturkalender.

**A trap that would have poisoned all 74:** every cybersax address page carries four **paid backlink ads** (motel-one.com, flyer-druck-muenchen.de, kunzmanns.de, mvz-marienplatz.de) plus cybersax's own socials and a Google-Maps link. **"Take the single outbound link" would have stored an ad for every venue.** Reading only the Kontakt block is what makes it correct — now smoke-tested against a fixture that *includes* the ad bar.

**The anti-fabrication rule earned its keep — two textbook cases among the 13 rejected descriptions [V]:**
- **St. Michaelskirche** — the fetched text describes the *Stadtteil Bühlau*, not the church.
- **Kirche Loschwitz** — the first paragraph ends at the failed rebuild attempts; the 1994 reconsecration is only in the third. **Storing the lede alone would have told readers the church is a ruin.**
- The general failure mode: *"first paragraph" works when it is a self-contained lede and lies when it is instalment one of a narrative.* Also rejected: six branch libraries sharing one text about the library *website*, a 25-keyword SEO list, ad copy with ★ glyphs, a sentence cut mid-way in the source, and a text describing the Verein rather than the venue. All recorded in `BESCHREIBUNG_PRUEFUNG` so David can override any.

**Only 2 `kind` set, each with a verbatim citation in `KIND_AUS_TEXT`:** `bautzner69` → `galerie` ("*Ausstellungsraum* bautzner69"), and **`Katy's Garage` → `club`** ("*Der Club* mit Biergarten… Livekonzerte") — **the one item on P5t's deliberate-`sonstiges` list that new fetched text actually settled.** **52 of 74 remain `sonstiges`**, all listed by id in the report; renders as "Veranstaltungsort" and reads fine.

### The sixth figure that failed to reproduce

Fixing the false zero flushed out a sibling: **`feed.venue_cover`'s docstring claims "569 never-queried venues, 67.7% with an event image"; it recomputes as 385/495 = 77.8%** — because P5t moved exactly 74 venues out of that group (569 − 74 = 495). **Traceable drift, not a contradiction.** Replaced with a pointer to the report rather than a new hardcoded number. Fallback logic untouched.

### Carried into P5c (hearts) from P5u

- **[V] `app/templates/venue.html` prints "Aus Dresdner Veranstaltungskalendern **und der Homepage der Venue**" whenever `meta_status` is non-NULL — now false for the 43 of these 74 with no homepage.** Pre-existing (already false for every `not_found` venue). **It is a provenance claim on a public page; fix it in the packet that next touches the venue template.**
- **[I] A genuinely untried third lever exists and needs no new fetching:** the cybersax contact cards carry **postal address, phone and opening hours**, already fetched and sitting in `data/venue_cache/cybersax_*.json`. **`venues` has no columns for any of them.** Adding columns + parsing the cache would give the 62 real information instead of a photo. Not attempted, not sized.
- **Kulturinsel Einsiedel's stored cover is a 6.1 MB hotlinked PNG** — correct motif (all 4 covers were downloaded and eyeballed), heavy for one page. No image proxy exists.
- **Johannisfriedhof's cover is a three-panel montage** of all three cemeteries the operator runs. Motif right, specificity wrong.
- **2 dead homepages deliberately NOT stored** (537 `skd.museum/?id=83` → 404; 616 greenpeace → ConnectionError). The template hangs the Homepage button on `homepage_root` alone, so a stored dead URL is a dead button. 537's is a deep link that probably has a live replacement — worth a retry.
- **Richard-Wagner-Stätten (510) — declined, David's call, text supplied:** "Ausstellungen und Veranstaltungen zu Richard Wagner, Vermietung Festsaal für Feiern und Hochzeiten." Real exhibition evidence, but it splits `museum`/`galerie` and the place also rents a hall. Left `sonstiges`.
- **Puppentheatersammlung (519):** re-checked as asked — its address page has no web link and no free text, so **nothing confirms or refutes** P5t's `museum` inference. Left as-is; reverting would be equally unevidenced.
- Of P5t's other 8 deliberate `sonstiges`, **5 have no web link at all** (441, 467, 506, 656, 696) — no further evidence obtainable from this source.

**Smoke 425 → 454 checks, 0 failures, no existing assertion changed or removed.** 29 added, including **a regression guard that reproduces the false zero** (a bare venue with `meta_status='not_found'` must still be counted). `enrichment.json` untouched and asserted so in the suite. 11 local commits ahead of `origin/main`, nothing pushed.

### P5v results (Sonnet, 2026-09-12) — DONE, committed `7d754c3`, smoke 485/0

**The trap did NOT spring — and only because it was checked.** The worker opened `data/venue_cache/cybersax_enrichment.json` directly **before writing any code** and found each of the 74 entries carries a `cs_sections` dict with real captured `Adresse` / `Kontakt` / `Öffnungszeiten` / `Anfahrt` text — not just the `Web:` link P5u's report mentioned. **[V] by reading the raw JSON, not by trusting a docstring. Zero network requests** (verified structurally — no `requests` import, no fetch in the new path).

**Counts, denominator 74, each verified by direct query after writing [V]:** address **56/74**, phone **22/74**, opening hours **8/74**, **18/74 nothing at all**. Phone and hours are subsets of the address set — **56 is the union, not a sum.**

**Bare-page count 62 → 62, unchanged and correctly so** — address/phone/hours are not part of the bare predicate, and `og_image_url`/`meta_description`/`events` were untouched. Recomputed by hand with the exact SQL predicate, **not** read off the tool's printed summary.

**[V] `venue.html`'s false provenance line fixed, and the root cause is sharper than reported earlier:** the footnote claimed "und der Homepage der Venue" whenever `meta_status` was merely **non-NULL** — but P5u had set `'not_found'` / `'error:*'` on venues with no homepage, and those are non-NULL. Now checks `meta_status == 'ok'`. **43 of the 74 were affected.**

**The one finding carried into hearts: `meta_status` being *set* and `meta_status` being `'ok'` are different, load-bearing facts in this codebase.** Any packet that treats non-NULL as success will reproduce this bug.

**Deliberately declined to store — present on the card, outside the asked-for fields, neither fabricated nor silently folded into a neighbouring column:** fax numbers (a fax is not a phone), email addresses (no column asked for), contact-person names (e.g. "Olaf Doehler" prefixing a Telefon line), and the `Anfahrt` block — **verified to be site chrome only** (`» Stadtplan`, `» Verkehrsverbindung`, a Google Maps link), never a real venue fact.

**18 of 74 have no contact data** (empty or homepage-only Kontakt block): 332, 364, 451, 458, 472, 479, 490, 506, 507, 523, 537, 597, 598, 651, 659, 690, 695, 706.

Files: `migrations/001_schema_v2.sql`, `tools/enrich_venues_cybersax.py` (new `extract_contact()`), `tools/load_cybersax_contact.py` (new), `app/templates/venue.html`, `app/static/app.css`, `tests_smoke.py`. 74 rows evaluated, 56 changed.

**RESOLVED (Haiku lookup, 2026-09-12) — the capture date IS rendered [V].** The P5v report was silent on it, so it was checked rather than assumed. `app/templates/venue.html:52-54` renders `Öffnungszeiten: {{ venue.opening_hours }} (Stand: {{ venue.contact_fetched_at | de_date }})`, styled `.venue-hours-date` in `app.css:350` — dimmed, **not hidden**. Backed by a real `contact_fetched_at TEXT` column declared in `migrations/001_schema_v2.sql:108-112`, populated by `load_cybersax_contact.py` from the **source page's** `meta_fetched_at`, **not the script's run time**. The schema comment states the reasoning explicitly: hours go stale, address/phone do not, so the date shows only beside hours. **Requirement met exactly as briefed.**

**Lesson: a silent report is not a negative report.** The supervisor asked for a specific deliverable, the report did not mention it, and the correct move was a cheap Haiku lookup — not an assumption in either direction.

### P5w results (Opus, 2026-09-12) — SUPERVISOR HYPOTHESIS FALSE, one real defect fixed, smoke 489/0, commit `4896c68`

**David reported "a lot entries doubled" on first look at the new frontend. Most of what he sees is CORRECT DATA.**

**The supervisor's fan-out hypothesis is FALSE — falsified three ways [V]. This is the supervisor's THIRD false premise in this project, and the third caught by a worker.**
- `db.events_for_range` (`app/db.py:539-543`) has **exactly one join**, `LEFT JOIN venues v ON v.id = e.venue_id` — 1:1 on a primary key. **Tags are not joined into the list at all**: `db.tags_for_events` is a separate uid-keyed query and **the tag filter runs client-side** (`app/static/app.js:247-250`). `event_tags` PK `(event_uid, tag_slug)`, 2154 rows / 2154 distinct pairs.
- Live API: **235 rows / 235 distinct uids**, zero repeats in *every* filter state tested (5 categories + combinations, region toggle, Dauerangebote, each of the 5 tags).
- **Zero uid repeats across 5027 winner rows (today…+45d), all 726 venue pages, and the static export.**
- **`DISTINCT` would have fixed nothing and hidden everything. The packet forbade it and the worker correctly refused it.**

**The bulk of the symptom is real, correct data [V]:** 245 same-day/same-title groups, **437 rows beyond the first / 5026 winner rows = 8.7%**. Verified against live source HTML — **kulturkalender-dresden.de itself renders 5 separate cards for "Domführung" today at 10:30/11:30/12:30/13:30/14:30**, and 2 for "Highlights der Gemäldegalerie". `dedup.py` Grundregel 1 refuses same-source merges **by design**. Untouched.

**Candidates ruled out with counts [V]:** `duplicate_of` **is** applied and current — re-ran `dedup.find_duplicates` over all 5545 future rows, 518 stored vs 518 computed, **0 added / 0 removed / 0 re-pointed**. No stale ghost rows — all 244 kulturkalender rows for today still exist on the live source under the same uid.

**The one genuine defect, found and fixed.** `_title_tokens` drops words under three characters, so `S.Y.N.T.H.E.T.I.C S.I.G.N.A.L.S` slugifies to single letters and yields **no tokens** — `_title_scores` is then forced to `overlap=0.0, words=0` no matter how identical the titles are. The strong same-venue rule consulted `min_overlap` **only** (`min_ratio=None`), so the 150-minute Einlass/Beginn window was **unreachable for such titles even at ratio 1.00**. Live case: Ostpol, kulturkalender 20:00 vs rauze 22:00, same venue, character-identical, 120 min apart — two rows for one club night. Fix adds `STRONG_TITLE_RATIO = 0.95`, OR-ed with the existing threshold so it can **only add**: over 5545 future rows, **exactly 1 link added, 0 removed, 0 re-pointed.** Live view 235 → 234.

**Residual cross-source misses: 24 pairs / 5027 = 0.48% before, 22 / 5026 = 0.44% after.**

**Counts kept apart as required:** run-seen **5948** (summed `scrape_runs.event_count`, 31-day window, rows seen not unique); reach **5880** (`event_sources`); winner **5026** (`duplicate_of IS NULL`, today…+45d) — every rate above is against winner.

**Smoke 485 → 489, no existing assertion changed.** The load-bearing addition was **verified to FAIL on the pre-fix `dedup.py`** and pass after.

### THE finding for hearts — a silent-vanish bug waiting one table over

**[V] A hearted uid can stop being rendered without ever disappearing, and `link_status='ok'` will still say it is fine.** The `hearts` schema anticipates uid *breakage* (`identity_key`, `link_status IN ('ok','verwaist','neu_verknuepft')`, `relinked_from`), but its `'ok'` means *"uid points at a living event row"* — **and that is not the predicate the list uses.** The list requires `duplicate_of IS NULL`. `dedup.link_duplicates` runs after **every** scrape over today…+31d and freely moves rows between winner and duplicate. **The worker produced exactly that transition inside this packet:** `15a4e9d368071799` is still a perfectly live row and is now invisible in every view. A heart on it would read `'ok'` and silently vanish from the curated page.

**This is the same conflation P5v just fixed — a status field being *set* versus the thing actually being *true*. Twice now, one table apart. Treat it as a project-wide failure mode, not two coincidences.**

**Second consequence: a heart lands on a *showing*, not an event.** Hearting "Domführung 11:30" leaves the other four uids that day unhearted, and **no code path relates them.**

### Carried into P5c (hearts)

- **Hearts must track the WINNER predicate, not row existence.** A fourth `link_status`, or a check on `duplicate_of`, plus a relink to the canonical uid — **`event_duplicates` already records `duplicate_uid → canonical_uid`, so the mapping is free.**
- **[Product question put to David 2026-09-12]** 8.7% of rows share a day and title with another, almost all correctly. Collapsing "Domführung ×5" into one row with five times is a **presentation** change in `loadList` — **doing it in the query or with `DISTINCT` would make real showings disappear.** The answer also decides what hearting a multi-showing event means.
- **22 cross-source misses / 5026 (45d)**, two data-shaped clusters: cybersax appending a parenthetical troupe name ("Kleine Geister" vs "Kleine Geister (Allraunen Theater)", ~0.50 overlap, recurs 4×), and sources disagreeing on start time by 3–6 h ("Scheune is Back" 15:00/20:00). **A fix means widening `SAME_VENUE_MIN_OVERLAP` or stripping trailing parentheticals — not deleting rows — and needs a false-positive count first.** Sonnet, measured before/after.
- **3 split venue rows** put one house on two `/orte` pages (`paula`/`club-paula`, `club-baerenzwinger`/`baerenzwinger`, an Erich-Kästner-Haus pair), 3 winner events affected. Dedup matches on `raw_venue`, not `venue_id`, so it splits *venue pages*, not list rows. **Venue identity is load-bearing — own packet, not a drive-by.**

### P5x results (Sonnet, 2026-09-12) — DONE, commit `7a2b7fe`, smoke 505/0

**Threshold 3+, chosen from the data and verified against content [V].** Histogram over **5026 winner rows** (`duplicate_of IS NULL`, 2026-09-12…+45d), grouped by **(date, venue, normalised title)**:

| group size | 1 | 2 | 3 | 4 | 5 | 7 | 8 |
|---|---|---|---|---|---|---|---|
| groups | 4394 | 154 | 21 | 32 | 22 | 1 | 2 |
| rows | 4394 | 308 | 63 | 128 | 110 | 7 | 16 |

**All 78 groups of size ≥3 were inspected by hand: 100% are one exact title at evenly-spaced times the same day** (Domführung/Turmführung at Dom zu Meißen 3–8×/day, Wein-Führung Wackerbarth 3×/day, one children's concert). **Zero coincidental collisions.** Size-2 groups are genuinely mixed — some two-slot tours, some real double-bills — so they stay two rows, as #24 ruled.

**THE SURPRISE: on David's actual default view, this changes almost nothing. [V]** Dresden-only + `fuehrungen` hidden + Dauerangebote hidden → **2281 → 2276 rows over 45 days (5 saved)**; today alone 154 → 154. Every long-run title is *also* `ongoing=True` (≥7 distinct days), *also* in the `fuehrungen` category (`default_visible=0`), *and* mostly at `region='weiter'/'umland'` venues — **three non-default toggles already hide them.** Only with every filter opened does it bite: **5026 → 4780, 246 rows saved (4.9%)**.

### The finding that matters — P5x likely fixed the wrong surface

**[V] `/orte/<slug>` has no category, region, Dauerangebote or date filtering, and no date cap.** `db.venue_upcoming_events` returns every future winner row for that venue unconditionally. **Dom zu Meißen's venue page: 307 rows one month out, 273 of them (89%) "Domführung" ×142 and "Turmführungen…" ×131.** That is a far more plausible place to see "a lot entries doubled" than the main list. **P5x deliberately left it alone** — `venue.html` is server-rendered Jinja with no JS, so it needs a Python-side grouping helper feeding both Flask and `tools/export_static.py`'s venue-page path, not a `loadList` change. **Scope call, correctly flagged rather than silently widened.**

### Hearts recommendation (reported, NOT built — David's to rule on)

**[V]** `hearts.event_uid` is a PRIMARY KEY on a **single showing**; `identity_key` only re-links the *same* showing across scraper churn. **Nothing relates the 5–8 sibling uids of one run.** P5x recommends: **a heart on a collapsed row hearts the whole run**, keyed by the same group key used for display (venue_slug + normalised title), rendering the row hearted if any member is hearted. Reasoning: seeing "Domführung, 5 Termine" the mental model is *"I like this tour"*, not *"I like the 12:30 slot"* — hearting one sibling and not the other four would read as a bug. **Requires a schema/lookup change (group-key → hearts, or a join table).** Build item for P5c.

### The SEVENTH figure that failed to reproduce — and it is P5w's

**P5w's "437 rows beyond the first / 5026 = 8.7%" only reproduces under a (date, title) key that OMITS VENUE** — exactly the mistake P5x's packet warned against. **Under the correct (date, venue, title) key it is 400 / 5026 = 8.0%.** The gap is same-titled events at *different* venues being merged by P5w's diagnostic. **Cite 8.0%, not 8.7%.** P5w's conclusions are unaffected (the finding was qualitative — these are real showings), but the rate was wrong.

Files: `app/static/app.js` (`RUN_MIN_SIZE`, `runSlug`, `runKey`, `buildEventRow`/`buildRunRow`, `loadList`), `app/static/app.css`, `tests_smoke.py` (489 → 505, new P5x regression section). Dev server restarted and confirmed healthy. Live DB untouched.

### P5c results (Opus, 2026-09-13) — HEARTS SHIP. ACCEPTANCE TEST PASSED. commit `d1e7bd6`, smoke 550/0

**THE ACCEPTANCE TEST FOR THE WHOLE REWORK PASSED [V].** Hearted a real 5-showing Domführung run plus a single event, then ran the **actual** `scheduler.run_scrape()` against all 10 live sources — 5804 seen, 415 new, 546 duplicates booked. **Both hearts survived.** The worker **did not trust the log line** ("2 ok / 0 relinked / 0 orphaned") and **re-derived the predicate**: each anchor exists **and** has `duplicate_of IS NULL`, all 5 showings returned as run members, both render on `/herzen` with live data. Hearts and their weight rows then removed, so the curated page ships genuinely empty per #19 (`hearts 0 | weights 0` **[V]**).

**Export verified clean [V]** — built from the real DB (5092 events, 32 days, 746 venue pages) and grepped across **every** file: no `/api/herz`, no `/api/feedback`, no `192.168.178.91`, no `:1111`, no `herzen.js`, no `/herzen` page, no `window.ddHerzButton =`. The only "herz" hit is `orte/herz-jesu-kirche.html`, a real Dresden church. **The worker renamed the READ endpoint to `/api/geherzt` specifically so `"/api/herz"` is an unambiguous grep for the WRITE route** — decision #8's check would otherwise have been un-greppable.

### The assumption was HALF FALSE, and the worker said so before ripping anything out

**Gating half HOLDS [V]** — template `{% if mode != 'static' %}`, `PUBLIC_ASSETS` exclusion + the exporter's active deletion, and `CAN_HEART = MODE === 'api'` all carried over unchanged; `herzen.js` slots exactly where `rating.js` sat.

**`scoring.py` half is FALSE [V].** `reactions` was a **two-sided** signal; a heart is one-sided. `weights.skips` is now permanently 0, so the Laplace rate `(likes+1)/(likes+skips+2)` is pinned in [0.5, 1) and **`score` can never fall below 50 again.** Two of the three consumers survive that (top-pick badge, `/api/fuer-dich` sorting). One cannot: **the "Wenig relevant" filter (`score < 40`) became permanently unreachable.**

**Resolution — both, cleanly, not half of each as the packet demanded:** `score` is fed from hearts **once per run, not per showing** (an 8×/day Domführung would otherwise outweigh a concert 8:1), **and the one dead consumer was removed** rather than left as a switch that can never filter anything. Two tests pin the reasoning.

### THE finding — the worst case cannot be repaired by the run key at all

**[V]** Confirmed in live data: uid `15a4e9d368071799` ("S.Y.N.T.H.E.T.I.C S.I.G.N.A.L.S") is alive with `duplicate_of = e5b0aa6df8071ec8`. **The sting nobody had looked at: the two rows carry `raw_venue` "Ostpol Dresden" vs "Ostpol".** P5x's run key is built from the **raw venue string**, so the two rows produce **different run keys** — a heart on the losing row is **not** rescuable by re-looking-up its own key. **The key itself has to move.**

`db._resolve_heart()` resolves in four steps (own key's winners → the dedup booking, adopting the canonical's key → `identity_key`+date → `verwaist`), and `relink_hearts()` runs after `dedup.link_duplicates()` on **every** scrape. **`link_status='ok'` is set in exactly one place and means "the anchor is a WINNER row", never "the row exists"** — a smoke invariant re-derives that over every heart. **A heart is never deleted:** orphaned, it lives on its snapshot, keeps its candidate uid list, and re-attaches if the series returns (tested).

### Date-in-run-key: INCLUDED. The number that decided it, for David to overrule

Key is `<date>|<venue-slug>|<title-slug>`. **Not a second notion of a run** — P5x already groups strictly *within* a day (`byDay`), so adding the date changes folding behaviour by **exactly nothing**; it only makes a *stored* identity unique across days, which a transient grouping key never needed.

**Measured over 5092 winner rows (`duplicate_of IS NULL`, today…+45d, post-scrape) [V]:** with the date, **4696 distinct runs, 78 of them ≥3 showings**; a heart covers **1.08 rows on average, at most 8**. **Without** the date, one click on "Domführung @ Dom zu Meißen" drops **145 rows across 32 days** onto the curated page, and **3057 of 5092 rows (60.0%)** sit under a key spanning more than one day — **a dateless key would make the majority of hearts multi-day, on a date-bearing page.**

**INDEPENDENTLY RECOMPUTED AND CONFIRMED [V] — the first figure in this project to be verified twice by two different code paths.** A slow O(n²) version of the measurement (per-key date sets built by rescanning the row list) finished after the fast rewrite that was quoted, and **every figure agrees exactly**: events total 6199; winner rows 5092; all rows in window 5638; runs with date 4696 (78 ≥3 showings); runs without date 2427; largest dateless group 145 rows across 32 days; **3057 of 5092 = 60.0%** dragged across days. **Seven figures in this project have failed to reproduce; this one was checked twice, deliberately, against the same denominator.**

**Trade-off David loses:** *"I like this tour, always"* now needs one heart per date. **The cheap fix is a second, dateless "Reihe merken" concept later — widening is easy, whereas a dateless key retroactively pulls in events he never saw, which is not undoable.**

**Consequence worth knowing [V]:** two showings of the same title/venue/day stay **two rows** (below `RUN_MIN_SIZE`, #24) but **share one heart** — hearting either marks both. Follows directly from "a heart lands on a run"; the server is idempotent (a second click does not double-count weights).

### Smoke assertions changed — all 15 named by the worker

505 → **550 checks, 0 failures**. **5 removed** (the thing tested no longer exists: `apply_reaction`, no-op like, score-after-no-op, "score back ≤50 after switching to skip" — **there is no skip** — and a dedup-like test using `set_reaction`). **4 relabelled**, same fact new mechanism. **4 rewritten** because the artefact changed (`rating.js`→`herzen.js`, `CAN_RATE`//api/feedback → `CAN_HEART`//api/herz). **1 updated** (the `runKey` exact-string check). **1 deliberately INVERTED:** P5x asserted a folded row gets *no* rating buttons and flagged that as an open question for hearts — **#26 answered it, so it now asserts exactly one heart button per folded row.** The dedup question got 3 replacement checks stricter than the one they replaced.

**Figure discipline [V]:** the 5026 winner count reproduces exactly. **One near-miss flagged honestly rather than claimed:** 78 runs ≥3 showings over **5092** rows here vs P5x's 78 over **5026** — *"same count, different denominator, treat as a coincidence, not a reproduction."*

### Carried forward from P5c

- **[V] Run keys use `raw_venue`, not `venue_slug`.** Both Ostpol rows resolve to the **same `venue_id` (77)** — keying on the resolved venue would have made the key survive the dedup transition on its own. **Deliberately not changed:** it would fold two spellings together in the list, which is a **product** change, not a repair. **Worth its own packet.**
- **The curated page `/herzen` is Flask-only and deliberately NOT in the static export.** **Whether it becomes a public surface is a P6 decision.** Note decisions #1 and #2 want two surfaces, both local *and* public — **so P6 must rule on this, it is not settled.**
- `/herzen` has **no ordering, notes or grouping UI**. The schema carries `note` and `sort_order` and `db.list_hearts` reads them; **nothing writes them yet.** Cheap once David has used the page.
- **[V]** Hearting something in a hidden category is invisible in the default list (the test Domführung is `fuehrungen`, `default_visible=0`, region `weiter`). Existing P5b behaviour, not new — **but the curated page is now the surface where such hearts are reliably visible, which is arguably the point.**
- `bump_weight` leaves zeroed rows (`likes=0, skips=0`) after un-hearting. Harmless (`get_weight` returns `(0,0)` either way) but makes an empty model look populated. Dev DB cleaned by hand rather than changing the clamp contract mid-packet.

### P6a results (Opus, 2026-09-14) — DONE, commit `59b91cc`, smoke 568/0, nothing pushed

**THE BLOCKER: `github.com/Trampa336/dd-was-geht` is a PRIVATE repository [V]** — unauthenticated `git ls-remote` is refused, the identical request against `DD_was_geht` returns refs, and the local reflog shows `update by push`, so the repo exists. **GitHub Pages cannot serve from a private repo on GitHub Free.**

**Decision #9 — "merge to one repo, delete the separate Pages repo" — therefore silently requires one of: make the source repo public, buy GitHub Pro, or do not consolidate the *published* repo.** P6b would have hit this at "Settings → Pages", **after the code was deployed and the cron possibly repointed.** It is **step 0** of the runbook. **Put to David 2026-09-14.**

**[V] The full git history was scanned and is clean of credentials** — `.env` never committed, no private keys, no tokens. The only private detail is the string `192.168.178.91` / `:1111` inside a `tests_smoke.py` assertion (RFC1918, not routable).

**Shape of the new path.** Source + built site in one repo, site under **`docs/`** — GitHub Pages' branch-deploy knows exactly two roots, `/` and `/docs`, and `/` would publish the whole source tree. A `gh-pages` orphan branch is the documented escape hatch, rejected for now because it needs a second worktree inside a root cron script. A GitHub Action cannot build it at all — **it would need the database.**

**The export still runs in the container and still writes `/app/data/site` — and that is correct, not lazy: `./data` is the ONLY bind-mounted path**, so it is the only place the container can write that the host can see. Everything *after* changed: `rsync --delete` now targets `$SITE_REPO/docs/`, staging is `git add -A -- docs`, and the clone does `fetch` + `reset --hard origin/main` **before** writing — **because consolidation creates a second writer to that repo, and without it the cron's push fails silently the first time David pushes source from his laptop.** `EXPORT_MODE=lokal` and `DRY_RUN=1` were added so the path can be driven outside CT103 at all.

**Verified locally [V]:** smoke **550 → 568, 0 failures** (counted by grepping `[OK]`/`[FAIL]`, **not** the trailing banner). Export **798 files**, 4970 events over 32 days, 752 venue pages. **Every file byte-read** for `/api/herz`, `/api/feedback`, `192.168.178.91`, `:1111`, `herz-entfernen`, `data-run-key`, `ddHerzButton =` — **zero hits**, no `herzen.js`/`rating.js`. `static/` **exactly equals** `PUBLIC_ASSETS` by set comparison. **5287 relative links, 0 absolute, 0 broken** — the property `docs/` rests on. Curated page present, **`<button>` count 0**, `noindex`, renders an 8-showing run as one row with all eight times — **seeded 3 real hearts in a DB copy first, because an empty page would have proven nothing.** Whole script end-to-end twice against a local bare repo, plus a **concurrent-writer test** (another clone pushed source, the cron clone was behind, `reset --hard` recovered, push succeeded, **source files survived**). **All six failure guards** exit 1 with a message and leave the clone untouched.

**File-list diff vs the published site** (probed over HTTPS — CT103 untouched): live **43 files**, new export **798**. **+755, −0.** All 43 existing files stay; only content changes.

### The assumption was INCOMPLETE, not false — four things cannot be verified locally, not one

1. `docker exec … --out /app/data/site` — the container invocation, and that the bind mount lands where the script expects **after** the deploy.
2. `git push` over SSH with a deploy key (the test pushed to a local bare repo).
3. **GitHub Pages building and serving `main:/docs` — including whether it is permitted at all** (the blocker above).
4. The cron entry itself — root's `$HOME`, `$PATH`, and `docker`/`rsync`/`git`/`find`.

**"Only the git push can't be tested" understates it by three.**

### The old script has ALREADY destroyed something [V]

`https://trampa336.github.io/DD_was_geht/README.md` is **404**, although `README.md` is tracked at the old clone's HEAD (`fe7d638`, "README mit Link zur Live-Seite ergänzen"). `.nojekyll` is present, so Jekyll is not the explanation — **a later cron run's `rsync -a --delete` into the repo root simply deleted it.** Targeting `docs/` removes that entire class of accident.

### Export churn — P5b's warning does NOT reproduce [V]

Method: snapshot the dev DB, real scrape against all 10 live sources, build A (pre-scrape), B (post-scrape same day), C (post-scrape, T+1). **Scrape push: 148/798 files, 116/752 venue pages = 15.4%** (26 h gap, so an **upper bound** for a 6-hourly run). **Rollover push: 70/798, 66/752 = 8.8%.** Worst observed across 12 builds **185/752 = 24.6%** — **not "most".** Packed growth **21.3 KB/push amortized → ~30 MB/year** at 1460 pushes; loose between GitHub's repacks ~83 KB/push → ~133 MB/yr. Initial import 8.4 MB of files → **1.19 MB packed**. **Verdict: no fix needed** — the 1 GB soft limit is 15–30 years out, and the `gh-pages` orphan branch stays available. **Not fixed, deliberately.**

### Two more defects found in passing

- **[V] The exporter's own `venues_written` counter was wrong by exactly 1 on every run.** `_write` read back in **text mode**, so universal newlines turned `\r\n` into `\n`; one scraped event title carries a literal CRLF ("King Of Pop … von\r\nMichael Jackson"), so `orte/boulevardtheater.html` was rewritten **every single export, byte-identically.** Git never saw it; the counter did. Now compared byte-wise, with a regression test. **Another instance of "do not trust a tool's printed summary".**
- **[V] A latent silent failure, present in the PRE-P6a script too:** `set -o pipefail` plus `DAYS=$(find "$EXPORT_DIR/data/days" … | wc -l)` means a missing `data/days` aborts the script with **no line in the cron log at all.** Never fires in normal operation — **would fire on cutover day**, when that directory is somewhere new for the first time. Fixed with a `-d` test, pinned by a check.

### The EIGHTH figure that failed to reproduce

**P1's "Pure static, 69 files" does not hold — the published site is 43 files [V]**, and 32 day files + 11 others is exactly what P1's own described shape gives. **Cite 43.**

### Smoke assertions changed — both named, neither loosened

Two P5c checks were **inverted because decision #27 overruled their premise**: *"die kuratierte Seite wird nicht exportiert"* → now asserts it **is** exported, exactly once, as `herzen.html`; *"die oeffentliche Seite verlinkt sie auch nicht"* → now asserts it links **relatively** (`href="herzen.html"`), never `href="/herzen"`. **The heart-button exclusion is checked more strictly than before** — no `<button>`, no `data-run-key`, no `herzen.js`, on a page proven non-empty first. 17 new checks.

### Carried into P6b

- **Step 0 is David's and gates everything:** public repo / GitHub Pro / don't consolidate the published repo.
- **The public URL changes** (`…/DD_was_geht/` → `…/dd-was-geht/`). **Decide before cutover** whether the old repo is deleted (old links die) or left as a redirect stub.
- **[I]** The cron's four times look like host **UTC**: live `generated_at 2026-09-14T21:15:02` is `19:15 + 2 h`, and the container runs `TZ=Europe/Berlin`. Confirm during cutover; changes nothing in the runbook.
- **`origin/main` is 16 commits behind local HEAD — David must push the source himself.** The worker did not.
- `/opt/dd-was-geht` is **8–14 commits behind**, pinned from the live site's own content (flatpickr present ⇒ ≥ `c27a84a`; no `site-nav`, `orte.js` 404, 7-entry `PUBLIC_ASSETS` ⇒ < `2b37172`). P1's "~14" is the top of that window.

**Runbook: `/home/admin/.claude/plans/P6b-cutover-runbook.md`** — 10 numbered steps, each with its rollback. Escape hatches preserved first (step 2 copies the old script and crontab; old deploy key, old clone and old repo all left untouched). **A SECOND deploy key, not a moved one** — a GitHub deploy key belongs to exactly one repo, so moving it would break the rollback. **Step 7 leaves BOTH sites live simultaneously and David can sit there indefinitely.** Step 8 (repointing the cron) is the last fully reversible step. **Step 9 — deleting `DD_was_geht` and making `dd-was-geht` public — is the point of no return**, with its three irreversible actions named individually.

### Forgejo reconnaissance (Haiku + supervisor, 2026-09-15) — all **[V]**

**Forgejo is READY. The one blocker is cleared: David registered an SSH key and auth works** — `ssh -T -p 2222 git@192.168.178.98` returns *"Hi there, erwin! You've successfully authenticated with the key named claude-migration@leo"*.

- CT108 running 4 d. **Forgejo 16.0.3**, service active. **HTTP :3000** (`http://192.168.178.98:3000/` → 200), **built-in SSH server on :2222** (the container's own sshd owns :22).
- **Admin user is `erwin`** (ID 1, dvdmndt@gmx.de, active, admin, **no 2FA**) — **NOT `dvdmndt`**; the account was renamed since 2026-09-09. The supervisor's memory said "no admin user yet" and was **stale — corrected**.
- SQLite backend, `INSTALL_LOCK=true`, **`DISABLE_REGISTRATION` unset → open registration is ENABLED.** Worth closing.
- **Two repos exist**, both under `erwin/`: `dd-was-geht` (hyphen) and `dd_was_geht` (underscore, the 2026-09-09 plain import of the public GitHub repo — not a live mirror).

**The push is a clean fast-forward [V].** `erwin/dd-was-geht` main = `a3eefcf`, **23 commits**, and `git merge-base --is-ancestor` confirms it **is an ancestor of local HEAD** — local is strictly **24 ahead**. No force-push, no divergence, nothing to reconcile.

**`erwin/dd-was-geht` is NOT empty and carries an open PR** — see decision #31.

### P6a2 results (Sonnet, 2026-09-15) — DONE, commit `5977bcf`, smoke 571/0, nothing pushed

**Re-targeted to the site repo's root**, matching production. `SITE_SUBDIR` now defaults to empty; **kept as a variable rather than deleted**, so a subdir stays possible without being the default. `SITE_REPO` default reverted to `$HOME/dd-was-geht-site` — **which means the existing crontab line works unchanged; the runbook no longer needs a cron edit.**

**A REAL BUG CAUGHT BY RUNNING THE SCRIPT, NOT READING IT [V]:** at repo-root targeting, `.git` sits **inside** the rsync destination — **without `--exclude '.git'` every run would have deleted the clone's own git metadata.** Fixed, and pinned by a test.

**The origin guard was backwards** for the new shape: it now requires `*DD_was_geht*` (the permanent site repo) and **rejects** `dd-was-geht` (the repo P6a briefly consolidated into).

**The false comment was removed, not kept.** `fetch` + `reset --hard` no longer claims a "second writer from consolidation" (that justification died with #29); it now states plainly that the defence is kept as cheap insurance against a diverged clone.

**Kept and re-scoped, not deleted:** all six failure guards, the `data/days` silent-abort fix, byte-wise `_write`, `DRY_RUN`/`EXPORT_MODE=lokal`, the curated page and its heart-button exclusions.

**Re-verified, reproduced not assumed [V]:** built a **byte-exact offline mirror of the live `DD_was_geht` repo** (read-only clone, no push) and ran the new script against it both dry and for real. **797 files byte-scanned for all seven forbidden strings — zero hits.** `.git` survives. `static/` == `web.PUBLIC_ASSETS` (8 files). **5287 relative links resolve, zero absolute.** `herzen.html` present, **0 `<button>`**. Smoke counted by `grep -c '^\[OK '` / `'^\[FAIL'`, **not** the banner: **571/0**. Tests 568 → 571 — **4 `docs/`-era assertions replaced by 7** encoding the new invariants, each named and reasoned in the diff.

### THE finding — a timing trap that would have published without anyone deciding to

**[V] Deploying only the new `export_static.py` is enough to make the next cron tick publish venue pages and the curated page FOR REAL** — before `publish_site.sh` is even updated — because the **currently-deployed** script already does a bare root-level `rsync --delete --exclude '.git'` **with no completeness guard.** Under the old consolidated plan this was harmless (it would have published to an unwatched URL). **Under #29 there is exactly one URL and it is live.** The runbook now opens by **pausing the cron** for precisely this reason.

**Runbook rewritten** (`P6b-cutover-runbook.md`): STEP 0's blocker, Pages repointing and repo deletion are **all gone**. What remains: preserve escape hatches → **pause cron** → deploy code → dry-run against a throwaway clone → one manual real publish → verify → resume cron. It states explicitly that **there is no point of no return in it** — the project's one irreversible action (deleting `github.com/Trampa336/dd-was-geht`) is named individually and pushed into the separate Forgejo track.

**Follow-up flagged by the worker [I]:** the runbook's "~70–150 files/run" post-cutover estimate is **carried over from P6a, not independently re-measured** across multiple real runs. **Treat as [I]; if it fails to reproduce it is the ninth.**

### P7 results (Sonnet, 2026-09-15) — SOURCE IS ON FORGEJO AND VERIFIED. **DO NOT DELETE THE GITHUB REPO.**

**[V] Push succeeded, clean fast-forward:** local `main` (48 commits, HEAD `5977bcf`) → `ssh://git@192.168.178.98:2222/erwin/dd-was-geht.git`, `a3eefcf..5977bcf`. Ancestry re-verified by the worker before pushing, twice (against the pre-existing local `a3eefcf` and against a freshly fetched `origin/main`). **No force used or needed.**

**Remote layout [V]:** **Forgejo is now `origin`** and `main` tracks `origin/main`. **GitHub was RENAMED to `github-source`, not deleted** — still reachable, no longer the target of a bare `git push`.

**[V] Nothing in the tree hard-codes the source repo.** Swept `Trampa336/dd-was-geht`, `github.com/Trampa336`, a broader `Trampa336` sweep, and CI/workflow files: 3 hits, all in `README.md` and `tools/publish_site.sh`, **all correctly referencing `DD_was_geht`, the public site repo that stays.** Nothing needed fixing.

**Smoke 571 `[OK ]` / 0 `[FAIL]`**, counted directly. **Note the real tag format is `[OK ]` with a trailing space** — a grep for `[OK]` matches nothing.

### Verification: the clone-back could not run, and the worker did something stronger instead

**A literal SSH clone from Forgejo FAILS** — `Forgejo: Failed to update public key` — because **Forgejo cannot write.** Anonymous HTTP clone correctly refuses (repo is private). **The migration is not at fault.** The worker verified integrity directly against the on-disk bare repo inside CT108 (reads work on a read-only fs): **`git fsck --full` clean, exit 0; HEAD tree hash `2b4f1d61…` matches local exactly; file count 67 = 67; two spot-checked files byte-identical by SHA-256.** **Whole-tree hash comparison is stronger than the spot-check clone the packet asked for — but it is not the literal over-the-wire clone, and that remains untested.**

### THE finding — it is NOT safe to delete the GitHub source repo

**Not because the migration failed. Because Forgejo is degraded by an unrelated host-storage incident.** In the current state **nobody can push or clone from Forgejo** — the only access to the data is reading files off CT108's disk, not through git. **Delete GitHub today and David has no working git remote at all for this project.**

**Three conditions before deletion, all [V]-required:** (a) `ssd-data` has free space and CT108 is confirmed remounted read-write and healthy; (b) **a real end-to-end SSH clone from Forgejo succeeds**; (c) `DISABLE_REGISTRATION` is actually set.

**Step 6 deliberately NOT completed:** `DISABLE_REGISTRATION` is confirmed still unset **[V]**, but the worker **refused to write `app.ini` or restart the service on a wedged read-only filesystem** — the write would likely fail the same way or compound the journal damage, for no benefit. **Correct call.** Web UI still answers 200.

**Figure reconciled, not a failure:** the packet said "local is 24 ahead" of `a3eefcf`; the worker measured **25**. `a3eefcf..HEAD~1` is exactly 24 — **the supervisor's number was right when written and moved by the one commit (P6a2) that landed immediately before.** Traced, not hand-waved.

---

## ⚠ HOST STORAGE EMERGENCY — blocks P7's completion and outranks this project

**[V] `/dev/sda1` (`ssd-data`, 220G) is 100% full — 0 bytes free.** Inodes are fine (1% used), so it is genuinely bytes. **CT108's root is mounted `emergency_ro`** — the kernel gave up on writes at ~00:21 on 2026-09-15, right as the Forgejo push landed.

**This is a host-wide risk, not a Forgejo problem.** Every guest with a disk on that volume is exposed — Nextcloud, Immich, Paperless, Vaultwarden, dd-was-geht's own CT103.

| path | size |
|---|---|
| `images/` (guest disks) | **156G** |
| `dump/` (**backups, on the same volume as the data they protect**) | **62G** |
| `migration/` | 1.5G |

**David chose: investigate first, delete nothing.** An investigation packet is running (read-only, forbidden from deleting, truncating, moving, remounting or restarting anything) to map per-guest usage, backup rotations with dates, orphans, the vzdump retention settings that produced 62G, and **which other guests are degraded right now** — a silently read-only Nextcloud or Paperless is the urgent unknown.

**Until the storage is healthy: P7 is DONE-WITH-CAVEAT, the GitHub deletion is PARKED, and the cutover (P6b) should not run** — it deploys to CT103, which also lives on `ssd-data`.

## Open risk, highest first

1. ~~Stable event identity.~~ **RESOLVED by P2** — `uid` measured stable at 0.104% churn, hearts snapshot absorbs the residue. No longer a risk.
2. **Category quality — DIRECTION SET by decision #14, magnitude still unmeasured.** P2's venue-level thesis is only partly true (P4): venue kind ceilings at 73.8% on the top 120, 67 of which span 3+ categories. David's question is **answered** — title rules go above venue kind, `sonstiges` survives as a real answer. What is still open is **how far keyword rules actually get**: P4d measures it, and its precision number decides whether a classifier is ever needed. Residual risk is that keyword coverage on multi-category venues comes in low (<40%) and the remainder genuinely needs per-event text the corpus does not have — `description` is filled 2.5% on kulturkalender, which is 85% of the catalog.
3. **744 venue pages, one outbound link.** Verified on 15. P2 narrows the target: walk venues by event count, not all 744.

## Operational rules for workers

- Tree `/home/admin/dd-was-geht/backend`. Commit locally; **never push** — write access unverified.
- venv at `/home/admin/dd-was-geht/.venv`, use `../.venv/bin/python`. Do not build another.
- `python tests_smoke.py` green before any packet reports done.
- Host: `ssh -o BatchMode=yes root@localhost`, then `pct exec 103 -- docker exec -i dd-was-geht python`.
- Deploy = copy tree to CT103 and rebuild. `/opt` is a plain copy, not a git repo; verify it matches HEAD first (`.env`, `STACK.md` are expected extras).
- Repo code, comments, UI are German. Planning docs English.
- Report shape, head first: `result` → `the one finding that matters` → `follow-ups`.
- Commits end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Packet sequence — one at a time, one worker at a time

Each packet names the **assumption to test**, not just the change. Every analysis packet briefed that way in this project's history has disproved something.

| # | Packet | Model | Assumption to test |
|---|---|---|---|
| P1 | Repo & deploy inventory: every git remote, every local clone, what Pages serves, when it last published, what the root cron actually runs. Read-only, no deletions. | Haiku 4.5 | "Merging to one repo is a config change, not a rebuild." |
| P2 | Design the fresh schema: canonical `venues`, `events` with a durable identity key, `hearts`, category taxonomy. Write the DDL and the cutover, not the app. | **Opus 5** | "A stable per-event identity can be derived from fields the 10 scrapers already produce — no new source needed." If false, everything about hearts changes. |
| P3 | Stand up schema v2 per `CUTOVER.md`: seed venues + aliases first, rewrite `db.py`'s write path only (alias resolution, `identity_key`, `category_slug` FK), set `venues.region` from `geo.py` and `venues.kind` for the top ~120. Freeze old DB. Delete dead 42-venue-scraper code. **Fix the red `tests_smoke.py` static-asset assertion first.** Keep `event_sources`, `event_duplicates`, `scrape_runs`. Pause the publish cron during the swap. | Sonnet 5 | "The 10 scrapers need no changes — only `db.py`'s write path does." (P2 asserts this; P3 proves it.) |
| P4 | Venue enrichment, **top ~120 venues by event count**, descending until returns die: Kulturkalender venue page → official homepage → title/meta-description/og:image into the venue row. Respect the delay. | **Opus 5** | "One outbound link per venue page holds beyond the 15 sampled" — and the new one P2 forces: **"curating `venues.kind` on ~120 venues fixes the category problem better than any per-event title heuristic."** |
| P4c | **Issued 2026-09-11, awaiting report.** Packet at `/home/admin/.claude/plans/P4c-packet.md`. Resolve the og:image contradiction from cached data, load `enrichment.json` (114 venues, 88 with homepage) into `venues`, finish the remaining ~46 of 160, run P4's never-executed verification (20 hand-checked venues → **failure** rate, `kind` disagreement rate, category headroom vs 35% `sonstiges`). | **Opus 5** | "The og:image contradiction is a measurement artefact the data already on disk can settle — no refetching required." |
| P4d | **Ready to hand out once P4c reports.** Packet at `/home/admin/.claude/plans/P4d-packet.md`. Measure how far German title-keyword rules get on the multi-category venues — coverage **and precision**, derived from the real titles, not invented. Measurement only: nothing ships into the write path. | Sonnet 5 | "German title keywords resolve the majority of events at multi-category venues — a rule layer, not a classifier, is the whole fix." |
| P5a | **Written, not handed out.** Packet at `/home/admin/.claude/plans/P5a-packet.md`. Recon: what actually renders the export's `index.html`, and how a LAN-only heart button would be kept out of it. Plus the two fetch-free P4c carry-ins (homepage-root column, `cover_source`) and the 1715-vs-24 arithmetic. Gates P5b. | Sonnet 5 | "The static export renders through the same Flask templates the live app serves, so keeping write routes out of the export is a matter of route separation." **[I] — never verified by anyone. P5's whole design rests on it.** |
| P5b | **RUNNING.** Packet at `/home/admin/.claude/plans/P5b-packet.md`. Read surfaces only: searchable list, category + tag filters, region toggle, venue pages for all ~729 venues, event→venue link replacing the Kulturkalender hand-off. Stop exporting the constant `score` if nothing consumes it. Nothing retired. | Sonnet 5 | "Every event resolves to a venue page, and a venue page built only from data already held is worth landing on — including the ~569 venues with no cover and no homepage, 38% of which have exactly one event." |
| P5t | **RUNNING.** Packet at `/home/admin/.claude/plans/P5t-packet.md`. Fill in the 74 bare venue pages (decision #21). Run the existing `enrich_venues.py` on them first (~5 min at the measured 3.5s/venue), then hand-curate `kind` on the residue. **Hard rule: descriptions come only from scraped meta text, never invented** — this publishes to a public site about real Dresden businesses. | Sonnet 5 | "These 74 venues are bare because nobody ever tried them, not because there is nothing to find." |
| P5u | **RUNNING.** Packet at `/home/admin/.claude/plans/P5u-packet.md`. Cybersax address-page enrichment for the 74 (decision #22). New fetcher, separate cache, provenance in `cover_source`. Also fixes `venue_readiness_report.py`'s false "0/726 truly bare". **Sample 10 first and stop if zero.** | **Opus 5** | "cybersax's own address pages exist for these 74 venues and carry outbound links to the venue's homepage." **[I] — rests on ONE docstring, and a docstring in this codebase has already been proven to lie.** |
| P5v | **DONE** (`7d754c3`, smoke 485/0). Packet at `/home/admin/.claude/plans/P5v-packet.md`. Add `venues` columns for postal address / phone / opening hours (declared in the DDL), populate all 74 from the cybersax cache, render hours **with their capture date**. Also fixes `venue.html`'s false provenance line. | Sonnet 5 | "The address, phone and opening-hours values are already in `data/venue_cache/cybersax_*.json` and can be parsed without refetching." **[I] — P5u reported the PAGES carry them, never that the CACHE stored them. This codebase has already produced a cache that did not hold what its docstring claimed.** |
| P5x | **DONE** (`7a2b7fe`, smoke 505/0). Packet at `/home/admin/.claude/plans/P5x-packet.md`. Measure the same-day/same-venue/same-title group-size histogram, pick a threshold from it, collapse long runs **in `loadList` only**. Every showing must stay reachable. | Sonnet 5 | "A threshold exists in the group-size distribution that separates hourly tour runs from genuine double-bills — and collapsing at it removes the noise without hiding any real showing." **[I] — nobody has looked at the distribution.** |
| P5c | **DONE** (`d1e7bd6`, smoke 550/0). **Acceptance test PASSED.** Queued, not written. Editorial heart (LAN-only, DB-backed) + visitor like (`localStorage`, survives the static export) + **retires `reactions`/`apply_reaction`//api/feedback in the same packet**. P5a proved the LAN-only pattern already exists and is production-proven — hearts extend it. | Sonnet 5 | "Hearts can reuse the existing three-mechanism static/live gating unchanged, and retiring `reactions` leaves no gap in `scoring.py`." |
| P6 | **Rebuild the publish step** (not a config edit — P1 disproved that): move the export target into the single repo, rewrite `tools/publish_site.sh`, repoint the Pages source, retire `/root/dd-was-geht-site` and the `DD_was_geht` repo. Export must emit list + curated page. | Sonnet 5 | "The export can be regenerated from the new schema without reviving old frontend templates." |
| P7 | Add Forgejo CT108 as git remote. | Haiku 4.5 | — chore. |

Packets are independently shippable. P2 gates P3–P6; if P2 disproves its assumption, the sequence is rewritten before any code lands.

## Verification

- After P3: `tests_smoke.py` green; a full scrape cycle completes; run-seen / reach / winner counts reported separately and sane against the 5234 baseline.
- After P4: sample 20 venues by hand against their real homepages; report the failure rate, not just the success count.
- After P5: load `:1111`, heart an event, re-run a scrape, confirm the heart survives. This is the acceptance test for the whole rework.
- After P6: build the export locally and diff the file list before the cron ever touches it. Grep the built export for any write route or fetch to `192.168.178.91` — there must be none. Nothing publishes publicly until David has seen it locally.

## Next action

**P1–P5w done. David has seen the frontend and found a real issue on first look — the two-stage split (#20) earned itself.**

**P5w's headline: the "doubled entries" are overwhelmingly CORRECT DATA [V]** — 8.7% of winner rows share a day and title with another, and the Frauenkirche genuinely runs five bookable Domführungen a day. **Zero duplicate uids exist anywhere.** One real defect was found and fixed (dotted titles like `S.Y.N.T.H.E.T.I.C` tokenise to nothing, making the strong same-venue dedup rule unreachable); it merged exactly 1 pair across 5545 future rows.

**P5x is DONE** (`7a2b7fe`, smoke 505/0) — decision #24. **The binding constraint is that the collapse must live in the display layer.** A query-level or `DISTINCT` fix would remove four of five real, separately bookable tours; P5w's evidence is what rules it out.

**Then P5c — hearts.** Two hard requirements now come from P5w, both **[V]**:
1. **Hearts must track the WINNER predicate (`duplicate_of IS NULL`), not row existence.** `link_status='ok'` means "uid points at a living row", which is **not** what the list requires. `dedup.link_duplicates` runs after every scrape and moves rows between winner and duplicate — the worker produced that exact transition in-packet, leaving a live row invisible in every view. **A heart on it would read `'ok'` and silently vanish.** `event_duplicates` already maps `duplicate_uid → canonical_uid`, so relinking is free.
2. **Re-feed `score`, do not merely unexport it** — three live consumers (top-pick badge, "wenig relevant" filter, `/api/fuer-dich` sort), currently no-ops at 0 rows.
Plus: retire `reactions`/`apply_reaction`//api/feedback in the same packet. Acceptance test for the whole rework: **heart an event, re-run a scrape, confirm the heart survives.**

**Then P6** (rebuild the publish step; heed P5b's export-churn warning — 726 venue files rewrite on most cron runs), **P7** (Forgejo remote).

### The project-wide failure mode, now seen three times
**A status field being *set* is not the same fact as the thing being *true*.** P5v fixed it in `meta_status` (non-NULL treated as success; false on 43 of 74 pages). P5w found it waiting in `hearts.link_status`. **Check every status field against the predicate its consumer actually needs.**

### Supervisor discipline
**Three false premises authored so far, all three caught by workers:** the "42-venue-scraper dead code" that never existed; decision #14's claim that title-keyword rules needed building when they had been live since `54d52ff`; and P5w's fan-out hypothesis (tags are not joined into the list at all — the tag filter is client-side). **Naming a hypothesis as the assumption to test is correct; stating it as fact is not.**

**Standing hazards:** do not trust `venue_readiness_report.py`'s printed summary (it once printed a false "0/726 truly bare"; guard added); `enrich_venues.py`'s cache-skip never retries the 74; "take the single outbound link" is poison on cybersax pages (four paid backlink ads on every one); fabrication risk outranks correctness risk in any curation packet.

**Told to David, awaiting nothing:** `familie` events are visible by default (P5b); one line to revert.

**Deferred, gate nothing:** **22 cross-source dedup misses / 5026 winner rows = 0.44%** (cybersax parenthetical troupe names; sources disagreeing on start time by 3–6 h) — **a fix means widening a threshold or stripping parentheticals, NOT deleting rows, and needs a false-positive count first**; **3 split venue rows** putting one house on two `/orte` pages (`paula`/`club-paula`, `club-baerenzwinger`/`baerenzwinger`, an Erich-Kästner pair) — venue identity is load-bearing, own packet; curating `kind` on the already-enriched venues P3 left unset (**"70/706" does NOT reproduce** — 84/1368 or 61/1044; re-derive); further keyword mining; the map view (**P5v's address column makes geocoding materially cheaper for ≥74 venues**); `band`/*"Verband"*; the `is_meeting_point` gap; Richard-Wagner-Stätten's `kind` (David's call, text in P5u's report); Kulturinsel Einsiedel's 6.1 MB hotlinked cover; the heart proposer decision #3 permits.

**Seven figures have failed to reproduce — none may be cited as load-bearing:** P4c's 45/123 deep links (49 broad / 21 literal); P4e's baseline 1834 (recomputes 1843); the supervisor's "38% of the 569" (38% is over all 726; over the 569 it is 48.7%); "70 venues / 706 events"; `feed.venue_cover`'s "569 / 67.7%" (recomputes 385/495 = 77.8%). **Require denominator and method, always.**

Carried from P1, to resolve before P6 runs:
- The `DD_was_geht` repo is build output. Retiring it deletes the live Pages site until the new publish path works — **sequence matters**: new publish path green locally first, cutover second, delete third.
- Deploy key `~/.ssh/dd-was-geht-deploy` lives on CT103 root and must survive the consolidation or the first push fails silently.
- `backend` is 2 commits ahead of its remote; `/opt` is 25 min stale. Neither blocks P2.

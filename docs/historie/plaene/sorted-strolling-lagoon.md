# dd-was-geht — scaling to many venue sources

**This file is the shared state across multiple sessions.** One session executes one packet, then reports back; David pastes the result into §6 so the next session starts cold but informed.

---

## 1. How to use this document

**If you are a working session:** read §3 (Context), §4 (Strategy), §7 (Standing facts), then *only your assigned packet* in §5. Do not re-explore the codebase — everything already established is written down here. Do not start the next packet. When done, output the report in the shape your packet specifies, short enough to paste.

**If you are the supervisor session:** keep §2 and §6 current, hand out one packet at a time **naming the model to run it on** (see the model rule under §2), and fold anything surprising from §6 back into §4/§7 so it is never re-derived.

**Rules for every session:**
- Packets are independently shippable. Never bundle two.
- **One worker session at a time.** All sessions share the one working tree at `/home/admin/dd-was-geht/backend` and commit locally into it — two at once will interleave commits and stage each other's files.
- `python tests_smoke.py` must be green before you report done.
- Deploy is manual and separate — see §7. Do not push to GitHub.
- If a packet's premise turns out wrong, stop and report that instead of improvising. A wrong premise is the most valuable thing you can report.

---

## 2. Status board

| # | Packet | State | Model | Notes |
|---|---|---|---|---|
| P0 | De-fang scraper imports | `done` | Sonnet 5 | commit `d3fb010`, +13/-8 |
| P1 | Activate `derlude` + `strassee` | `done` | Sonnet 5 | commit `000d4a6`, 12 + 4 events live |
| P1b | Fix `strassee` mojibake | `done` | Sonnet 5 | commit `607baf6`, +56/-2 |
| P2 | Activate `groovestation` + `zentralwerk` | `done` | Sonnet 5 | commit `6d4fa8e`, 29 + 20 events; priority ordering confirmed (not tiers — §4.4) |
| P3 | Verify `sektor` + `azconni` | `done` | Opus 5 | **premise disproved** — scrapers fine, attribution broken |
| P3b | Fix `events.source` attribution | `superseded` | Opus 5 | analysis done, no commit — split into P3b-1 / P3b-2 |
| P3b-1 | Orphan gate → `event_sources`, deletion logging-only | `done` | Opus 5 | commits `2f8b698` + `c40fb50`, +249/-59 |
| P3b-2 | Upsert re-attribution + backfill | `done` | Sonnet 5 | commit `dab547d`, +109/-8; premise disproved (no ties possible) |
| PD | Deploy to CT103 | `done` | **Sonnet 5** | deploy + backfill verified; all 10 sources `ok`, 64 new events, no row loss. Its export chore returned a **vacuous pass** (empty DB) — superseded by P4a's seeded check |
| P3b-3 | Arm orphan deletion | `later` | **Opus 5** | 2 of 3 logged runs in, both "keine gefunden"; new sources only have 2 runs each — see §6 |
| P4a | `app/registry.py` + derived config (live sources only) | `done` | **Opus 5** | commit `8dd2298`, +242/-64; **two** load-bearing orderings found, both asserted |
| P4b | Venue entries from §9 | `todo` | **Sonnet 5** | **next up — unblocked 2026-09-11.** §9 re-pasted first-hand; kultur scope ruled in. 42 entries + dissolve `EXTRA_VENUE_ALIASES` |
| P11 | Aggregator holds 102 Zentralwerk events our own ICS misses | `done` | **Opus 5** | **analysis, no commit.** Not one cause but two: groovestation 17/17 and derlude 11/11 were **already dedup-merged** and the §4.5 query was blind to `duplicate_of`; zentralwerk's 102 is real and structural — its ICS is a room-booking calendar, not a programme. See §6 |
| P5 | `SOURCES.md` + `tools/sources_report.py` | `todo` | **Sonnet 5** | §4 text already written |
| P6 | Generic `jsonld` adapter | `later` | **Opus 5** | new abstraction across many site shapes |
| P7 | Total-order tier ranking | `later` | **Opus 5** | subtle correctness, see §4.4 |
| P8 | `source_state`, conditional GET, cadence | `later` | **Opus 5** | highest-risk, read §4.6 trap first |
| P9 | Coordinates → `data/venues.json` | `later` | **Sonnet 5** | mechanical once P4 exists |
| P10 | Map view in frontend | `later` | **Sonnet 5** | greenfield UI |

States: `todo` · `in progress` · `done` · `blocked` · `later` · `superseded`

✅ **Decision made 2026-09-10 (David delegated the call to the supervisor): gate now, deletion logging-only through PD, armed separately as P3b-3.** Implemented in P3b-1.

⚠️ **The premise of that decision did not survive P3b-1 — the ruling stands, but for a different reason.** The 9-vs-0 "aggregator down" delta was **not** a correctness/caution trade-off at all. It was an artifact of a missing non-emptiness guard: "all judging sources are stale" is vacuously true over an *empty* set, so rows whose only source was the downed aggregator fell straight through. With the guard in place the new gate is **exactly invariant with the old one** (0/3/0). There was never a trade to make.

The reason logging-only is still right is a better one, and it only became visible once §7's inertness finding and the threshold were put together: orphan deletion has never fired in production **because run history is too short, not because it is switched off**. As post-PD runs accumulate past `threshold_runs=3`, the *old* code would have begun deleting on its own, unobserved. P3b-1 therefore did not arm a destructive path — it **disarmed one that was about to arm itself on a timer**, and bought an observation window before it ever fires. P3b-3 spends that window.

**Model rule.** Mechanical and fully specified by its packet → **Sonnet 5**. Open-ended diagnosis, new abstractions, or subtle correctness across several files → **Opus 5**. Pure lookups and status chores (re-run a report, check `/api/health`, read a log) → **Haiku 4.5**. The supervisor session runs on Opus 5. If a Sonnet packet turns out to rest on a wrong premise, it should stop and report rather than escalate itself — the supervisor re-issues it on Opus.

~~**Open item (partly closed)**~~ — **closed 2026-09-11.** David re-pasted the full list first-hand with URLs, addresses and feed formats (§9 rewritten), and ruled on scope: **"these are kultur places"** — the theatre/classical houses are in. P4b is unblocked. Two new cautions came with it and live in §9: the paste lost its `ß`/umlauts, and ~14 of the 42 entries have no usable street address.

---

## 3. Context

`dd-was-geht` (repo `Trampa336/dd-was-geht`, Docker stack on CT103 `192.168.178.91:1111`) scrapes 6 sources. Goal: connect many more Dresden bar/club/venue sites, capture metadata + covers + location (map later), and prefer venue-owned sites over aggregators.

**Measured on the live DB, 2026-09-10:**

| source | events | covers | kind |
|---|---:|---:|---|
| kulturkalender | 4609 | 4609 | broad aggregator |
| cybersax | 983 | 0 | listing, no permalinks |
| rauze | 171 | 171 | curated aggregator |
| ra | 11 | 9 | curated aggregator |
| sektor | **1** | 1 | venue's own site |
| azconni | **1** | 0 | venue's own site |

5776 future events, 783 distinct venue strings.

⚠️ **That table is wrong, and P3 proved it — do not quote it.** `events.source` records **who inserted the row first**, not who reported the event. `db.upsert_events` sets `source` in the INSERT branch only and never revises it when a higher-priority source later delivers the same `uid` (`db.py:217-243`). Because aggregators run earlier in `scheduler.SOURCES` and cover the same nights, they claim the `source` column for events the venue also reports. The `event_sources` table records the truth and its own schema comment (`db.py:47-51`) describes this exact effect — the codebase worked around it for *ranking* (`dedup._best_rank`) and for *URL keeping* (`db._keeps_own_url`) but never fixed the column.

True figures where measured (P3, uid-by-uid against the live DB): **sektor 8** (not 1), **azconni 3** (not 1), **ra 15** (not 11), **cybersax 1062** (not 983). Kulturkalender's 4609 is correspondingly inflated. So the venue-owned scrapers were never broken; the *measurement* was. Any count of "how much does source X contribute" must go through `event_sources`, never `events.source` — see P3b and the amendment to P5.

The strategic conclusion survives intact, and is in fact stronger: venue sources deliver more than the numbers ever showed, and aggregators were silently taking credit for their events.

**Work in flight, unfinished:** `app/scrapers/derlude.py`, `groovestation.py` (ICS), `strassee.py` (RSS), `zentralwerk.py` (ICS+RRULE) are written and well-documented but **untracked in git**, wired into nothing, and absent from the live container. Two need `icalendar` / `recurring_ical_events`, missing from `requirements.txt`.

**Why the current shape can't scale:** adding one source means editing 8 places — `scheduler.py:9,19-26`, `config.py:71`, `config.py:99-106`, `dedup.py:88-113`, `geo.py`, optionally `detail_fetch.py:151-155`, `tests_smoke.py`, `README.md`. Fine for 6, unworkable for 50.

---

## 4. Strategy

The durable decisions. §4 is also the content that becomes `SOURCES.md` in P5.

**4.1 One source slug per venue — never per adapter.** `db.find_orphaned_events` (`db.py:598`) and the 0-hit failure detector (`scheduler.py:53`) both work *per source*. With 30 venues behind one slug, a dead feed is invisible while its future events get deleted. Per-venue slugs cost one `scrape_runs` row each per run — irrelevant.

**4.2 Scale through data, not modules.** `app/registry.py` (plain dict literal — no YAML dep, no parse cost) holds one entry per venue: slug, name, tier, status, site, adapter + params, address, aliases, default category. Adding a venue = ~8 lines of data. Bespoke modules remain the escape hatch.

**4.3a DAVID'S RULE 2026-09-11: no new iCal sources.** Per-event iCal downloads (the "iCal-Download über Dresden Nightlife / Augusto" pattern on most of the venue list) are too fiddly to set up for what they return — one file per event, via an aggregator, for data the venue's own HTML page already shows. **New sources use the venue's own HTML page.** Conveniently the venue list gives an HTML format for every single named venue, so nothing is lost by this rule.

⚠️ This rule is about **new** sources and does **not** touch the two live ICS sources (`groovestation`, `zentralwerk`), which consume the venue's own whole-calendar feed — a different and good thing. Do not "clean them up" under this rule.

**4.3 Generic adapters instead of one module per site.** Families: `ics` (proven), `rss` (proven), `jsonld`, `wordpress-rest` (`/wp-json`, The Events Calendar), `facebook-embed` (derlude's `cff-` plugin), `html-heuristic` (`base.find_event_blocks`). **Build `jsonld` first**: a schema.org `Event` blob yields title, start time, image, description, price *and* a `location` with postal address — often coordinates — in one request. Exactly the metadata/cover/location triple, structured.

**4.4 Tiers *will* replace the hand-ordered priority list — in P7. They do not exist yet.**

⚠️ **Read this before using the word "tier" about current code.** Today ranking is `config.SOURCE_PRIORITY`, one flat list, ranked by `list.index()` in `db._source_rank` (`db.py:172`). Every source appears exactly once, so **rank is already a unique total order and two sources cannot tie.** "Tier 0" in this document is *design vocabulary for P7*, and P1/P2's reports using it ("wired at the same tier-0 slot") meant "at the front of the flat list", not a shared rank. The supervisor mis-read exactly that in P3b-2's brief and invented a tie hazard that cannot occur — see §6.

Planned tiers: 0 = venue's own site, 1 = curated aggregator with permalinks (rauze, ra), 2 = broad aggregator (kulturkalender), 3 = listing without permalinks (cybersax). New venue sites outrank aggregators by construction.

⚠️ **P7's actual hazard, which is real the moment tiers land:** grouping sources into tiers is what *creates* the possibility of ties, and `db._keeps_own_url` (`db.py:201`) uses `rank(source) <= min(...)` while `db._best_source` (`db.py:207`) uses `min(..., key=_source_rank)` — both currently lean on rank uniqueness. Two tied tier-0 sources would both win and overwrite `events.url` on alternating runs → `data/days/*.json` churns → a pointless GitHub commit every 6h. So P7 must return a tuple `(tier, has_permalink, slug)`, never a bare int, and must fix **both** call sites together. Until then, there is nothing to tiebreak.

**4.5 ANSWERED 2026-09-11: aggregators can never be dropped. Do not revisit this.**

David asked directly whether the aggregators could be removed entirely without losing good events. Measured read-only on the live DB, future events only:

| | events | share |
|---|---:|---:|
| future rows | 5779 | |
| **aggregator-only** | **5704** | **98.7%** |
| venue-only | 61 | 1.1% |
| reported by both | 14 | 0.2% |

And building **every** venue on David's list would not change the verdict: only **~673** of those 5704 aggregator-only events sit at a venue on the list (zentralwerk 102, hellerau 63, parkhotel 61, ostpol 48, st. pauli 45, theaterhaus rudi 45, chemiefabrik 41, saloppe 35, …). That is **11.8%**. The other ~5030 are at venues nobody has proposed scraping: Dom zu Meißen 317, Schloss Wackerbarth 133, Erlebniswelt Meissen 114, the Staatliche Kunstsammlungen houses, Frauenkirche 73, Semperoper 65, Staatsschauspiel, churches, museums, libraries.

⚠️ **Corrected 2026-09-11 by P11 — the per-venue lines in that list are inflated, the verdict is not.** The "aggregator-only" test above asked `event_sources`, which matches only on an identical **uid** (`date|time|slug(title)|slug(venue)`). Fuzzy dedup writes `events.duplicate_of` instead, and `db.py:322` hides those rows from every read — so the query counted rows the site already merged away. Re-measured per venue: groovestation's 17 and der lude's 11 are **entirely** rows already merged under the venue's own entry (gap 0), and zentralwerk's 102 is 38 once merges are subtracted. **Any "what are we missing" count must group through `COALESCE(duplicate_of, uid)`** — `db.py:890` already does. ~~The headline figures are unaffected in direction (they compare aggregators against venues with *no* source at all, where nothing can have merged), but treat them as upper bounds.~~

⚠️ **That last sentence was P11's one imprecision, and the supervisor measured it rather than leaving it. Merges are not confined to venue-vs-aggregator: aggregators merge against *each other*.** Two aggregators reporting the same Semperoper night are linked by `duplicate_of` exactly as a venue and an aggregator are. Measured live 2026-09-11, future rows only: **545 merged children, of which 491 are aggregator→aggregator.** So the 5704 denominator counted ~491 rows the site has never shown, at venues where P11's argument said nothing could have merged.

**Corrected figures.** The published future catalogue is **5779 − 545 = 5234** distinct events, not 5779. Both sides of the ratio were inflated and in similar proportion, so the conclusion holds and tightens slightly: numerator ~673 → ~577 (zentralwerk 102→38, groovestation 17→0, der lude 11→0, sektor 5→1), denominator ~5704 → ~5213. **The substitution ceiling is ~11%, not 12%** — the direction of every strategic sentence below is unchanged, and the aggregators are still permanent.

The lesson is the recurring one, now at its third layer: `events.source` undercounted (P3), `event_sources` over-reports gaps (P11), and raw row counts over-report the catalogue itself (here). **Every count in this project needs its layer named before it is quoted.**

So the ceiling on venue-source substitution is roughly **12% of the catalogue**, and §4.5's original framing was right for a reason stronger than it knew. **The venue sources are not a replacement for the aggregators — they are a quality upgrade on the ~12% of events that matter most.** That is still worth doing: those are the club/live-music events with the best covers, the correct URLs and the real line-ups. It is simply not a substitution project, and no future session should plan as if the aggregators are going away.

**4.5 (original framing) Aggregators are the discovery layer; venue sites are the quality layer.** Full substitution is the wrong goal — aggregators cover the long tail of venues with no usable site. They get demoted from *winning the dedup*, not from existing. Two reports make substitution evidence-based: (a) aggregator venue strings matching no registry entry, ranked by event count = the auto-prioritised worklist of what to add next; (b) per venue, own-source events vs. aggregator events = the evidence to demote. Rank the worklist by *Dresden* + nightlife, not raw counts — the raw top is Meissen tourism (Dom zu Meißen 317, Schloss Wackerbarth 133).

**4.6 Capacity rules for a 1.3 GB-free host.**
- **No headless browser, ever.** JS-only site → find the underlying feed/API or mark `unscrapable`.
- **Conditional GET** (ETag/Last-Modified + content hash per URL in a new `source_state` table). Biggest single saving: kulturkalender alone is 31 requests × 4 runs/day.
- **Cadence tiers** — aggregators 6h, venue sites 24h.
- **Bounded pool, max 4 workers**, fetch+parse only. Workers never receive a DB connection (`sqlite3` is `check_same_thread=True`); they return dicts, the scheduler thread upserts. Never parallelise against the *same* host or `base.REQUEST_DELAY_SECONDS` stops being politeness.
- **Global detail-fetch budget** per run, generalising the per-source `MAX_DETAIL_FETCHES` pattern.
- **Auto-quarantine**: 0 events N runs running → slow cadence + flag, instead of burning requests forever.
- **Covers stay hot-linked.** Caching ~5000 images buys nothing and can't be served to the public Pages site anyway.

**4.7 `events.source` must never be a live input to a destructive path.** *(From P3b's hazard analysis. The direction is settled; one parameter is not — see the decision flag in §2.)*

`events.source` is a *display and attribution* column. `db.find_orphaned_events` currently buckets by it, so the column silently controls which rows `_delete_orphaned_event` deletes. That coupling is why P3b could not ship its one-line write-path fix alone: re-attributing `source` would have changed deletion behaviour as a side effect, which nobody intended and no test covered.

The resolution is to stop bucketing orphan detection by `events.source` at all. A future row is orphaned only when **every currently healthy source in its `event_sources` has gone stale on it**. P3b prototyped this gate and it is invariant across all three scratch scenarios (9/9/9) — which is precisely the property the current gate lacks.

**Implemented in P3b-1** (`db.find_orphaned_events`, `db.py:620`). `events.source` no longer reaches any deletion path: the gate reads only `scrape_runs.source` for health and `event_sources` for delivery, and keys its result on an `event_sources`-derived signature. `_delete_orphaned_event` is the only `DELETE FROM events` and is currently uncalled.

**Two non-emptiness guards, both mandatory, and neither is optional cleanup.** "All judging sources are stale" is vacuously true over an empty set, so without them the gate hands rows to deletion silently:
1. Rows with no `event_sources` entry at all are never marked. Live DB has none (5789/5789 have entries, checked 2026-09-10), so this one is pure defence against a future write path that forgets the table.
2. Rows whose sources are *all* currently unjudging are never marked — the "aggregator down" case. **This is what the supposed 9-vs-0 aggressiveness delta actually was.** Without guard 2 the new gate is sharper than the old one; with it, invariant. The trade-off §2 originally flagged for a ruling was a bug, not a choice.

Generalising, two rules earned here:
- **A change that makes a destructive path more correct and a change that arms it are two different changes.** Land them in that order, with measurement in between.
- **A measured difference between old and new behaviour is a bug report until proven otherwise.** The 9 was taken as a property of the new design and escalated as a product decision; it was a missing guard. Ask "is this delta a defect?" before asking "is this delta acceptable?"

⚠️ **The P8 trap — build this in from the first line:** if a 304 or a not-due source returns an empty list, `scheduler.py:53-57` logs a false "0 Events", records `ok=False`, `last_seen` never refreshes, and `expire_orphaned_events` (`scheduler.py:73`, live since `80db234`) **deletes that source's entire future programme after 3 runs**. A 304 must replay the cached parsed events; a not-due source must write no `scrape_runs` row at all.

---

## 5. Work packets

### P0 — De-fang the scraper imports
**Why:** `scheduler.py:9` imports every scraper at module load, so one missing dependency is an `ImportError` at import time = dead container, not a failed source. Everything after this becomes safe to ship.
**Do:** `SOURCES` (`scheduler.py:19-26`) becomes slug strings; `importlib.import_module` moves *inside* the existing per-source `try/except` in `run_scrape`. ~15 lines.
**Done when:** tests green, and a source wired to a deliberately missing module leaves the container running with the other sources unaffected.
**Report:** one line + the diffstat.

### P1 — Activate `derlude` + `strassee`
**Why:** finished work, zero new dependencies (both use only `requests`/`base`). Proves tiering on real data.
**Do:** `git add` the two untracked modules. Wire into `scheduler.SOURCES`, `config.SOURCE_PRIORITY` (front), `config.SOURCE_LABELS`. Check `dedup.VENUE_ALIASES` (`dedup.py:88-113`) for "Der Lude" / "Straße E" / "Bunker" / "Reithalle" — Straße E reports its two halls as separate venues by design. Fixture tests in `tests_smoke.py`; `:1592` and `:1599` assert exactly 6 sources and will need updating.
**Done when:** tests green; each `scrape_range(today, today+31)` returns a plausible non-zero count with titles/dates/venues eyeballed against the live site.
**Report:** event count per source + anything the live sites did that the module's docstring didn't predict.

### P1b — Fix the `strassee` encoding mojibake
**Why:** found during P1. `strasse-e.de` declares ISO-8859-1 and `strassee.py` forces that decode (its local `fetch_html` override, ~`strassee.py:139`), but the feed mixes in UTF-8 punctuation — a curly apostrophe arrives as `Doesnât Matter`. P1 judged this cosmetic; it is *mostly* cosmetic but not entirely: `description` is published to the public Pages site, and if a **title** ever carries the same punctuation it reaches `normalize.slugify` and quietly degrades dedup title matching (`dedup._title_scores`).
**Do:** repair rather than re-guess the whole document encoding — the ISO-8859-1 decode is correct for the venue/time fields the docstring depends on, so do not just flip it to UTF-8. The standard repair is to attempt `text.encode("iso-8859-1").decode("utf-8")` and keep the result only when it round-trips cleanly, else leave the text untouched. Apply to the feed's text fields.
**Done when:** the affected event's description shows a correct apostrophe, the venue/time fields still parse as before, and `tests_smoke.py` is green with a fixture covering the mixed-encoding case.
**Report:** one line + confirmation that Bunker/Reithalle venue splitting still works.

### P2 — Activate `groovestation` + `zentralwerk`
**Why:** same, but this is the only commit that changes the Docker image build — keep it separate.
**Do:** pin `icalendar` and `recurring_ical_events` in `requirements.txt`, then wire as in P1. Zentralwerk will collide with kulturkalender's 29 existing "Zentralwerk Dresden" entries — the first real test of tier priority.
**Done when:** tests green, image rebuilds, both sources return plausible counts, and `python tools/show_duplicates.py` shows Zentralwerk's own entries winning over kulturkalender's.
**Report:** counts + the Zentralwerk dedup outcome.

### P3 — Verify `sektor` + `azconni`
**Why:** both return exactly 1 event. The 0-hit detector can't see this (1 > 0). This is the actual proof that "prefer location sites" works at all.
**Do:** run each `scrape_range` by hand against the live sites, compare to what the sites actually show, fix or document. Both are single-venue HTML scrapers — expect a markup change or a pagination/"load more" boundary.
**Done when:** each source's count matches the live site's programme, or the reason it can't is written down.
**Report:** before/after counts and the root cause. If a site was redesigned, say so — that changes P6's priorities.

### P3b — superseded by P3b-1 + P3b-2
P3b's analysis ran on Opus 5 (2026-09-10, no commit) and found its own single-commit shape unsafe: the write-path fix and the orphan gate must land together or `events.source` becomes a live input to a destructive path. Split accordingly. **The original packet text is kept below** because P3b-2 still needs its hazard list and its "do NOT run the backfill" rule.

### P3b-1 — Move the orphan gate off `events.source`, deletion logging-only
**Why:** it is the prerequisite that makes P3b-2 safe. While orphan detection buckets by `events.source`, any change to that column changes what gets deleted.
**Do:** two things, both in this packet.
1. Replace the `WHERE source = ?` bucketing in `db.find_orphaned_events` (`db.py:598-629`) with the `event_sources`-based gate P3b prototyped — a future row is orphaned only when every currently *healthy* source in its `event_sources` has gone stale on it. Reuse P3b's scratch harness rather than rebuilding it; ask David for it if it did not survive the session.
2. Make `expire_orphaned_events` (`scheduler.py:73`) **log what it would delete and delete nothing** — count plus a sample of uids/titles/sources, at a level that survives in the container log. This is deliberate and temporary; P3b-3 arms it. Leave an obvious marker in the code so it cannot be mistaken for a bug.
**Done when:** tests green; the three scratch scenarios are invariant (P3b measured 9/9/9); the "aggregator down" delta is re-measured and stated, not assumed to still be 9-vs-0; and a scratch run proves the logging path fires while row counts stay unchanged.
**Hazard:** the orphan detector is **inert on the live DB today** — see §7. A scratch DB needs synthesised multi-run history or you get a false all-clear. P3b did.
**Report:** the scenario table before/after, and confirmation that `source` no longer reaches any deletion path.

### P3b-2 — Make `events.source` reflect the best reporting source
**Blocked on:** P3b-1 landing first.
**Why:** P3's finding. `events.source` is the first inserter, not the best reporter, so every venue site that overlaps an aggregator is undercounted — catastrophically for small sources (sektor read as 1 instead of 8). This corrupts every "which source contributes what" measurement, which is the evidence base for §4.5's substitution decisions and for P5's whole report.
**Do:** in `db.upsert_events`'s UPDATE branch (`db.py:217-229`), revise `source` to the highest-priority slug among the row's `event_sources`, reusing the *same* rank function as `_keeps_own_url` (`db.py:172`) rather than writing a third copy of that closure. Plus a one-off backfill recomputing `source` for existing rows from `event_sources` — as a `tools/` script, not an `init_db` side effect, so it can be run and reviewed deliberately.
**Hazards — check each explicitly, do not assume:**
- ~~⚠️ Ranking ties are now guaranteed~~ — **wrong, and disproved by the packet.** The supervisor asserted that P1/P2's six venue sources shared a tier-0 rank and could tie. There are no tiers in code (§4.4): `SOURCE_PRIORITY` is flat and `list.index()` is already a unique total order. No tiebreak was needed or written. Left here struck through rather than deleted, because the *shape* of the error is worth seeing: a plan document's design vocabulary was mistaken for a description of the code.
- `dedup.match()` rule 1 (`dedup.py:308`) treats two entries with the *same* source as never duplicates. Changing `source` changes which pairs are compared. Verify the dedup outcome is unchanged on a scratch DB before and after.
- ~~`db.find_orphaned_events` filters `WHERE source = ?`~~ — **resolved by P3b-1**, which moves that gate onto `event_sources`. Confirm P3b-1 is actually in the tree before you start; if it is not, stop and say so. (The original guess here — "`last_seen` is per-row, which likely makes this safe" — was **wrong**. P3b disproved it. Do not revive it.)
- Run `tools/export_static.py` twice with no scrape between and confirm no diff (§4.4).
**Do NOT** run the backfill against the live DB — that is PD's job, after a backup.
**Done when:** tests green, a scratch-DB before/after shows corrected attribution with unchanged dedup results, and the hazard analysis is written down.
**Report:** corrected per-source counts on the scratch DB, plus your verdict on the orphan-deletion interaction.

### PD — Deploy P0–P3b-2 to CT103
**Why:** P0–P1b are committed locally only. The live container still runs 6 sources; four more are waiting. Ship once, after **both** P3b-1 and P3b-2, so the image is rebuilt a single time.
⚠️ **Do not deploy P3b-2 without P3b-1**, and do not run the backfill until both are in the tree — see §4.7. Shipping the re-attribution alone puts `events.source` in control of a deletion path.
**Orphan deletion ships disabled** (P3b-1's logging-only guard) and must stay that way through this deploy — P3b-3 arms it later. Confirm the guard is present *before* rebuilding, and after the first post-deploy scrape capture the logged would-delete output: that is P3b-3's entire input. Future-event counts should not drop at all; if they do, the guard is not working and that is a rollback.
**Blast radius — real, read before starting.** This restarts a live service, and 45 minutes after each scrape a root cron on CT103 publishes the result to the **public** GitHub Pages site. A bad deploy is publicly visible. Host RAM is tight (~1.3 GB free), and this rebuild installs new deps.
**Also runs P3b's backfill** against the live DB — take an `app/backup.py` snapshot first and confirm it opens, then run the backfill, then report corrected per-source counts.
**Do:** copy the working tree to CT103 `/opt/dd-was-geht` (it is a plain copy, not a git repo — do not try to pull), rebuild the image, restart the container. **Stop and ask David before the restart**, and again before anything that would trigger an off-schedule publish.
**Done when:** `curl -s http://192.168.178.91:1111/api/health` lists all sources with a recent `last_success` and sane counts; the first post-deploy scrape completes in the log; `docker stats --no-stream` and `free -m` show the host is not into swap; and `tools/export_static.py` run twice with no scrape between produces identical `data/days/*.json` content and per-day `v` hashes (§4.4 hazard — note the `generated_at`/`dataVersion` stamps always differ and are not a failure, see §7).
**Rollback:** the pre-deploy copy of `/opt/dd-was-geht` and the nightly `vzdump` snapshot of CT103. Take a copy of the current directory before overwriting it.
**Report:** health output, event counts per source, host RAM before/after.

### P3b-3 — Arm orphan deletion
**Blocked on:** at least 3 post-PD scrape runs producing logged would-delete data (that is also the threshold `expire_orphaned_events` itself needs).
**Why:** §4.7 — making a destructive path more correct and arming it are two different changes. P3b-1 does the first; this does the second, on evidence instead of a scratch scenario.
⚠️ **There are three guards in this code and they are not interchangeable. Arming means removing exactly one of them.**
- `ORPHAN_DELETION_DISABLED` in `db.py` (~`:750`) — **this is the only one you remove.** It is the logging-only switch P3b-1 added deliberately; the code says so at length.
- **Non-emptiness guard 1** (rows with no `event_sources` entry) and **guard 2** (rows whose sources are all unjudging) inside `find_orphaned_events` (`db.py:620`) — **permanent. Never remove either.** Guard 2 in particular is the entire reason the new gate is not more deletion-happy than the old one (§4.7). Removing it reintroduces the 9-row over-deletion under "aggregator down". They look like the same kind of safety scaffolding as the switch. They are not.

**Do:** read the logged would-delete output from the live container. If it is empty or obviously right, remove `ORPHAN_DELETION_DISABLED` only. If it names events that are plainly still on the venues' sites, do **not** arm it and report the discrepancy — that is a real bug the harness missed.
**Done when:** either deletion is armed with the logged evidence quoted in the report, or it stays off with the reason written down.
**Report:** the logged sample, your read of it, and which way you went.

### P4 — split into P4a (mechanism) + P4b (data)
§8 flagged P4 as probably too big; confirmed on reaching it. The registry *mechanism* is a refactor with 5+ consumers and a real "did anything move?" bar; the *venue entries* are bulk data entry gated on David re-pasting two sections. Bundling them means a refactor whose regressions hide inside 27 new dict literals. **P4a must land and be proven inert before P4b starts.**

### P4a — `app/registry.py` + derived config, live sources only
**Model:** Opus 5 — 5+ consumers, and the whole point is that nothing observable changes.
**Do:** build `app/registry.py` (plain dict literal, §4.2) with entries for **only the 10 currently-wired sources**, all `status: live`. Derive `config.SOURCE_PRIORITY`, `SOURCE_LABELS` and the tier map from it, **exported under the same names** so no consumer moves. Split `SOURCE_LABELS`'s two jobs: `config.SOURCES` (all slugs → `db.py:529`, `db.py:598`) and `SOURCE_GROUP_LABELS` (~5 UI chips → `web.py:65`, `export_static.py:130,164`). Migrate `dedup.VENUE_ALIASES` into registry `aliases`.
⚠️ **`SOURCE_PRIORITY` order is load-bearing and must be preserved exactly.** `db._source_rank` is `list.index()`, and P3b-2 established that its uniqueness is what makes `_best_source` and `_keeps_own_url` unambiguous with no tiebreak (§4.4). Deriving the list from a dict must reproduce the **same order**, not merely the same membership — a reordering silently re-attributes events and flaps `events.url`. Assert the derived list equals the current literal, in a test.
**Do not** introduce tiers here. Tiers are P7 and they are what *create* ties (§4.4).
**Done when:** tests green; `config.SOURCE_PRIORITY` derived == the current literal, asserted; `/api/health` byte-identical before/after; `export_static.py` ×2 idempotent (remember the `generated_at`/`dataVersion` caveat, §7); registry is the only place a source is declared.
**Report:** head first — the derived-equals-literal proof, then what moved, then follow-ups.

### P4b — Venue entries from §9
**Blocked on:** P4a landed, **and** David re-pasting §9's "Bars / kleinere Locations" and "Aggregatoren mit iCal" sections verbatim (§9 is a second-hand transcription; those two were summarised).
**Model:** Sonnet 5 — mechanical once P4a exists.
**Do:** add the §9 venues as registry entries with the right `status`. GrooveStation and Der Lude are already live — `status: live`, not `todo`. **Ask David before adding the classical/theatre houses** (Kulturpalast, HfM Konzertsaal, Festspielhaus Hellerau, Societaetstheater, Yenidze Theater): §9 flags that as a deliberate widening from "bars and clubs", and it is his scope call, not a session's.
**Done when:** tests green, `/api/health` unchanged (entries that aren't wired must stay inert), venue count by status reported.
**Report:** venue count by status + any entry that could not be classified.

### P4 (original, superseded — kept for its input pointer)
**Input:** the venue list in **§9**. Before writing entries, ask David to re-paste the "Bars/kleinere Locations" and "Aggregatoren mit iCal" sections — §9's named venues are complete, those two sections are not.
**Do:** registry entries for all live sources plus every venue from the list as `status: todo`. `config.SOURCE_PRIORITY`, `SOURCE_LABELS` ~~and the tier map~~ (**struck — this contradicted the tier prohibition in the same packet; supervisor drafting error, caught by P4a**) become derived from it, exported under the same names so nothing else moves. Split `SOURCE_LABELS`'s two jobs: `config.SOURCES` (all slugs → `db.py:529`, `db.py:598`) and `SOURCE_GROUP_LABELS` (~5 UI chips → `web.py:65`, `export_static.py:130,164`). Migrate `dedup.VENUE_ALIASES` into registry `aliases`.
**Grace period:** `app/static/app.js:225` only hides an event whose source *is* in the label map, so unknown sources always show — the frontend can lag safely.

```python
"objekt-klein-a": dict(
    name="objekt klein a", tier=0, status="todo",
    site="https://objektkleina.com/", adapter=None, params={},
    address="Bremer Str. 65, 01067 Dresden",   # coordinates deferred to P9
    aliases=["oka", "objektkleina"],           # from dedup.VENUE_ALIASES
    default_raw_category="Party",
),
```
Status values: `live` · `wired` (awaiting first verified run) · `ready` (module written, not wired) · `todo` (site known, no scraper) · `research` (no site found) · `unscrapable` (Instagram/FB-only or JS-only) · `aggregator-only` (adequately covered, own site not worth it).
**Done when:** tests green, `/api/health` unchanged, registry is the only place a source is declared.
**Report:** venue count by status + any list entries you couldn't classify.

### P11 — The venue sources we already have are missing events the aggregators hold
**Why:** the §4.5 measurement turned up something nobody was looking for. Aggregator-**only** future events at venues that already have a live own-source scraper: **zentralwerk 102**, groovestation 17, der lude 11, sektor 5, conni 3. Zentralwerk's own ICS returns **20** events while the aggregators hold 102 more that no venue source reports. Either the venue feeds are far less complete than their first-run counts suggested, or dedup is not matching and we store the same night twice under two venue strings — `Zentralwerk` (60) and `Zentralwerk Dresden` (42) both appear in the data.

Those two readings have opposite fixes, and the strategy rests on knowing which. §4.5's "quality layer" case assumes a venue's own feed is the *more complete* source for its own events. If that is false, the priority ordering is upgrading URLs onto a thinner set of events — and P2's "zentralwerk won all 4 collisions" proved the ranking works, never that the feed was complete.

**The assumption to test:** *a venue's own feed is more complete than the aggregator's coverage of that venue.* Nothing in this project has ever checked it. Test zentralwerk first — largest gap, and its ICS+RRULE expansion is the most likely to silently truncate a window.
**Do:** sample the 102 and check each against the venue's own site and its ICS output. Classify three ways: genuinely absent from the feed / present but outside the scraped window / present but dedup failed on the venue string. **Read-only until the cause is known** — do not add aliases before you know which of the three it is.
**Hazard:** if the cause is dedup, a `VENUE_ALIASES` entry changes what `dedup.match()` compares and can merge rows retroactively. Re-run the §4.4 guard after any alias change, and note §7's corrected rule — a `generated_at` diff on a ×2 run is now a **finding**, not a caveat.
**Report:** head first — the three-way classification with counts, the cause for zentralwerk, whether it generalises to the other four.

### P5 — `SOURCES.md` + `tools/sources_report.py`
**Do:** one English document at repo root: §4 by hand, plus a status table regenerated between `<!-- STATUS:BEGIN/END -->` markers by `tools/sources_report.py` (reads registry + live DB: tier, status, adapter, last successful run, event count, cover count, whether an aggregator already covers it). Generated, so it can't rot. Same tool prints the §4.5 gap report.
⚠️ **Second counting rule (from P11):** and never count a *gap* without collapsing merged rows — group through `COALESCE(duplicate_of, uid)` as `db.py:890` does, or the report hands back rows the site already merged as if they were missing. That error made three of P11's five venues look like they had coverage gaps when two had none at all.

⚠️ **Counting rule (from P3):** never count a source's contribution as `WHERE events.source = X`. Use `event_sources`, or a per-uid highest-priority join. Doing it the naive way reproduces the exact undercount that made sektor look like 1 event instead of 8 — and it would do it silently for every future venue site. **Amended after PD:** the rule means *reach*, and reach is deliberately not the same number as the winner column — see §7's "two different numbers" entry before writing the report, and label every column in the output as one or the other. Post-backfill, `events.source` is trustworthy *as an attribution column*; it is still the wrong number for a contribution report.
**Done when:** the tool runs against the live DB and its output is committed into `SOURCES.md`.
**Report:** the gap report's top 15 — that *is* the worklist for P6 onward.

### P6–P10 — later
P6 generic `jsonld` adapter (then `wordpress-rest`) · P7 total-order tier ranking replacing list-index ranking in `dedup.py:392` + `db.py:172` · P8 `source_state` + conditional GET + cadence + bounded pool (**read §4.6's trap first**) · P9 coordinates as a separate `data/venues.json` keyed by venue slug, *not* two floats on 5000 rows in `feed.EVENT_FIELDS` · P10 map view.

---

## 6. Session notes / results

David pastes session reports here. Newest at the bottom. Supervisor folds anything durable into §4/§7 and updates §2.

```
### P<n> — <date> — <done | blocked | partial>
result:
surprises:
follow-ups:
```

### P0 — 2026-09-10 — done
result: `SOURCES` became slug strings; `importlib.import_module` moved inside `run_scrape`'s per-source `try/except`. Commit `d3fb010`, 1 file, +13/-8. Isolation verified directly (import of a nonexistent slug raises cleanly and is caught).
surprises: no local venv and no git identity in the clone — both cost setup time.
supervisor follow-up: both now fixed permanently, see §7 (persistent venv at `/home/admin/dd-was-geht/.venv`, git identity set repo-locally). Also confirmed the host **does** have outbound internet — that session's sandbox blocked it, the machine didn't.

### P1 — 2026-09-10 — done
result: derlude + strassee wired into `scheduler.SOURCES`, front of `SOURCE_PRIORITY`, and `SOURCE_LABELS`. No `VENUE_ALIASES` needed. Health-count assertion updated 6 → 8. Commit `000d4a6`, 5 files, +341/-2, tests green. Live: derlude 12 events / 31 days (all `Der Lude`); strassee 4, correctly split into `Bunker Straße E` (1) and `Reithalle Straße E` (3).
surprises: strassee descriptions show mojibake on non-ASCII punctuation (`Doesnât Matter`) — the feed declares ISO-8859-1 but mixes UTF-8 punctuation. Correctly judged out of scope and flagged rather than fixed mid-packet.
### P2 — 2026-09-10 — done
result: `icalendar==7.3.0` + `recurring-ical-events==3.8.2` pinned and installed; groovestation + zentralwerk wired at the same tier-0 slot. Health count 8 → 10. Commit `6d4fa8e`, 6 files, +368/-2, tests green. Live: groovestation 29 events (incl. venues the booking agency runs elsewhere, as its docstring predicts), zentralwerk 20 RRULE-resolved.
**Tier priority proven:** ran kulturkalender + zentralwerk into a scratch DB, 4 overlapping events, zentralwerk won all 4. §4.4's premise holds against a real collision.
surprises: none. Note `recurring-ical-events` is hyphenated on PyPI but `recurring_ical_events` on import.
supervisor follow-up: **six venue-owned sources are now committed but not deployed** — added packet **PD**. Ship after P1b + P3 so the image rebuilds once.

### P3 — 2026-09-10 — done, **premise disproved**
result: sektor = 8 events, azconni = 3, both matching the live sites exactly. Neither scraper is broken — no markup change, no pagination boundary. No code changes, no commit.
root cause: `events.source` is set only at first INSERT and never revised when a higher-priority source later upserts the same `uid`. Aggregators run earlier in `scheduler.SOURCES`, so they claim the column for events the venue also reports — even though `_keeps_own_url` already correctly hands the venue the URL. Verified uid-by-uid read-only against the live DB. Same mechanism found undercounting ra (15 → 11) and cybersax (1062 → 983).
surprises: systemic across every source overlapping an aggregator, not sektor/azconni-specific — merely catastrophic for sources with small totals.
supervisor follow-up: filed as **P3b** (fix + backfill; Opus, because it touches the write path, dedup rule 1 and the orphan-*deletion* path). §3's table is now marked as not-to-be-quoted, and **P5 carries a hard counting rule** — count via `event_sources`, never `events.source`. This is the highest-value finding of the project so far: it means the venue-source strategy was always working better than the instrumentation showed.

### P1b — 2026-09-10 — done
result: `_fix_mojibake()` added to `strassee.py` (encode iso-8859-1 → decode utf-8, kept only on a clean round-trip, else text untouched), applied to `_parse_feed`'s title/description only — venue/time come from the detail page and were left alone. Commit `607baf6`, 2 files, +56/-2, tests green. Fixture covers both the mojibake case and a genuine ISO-8859-1 umlaut that must *not* be touched. Live re-scrape: Bunker Straße E / Reithalle Straße E split still correct, 4 events / 2 venues.
surprises: none. The round-trip heuristic fails cleanly on real `ß`/`ö` because those single bytes aren't valid UTF-8 lead bytes — which is exactly why it is safe to apply blind.
supervisor follow-up: commit verified in the log, working tree clean. The heuristic is now a reusable answer to a class of problem, not a one-off — promoted to §7 so the next feed that declares a legacy charset doesn't get re-diagnosed from scratch. David's venue list arrived mid-session and is captured in §9; the §2 open item is now partly closed.

### (P1 follow-up)
supervisor follow-up: filed as **P1b**. Not purely cosmetic — `description` reaches the public site, and the same punctuation in a *title* would degrade dedup matching via `slugify`. Note the real signal here: **first two venue-owned sources now deliver 16 events vs. the 2 that sektor+azconni manage** — consistent with P3's premise that those two are broken, not thin.

### P3b — 2026-09-10 — **analysis done, packet re-scoped, no commit**
⚠️ *Only the verdict and follow-ups of this report were pasted; the `result` and `surprises` head was not captured, including the names of the three scratch scenarios and the content of "surprise 1". The findings below are recorded verbatim from what arrived. If the head is still recoverable, paste it and the supervisor will fold it in.*
verdict: **not inert.** The `upsert_events` change must not ship on its own — the write-path fix and the orphan gate have to land together, or `source` becomes a live input to a destructive path nobody intended it to control.
result: prototyped an `event_sources`-based orphan gate in a scratch harness. Invariant across all three scenarios (9/9/9) — the property the current gate lacks. Not a free swap: under "aggregator down" it finds 9 orphans where today's code finds 0.
follow-ups raised: (1) re-scope into P3b-1 (orphan gate, Opus, first) + P3b-2 (re-attribution + backfill, Sonnet, after); (2) PD must not run the backfill until both land; (3) §2's "blocks P5 from being meaningful" was inaccurate — P5's counting rule already covers it; (4) record that the orphan detector is inert on the live DB.
supervisor follow-up: all four accepted and applied — packets split in §2/§5, the structural finding promoted to **§4.7**, the live-DB inertness promoted to **§7**, PD's ordering hardened, and the inaccurate P5 note removed. The aggressiveness trade-off is **not** a session's call and is now a flagged decision for David at the top of §2; P3b-1 sits `blocked` until he rules. Verified: no commit, working tree clean. Also note the packet's own stated hazard — "`last_seen` is per-row, which likely makes this safe" — was **wrong**, and P3b was right to test it rather than inherit it. Second packet in a row where naming the assumption produced the finding.

### P3b-1 — 2026-09-10 — done
⚠️ *Head captured, tail truncated again — `surprises` and `follow-ups` did not arrive. Nothing critical appears missing this time, because the head-first instruction worked and the findings are legible from the scenario table and the code.*
result: orphan gate moved off `events.source` onto `event_sources`; deletion disabled behind `ORPHAN_DELETION_DISABLED`. Commits `2f8b698` (+`c40fb50`, harness → `tools/orphan_harness.py`), +249/-59, 370 smoke tests green. Scenario table (steady / event-dropped / aggregator-down): old gate 0/3/0, new gate 0/3/0 — **invariant**. Row counts 18→18 in all three with `dry_run=False`; before the change, "event dropped" deleted 3. `source` confirmed absent from every deletion path; `_delete_orphaned_event` now uncalled, kept for P3b-3.
**The finding that matters:** the 9-vs-0 "aggregator down" delta — the thing I escalated to David as a product decision — **was a bug, not a trade-off.** It is reproducible only under the vacuous reading of "all judging sources are stale" over an empty set, and it is entirely aggregator-only rows. The packet added two non-emptiness guards; with guard 2 in place the delta vanishes. Assumption 1 came back clean in fact but the guard was kept anyway: 5789/5789 live rows have `event_sources` entries.
supervisor follow-up: commits verified, tree clean, guard is unmistakable in the code (named constant, German comments, explicit "ABSICHT, KEIN BUG"). §4.7 rewritten — the guards are documented as permanent and P3b-3 is now explicit that arming means removing `ORPHAN_DELETION_DISABLED` *only*, never the guards. §2's decision note amended in place rather than deleted: the ruling stands, but the reason changed, and the honest version is that logging-only turned out to **disarm a path that was about to arm itself on a timer** — which is a better justification than the one I gave. Also promoted to §4.7 as a general rule: *a measured old/new behaviour delta is a bug report until proven otherwise* — I skipped that question and went straight to "is this acceptable?", which cost David a decision he should never have been asked to make.

### P3b-2 — 2026-09-10 — done
result: `upsert_events`'s UPDATE branch now revises `source` to the best-ranked slug across the row's `event_sources` on every upsert, via a new `db._best_source`, sharing `_source_rank` with `_keeps_own_url` (no third copy of the closure). `tools/backfill_source.py` added for the one-off backfill (dry-run default, `--apply` to write; not run against live). Commit `dab547d`, 2 files, +109/-8, 370 smoke tests green.
surprises: **the packet's own premise — that ties are "now guaranteed" — is false in this codebase.** There is no actual tier structure in code; `config.SOURCE_PRIORITY` is one flat list and `rank(name) = priority.index(name)`, which is a unique integer per source by construction (`list.index`). Two distinct sources can never share a rank, so "highest-priority slug among the row's `event_sources`" is already unambiguous — no tiebreak needed. Verified two ways: (1) `{s: db._source_rank(s) for s in config.SOURCE_PRIORITY}` has 10 distinct values for 10 sources, no duplicates possible since `SOURCE_PRIORITY` itself has no duplicate entries; (2) scratch-DB test upserting all six "tier-0" venue sources for one event, in three different random insertion orders — `derlude` (lowest index) won every time, deterministically, with no tiebreak code needed. §4.4/§4.7's "tier 0" language describes an *aspirational* tiering (P7's total-order-tuple restructuring) that hasn't been built yet — the flat priority list happens to already be a total order, so P3b-2's hazard doesn't currently bite. Wrote no tiebreak code since there is nothing to break ties between; flagged for P7 to either confirm this stays true or to actually introduce tiers (at which point ties become real and a tiebreak becomes necessary).
Other hazards checked: dedup rule 1 (`same source ⇒ never duplicate`) still holds — verified on scratch DB. `tools/export_static.py` run twice on a seeded scratch DB (10 events, aggregator+venue overlap across several days) with no scrape between: `data/days/*.json` and the per-day `v` hashes are byte-identical between runs; the only diff was the export's own `generated_at`/`dataVersion` timestamp, unrelated to attribution. P3b-1 confirmed in the tree before starting (`2f8b698`, `c40fb50`).
follow-ups: P7 (total-order rank tuples) should note that P3b-2 shipped *without* a tiebreak because none was needed yet — if P7 introduces real tiers, revisit `_best_source`/`_keeps_own_url` for a tiebreak at that point, not before.
supervisor follow-up: commit `dab547d` verified, tree clean, and the no-ties claim independently confirmed in code (`_source_rank`'s own docstring now states the uniqueness argument; `_best_source` is `min(..., key=_source_rank)`). **The false premise was mine, not the packet's** — I read P2's phrase "wired at the same tier-0 slot" as describing a tier structure in code and wrote a guaranteed-tie hazard into the brief. §4.4 has been rewritten to say plainly that tiers are P7 vocabulary and do not exist yet, and P7's entry now carries the real version of the hazard: **introducing tiers is what creates ties**, and it must fix `_keeps_own_url` and `_best_source` together, since both now lean on rank uniqueness. Also promoted to §7: the twice-`export_static.py` check produces a `generated_at`/`dataVersion` diff *by design* — PD's done-when previously said "no diff" and would have raised a false alarm. Third packet in a row where naming the assumption paid; this time it caught the supervisor.

### PD — 2026-09-10 — **partial, mid-packet** (worker session still open)
result: deploy done and verified. `/opt/dd-was-geht` on CT103 now byte-identical to local `HEAD` (`dab547d`); image rebuilt, container restarted with David's explicit go-ahead (stop-and-ask point 1 honoured). `/api/health`: the 6 established sources `ok` (kulturkalender 4610, cybersax 990, rauze 167, ra 11, sektor 8, azconni 3); the 4 new sources report `ok:false`/`null` because they have **never run yet** — the container skipped an immediate scrape since the last success was <6h old, which is by design, not a failure. Host RAM before 286 MB free / 5399 MB available, after 379 MB free / 5560 MB available — no swap. Backup `dd-was-geht-2026-09-10.db` taken, confirmed to open, 5789 rows. Backfill: dry-run read first, then `--apply` → **9 rows updated**, `events.source` only, re-run dry-run shows 0 diff (idempotent).
**The one finding that matters:** the premise held. The pre-deploy `/opt` tree was verified byte-identical to git `a3eefcf` by full tree diff (excluding untracked `.env`/`STACK.md`) — no hand-edits, so the plain-copy deploy method was safe to trust. Also confirmed `db.ORPHAN_DELETION_DISABLED == True` **inside the rebuilt image** before the restart, not merely in source.
still open: first post-deploy scrape (18:30 Berlin / 16:30 UTC, fixed `CronTrigger`) not yet run. The session deliberately did **not** force it early — outside the packet's stop-and-ask scope and no reason to deviate from cadence. Outstanding: capture the logged would-delete output (P3b-3's input), confirm future-event counts do not drop, run the `export_static.py` ×2 idempotence check.
supervisor follow-up: **the 9-row backfill looked too small against P3's "true figures" (sektor 8, azconni 3, ra 15, cybersax 1062) and I checked it before raising it — it is correct, not a defect.** Measured read-only on the live DB: `event_sources` reach is kulturkalender 4615 / cybersax 1069 / rauze 171 / ra 15 / sektor 8 / azconni 3, against 5789 rows with 91 multi-source rows. Reach sums to 5881 = 5789 + 92, so the two numbers reconcile exactly. **They measure different things and both are legitimate** — see the new §7 entry. Only sektor (+7) and azconni (+2) rows changed hands, because they are the only sources that *outrank the incumbent* on rows they co-report; ra and cybersax rank below kulturkalender, so their extra reach correctly does not win the column. 7+2 = the 9 rows observed. §4.7's rule applied as intended: asked "is this delta a defect?" first, and this time the answer was no.

### PD (continued) — 2026-09-11 — **post-deploy scrapes verified, packet all but closed**
Supervisor-measured read-only at 02:27 Berlin, because the worker session's tail never arrived. All figures live from CT103.

result: **the deploy works.** `/api/health` — all **10** sources `ok=true`, `error=null`. The four new venue sources ran for the first time and delivered as predicted locally: derlude 11, groovestation 29, strassee 4, zentralwerk 20 = **64** (local runs suggested ~65). Rows 5789 → **5946**, future rows **5779** — **nothing was deleted**, which is the guard behaving exactly as PD's done-when required. Host was not pushed into swap.

**The thesis is now true in production, for the first time.** Winner column after two post-deploy scrapes: kulturkalender 4688, cybersax 993, rauze 175, **groovestation 30, zentralwerk 20**, ra 13, **derlude 12**, sektor 8, **strassee 4**, azconni 3. The four venue-owned sources are winning the attribution on events the aggregators also report — that is §4.5's quality layer working end to end (scraper → priority → `_best_source` → published feed), not just in a scratch DB.

orphan logger (P3b-3's input, verbatim, both post-deploy runs):
```
2026-09-10 18:35:14,976 INFO dd-was-geht.db: Verwaiste Events: keine gefunden (Schwelle 3 Laeufe, Loeschen abgeschaltet).
2026-09-11 00:35:04,070 INFO dd-was-geht.db: Verwaiste Events: keine gefunden (Schwelle 3 Laeufe, Loeschen abgeschaltet).
```
Run history: the 6 established sources have 5 runs each (all `ok`), the 4 new ones **2 each**.

still open: only the `export_static.py` ×2 idempotence check. Worth a Haiku 4.5 chore, not a packet.

supervisor follow-up: **PD's report mislabelled its own numbers** — it quoted 4610 / 990 / 11 as `/api/health` output, but those are winner counts from the DB; health returns *run-seen* counts (`scrape_runs.event_count`, `db.py:564`, verified in code). The numbers were right, the source label was wrong. This is the second time in one packet that two legitimate counts got crossed, which is why §7 now names all three explicitly. **Caveat recorded for P3b-3:** the threshold is about to be met on the *aggregators'* history, but the four new sources have only 2 runs each, so the orphan path has barely been exercised against exactly the sources whose disappearance would matter most. Arming on aggregator history alone would satisfy the letter of the gate and miss its point — P3b-3's kickoff must name that as the assumption to test.

### P4a — 2026-09-11 — done
result: `app/registry.py` is now the single declaration site. `config.SOURCE_PRIORITY` = `registry.priority_order()`, asserted element-for-element against a hard-coded copy of the pre-refactor literal (not a set, not membership): `derlude > strassee > groovestation > zentralwerk > sektor > azconni > rauze > ra > kulturkalender > cybersax`. Order comes from an explicit unique `priority` int per entry (10, 20, … 100) rather than declaration order, so a venue pasted into the middle of the file cannot silently reorder ranking; `registry._check_unique()` raises **at import time** on a duplicate priority — the exact tie `_best_source`/`_keeps_own_url` cannot resolve. Four declaration sites collapsed; `SOURCE_LABELS` split into `config.SOURCES` (all slugs) and `config.SOURCE_GROUP_LABELS` (chips). `VENUE_ALIASES` derived == old literal, all 21 keys. Commit `8dd2298`, +242/-64, 377 checks green. `/api/health` byte-identical; export ×2 byte-identical on a seeded 20-event DB; HEAD-vs-refactored export differs only in the stamp. No `tier` field — a test asserts its absence.

**The one finding that matters: there were *two* load-bearing orderings, and only one was written down.** `SOURCE_LABELS`'s insertion order sets `/api/health`'s key order via `db.scrape_health`, and that order is **scrape order**, not priority order. Deriving labels from `priority_order()` — the obvious move, same ten slugs — would have left `SOURCE_PRIORITY` proving equal while `/api/health` silently shifted, under a check that only looked at the priority list. Promoted to §7.

surprises: (1) `SOURCE_GROUP_LABELS (~5 UI chips)` in the packet text is **stale** — every source has its own chip today; the split was made by role, content identical, and chip *grouping* left as a P4b/P7 decision. (2) `VENUE_ALIASES` could not fully migrate: 21 aliases → 12 canonical venues, but only 3 (`conni`, `sektor-evolution`, `groovestation`) belong to a wired source. The other 9 are venues with **no** source; inventing source entries for them would have injected nine non-sources into `config.SOURCES`, hence into `/api/health` **and the orphan gate**. Parked in `registry.EXTRA_VENUE_ALIASES`, marked as what P4b dissolves. (3) The packet said "derive … the tier map from it" *and* "do not introduce tiers here" — contradictory; the prohibition was followed.

follow-ups: P4b dissolves `EXTRA_VENUE_ALIASES`, deletes the `SOURCE_GROUP_LABELS == SOURCE_LABELS` check (the split is durable, the equality is not), and should settle chip grouping before ~15 chips become unusable. P7: the `priority` ints are spaced by 10 on purpose so a tier map can key off them without renumbering, and `_check_unique()` is where the tie ban lives — P7 must **replace** it, not bypass it. Local DB holds 0 events, so a naive local export ×2 is vacuous.

supervisor follow-up: commit verified, tree clean. **Two corrections to this document, both mine.** (1) The "derive the tier map" line contradicted the tier prohibition in the same packet — my drafting error; P4a was right to follow the prohibition, and the line is struck. (2) Far more serious: §7's caveat that `generated_at`/`dataVersion` "always differ and are not a failure" is **false**, and I wrote it. Verified in code: `_previous_generated_at` (`tools/export_static.py:66-75`) deliberately *reuses* the stamp when content is unchanged, and `dataVersion` is the same value rendered into the template — one stamp, stable when content is stable. The wording told three sessions to excuse the clearest available signal that the §4.4 URL-flapping hazard had fired. Rewritten; a stamp diff on a ×2 run is now a **finding**. (3) P4a's throwaway note that the local DB is empty is what exposed **PD's closing chore as a vacuous pass** — 0 events, 0 day files, two empty exports compared, confident green. PD is marked `done` because P4a's seeded check covers the same ground more strictly, not because that chore verified anything. Fourth packet in a row where naming the assumption caught something; the second in a row where what it caught was the supervisor.

---

### P11 — 2026-09-11 — **analysis done, premise half-disproved, no commit**
*(This session wrote its own §4.5 correction, §5 counting rule and §6 entry directly — a deviation from §1, where the supervisor folds reports in. The work was accurate and is kept. Supervisor verified each edit and added the piece below that the packet's own reasoning missed. **If you are a working session: still report rather than edit** — the value here came from a second reader checking the claim, which does not happen if the claim is written straight into the file.)
result: the three-way classification of zentralwerk's 102, plus the same measurement re-run for all five venues.

| venue | own future rows | agg-only (§4.5 method) | already `duplicate_of`-linked | …onto a row the venue itself reported | **truly unexplained** |
|---|---:|---:|---:|---:|---:|
| zentralwerk | 20 | 102 | 64 | 14 | **38** |
| groovestation | 29 | 17 | 17 | 17 | **0** |
| derlude | 11 | 11 | 11 | 11 | **0** |
| sektor | 8 | 5 | 4 | 4 | **1** |
| azconni | 3 | 3 | 0 | 0 | **3** |

Of zentralwerk's 102, checked one by one against the live Teamup ICS (fetched today, window widened to 2027-03-31 — 111 events, so the feed itself is not truncated): **outside the scraped window 0**, **dedup should have matched 15** (11 that `dedup.match()` accepts once both rows are put to it, 4 near-misses), **genuinely absent from the feed 87**.

**The one finding that matters: the 102 was never a coverage number, and for three of the five venues the gap is exactly zero.** §4.5's "aggregator-only" test asked `event_sources`, which is the **exact-uid** layer — `normalize.make_event_uid` hashes `date|time|slug(title)|slug(venue)` (`normalize.py:264`), so two sources share a uid only when all four agree to the character. Fuzzy dedup lives somewhere else entirely: `dedup.link_duplicates` writes `events.duplicate_of`, and `db.py:322` hides those rows from every read. The measurement counted rows the site does not show. groovestation 17/17 and derlude 11/11 are *fully* explained by that one omission — every single "missing" event is already sitting merged under the venue's own row. **Two of the four "generalises?" candidates were not gaps at all.**

Zentralwerk is a real gap and a different thing: **its ICS is a room-booking calendar, not a programme.** `2968691.ics` is one sub-calendar of a Teamup whose all-calendar feed (`…/0.ics`) holds 725 bookings under headings like `e.V. intern`, `Kuratorium e.V.`, `Christian ORGA`. The feed books *the night*; the aggregators list *the line-up*. The ICS has one `djummi-Festival (Label-Jubiläum)` where cybersax has Lestar/Lindbergh, rokotak/Fortuna Kevin, Stille Post/Dave Schoepke; one `Literatur JETZT! Festival 2026` where rauze and kulturkalender have ~40 readings. Probing the **full** 725-booking feed for the missing titles — `Lestar`, `rokotak`, `Marcel Beyer`, `Lyrikparcours`, `read the room`, `Stille Post` — returns **not present, none of them**. So this is not the wrong sub-calendar and there is no better own source: `zentralwerk.de` publishes no programme page at all (`/termine/`, `/veranstaltungen/`, `/programm/` all 404, no JSON-LD), only a link to the same Teamup.

**So the project's founding assumption is false as stated and true as intended.** "A venue's own feed is more complete than the aggregators' coverage of that venue" does *not* hold — zentralwerk's own feed is genuinely thinner, and no fix to our code changes that. What P2 proved still stands and is what §4.5 actually needs: when both report the same night, the venue source wins and carries the better title, URL and time. **Venue sources are a quality layer, not a coverage layer — which is exactly what §4.5's title already says and its argument quietly stopped believing.** Nothing in §4 needs reversing; one sentence in it needed checking and now has been.

surprises: (1) zentralwerk's 20 own rows have **zero** entries in `event_sources` beyond themselves — P2's "won all 4 collisions" happened at the `duplicate_of` layer, not the uid layer, and re-reading the number as a uid-layer fact is what made the feed look isolated. (2) `dedup._venue_key` already strips `dresden` as a generic word (`dedup.py:93`), so `Zentralwerk` and `Zentralwerk Dresden` **are the same key today** — the packet's second reading was disproved before it was tested, and the `VENUE_ALIASES` entry the hazard note warned about would have been a no-op. The two strings still produce different **uids**, which is why they look split in `event_sources` and are not split on the site. (3) 38 of zentralwerk's 102 are neither linked nor in the feed, and ~20 of those are one exhibition (`All Colours Are Beautiful`) that kulturkalender emits once **per day** — present in the internal Teamup sub-calendar, absent from the public one. (4) azconni's whole "gap" is one 3-day festival its own site never lists; sektor's single one is `Brennpunkt` at 17:00 (sektor) vs 23:00 (rauze), 360 min apart — a time-delta near-miss, not a venue-string one.

follow-ups: (a) **§4.5's gap report and P5's `tools/sources_report.py` must count through `COALESCE(duplicate_of, uid)`** — `db.py:890` already does exactly this for the published feed; the ad-hoc §4.5 query did not, and any future "what are we missing" number written the naive way will re-report merged rows as gaps. This is the same shape of error as P3's `events.source` undercount, one layer up. (b) A `dedup` packet could pick up the 15 that should have matched — the recurring shape is a parenthetical genre suffix on the venue side (`Jazzfanatics (Jazzkonzert)` vs `JAZZFANATICS Live Jazz im Foyer`) — but it is worth ~15 rows across five venues and should be sized accordingly. (c) Real and worth more: zentralwerk-style umbrella bookings would benefit from `_is_umbrella` (`dedup.py:319`), today a cybersax-only marker, being set by ICS sources whose event spans a whole day — that is what would hang the djummi and Literatur JETZT! line-ups under the venue's own row instead of under rauze's. P7-adjacent; not P11's to make. (d) Do **not** open a P-packet to "fix zentralwerk's feed". There is nothing to fix on our side.

no commit: read-only throughout, per the packet. No `VENUE_ALIASES` entry added — the cause was never the venue string. Nothing in `/home/admin/dd-was-geht` was touched, so the §7 export-×2 check does not apply.

---

## 7. Standing facts

Every session needs these; nobody should re-derive them.

**Deploy path.** CT103's `/opt/dd-was-geht` is byte-identical to git `HEAD` but is **not a git repo** — a copy. ✅ **Verified by full tree diff during PD (2026-09-10)**, not just asserted: the pre-deploy `/opt` tree matched `a3eefcf` exactly, with only untracked `.env` and `STACK.md` extra. So the plain-copy deploy is safe *and* those two untracked files are the things a copy must preserve. Re-run that diff before any future overwrite — it is cheap and it is the only thing standing between a deploy and a silent loss of a hand-edit. The local clone `/home/admin/dd-was-geht/backend` was cloned with a read-only deploy key; write access to `Trampa336/dd-was-geht` is **unverified**. So: commit locally, deploy by copying to CT103 and rebuilding the container, **never push**. CT103's write key covers only the *site* repo `DD_was_geht`. Backups are covered: CT103 is in the nightly `vzdump` job and `app/backup.py` snapshots the DB daily at 03:45.

**Host access.** `ssh -o BatchMode=yes root@localhost` from `admin` (no sudo on this host), then `pct exec 103 -- ...`. For a script: `pct exec 103 -- docker exec -i dd-was-geht python <<'EOF'`. Host `leo` has 7.6 GB RAM total, ~1.3 GB free — that constraint drives §4.6.

**Python environment — do not build your own.** A persistent venv lives at `/home/admin/dd-was-geht/.venv` (Python 3.13, `backend/requirements.txt` installed, smoke tests green as of 2026-09-10). Use `../.venv/bin/python` from inside `backend/`. Do not create a venv in the scratchpad — that dies with the session, which is exactly what P0 wasted time on. If you add a dependency, install it into this venv *and* pin it in `requirements.txt`.

**Git identity** is already configured repo-locally in the clone (`David <dvdmndt@gmx.de>`). No setup needed.

**Network.** The host has working outbound internet — verified 2026-09-10 by fetching derlude.de (200), groovestation's ICS (200) and strasse-e.de's RSS (301 → redirect, which `requests` follows by default). If your Bash sandbox blocks outbound requests, that is the sandbox, **not** the machine: say so and use the sandbox escape rather than reporting the live site as unreachable, because packets P1–P3 cannot be verified without hitting real sites.

**Verification commands.** (run from `/home/admin/dd-was-geht/backend`)
```bash
../.venv/bin/python tests_smoke.py
../.venv/bin/python -c "from app.scrapers import derlude; import datetime as d; print(len(derlude.scrape_range(d.date.today(), d.date.today()+d.timedelta(days=31))))"
curl -s http://192.168.178.91:1111/api/health | python3 -m json.tool
../.venv/bin/python tools/show_duplicates.py
```
Plus, after any change touching URLs or priority: run `tools/export_static.py` twice with no scrape in between and confirm no diff — that guards against the §4.4 URL-flapping hazard.

⚠️ ~~**"No diff" does not mean byte-identical files.** The export stamps its own `generated_at` and `dataVersion` on every run, so those two always differ and are **not** a failure.~~ **This was WRONG and it was the supervisor's entry. Corrected 2026-09-11 in code (P4a).**

The truth: `export_static._previous_generated_at` (`tools/export_static.py:66-75`) **reuses the previous timestamp when the index payload is unchanged**, precisely so an unchanged export does not produce a pointless commit — the German comment at `:132-137` says so. And `dataVersion` is not a second stamp at all: it is the *same* `generated_at` rendered into the template (`app/templates/index.html:36` → `app/static/app.js:159`). One stamp, and it is **stable when content is stable**.

So a genuine ×2 run with no scrape between should be **byte-identical, timestamp included**. P4a measured exactly that on a seeded DB. A differing `generated_at` means **the content changed** — which is the very thing the check exists to detect.

**Why this mattered:** the old wording told every session to *expect and excuse* a differing stamp, i.e. to wave through the single clearest signal that the URL-flapping hazard (§4.4) had fired. It was quoted into PD's done-when, the PD chore, and P4a's brief. A stamp diff is now a **finding**, not a caveat. (Where it legitimately differs: across a code change that alters the index payload — P3b-2 and P4a both saw that comparing old code to new, which is a different comparison from ×2 on one build.)

⚠️ **An export check against an empty DB is vacuous and passes.** (P4a.) Local `data/dd-was-geht.db` holds **0 events**, so `export_static.py` ×2 there compares two empty exports — 0 day files, nothing to differ — and reports a confident green. **The PD closing chore did exactly this** and its "Pass" is void. Seed a temp DB (P4a used 20 events spanning several days with aggregator/venue overlap) or run against a copy of live. What must match: `data/days/*.json` content, the per-day `v` hashes, **and** `generated_at`.

**Scraper module contract.** `SOURCE` slug + `scrape_range(start_day, end_day)` → list of dicts with `uid, source, date, time, title, venue, category, raw_category, url, image_url, price_text, description, detail_fetched_at`. Helpers: `normalize.make_event_uid/classify_category/normalize_time/slugify`, `base.fetch_html/make_soup/find_event_blocks/extract_title/extract_venue/scrape_days`. Day-paged sources use `base.scrape_days`. Convention: a pure `_parse*(text)` function with no network, plus injectable `fetch_detail=`/`fetch_image=` kwargs for tests.

**Free detail parsing.** `detail_fetch._parse_generic_detail` (`detail_fetch.py:121`) reads `og:description` + `og:image` for *any* source as a fallback, lazily on click, persisted after the first fetch. A new venue source usually needs no custom detail parser.

**The orphan detector is inert on the live DB — for now, and by accident.** Each source has exactly 1 successful run recorded and `expire_orphaned_events` needs `threshold_runs=3`. So testing that path against live-shaped data gives a **false all-clear** — P3b got one before spotting it. Anyone touching `find_orphaned_events` / `_delete_orphaned_event` / `expire_orphaned_events` must synthesise multi-run `scrape_runs` history on a scratch DB first. Use **`tools/orphan_harness.py`** (P3b-1, commit `c40fb50`) — it builds 6 synthetic runs 6h apart over co-reported and aggregator-only rows; do not rebuild it a third time.

The inertness is temporary and nobody chose it: it expires as run history accumulates, at which point deletion would have begun firing unobserved. P3b-1's `ORPHAN_DELETION_DISABLED` switch is what actually holds it off now. Related live-DB fact, checked read-only 2026-09-10: **5789/5789 event rows have `event_sources` entries** — `upsert_events` calls `_record_source()` unconditionally and `init_db()` backfills older rows.

**`events.source` and `event_sources` reach are two different numbers — both correct, neither interchangeable.** (Measured live, PD, 2026-09-10.) `events.source` is **winner-take-all**: one row, one slug, the best-ranked source among that row's reporters. `event_sources` is **reach**: every source that reported the row, so a row with 3 reporters is counted 3 times. Live figures — rows 5789, multi-source rows 91; reach kulturkalender 4615 / cybersax 1069 / rauze 171 / ra 15 / sektor 8 / azconni 3 (sums to 5881 = 5789 + 92); winner kulturkalender 4610 / cybersax 990 / rauze 167 / ra 11 / sektor 8 / azconni 3.

The gap between a source's reach and its winner count is **not** the attribution bug P3 found — that bug is fixed, and after the backfill the winner column is correct by construction. The gap is just the rows where a *higher-priority* source also reported the event. That is why P3b-2's backfill moved only **9** rows and not ~90: sektor (+7) and azconni (+3→ +2 net) are the only sources that outrank their incumbent on co-reported rows. Anyone expecting the backfill to close the whole reach/winner gap has misread which number is which.

**So say which one you mean.** "How much does source X contribute / what would we lose if it vanished" → **reach** (`event_sources`). "Who is this event attributed to in the UI and the published feed" → **winner** (`events.source`, now trustworthy). P5's counting rule in §5 means *reach*, and is amended to say so.

**A third number: `/api/health`'s `event_count` is neither of the above.** It is `scrape_runs.event_count` from that source's **last successful run** (`db.py:564`, written at `db.py:506-514`) — *events seen in that run*, not rows in the DB. Verified in code 2026-09-10. So health legitimately reports kulturkalender 4682 / cybersax 1070 / ra 15 while the DB holds 4610 / 990 / 11 as winners and 4615 / 1069 / 15 as reach. **Three numbers, three meanings, none of them wrong.** A source that scrapes a wider window than it stores, or stores events that later expire, will show a health count above both DB numbers permanently.

Consequence for PD's done-when ("sane counts") and for P5: *say which number you are quoting*. A count from `curl /api/health` cannot be compared against a count from a DB query without first converting one to the other, and doing so accidentally will look exactly like a regression.

**Two orderings are load-bearing, not one.** (P4a, the finding that matters.) `config.SOURCE_PRIORITY`'s order drives ranking via `db._source_rank`'s `list.index()`. But `config.SOURCE_LABELS`'s *insertion* order drives the key order of `/api/health`, because `db.scrape_health` iterates it — and that order is **scrape order** (`scheduler.SOURCES`, aggregators first), which is **not** priority order (venue sources first). Deriving labels from the priority list is the obvious move and is wrong: `SOURCE_PRIORITY` would still prove equal while `/api/health` silently shifted its key order, under a check looking only at the priority list. The registry is therefore declared in **scrape order**, with priority as an explicit `int` field. Both orderings are asserted in `tests_smoke.py`.

**Dedup has two layers and they answer different questions.** (P11, and the single most misread thing in this project.)
- **The uid layer — exact.** `normalize.make_event_uid` hashes `date|time|slug(title)|slug(venue)` (`normalize.py:264`). Two sources share a uid only when all four agree *to the character*. `event_sources` lives here. It answers "did these sources report the identical event".
- **The `duplicate_of` layer — fuzzy.** `dedup.link_duplicates` writes `events.duplicate_of`, and `db.py:322` hides linked rows from **every read**. `db.py:890` groups through `COALESCE(duplicate_of, uid)`. This layer is what the site and the published feed actually show.

**Querying the uid layer and calling the result "missing" counts rows the site already merged away.** That single omission made three of P11's five venues look like they had coverage gaps when two had none at all, and inflated §4.5's headline denominator by 491. Live shape, 2026-09-11: 5779 future rows, **545 merged children (491 aggregator→aggregator), 5234 distinct published events.**

**Zentralwerk's ICS is a room-booking calendar, not a programme — and there is no better source.** (P11, checked exhaustively.) `2968691.ics` is one sub-calendar of a Teamup whose all-calendar feed holds 725 bookings under headings like `e.V. intern` and `Kuratorium e.V.`. It books *the night*; the aggregators list *the line-up* — one `djummi-Festival` booking where cybersax has three acts, one `Literatur JETZT! Festival 2026` where rauze and kulturkalender have ~40 readings. The full 725-booking feed was probed for the missing titles and holds none of them, and `zentralwerk.de` publishes no programme page at all (`/termine/`, `/veranstaltungen/`, `/programm/` all 404, no JSON-LD). **Do not open a packet to "fix" this and do not treat zentralwerk's 38 residual as a scraper defect.** The structural fix, if one is ever wanted, is `_is_umbrella` (`dedup.py:319`) — today a cybersax-only marker — being set for ICS events spanning a whole day, so line-ups hang under the venue's own row. P7-adjacent.

**A venue's own feed is not necessarily more complete than the aggregators' coverage of it.** (P11 — the founding assumption, tested at last.) It is false as stated and true as intended: when both report the same night the venue source wins and carries the better title, URL and time. §4.5's *title* — quality layer — was right; its argument had quietly started claiming coverage. Plan on quality, never on completeness.

**Mixed-encoding feeds.** German venue feeds that declare a legacy charset often mix in UTF-8 punctuation from a CMS. The repair is *not* to flip the declared encoding — that breaks the fields the legacy decode gets right. Decode as declared, then per text field attempt `text.encode("iso-8859-1").decode("utf-8")` and keep the result **only if it round-trips cleanly**. Genuine `ß`/`ö`/`ä` survive untouched because those single bytes aren't valid UTF-8 lead bytes. Reference implementation: `strassee._fix_mojibake` (P1b). Apply it to whichever fields the feed itself supplies, not to fields parsed from a separate detail page.

**German docs, English planning.** Repo README, code comments and UI are German — match that in code. `SOURCES.md` and this file are English (David's choice).

---

## 8. Supervisor handoff

State as of 2026-09-11, after P0–P4a and PD. Written by the outgoing supervisor for the next one.

**Where things stand — the project changed shape this session.** Eight commits, the last being `8dd2298` (P4a). Working tree clean, 377 smoke checks green. **PD shipped**, so for the first time local `HEAD` and production are not far apart — the seven-commit gap that was called "the single biggest risk" for four sessions is closed, and CT103 runs all 10 sources with the four new venue sources delivering 64 events per run. §8's old "nothing is deployed" paragraph is struck in place; read it once for the lesson (*the gap grew every session that treated deploying as the boring part*) and then leave it.

**The strategic question is answered and must not be reopened.** David asked whether the aggregators could be dropped entirely. Measured: **98.7% of future events are aggregator-only**, and building *every* venue on his list would recover only ~12%. §4.5 now carries the table. The consequence is a reframe the whole backlog should be read through: **venue sources are a quality upgrade on ~12% of the catalogue, not a replacement for anything.** Still worth doing — that 12% is the club and live-music programme with the best covers and real line-ups — but no plan should assume the aggregators are going away.

~~**Your next action: ask David whether he wants P4b or P11 first.**~~ **Answered 2026-09-11: P11 first**, on the reasoning below. P4b is fully unblocked and goes out the moment P11 reports.
- **P4b (Sonnet 5)** — venue entries from §9, now unblocked: the list is first-hand, the kultur-scope question is ruled, and the no-iCal rule is §4.3a. Mechanical.
- **P11 (Opus 5)** — the coverage gap. My recommendation: **run this before P6, and arguably before P4b.** It tests an assumption the entire strategy rests on and that nobody has ever checked — *is a venue's own feed actually more complete than the aggregator's coverage of that venue?* Zentralwerk's ICS returns 20 events while aggregators hold 102 more for the same venue. P2 proved the venue source *wins* collisions; it never proved the feed was *complete*. If it is not, P6's "which adapter to build first" is being chosen on a false premise.

**Decisions already made — do not reopen:**
- Aggregators are permanent (§4.5, measured).
- No new iCal sources (§4.3a, David 2026-09-11). Does **not** apply to the live ICS sources groovestation/zentralwerk — that rule is about per-event iCal downloads on aggregator sites.
- The classical/theatre houses are in scope — "these are Kultur places".
- Orphan deletion stays disabled until P3b-3 arms it. Two logged runs so far, both "keine gefunden". **Its gate is nearly satisfied on the aggregators' run history while the four new sources have only 2 runs each** — arming on that would satisfy the letter of the threshold and miss its point. Say so in P3b-3's kickoff.

~~**Open, needing David:** whether Kuppelhalle Tharandt belongs in the registry.~~ **Answered: keep it, unflagged** (§9). The ten bars in §9 have no confirmed own-site URLs and are `research`, not `todo` — a session must not invent URLs for them.

**What to watch — this is where the value is.**
- **Every analysis packet in this project has disproved its own premise: P3, P3b, P3b-1, P3b-2, P4a, P11.** That is the direct result of briefing each packet by *naming the assumption to test* rather than the change to make. It costs one paragraph and it has paid every single time. Keep doing it. P11 is written that way on purpose.
- **The supervisor is now the most common source of wrong premises — three times.** P3b-2 caught me reading this document's design vocabulary ("tier 0") as a description of code. P4a caught two more in one packet: a brief that said "derive the tier map" *and* "do not introduce tiers", and — worse — §7's claim that `generated_at`/`dataVersion` "always differ and are not a failure", which was **false** and had been quoted into three briefs. It told sessions to excuse the single clearest signal that the §4.4 URL-flapping hazard had fired. **When you write a hazard or a standing fact, say whether you verified it in code or inferred it from this file.** Inferred facts here have a poor record.
- **Beware the vacuous green.** PD's closing chore reported "Pass" on an `export_static.py` ×2 check that compared two *empty* exports — the local DB holds 0 events. The session was honest; the check was hollow. Ask what a passing test would have had to contain to fail.
- **Reports arrive truncated.** Five in a row lost head or tail. "Head first: result, the one finding that matters, follow-ups" fixed it. Keep that line in every kickoff.
- **Measure before escalating.** Twice now a number looked alarming and was fine — the 9-row backfill, and PD's mislabelled health counts. §4.7's rule is *ask "is this delta a defect?" before "is this delta acceptable?"*, and §7's three-numbers entry (run-seen / reach / winner) exists because two legitimate counts got crossed twice in one packet.

## 9. David's venue list — P4b input

**Received verbatim from David 2026-09-11**, replacing the second-hand transcription. All three sections are now captured, including the two that were previously summarised. **42 entries: 27 named venues, 10 bars/smaller locations, 5 aggregators.** ⁽¹⁾ = the one spelling inferred rather than recovered.

⚠️ **DECISION (David, 2026-09-11): the classical/theatre houses are in scope — "these are kultur places".** Kulturpalast, HfM Konzertsaal, Festspielhaus Hellerau, Societaetstheater, Yenidze, Jazzclub Tonne, TheaterRuine St. Pauli, Theaterhaus Rudi all get registry entries. The project's scope is **Kultur in Dresden broadly**, not nightlife. This is a deliberate widening and it has a consequence beyond P4b: the UI chips and `normalize.classify_category` were built around a club/party vocabulary, and a feed containing Klassik, Tanztheater, Lesungen and Travestie will strain both. Flag for the chip-grouping decision (P4b/P7).

⚠️ **Two independent pastes, two different corruptions — the addresses below are RECONSTRUCTED from both, and are the best available text.** David pasted this list twice on 2026-09-11 and the channel mangled it both times, in different ways:
- **Paste 1** dropped every non-ASCII character: `ß`→`B`, umlauts stripped. `Prießnitzstraße` arrived as `PrieBnitzstraBe`, `Schloßstraße` as `SchloBstraBe`, `über` as `uber`.
- **Paste 2** kept the characters but appended a spurious superscript digit to each: `ß³`/`ß²` for `ß`, `ä³³` for `ä`, `u⁴` for `ü`, `Ü³` for `Ü`, `é³³` for `é`. So `Jordanstraß³e`, `Prieß²nitzstraß³e`, `Vollstä³³ndiger`, `Veranstaltungsu⁴bersicht`.

Neither is clean, but **they fail differently, so cross-referencing them recovers the true string with high confidence** — paste 1 confirms where a special character belongs, paste 2 confirms which one it is. The table below holds the reconstruction. **A third paste is not worth requesting**; the channel is the problem, not David's source.

One character could not be recovered from either: paste 2 gives `Königsbrucker Str.` for GrooveStation, which is missing the umlaut in `-brücker` (correct: **Königsbrücker Straße**) — paste 1 has `Konigsbrucker`, so neither source carries it. It is corrected here on the strength of the street being unambiguous, and flagged as the one inferred spelling.

**Still: do not geocode from this table.** Reconstruction is not verification, and the mixed-quality problem below is untouched by it.

⚠️ **Addresses are of mixed quality and are not uniformly geocodable.** Six entries say so outright — Katy's Garage, Der Lude, Cafe Saite, Theaterhaus Rudi, Carte Blanche, StadtKind all carry `(genaue Adresse über Website prüfen)` or similar. Roughly seven more give a *venue name where a street address belongs* (`Saloppe, 01159 Dresden`, `Festspielhaus Hellerau, 01109 Dresden`, `Alter Schlachthof, 01099 Dresden`, `Fortschrittsgelände, 01099 Dresden`, `Kuppelhalle Tharandt, 01762 Tharandt`, `Parkhotel Dresden, 01069 Dresden`, `St. Pauli-Ruine, 01099 Dresden`). Treat `address` as **free text pending verification**, never as a field P9 can geocode unattended. A couple also look internally suspect — `Blaue Fabrik` and `Yenidze Theater` are given adjacent numbers on the same street (`Wilsdruffer Str. 19` / `17`), which may be right but is worth one check before it becomes a map pin.

**The iCal columns below are evidence, not a route — see §4.3a.** `Dresden Nightlife` is named as the per-event iCal source for **Beatpol, Tante JU, GrooveStation, Jazzclub Tonne and Parkhotel**, and `Augusto` is described the same way. When this section was first written the supervisor flagged that as a promising cheap route to several venues at once. **David had already ruled the opposite the same day (§4.3a): no new iCal sources** — one file per event, fetched via an aggregator, for data the venue's own HTML page already shows. Every named venue in this list has an HTML format, so the rule costs nothing.

What the iCal columns are still *good* for is the §4.5 reframe: a venue that an aggregator publishes per-event iCal for is a venue the aggregators already cover well, which is a hint about how much a bespoke scraper would actually add. Record the format as data; do not treat it as an adapter plan. (This rule is about per-event iCal downloads on aggregator sites. It does **not** touch the live ICS sources `groovestation` and `zentralwerk`.)

---

### CLUBS & MUSIKLOCATIONS

| Venue | URL | Address (reconstructed — see warning above) | Format |
|---|---|---|---|
| Chemiefabrik Dresden | https://www.chemiefabrik.de/programm/ | Zwickauer Str. 76, 01069 Dresden | HTML-Liste (Datum, Titel, Preis) |
| Club Puschkin | https://www.clubpuschkin.de/ | Rahnitzgasse 16, 01097 Dresden | HTML-Übersicht |
| Beatpol | https://www.beatpol.de/programm/ | Ostragehege 11, 01067 Dresden | HTML-Programm; **iCal pro Event** |
| Tante JU (Tante-JU Liveclub) | https://www.tante-ju.de/ | Jordanstraße 5, 01099 Dresden | HTML-Programm; **iCal via Dresden Nightlife** |
| OstPol | https://www.ostpol.de/ | Prießnitzstraße 15, 01099 Dresden | HTML-Liste |
| **GrooveStation** *(live — P2)* | https://www.groovestation.de/programm/heute | Königsbrücker Str. 4, 01099 Dresden **⁽¹⁾** | HTML-Programm; **iCal via Dresden Nightlife** |
| objekt klein a (oka) | https://objektkleina.com/ | Prießnitzstraße 9, 01099 Dresden | HTML-Liste (Datum, Titel, Beschreibung, Line-up) |
| Club Paula | https://www.club-paula.de/ | Prießnitzstraße 13, 01099 Dresden | HTML-Programmseite |
| Katy's Garage | *(Aggregatoren: Rausgegangen, Kulturkalender)* | *(nicht eindeutig dokumentiert)* | Einzelne Events auf Aggregatoren |
| Blaue Fabrik | https://www.blaue-fabrik.de/ | Wilsdruffer Str. 19, 01067 Dresden ⚠️ | HTML-Programm (Konzerte, Workshops) |
| Saloppe (Sommerwirtschaft) | https://www.saloppe.de/programm/ | Saloppe, 01159 Dresden ⚠️ | Vollständiger HTML-Kalender (Tabelle) |
| TheaterRuine St. Pauli | https://www.stpauli-ruine.de/ | St. Pauli-Ruine, 01099 Dresden ⚠️ | HTML-Spielplan |
| Festspielhaus Hellerau | https://www.hellerau.org/ | Festspielhaus Hellerau, 01109 Dresden ⚠️ | HTML-Spielplan mit Filtern |
| Kulturpalast Dresden | https://www.kulturpalast-dresden.de/ | Schloßstraße 2, 01067 Dresden | HTML-Programm (Jazz, Klassik, Lesungen) |
| Hochschule für Musik — Konzertsaal | https://www.hfm-dd.de/ | Wettiner Platz 13, 01067 Dresden | HTML-Veranstaltungsübersicht |
| Alter Schlachthof | https://www.alter-schlachthof.de/konzerte/ | Alter Schlachthof, 01099 Dresden ⚠️ | HTML-Konzertübersicht |
| Jazzclub Tonne | https://www.jazzclubtonne.de/de/programm/ | Königstraße 13, 01097 Dresden | HTML-Programm; **iCal via Dresden Nightlife** |
| Societaetstheater | https://www.societaetstheater.de/ | Rahnitzgasse 18, 01097 Dresden | HTML-Spielplan |
| Yenidze Theater | https://yenidze-theater.de/spielplan | Wilsdruffer Str. 17, 01067 Dresden ⚠️ | HTML-Spielplan (Tanztheater, Shows) |
| Gartenlokal Fortschritt | https://www.fortschritt-gartenlokal.de/programm/ | Fortschrittsgelände, 01099 Dresden ⚠️ | Vollständiger HTML-Kalender |
| **Der Lude (Tanzbar)** *(live — P1)* | https://derlude.de/ | Neustadt, Dresden ⚠️ | HTML-Eventliste |
| Parkhotel Dresden (Ballsaal / Kakadu Bar / Blauer Salon / Roter Salon) | https://www.parkhotel-dresden.de/programm/ | Parkhotel Dresden, 01069 Dresden ⚠️ | HTML-Programm; **iCal via Dresden Nightlife/Augusto** |
| Café Saite | https://www.cafe-saite.de/ | Neustadt, Dresden ⚠️ | HTML-Veranstaltungsübersicht |
| Theaterhaus Rudi | https://www.theaterhausrudi.de/ | *(prufen)* ⚠️ | HTML-Spielplan |
| Carte Blanche | *(Kulturkalender / PRINZ)* | *(erfragen)* ⚠️ | HTML-Eventübersicht (Travestie, Shows) |
| Kuppelhalle Tharandt | https://www.kuppelhalle-tharandt.de/ | Kuppelhalle Tharandt, 01762 Tharandt ⚠️ | HTML-Programm (Open-Air-Konzerte) |
| StadtKind Dresden | *(Kulturkalender / eigene Website)* | *(erfragen)* ⚠️ | HTML-Eventübersicht (Festivals, Partys) |

✅ **RULED (David, 2026-09-11): Kuppelhalle Tharandt stays, unflagged.** It is in 01762 Tharandt, not Dresden, so it is the one entry where §4.5's "rank by *Dresden*" heuristic and the list disagree. David was asked directly and chose to keep it as a normal entry — **so it gets an ordinary registry entry, not an out-of-town flag.** Do not quietly deprioritise it the way Meissen tourism was deprioritised; that demotion was about *aggregator noise nobody asked for*, and this is a venue David picked.

### BARS & KLEINERE LOCATIONS

*(Previously missing. Note how thin these are: **9 of 10 have no usable URL**, and most are `HTML-Eventübersicht` with no site named — these are `research` or `unscrapable` candidates, not `todo`.)*

| Venue | URL | Format |
|---|---|---|
| Downtown Dresden | https://dresdennightlife.de/locations/downtown-dresden-1273/ | HTML-Eventseiten; **iCal pro Event** |
| Boys Bar | *(Aggregatoren)* | Einzelne Event-Seiten auf Aggregatoren |
| Felix Rooftop Bar | *(PRINZ)* | Einzelne Event-Ankündigungen |
| HD — Die Rock & Metalbar | *(eigene Website / Aggregatoren)* | HTML-Eventübersicht (Konzerte) |
| Biarritz Club | *(eigene Website / Aggregatoren)* | HTML-Eventübersicht |
| CaveClub | *(eigene Website / Aggregatoren)* | HTML-Eventübersicht |
| Area 29 (Gay Club) | *(eigene Website / Aggregatoren)* | HTML-Eventübersicht |
| Gisela Club | *(eigene Website / Aggregatoren)* | HTML-Eventübersicht |
| fuego club & bar / galaxy | *(eigene Website / Aggregatoren)* | HTML-Eventübersicht |
| H.O.T. Club | *(eigene Website / Aggregatoren)* | HTML-Eventübersicht |

### AGGREGATOREN MIT ICAL-EXPORT

| Aggregator | URL | Format | Status |
|---|---|---|---|
| Dresden Nightlife | https://dresdennightlife.de/ | HTML-Eventseiten; **iCal pro Event** | **not wired** — named as the iCal route for 5 venues above |
| Rausgegangen Dresden | https://rausgegangen.de/ | HTML-Eventseiten (Datum, Ort, Preis) | not wired |
| Kulturkalender Dresden | https://www.kulturkalender-dresden.de/ | HTML-Listen (breite Abdeckung) | **live** |
| Augusto | https://augusto.io/ | HTML-Eventseiten; **iCal pro Event** | not wired |
| PRINZ Dresden | https://prinz.de/dresden/ | HTML-Eventübersicht | not wired |

**Not in this list but already live:** `rauze` (Rauze), `ra` (Resident Advisor), `cybersax` (SAX Terminal), `sektor` (Sektor Evolution), `azconni` (AZ Conni), `strassee` (Straße E), `zentralwerk` (Zentralwerk). The list is additive to what exists, not a replacement for it — **do not remove a live source because it is absent here.**

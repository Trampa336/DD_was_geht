# P5v — store the cybersax contact-card data (address, phone, opening hours)

**Model: Sonnet 5.** Mechanical and fully specified — a schema addition, a parse of data already on
disk, and a template change.

Tree `/home/admin/dd-was-geht/backend`. Python `../.venv/bin/python`. **Commit locally. NEVER push.
NEVER touch CT103 or the live database.** Work against `backend/data/dd-was-geht-v2.db`. A root cron
publishes publicly at 15 1,7,13,19.

**Why this packet exists:** P5u established **[V]** that the 62 still-bare venue pages can never get a
photo — a cybersax address page is a contact card with **no `<img>` at all**, and the venue-homepage
`og:image` path failed at 75%. But those cards carry **postal address, phone and opening hours**, and
`venues` has no column for any of them, so P5u read them and threw them away. David chose to store
them (#23) before hearts: those 62 pages stop being a dead end even without a picture.

## The assumption to test — and it is exactly this project's recurring trap

> **"The address, phone and opening-hours values are already in `data/venue_cache/cybersax_*.json`
> and can be parsed out without refetching anything."**

**[I]. Nobody has verified it.** P5u's report says the *pages* carry those fields — **it does not say
the cache stored them.** A cache that keeps only the fields its parser extracted (`Web:` links) would
not contain them.

**This project has already been burned by exactly this:** `enrich_venues.py`'s docstring claims it
caches raw HTML; **it never wrote any**, and a packet's "verified against raw HTML" claim had to be
retracted. **Open the cache files and look before you plan around them.**

- **If the fields are there:** parse them, zero network requests.
- **If they are not:** say so plainly in your report, then refetch the 74 address pages —
  **respecting the mandated 1.2s request delay**, ~5 minutes at the measured pace. Do not invent a
  value that is not on the page, and do not silently switch to refetching without reporting it.

## What to store

Add columns to `venues` for **postal address**, **phone**, and **opening hours**. Populate for all
**74** venues P5u fetched (not only the 62 still bare).

- **Declare the new columns in `migrations/001_schema_v2.sql`.** **[V]** precedent: P5a's
  `homepage_root`/`cover_source` are in the DDL, and P5b verified a fresh DB from the DDL has them.
  Make sure that stays true here, and that an existing DB is handled too.
- **Store opening hours as the source's own text.** Do not parse them into a structured schedule, do
  not normalise them, do not fill gaps. Structuring implies a precision the source does not have.
- **Record when each value was captured**, and render opening hours **with that date visible**.

## Why the date matters — read this before you design the template

**Opening hours go stale, and this publishes to a public website about real small businesses in
Dresden.** An address or a phone number ages slowly. A six-month-old "Mo–Fr 10–18" on a bar that has
since changed its hours sends a real person to a locked door on your say-so. **Showing the capture
date is what makes it honest** — the reader can judge it. Address and phone render plainly; opening
hours render dated. If that turns out awkward in the template, **report it rather than quietly
dropping the date.**

## The standing anti-fabrication rule still applies

**Store only what is literally on the card.** Never write, complete, tidy or infer a value from your
own knowledge or from the venue's name. A missing field is missing. Two workers have now held this
line correctly, and P5u caught two cases that prove why: a church description that was actually about
the *neighbourhood*, and one whose opening paragraph ends at the failed rebuild attempts — publishing
it alone would have told readers **the church is a ruin**.

## Also fix, while you are in the venue template

**[V]** `app/templates/venue.html` prints "Aus Dresdner Veranstaltungskalendern **und der Homepage der
Venue**" whenever `meta_status` is non-NULL. That is **false for the 43 of these 74 that have no
homepage**, and was already false for every `not_found` venue. **It is a provenance claim on a public
page.** Make it say what is actually true for that venue.

## Do not touch

- The cover fallback order (`kk_cover_url` first, homepage `og:image` second) — two stored og:image
  URLs are already dead.
- P5b's event-image fallback — it is why the bare count is 62 and not 277.
- `enrichment.json` — the smoke suite asserts it stays untouched.
- Hearts, visitor likes, `reactions`/`apply_reaction`/`/api/feedback`, `score`. **Next packet.**

## Gates

- `../.venv/bin/python tests_smoke.py` green — **stands at 454 checks / 0 failures.** Name any
  assertion you change and why.
- `git status --short` clean, committed locally. Commits end
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Repo code, comments and UI are **German**. Planning docs English.
- Mark every fact **[V]** (say how) or **[I]**. **Any rate needs its denominator.** **Six figures in
  this project have failed to reproduce** — if one you are handed does not reproduce, report it.
  **Do not trust a tool's printed summary without re-deriving the predicate**; P5u added a regression
  guard for exactly that after a report printed a false "0 truly bare".

## Report — head first

1. **result** — whether the cache held the fields, how many of the 74 now have an address / phone /
   hours, and the bare-page count over all 726 before and after.
2. **the one finding that matters** — what this changes for hearts.
3. **follow-ups** — including every venue left without contact data, and anything you declined to store.

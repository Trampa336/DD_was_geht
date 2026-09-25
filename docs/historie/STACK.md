# dd-was-geht — deployment stack (quick reference)

Ops-level orientation for this specific deployment on `leo`/CT103. For what the
app *does* (scoring, sources, scraper internals, GitHub Pages setup), see
[`README.md`](README.md) in this same directory — that one ships with the
GitHub repo and is the authoritative app doc. This file is deployment-local,
not part of the repo, and won't survive a `git pull` (there's no `.git` here
anyway — this directory is a plain deployed copy, not a clone).

## Where this lives

- Host: Proxmox node `leo` → CT103 (`192.168.178.91`), the general-purpose
  Docker host — **not** a dedicated LXC. CT103 also runs other unrelated
  Docker stacks; don't assume everything under `docker ps` here belongs to
  this project.
- Project dir: `/opt/dd-was-geht/`
- CT103 sits in the host's nightly `vzdump` backup job — this whole directory
  is covered automatically, no separate backup needed.

## Directory layout

```
/opt/dd-was-geht/
├── app/                  # Flask app + scraper + scheduler + scoring
├── data/                 # bind-mounted into the container as /app/data
│   ├── dd-was-geht.db    # SQLite, all scraped/rated events
│   ├── site/             # static export, regenerated each publish run
│   └── publish.log       # cron job output (see below)
├── tools/
│   ├── export_static.py  # renders data/site/ from the DB (runs IN container)
│   ├── publish_site.sh   # rsync+commit+push data/site/ to GitHub Pages (runs on HOST)
│   ├── reclassify.py, show_duplicates.py, inspect_source.py  # maintenance/debug scripts
├── .env                  # real config (not in git); .env.example has the template
├── docker-compose.yml
├── Dockerfile
├── main.py               # entrypoint: startup scrape check → scheduler → web server
├── requirements.txt
├── tests_smoke.py
└── README.md             # full app documentation (German)
```

## The container

- One service, `docker-compose.yml`, container name `dd-was-geht`, built from
  the local `Dockerfile` (`python:3.12-slim`).
- Port: host `1111` → container `8080` (Flask). Web UI:
  `http://192.168.178.91:1111` — home-network only, not exposed further.
- `TZ=Europe/Berlin` is set explicitly (base image defaults to UTC — this bit
  the scheduler and the "today" date logic once already, see the comment in
  `docker-compose.yml`).
- Volume: `./data:/app/data` — this is the *only* persistent state; the image
  itself is stateless/rebuildable.
- `restart: unless-stopped`.

Runtime behavior worth knowing before you go debugging: on container start,
`main.py` only re-scrapes if the last successful scrape is >6h old (otherwise
a crash-loop would hammer the source sites on every restart). Normal operation
scrapes via an in-process APScheduler every 6h regardless.

## The publish pipeline (GitHub Pages)

Two GitHub repos under `Trampa336`:
- `dd-was-geht` — this backend
- `DD_was_geht` — static frontend, published at
  https://trampa336.github.io/DD_was_geht/ (read-only, no rating buttons)

Flow, root's crontab on the CT103 **host OS** (not in the container):
```
15 1,7,13,19 * * * /opt/dd-was-geht/tools/publish_site.sh >> /opt/dd-was-geht/data/publish.log 2>&1
```
(45 min after each 6-hourly scrape.) The script:
1. `docker exec dd-was-geht python3 tools/export_static.py` → writes into
   `data/site/` (bind-mounted, so the host sees it immediately)
2. Refuses to continue if the export looks incomplete (empty index / <1 day
   of data) — protects against `rsync --delete` wiping the live public site
3. `rsync --delete` into `/root/dd-was-geht-site` (the site repo clone)
4. commit + push, using the deploy key at `/root/.ssh/dd-was-geht-deploy`
   (SSH config alias `github-dd` in `/root/.ssh/config`, write access to
   `DD_was_geht` only — unrelated to the read-only key used elsewhere to
   clone both repos onto host `leo` itself)

## Common commands (run inside CT103, e.g. via `pct exec 103 -- bash`)

```bash
cd /opt/dd-was-geht

# logs / status
docker compose logs -f --tail 100
docker ps --filter name=dd-was-geht
tail -f data/publish.log

# restart / rebuild after a code change
docker compose up -d --build

# force a static export + publish manually (normally cron-only)
tools/publish_site.sh

# poke the DB directly
sqlite3 data/dd-was-geht.db
```

## Related paths outside CT103

- Read-only reference clones of both repos on host `leo`:
  `/home/admin/dd-was-geht/{backend,frontend}` (not used at runtime, just for
  browsing/editing from the Proxmox host without going into the container).

#!/usr/bin/env bash
# Veroeffentlicht den Kalender als statische Seite auf GitHub Pages.
#
# Laeuft auf dem PI-HOST (nicht im Container): exportieren laesst sich nur im
# Container (dort liegen Python-Abhaengigkeiten und die DB), gepusht wird vom
# Host (dort liegt der Deploy-Key).
#
#   1. Export im Container   -> data/site/   (Bind-Mount, landet direkt hier)
#   2. rsync in das Site-Repo
#   3. commit + push         -> GitHub Pages baut die Seite neu
#
# Einrichtung (einmalig, siehe README "Oeffentliche Seite fuer Freunde"):
#   ssh-keygen -t ed25519 -f ~/.ssh/dd-was-geht-deploy -N ""
#   Pubkey bei GitHub als Deploy Key MIT Schreibrecht eintragen
#   git clone git@github-dd:<user>/DD_was_geht.git ~/dd-was-geht-site
#
# Cron (45 min nach jedem Scrape, der um */6:30 laeuft):
#   15 1,7,13,19 * * * /home/pi/dd-was-geht/tools/publish_site.sh >> /home/pi/dd-was-geht/data/publish.log 2>&1

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_REPO="${SITE_REPO:-$HOME/dd-was-geht-site}"
CONTAINER="${CONTAINER:-dd-was-geht}"
EXPORT_DIR="$PROJECT_DIR/data/site"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

if [[ ! -d "$SITE_REPO/.git" ]]; then
    log "FEHLER: $SITE_REPO ist kein Git-Repo. Siehe README, Abschnitt 'Oeffentliche Seite fuer Freunde'."
    exit 1
fi

log "Export im Container ..."
docker exec "$CONTAINER" python3 tools/export_static.py --out /app/data/site

# Schutz vor dem schlimmsten Fall: ein halber oder leerer Export wuerde per
# rsync --delete die oeffentliche Seite loeschen. Lieber gar nicht pushen.
DAYS=$(find "$EXPORT_DIR/data/days" -name '*.json' 2>/dev/null | wc -l)
if [[ ! -s "$EXPORT_DIR/index.html" || ! -s "$EXPORT_DIR/data/index.json" || "$DAYS" -lt 1 ]]; then
    log "FEHLER: Export unvollstaendig ($DAYS Tagesdateien) - es wird nichts veroeffentlicht."
    exit 1
fi

log "Uebernehme $DAYS Tagesdateien nach $SITE_REPO ..."
rsync -a --delete --exclude '.git' "$EXPORT_DIR/" "$SITE_REPO/"

cd "$SITE_REPO"
git add -A
if git diff --cached --quiet; then
    log "Nichts geaendert - kein Commit noetig."
    exit 0
fi

git commit -q -m "Kalender-Stand $(date '+%Y-%m-%d %H:%M')"
git push -q -u origin HEAD
log "Veroeffentlicht: $(git rev-parse --short HEAD)"

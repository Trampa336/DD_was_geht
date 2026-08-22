#!/usr/bin/env bash
# Update-Helfer: neue Version einspielen, ohne Datenbank oder .env zu verlieren.
#
# Ablauf auf dem Pi:
#   1. Neues Zip nach ~/ kopieren (scp vom Laptop)
#   2. cd ~/dd-was-geht && ./update.sh ~/2026-XX-XX-dd-was-geht-pi-service.zip
#
# .env, data/ und die gepflegte Subreddit-Liste bleiben unangetastet.

set -euo pipefail

ZIP="${1:-}"
if [[ -z "$ZIP" || ! -f "$ZIP" ]]; then
    echo "Nutzung: ./update.sh /pfad/zum/neuen-paket.zip"
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "==> Sichere .env, Datenbank und Konfiguration"
BACKUP="../dd-was-geht-backup-$(date +%Y-%m-%d-%H%M%S)"
mkdir -p "$BACKUP"
[[ -f .env ]] && cp .env "$BACKUP/"
[[ -d data ]] && cp -r data "$BACKUP/"
[[ -d config ]] && cp -r config "$BACKUP/"
echo "    Backup liegt unter: $BACKUP"

echo "==> Entpacke neue Version (überschreibt Code, NICHT .env/data/config)"
TMP="$(mktemp -d)"
unzip -q "$ZIP" -d "$TMP"
# Das Zip enthält einen Ordner 'dd-was-geht/' - dessen Inhalt kopieren.
# config/ ist ausgenommen, sonst würde die selbst gepflegte Subreddit-Liste
# durch die leere Vorlage aus dem Paket ersetzt.
rsync -a --exclude '.env' --exclude 'data/' --exclude 'config/' \
    "$TMP/dd-was-geht/" "$PROJECT_DIR/"
# Neue Vorlagen trotzdem bereitstellen, falls es config/ noch gar nicht gibt
mkdir -p "$PROJECT_DIR/config"
for f in "$TMP/dd-was-geht/config/"*; do
    [[ -e "$f" && ! -e "$PROJECT_DIR/config/$(basename "$f")" ]] && cp "$f" "$PROJECT_DIR/config/"
done
rm -rf "$TMP"

echo "==> Baue Container neu und starte"
docker compose up --build -d

echo "==> Fertig. Logs mit:  docker compose logs -f"

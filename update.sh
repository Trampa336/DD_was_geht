#!/usr/bin/env bash
# Update-Helfer: neue Version einspielen, ohne Datenbank oder .env zu verlieren.
#
# Ablauf auf dem Pi:
#   1. Neues Zip nach ~/ kopieren (scp vom Laptop)
#   2. cd ~/dd-was-geht && ./update.sh ~/2026-XX-XX-dd-was-geht-pi-service.zip
#
# .env und data/ bleiben unangetastet.

set -euo pipefail

ZIP="${1:-}"
if [[ -z "$ZIP" || ! -f "$ZIP" ]]; then
    echo "Nutzung: ./update.sh /pfad/zum/neuen-paket.zip"
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "==> Sichere .env und Datenbank"
BACKUP="../dd-was-geht-backup-$(date +%Y-%m-%d-%H%M%S)"
mkdir -p "$BACKUP"
[[ -f .env ]] && cp .env "$BACKUP/"
[[ -d data ]] && cp -r data "$BACKUP/"
echo "    Backup liegt unter: $BACKUP"

echo "==> Entpacke neue Version (überschreibt Code, NICHT .env/data)"
TMP="$(mktemp -d)"
unzip -q "$ZIP" -d "$TMP"
# Das Zip enthält einen Ordner 'dd-was-geht/' - dessen Inhalt kopieren.
rsync -a --exclude '.env' --exclude 'data/' \
    "$TMP/dd-was-geht/" "$PROJECT_DIR/"
rm -rf "$TMP"

echo "==> Baue Container neu und starte"
docker compose up --build -d

echo "==> Fertig. Logs mit:  docker compose logs -f"

#!/usr/bin/env bash
# Veroeffentlicht den Kalender als statische Seite auf GitHub Pages.
#
# Ziel ist ein einziges, eigenes Repo fuer die Seite selbst
# (github.com/Trampa336/DD_was_geht), Ausgabe an dessen WURZEL - so wie es
# schon vor P6a lief und wie es seit Entscheidung #29 wieder gilt.
#
# Zwischenzeitlich (P6a) sollten Quellcode UND gebaute Seite ein gemeinsames
# Repo teilen, die Seite unter docs/ - weil GitHub Pages' "deploy from a
# branch" nur / und /docs kennt. David hat sich dagegen entschieden
# (Entscheidung #29): GitHub behaelt NUR die oeffentliche Seite, unveraendert,
# der Quellcode zieht auf einen eigenen Forgejo-Server um (eigenes Paket,
# eigener Cutover). Es gibt also KEINE Zusammenlegung mehr - dieses Skript
# schreibt wieder direkt in das Seiten-Repo, wie am Anfang des Projekts.
#
# SITE_SUBDIR bleibt trotzdem eine Variable (Voreinstellung: leer = Wurzel),
# statt hart auf die Wurzel verdrahtet zu sein - siehe die Pruefung unten, wo
# das erklaert ist.
#
# Die Ausgabe ist relativ verlinkt (tools/export_static.py:_static_urls) und
# funktioniert unveraendert, egal ob sie an der Repo-Wurzel oder (SITE_SUBDIR)
# in einem Unterverzeichnis landet.
#
# Laeuft auf dem HOST von CT103, nicht im Container: exportieren laesst sich nur
# im Container (dort liegen Python-Abhaengigkeiten und die DB, und /app/data ist
# der einzige Pfad, den der Host ueberhaupt zu sehen bekommt), gepusht wird vom
# Host (dort liegt der Deploy-Key).
#
#   1. Export im Container      -> data/site/   (Bind-Mount, landet direkt hier)
#   2. Vollstaendigkeit pruefen  (ein halber Export wuerde die Seite leeren)
#   3. Klon hart auf origin ziehen
#   4. rsync in die Repo-Wurzel (oder SITE_SUBDIR, falls gesetzt)
#   5. commit + push            -> GitHub Pages baut die Seite neu
#
# Probelauf ohne Docker und ohne Push - genau so laesst sich der Weg lokal fahren:
#   EXPORT_MODE=lokal PYTHON=../.venv/bin/python DRY_RUN=1 \
#     SITE_REPO=/pfad/zum/klon tools/publish_site.sh
#
# Einrichtung (einmalig, siehe README "Oeffentliche Seite fuer Freunde") -
# unveraendert gegenueber der Fassung vor P6a, denn es ist dasselbe Repo:
#   ssh-keygen -t ed25519 -f ~/.ssh/dd-was-geht-deploy -N ""
#   Pubkey bei GitHub AM REPO DD_was_geht als Deploy Key MIT Schreibrecht eintragen
#   ~/.ssh/config:
#       Host github-dd
#           HostName github.com
#           User git
#           IdentityFile ~/.ssh/dd-was-geht-deploy
#   git clone git@github-dd:Trampa336/DD_was_geht.git ~/dd-was-geht-site
#
# Cron (45 min nach jedem Scrape, der um */6:30 laeuft):
#   15 1,7,13,19 * * * /opt/dd-was-geht/tools/publish_site.sh >> /opt/dd-was-geht/data/publish.log 2>&1

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_REPO="${SITE_REPO:-$HOME/dd-was-geht-site}"
SITE_SUBDIR="${SITE_SUBDIR:-}"
BRANCH="${BRANCH:-main}"
CONTAINER="${CONTAINER:-dd-was-geht}"
EXPORT_MODE="${EXPORT_MODE:-container}"
PYTHON="${PYTHON:-python3}"
DRY_RUN="${DRY_RUN:-0}"
# Im Container-Betrieb ist das der Bind-Mount-Gegenpart zu /app/data/site und
# darf sich nicht aendern; ueberschreibbar ist er nur, damit sich die
# Vollstaendigkeits-Pruefung unten ueberhaupt testen laesst (tests_smoke.py).
EXPORT_DIR="${EXPORT_DIR:-$PROJECT_DIR/data/site}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
fail() { log "FEHLER: $*"; exit 1; }

# SITE_SUBDIR ist seit Entscheidung #29 in der Voreinstellung LEER (= die
# Ausgabe landet an der Repo-Wurzel, wie im laufenden Betrieb). Zu P6a-Zeiten
# stand hier "docs", weil Quellcode und Seite ein Repo teilten - das ist mit
# der Ruecknahme der Zusammenlegung nicht mehr noetig. Die Variable bleibt
# trotzdem bestehen (re-scoped, nicht entfernt): ein GEFUELLTER, aber
# gefaehrlicher Wert (ein fuehrendes "/", ein herausfuehrendes "..") waere
# immer noch die eine Zeile, die rsync --delete auf das falsche Verzeichnis
# zeigen liesse. Nur "leer" ist jetzt kein Fehler mehr, sondern der Normalfall.
[[ -z "$SITE_SUBDIR" || "$SITE_SUBDIR" =~ ^[A-Za-z0-9_-]+$ ]] \
    || fail "SITE_SUBDIR='$SITE_SUBDIR' ist kein einfacher Ordnername (leer = Repo-Wurzel)."
[[ -d "$SITE_REPO/.git" ]] || fail "$SITE_REPO ist kein Git-Repo. Siehe Kopf dieser Datei."

# Zeigt der Klon auch wirklich auf die OEFFENTLICHE Seite? Unter Entscheidung
# #29 bleibt DD_was_geht das einzige Repo, in das dieses Skript je schreiben
# soll. Ein liegen gebliebener Klon des waehrend P6a kurz geplanten
# Quellcode/Seite-Repos (dd-was-geht, mit Bindestrich statt Unterstrich)
# wuerde sonst klaglos weiterbedient, und die Ruecknahme der Zusammenlegung
# waere nur scheinbar passiert.
ORIGIN_URL="$(git -C "$SITE_REPO" remote get-url origin)"
[[ "$ORIGIN_URL" == *DD_was_geht* ]] \
    || fail "origin von $SITE_REPO ist '$ORIGIN_URL' - erwartet wird DD_was_geht (Entscheidung #29)."

log "Export ($EXPORT_MODE) ..."
case "$EXPORT_MODE" in
    container)
        docker exec "$CONTAINER" python3 tools/export_static.py --out /app/data/site
        ;;
    lokal)
        # Derselbe Aufruf ohne Docker. Nur damit laesst sich dieser Weg
        # ueberhaupt ausserhalb von CT103 durchspielen - siehe Kopf.
        ( cd "$PROJECT_DIR" && "$PYTHON" tools/export_static.py --out "$EXPORT_DIR" )
        ;;
    *)
        fail "EXPORT_MODE='$EXPORT_MODE' - erlaubt sind 'container' und 'lokal'."
        ;;
esac

# Schutz vor dem schlimmsten Fall: ein halber oder leerer Export wuerde per
# rsync --delete die oeffentliche Seite leeren. Lieber gar nicht pushen.
# Geprueft werden alle vier Oberflaechen, nicht nur die Startseite: Liste,
# kuratierte Seite (Entscheidung #27), Orte-Index, Tagesdateien.
# Erst pruefen, dann zaehlen: fehlt data/days ganz, liefert find einen Fehler,
# den `set -o pipefail` in den Rueckgabewert der Zuweisung durchreicht - und
# `set -e` beendet das Skript an dieser Zeile, ohne eine einzige Zeile ins
# Cron-Log zu schreiben. Genau so stand es schon in der Fassung vor P6a; im
# Alltag faellt es nie auf, weil data/days immer existiert. Am Tag des Umzugs,
# an dem das Verzeichnis zum ersten Mal woanders liegt, waere es der teuerste
# denkbare stille Abbruch.
DAYS=0
if [[ -d "$EXPORT_DIR/data/days" ]]; then
    DAYS=$(find "$EXPORT_DIR/data/days" -name '*.json' | wc -l)
fi
for datei in index.html herzen.html orte/index.html data/index.json; do
    [[ -s "$EXPORT_DIR/$datei" ]] || fail "Export unvollstaendig: $datei fehlt oder ist leer."
done
# .nojekyll ist absichtlich 0 Byte gross, deshalb -e statt -s. Ohne sie
# ignoriert GitHub Pages Dateien mit fuehrendem Unterstrich.
[[ -e "$EXPORT_DIR/.nojekyll" ]] || fail "Export unvollstaendig: .nojekyll fehlt."
[[ "$DAYS" -ge 1 ]] || fail "Export unvollstaendig ($DAYS Tagesdateien)."

# TARGET_DIR/GIT_PATH fassen zusammen, wohin rsync schreibt und welcher Pfad
# bei git add/diff/clean gilt. Bei leerem SITE_SUBDIR (Normalfall seit #29)
# ist das Ziel die Repo-Wurzel selbst und "." der Pfad dafuer; ist SITE_SUBDIR
# gesetzt, gilt weiterhin genau das Verhalten aus der P6a-Fassung.
if [[ -n "$SITE_SUBDIR" ]]; then
    TARGET_DIR="$SITE_REPO/$SITE_SUBDIR"
    GIT_PATH="$SITE_SUBDIR"
else
    TARGET_DIR="$SITE_REPO"
    GIT_PATH="."
fi

# Der Klon auf CT103 ist Wegwerf-Arbeitsplatz, kein Arbeitsbaum: der Inhalt
# entsteht bei jedem Lauf neu. Deshalb VOR dem Schreiben hart auf origin ziehen.
#
# Die urspruengliche Begruendung dafuer (P6a) war ein zusammengelegtes Repo
# mit zwei Schreibern - Quellcode-Pushes von ueberall UND dieser Cronjob.
# Diese Begruendung gilt mit Entscheidung #29 NICHT MEHR: das Seiten-Repo
# (DD_was_geht) hat, wie schon vor P6a, ausser diesem Cronjob keinen zweiten
# Schreiber. Der fetch+reset bleibt trotzdem stehen, als guenstige
# Absicherung gegen einen Klon, der aus irgendeinem anderen Grund (ein
# manueller Eingriff, ein Rest von einem vorigen Fehlschlag) von origin
# abweicht - er kostet im Normalfall nichts.
log "Klon auf origin/$BRANCH ziehen ..."
git -C "$SITE_REPO" fetch -q origin "$BRANCH"
git -C "$SITE_REPO" checkout -q "$BRANCH"
git -C "$SITE_REPO" reset -q --hard "origin/$BRANCH"
git -C "$SITE_REPO" clean -qfd -- "$GIT_PATH"

mkdir -p "$TARGET_DIR"
log "Uebernehme $DAYS Tagesdateien nach $TARGET_DIR ..."
# --exclude '.git': an der Repo-Wurzel (SITE_SUBDIR leer, der Normalfall seit
# #29) liegt .git GENAU im rsync-Ziel. Ohne den Ausschluss wuerde --delete es
# bei jedem Lauf als "nicht mehr in der Quelle vorhanden" wegraeumen - die
# Ausgabe von export_static.py enthaelt naturgemaess kein .git. Bei gesetztem
# SITE_SUBDIR liegt .git ohnehin eine Ebene hoeher; der Ausschluss ist dann
# wirkungslos, aber unschaedlich.
rsync -a --delete --exclude '.git' "$EXPORT_DIR/" "$TARGET_DIR/"

cd "$SITE_REPO"
# GIT_PATH ist derselbe Pfad wie beim rsync-Ziel oben. An der Repo-Wurzel
# (".") macht das inhaltlich keinen Unterschied zu einem plumpen "git add -A"
# mehr - das Seiten-Repo enthaelt seit Entscheidung #29 ohnehin nur noch die
# Ausgabe, keinen Quellcode. Der Pfad bleibt trotzdem ausdruecklich benannt:
# sollte SITE_SUBDIR je wieder gesetzt werden (etwa fuer ein gemeinsames Repo
# wie zu P6a-Zeiten), gilt dieselbe Grenze wie damals - "git add -A" ohne
# Pfad wuerde dann auch Quellcode-Aenderungen mitnehmen, die auf CT103 liegen
# blieben.
git add -A -- "$GIT_PATH"
if git diff --cached --quiet; then
    log "Nichts geaendert - kein Commit noetig."
    exit 0
fi

GEAENDERT=$(git diff --cached --numstat -- "$GIT_PATH" | wc -l)
if [[ "$DRY_RUN" == "1" ]]; then
    log "DRY_RUN=1: kein Commit, kein Push. Anstehen wuerden $GEAENDERT Dateien:"
    git diff --cached --shortstat -- "$GIT_PATH"
    git reset -q
    exit 0
fi

git commit -q -m "Kalender-Stand $(date '+%Y-%m-%d %H:%M')"
git push -q origin "HEAD:$BRANCH"
log "Veroeffentlicht: $(git rev-parse --short HEAD) ($GEAENDERT Dateien)"

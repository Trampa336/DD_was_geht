#!/usr/bin/env bash
# Veroeffentlicht den Kalender als statische Seite auf GitHub Pages.
#
# EIN Repo (P6, Entscheidung #9): Quellcode UND gebaute Seite liegen ab jetzt
# beide in github.com/Trampa336/dd-was-geht. Die Seite steht dort unter docs/,
# die URL wird https://<user>.github.io/dd-was-geht/.
#
# Warum docs/ - und nicht die Wurzel, nicht ein zweiter Branch, keine Action:
#   * GitHub Pages kennt bei "deploy from a branch" genau zwei Wurzeln: / und
#     /docs. / wuerde den kompletten Quellbaum als Website ausliefern (app/,
#     tools/, tests_smoke.py, README.md). docs/ trennt Ausgabe von Quelle,
#     ohne dass irgendwo ein zweiter Ort gepflegt werden muss.
#   * Ein orphan-Branch gh-pages haelt die vier taeglichen Diffs aus der
#     Historie von main heraus - der einzige echte Vorteil, und er kostet einen
#     zweiten Arbeitsbaum in einem Skript, das als root im Cron laeuft. Wenn
#     die Historie von main durch die Seite unertraeglich wird, ist DAS der
#     Ausweg; gemessen ist er derzeit nicht noetig (P6a).
#   * Eine GitHub Action koennte die Seite gar nicht bauen: dazu braeuchte sie
#     die Datenbank, und die verlaesst das Heimnetz nicht.
#
# Die Ausgabe ist relativ verlinkt (tools/export_static.py:_static_urls) und
# funktioniert in einem Unterverzeichnis unveraendert.
#
# Laeuft auf dem HOST von CT103, nicht im Container: exportieren laesst sich nur
# im Container (dort liegen Python-Abhaengigkeiten und die DB, und /app/data ist
# der einzige Pfad, den der Host ueberhaupt zu sehen bekommt), gepusht wird vom
# Host (dort liegt der Deploy-Key).
#
#   1. Export im Container      -> data/site/   (Bind-Mount, landet direkt hier)
#   2. Vollstaendigkeit pruefen  (ein halber Export wuerde die Seite leeren)
#   3. Klon hart auf origin ziehen
#   4. rsync nach $SITE_REPO/docs/
#   5. commit + push            -> GitHub Pages baut die Seite neu
#
# Probelauf ohne Docker und ohne Push - genau so hat P6a den Weg lokal gefahren:
#   EXPORT_MODE=lokal PYTHON=../.venv/bin/python DRY_RUN=1 \
#     SITE_REPO=/pfad/zum/klon tools/publish_site.sh
#
# Einrichtung (einmalig):
#   ssh-keygen -t ed25519 -f ~/.ssh/dd-was-geht-repo-deploy -N ""
#   Pubkey bei GitHub AM REPO dd-was-geht als Deploy Key MIT Schreibrecht
#   ~/.ssh/config:
#       Host github-dd-repo
#           HostName github.com
#           User git
#           IdentityFile ~/.ssh/dd-was-geht-repo-deploy
#   git clone git@github-dd-repo:Trampa336/dd-was-geht.git ~/dd-was-geht-repo
#
#   ACHTUNG, der Grund fuer den ZWEITEN Schluessel: ein Deploy-Key gilt bei
#   GitHub genau einem Repository. Der alte ~/.ssh/dd-was-geht-deploy bleibt
#   deshalb unangetastet am alten Seiten-Repo haengen - und genau darum bleibt
#   der alte Weg bis zum letzten Schritt zurueckrollbar.
#
# Cron (45 min nach jedem Scrape, der um */6:30 laeuft):
#   15 1,7,13,19 * * * /opt/dd-was-geht/tools/publish_site.sh >> /opt/dd-was-geht/data/publish.log 2>&1

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_REPO="${SITE_REPO:-$HOME/dd-was-geht-repo}"
SITE_SUBDIR="${SITE_SUBDIR:-docs}"
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

# rsync --delete zeigt gleich auf $SITE_REPO/$SITE_SUBDIR. Ein leerer, ein
# absoluter oder ein herausfuehrender Wert machte daraus ein Loeschen des halben
# Repos - das ist die eine Zeile hier, die wirklich weh tun kann.
[[ "$SITE_SUBDIR" =~ ^[A-Za-z0-9_-]+$ ]] \
    || fail "SITE_SUBDIR='$SITE_SUBDIR' ist kein einfacher Ordnername."
[[ -d "$SITE_REPO/.git" ]] || fail "$SITE_REPO ist kein Git-Repo. Siehe Kopf dieser Datei."

# Zeigt der Klon auch wirklich auf das ZUSAMMENGEFUEHRTE Repo? Ein liegen
# gebliebener Klon des alten Seiten-Repos wuerde sonst klaglos weiterbedient,
# und der Umzug waere nur scheinbar passiert.
ORIGIN_URL="$(git -C "$SITE_REPO" remote get-url origin)"
[[ "$ORIGIN_URL" == *dd-was-geht* && "$ORIGIN_URL" != *DD_was_geht* ]] \
    || fail "origin von $SITE_REPO ist '$ORIGIN_URL' - erwartet wird dd-was-geht."

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

# Der Klon auf CT103 ist Wegwerf-Arbeitsplatz, kein Arbeitsbaum: der Inhalt von
# docs/ entsteht bei jedem Lauf neu. Deshalb VOR dem Schreiben hart auf origin
# ziehen. Ohne das scheitert der Push in dem Moment, in dem David von woanders
# am Quellcode etwas pusht - und zwar still, in einem Cron-Log, das niemand
# liest. Das ist die neue Fehlerquelle, die das Zusammenlegen mitbringt: das
# alte Seiten-Repo hatte ausser dem Cron keinen zweiten Schreiber.
log "Klon auf origin/$BRANCH ziehen ..."
git -C "$SITE_REPO" fetch -q origin "$BRANCH"
git -C "$SITE_REPO" checkout -q "$BRANCH"
git -C "$SITE_REPO" reset -q --hard "origin/$BRANCH"
git -C "$SITE_REPO" clean -qfd -- "$SITE_SUBDIR"

mkdir -p "$SITE_REPO/$SITE_SUBDIR"
log "Uebernehme $DAYS Tagesdateien nach $SITE_REPO/$SITE_SUBDIR ..."
# Kein --exclude '.git' mehr noetig: das Ziel ist ein Unterordner, das Repo
# liegt eine Ebene darueber. --delete raeumt damit nur noch die Seite auf, nie
# den Quellbaum daneben.
rsync -a --delete "$EXPORT_DIR/" "$SITE_REPO/$SITE_SUBDIR/"

cd "$SITE_REPO"
# Nur den Ausgabeordner anfassen. Ein "git add -A" wuerde in diesem Repo auch
# Quellcode-Aenderungen mitnehmen, die jemand auf CT103 hinterlassen hat.
git add -A -- "$SITE_SUBDIR"
if git diff --cached --quiet; then
    log "Nichts geaendert - kein Commit noetig."
    exit 0
fi

GEAENDERT=$(git diff --cached --numstat -- "$SITE_SUBDIR" | wc -l)
if [[ "$DRY_RUN" == "1" ]]; then
    log "DRY_RUN=1: kein Commit, kein Push. Anstehen wuerden $GEAENDERT Dateien:"
    git diff --cached --shortstat -- "$SITE_SUBDIR"
    git reset -q
    exit 0
fi

git commit -q -m "Kalender-Stand $(date '+%Y-%m-%d %H:%M')"
git push -q origin "HEAD:$BRANCH"
log "Veroeffentlicht: $(git rev-parse --short HEAD) ($GEAENDERT Dateien)"

"""Taegliche Sicherung der Datenbank.

Warum ueberhaupt: die Reaktionen sind das persoenliche Lernmodell und
entstehen nur durch Klicks - erneutes Scrapen stellt sie NICHT wieder her.
Das Homelab-Skript (scripts/docker-backup.sh) sichert ausschliesslich
$HOME/docker, dieses Verzeichnis lag also noch nie in einer Sicherung. Die
sechs von Hand angelegten .bak-Dateien in data/ zeigen, wie oft der Bedarf
schon da war.

Warum kein Dateikopieren: die Datenbank laeuft im WAL-Modus (app/db.py), ein
`cp` waehrend eines Schreibvorgangs ergaebe eine Datei ohne die Aenderungen,
die noch im WAL stehen. sqlite3.Connection.backup() nimmt die noetigen Sperren
selbst und darf deshalb im laufenden Betrieb arbeiten.

Ehrliche Grenze: das ist EINE Platte. Gegen einen Ausfall der SSD hilft es
nicht. Es schuetzt gegen die Fehler, die dieses Projekt real getroffen haben -
Korruption, missglueckte Migration, verunglueckter Dedup-Lauf.
"""
import glob
import logging
import os
import sqlite3
from datetime import date

from . import config

logger = logging.getLogger("dd-was-geht.backup")

# Nur Dateien nach diesem Muster gelten als eigene Sicherung. Alles andere im
# Verzeichnis fasst die Rotation nicht an.
SNAPSHOT_GLOB = "dd-was-geht-*.db"


def backup_dir():
    """Sicherungen liegen neben der Datenbank, damit sie derselbe Docker-Mount
    mitnimmt - eine zweite Volume-Zeile waere eine zusaetzliche Stelle, an der
    ein Deploy sie vergessen kann."""
    return os.path.join(os.path.dirname(config.DB_PATH) or ".", "backups")


def create_backup(keep=None, today=None):
    """Schreibt einen Snapshot des heutigen Tages und gibt seinen Pfad zurueck.

    Ein zweiter Lauf am selben Tag ueberschreibt den Snapshot des Tages, statt
    einen weiteren anzulegen: der Dateiname ist das Datum, und die Rotation
    soll Tage zaehlen, nicht Neustarts.
    """
    keep = config.BACKUP_KEEP if keep is None else keep
    target_dir = backup_dir()
    os.makedirs(target_dir, exist_ok=True)
    stamp = (today or date.today()).isoformat()
    target = os.path.join(target_dir, f"dd-was-geht-{stamp}.db")

    # Erst unter einem Zwischennamen schreiben und dann umbenennen: bricht der
    # Lauf ab (Strom weg, Platte voll), bleibt sonst eine halbe Datei unter dem
    # Namen des Tages liegen - und die Rotation zaehlte sie als gueltige
    # Sicherung mit, waehrend eine echte dafuer weggeraeumt wird.
    tmp = target + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)

    source = sqlite3.connect(config.DB_PATH)
    try:
        dest = sqlite3.connect(tmp)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    os.replace(tmp, target)

    _rotate(target_dir, keep)
    return target


def _rotate(target_dir, keep):
    """Behaelt die juengsten `keep` Snapshots. Sortiert wird nach Dateiname -
    das Datum steht im ISO-Format darin, alphabetisch ist also chronologisch."""
    if keep <= 0:
        return
    snapshots = sorted(glob.glob(os.path.join(target_dir, SNAPSHOT_GLOB)))
    for old in snapshots[:-keep]:
        os.remove(old)
        logger.info("Alte Sicherung entfernt: %s", os.path.basename(old))


def run_backup():
    """Einstiegspunkt fuer den Scheduler.

    Faengt alles ab: eine fehlgeschlagene Sicherung ist ein Grund fuer eine
    Zeile im Log, aber keiner, den Dienst zu beenden - sonst nimmt ausgerechnet
    die Vorsichtsmassnahme die Web-Oberflaeche mit runter.
    """
    try:
        path = create_backup()
    except Exception:
        logger.exception("Sicherung fehlgeschlagen - der Dienst laeuft weiter.")
        return None
    logger.info("Sicherung geschrieben: %s (%.1f MB)",
                path, os.path.getsize(path) / 1_000_000)
    return path

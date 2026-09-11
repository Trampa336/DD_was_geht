"""Datumsbereiche fuer die Seite: ein einzelner Tag (Kalenderauswahl) und die
rollierende Woche fuer die Empfehlungszeile.

Bewusst als rollierendes Fenster ab heute definiert (nicht Kalenderwoche
rueckwirkend) - das ist es, was man von einem "was ist los"-Newsletter
erwartet.
"""
from datetime import timedelta


def week_range(today):
    return today, today + timedelta(days=6)


def day_range(day):
    return day, day

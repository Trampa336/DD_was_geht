"""Datumsbereiche für 'Heute' / 'Diese Woche' / 'Diesen Monat'.

Bewusst als rollierendes Fenster ab heute definiert (nicht Kalenderwoche/-monat
rückwirkend) - das ist es, was man von einem "was ist los"-Newsletter erwartet.
"""
import calendar
from datetime import date, timedelta


def week_range(today):
    return today, today + timedelta(days=6)


def month_range(today):
    last_day = calendar.monthrange(today.year, today.month)[1]
    return today, date(today.year, today.month, last_day)

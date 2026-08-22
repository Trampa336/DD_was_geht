"""Telegram-Bot: täglicher/wöchentlicher Push + Befehle.

Bewertet wird hier bewusst nicht: 👍/👎 trainieren ein einziges, persönliches
Modell, und das soll nur über die Weboberfläche im Heimnetz beschickt werden.
Der Digest ist reiner Lesekanal - genau wie die öffentliche Kopie auf GitHub
Pages (siehe tools/export_static.py).
"""
import html
import logging
from datetime import date, datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message

from . import config, db, scoring
from .ranges import month_range, week_range

logger = logging.getLogger("dd-was-geht.bot")

dp = Dispatcher()

# Der Bot wird bewusst NICHT beim Import des Moduls erzeugt: aiogram prüft das
# Token-Format sofort bei Bot(...) und wirft sonst schon beim reinen Import
# einen Fehler, falls .env noch fehlt/leer ist (z.B. beim Testen einzelner
# Module). Stattdessen wird er beim ersten tatsächlichen Gebrauch angelegt.
_bot_instance = None


def get_bot():
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = Bot(token=config.TELEGRAM_BOT_TOKEN)
    return _bot_instance


# Kurze deutsche Wochentage für die Datumsspalte in Wochen-/Monatsdigest.
_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")

# Telegram hängt an jede Nachricht mit Link eine Vorschaukarte. Bei sechs
# Einzelnachrichten pro Digest bläht das den Push komplett auf.
_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def _format_day(date_text):
    """'2026-08-22' -> 'Fr 22.08.'"""
    try:
        day = datetime.strptime(date_text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return ""
    return f"{_WEEKDAYS[day.weekday()]} {day.strftime('%d.%m.')}"


def _event_line(e, with_date=False):
    """Eine Digest-Zeile, als HTML.

    HTML deshalb, weil der Titel auf die Veranstaltungsseite verlinkt. Das
    heißt aber auch: ALLES, was aus den Quellen kommt, muss escaped werden -
    286 Titel in der Datenbank enthalten ein '&' ("Semperoper & Dresdner
    Altstadt"), und ein unmaskiertes Sonderzeichen lässt Telegram die ganze
    Nachricht mit 400 ablehnen.
    """
    time_part = e["time"] or "--:--"
    date_part = f"{_format_day(e['date'])}  " if with_date else ""
    title = html.escape(e["title"] or "")
    url = (e.get("url") or "").strip()
    if url:
        title = f'<a href="{html.escape(url, quote=True)}">{title}</a>'
    venue = f" — {html.escape(e['venue'])}" if e.get("venue") else ""
    return f"{date_part}{time_part}  {title}{venue}"


async def _send_event(chat_id, event, text):
    """Schickt EINE Digest-Zeile - mit Cover, wenn es eins gibt.

    Das Bild wird nie extra nachgeladen: genutzt wird nur, was beim Scrapen
    ohnehin schon in image_url stand (Rauze und RA liefern es mit, der
    Kulturkalender erst beim Detail-Klick im Web). Kein Bild oder eine URL,
    die Telegram nicht annimmt -> ganz normale Textnachricht. Ein kaputtes
    Cover darf den Digest nie kippen.
    """
    image_url = (event.get("image_url") or "").strip()
    if image_url:
        try:
            await get_bot().send_photo(
                chat_id, photo=image_url, caption=text, parse_mode="HTML",
            )
            return
        except (TelegramBadRequest, TelegramNetworkError) as exc:
            # Typisch: toter Link, 403 vom CDN, Bild größer als 5 MB.
            logger.info("Cover für %s nicht sendbar (%s), fällt auf Text zurück",
                        event.get("uid"), exc)

    await get_bot().send_message(
        chat_id, text, parse_mode="HTML",
        link_preview_options=_NO_PREVIEW,
    )


async def send_digest(chat_id, title, events, footer=None, with_date=False):
    if not events:
        await get_bot().send_message(chat_id, f"{title}\n\nKeine Veranstaltungen gefunden.")
        return

    header = f"<b>{title}</b>\n"
    await get_bot().send_message(chat_id, header, parse_mode="HTML")

    # Der Score entscheidet, WER in den Digest kommt - die Reihenfolge macht
    # danach das Datum. Über mehrere Tage hinweg liest sich eine nach Score
    # sortierte Liste sonst wie Zufall: zwölf Zeilen mit Uhrzeit, aber ohne
    # erkennbaren Tag. Für "heute" (with_date=False) ändert das nichts.
    if with_date:
        events = sorted(events, key=lambda e: (e["date"], e["time"] or "99:99"))

    for e in events:
        text = _event_line(e, with_date=with_date)
        await _send_event(chat_id, e, text)

    if footer:
        await get_bot().send_message(chat_id, footer)


async def send_daily_digest(chat_id=None):
    chat_id = chat_id or config.TELEGRAM_CHAT_ID
    today = date.today()
    with db.get_conn() as conn:
        # exclude_far: der Digest bleibt auf Dresden und den Speckgürtel
        # beschränkt (siehe app/geo.py). Im Web ist das Umland über den
        # Schalter "Umgebung einschließen" weiterhin erreichbar.
        events = db.events_for_range(
            conn, today.isoformat(), today.isoformat(),
            exclude_categories=config.EXCLUDED_CATEGORIES, exclude_far=True)
        top = scoring.top_picks(conn, events, limit=config.DAILY_TOP_N)
    await send_digest(
        chat_id,
        f"📅 Heute in Dresden – {today.strftime('%d.%m.%Y')}",
        top,
        footer="Bewerten (👍/👎) geht auf der Webseite im Heimnetz – die Empfehlungen lernen daraus.",
    )


async def send_weekly_digest(chat_id=None):
    chat_id = chat_id or config.TELEGRAM_CHAT_ID
    start, end = week_range(date.today())
    with db.get_conn() as conn:
        events = db.events_for_range(
            conn, start.isoformat(), end.isoformat(),
            exclude_categories=config.EXCLUDED_CATEGORIES, exclude_far=True)
        top = scoring.top_picks(conn, events, limit=config.DAILY_TOP_N * 2)
    await send_digest(
        chat_id,
        f"🗓️ Diese Woche in Dresden ({start.strftime('%d.%m.')}–{end.strftime('%d.%m.%Y')})",
        top,
        with_date=True,
    )


@dp.message(Command("heute"))
async def cmd_heute(message: Message):
    await send_daily_digest(chat_id=message.chat.id)


@dp.message(Command("woche"))
async def cmd_woche(message: Message):
    await send_weekly_digest(chat_id=message.chat.id)


@dp.message(Command("monat"))
async def cmd_monat(message: Message):
    start, end = month_range(date.today())
    with db.get_conn() as conn:
        events = db.events_for_range(
            conn, start.isoformat(), end.isoformat(),
            exclude_categories=config.EXCLUDED_CATEGORIES, exclude_far=True)
        top = scoring.top_picks(conn, events, limit=config.DAILY_TOP_N * 3)
    await send_digest(message.chat.id, f"📆 Diesen Monat in Dresden ({start.strftime('%B %Y')})",
                      top, with_date=True)


@dp.message(Command("favoriten"))
async def cmd_favoriten(message: Message):
    with db.get_conn() as conn:
        liked = db.liked_events(conn, limit=15)
    if not liked:
        await message.answer("Noch keine Favoriten – bewerte ein paar Events auf der Webseite im Heimnetz.")
        return
    lines = "\n".join(_event_line(e, with_date=True) for e in liked)
    await message.answer(
        f"<b>Deine bisherigen 👍-Favoriten:</b>\n{lines}",
        parse_mode="HTML", link_preview_options=_NO_PREVIEW,
    )


@dp.message(Command("start", "hilfe", "help"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Willkommen bei <b>DD was geht</b>.\n\n"
        "/heute – heutige Empfehlungen\n"
        "/woche – diese Woche\n"
        "/monat – diesen Monat\n"
        "/favoriten – deine bisherigen 👍\n\n"
        "Bewertet wird nicht hier, sondern auf der Webseite im Heimnetz – "
        "der Digest zeigt nur, was dabei herauskommt.",
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("fb:"))
async def on_feedback(callback: CallbackQuery):
    """Nur noch Altlast: neue Digests haben keine Buttons mehr, aber die alten
    Nachrichten im Chat behalten ihre. Ohne Handler drehte der Knopf ewig - also
    kurz erklären und nichts schreiben."""
    await callback.answer(
        "Bewerten geht nur noch auf der Webseite im Heimnetz.", show_alert=True)


async def run_bot():
    await dp.start_polling(get_bot())

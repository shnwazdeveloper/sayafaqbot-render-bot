import asyncio
import html
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from pyrogram import enums, filters
from pyrogram.enums import ButtonStyle
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from pytgcalls import exceptions, types
from yt_dlp import YoutubeDL

from AloneX import pbot as bot, pytgcalls, user as assistant_client
import config


__module__ = "Music"


DOWNLOAD_DIR = Path("downloads/music")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_DURATION = int(os.getenv("MUSIC_MAX_DURATION", "1800"))
RESULT_TTL = 1800
RESULTS = {}
ACTIVE_STREAMS = {}


def _bot_tag() -> str:
    username = (config.BOT_USERNAME or "Sayafaqbot").lstrip("@")
    return f"@{username}"


def _assistant_tag() -> str:
    username = getattr(config, "ASSISTANT_USERNAME", "Lyricsdev").lstrip("@")
    return f"@{username}"


__help__ = f"""
Music commands

Commands:
`/mplay <song name or YouTube URL>` - play music in the group voice chat.
`/mmusicplay <song name or YouTube URL>` - same as /mplay.
`/mmusic <song name or YouTube URL>` - same as /mplay.
`/mstop` - stop voice chat music.
`/mpause` - pause voice chat music.
`/mresume` - resume voice chat music.
`/msong <song name or YouTube URL>` - download and send the first audio result.
`/msearch <song name>` - show the top YouTube results with buttons.
`/mhelp` - show this help message.

Assistant: {_assistant_tag()}
Start the group voice chat and add {_assistant_tag()} to the group before using /mplay.
"""


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_group(message: Message) -> bool:
    return message.chat.type in {enums.ChatType.GROUP, enums.ChatType.SUPERGROUP}


def _clean_old_results() -> None:
    now = time.time()
    stale = [key for key, value in RESULTS.items() if now - value.get("created_at", 0) > RESULT_TTL]
    for key in stale:
        RESULTS.pop(key, None)


def _duration(value) -> str:
    try:
        seconds = int(value or 0)
    except (TypeError, ValueError):
        return "Unknown"
    if seconds <= 0:
        return "Unknown"
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def _search_sync(query: str, limit: int = 5):
    target = query if _is_url(query) else f"ytsearch{limit}:{query}"
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": True,
    }
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(target, download=False)

    entries = info.get("entries") if isinstance(info, dict) else None
    if entries:
        items = [item for item in entries if item]
    elif isinstance(info, dict):
        items = [info]
    else:
        items = []

    results = []
    for item in items[:limit]:
        title = item.get("title") or "Unknown title"
        url = item.get("url") or item.get("webpage_url")
        if url and not str(url).startswith("http"):
            url = f"https://www.youtube.com/watch?v={url}"
        if not url:
            continue
        results.append(
            {
                "title": title,
                "url": url,
                "duration": item.get("duration"),
                "uploader": item.get("uploader") or item.get("channel") or "Unknown artist",
            }
        )
    return results


def _download_sync(query_or_url: str):
    search_target = query_or_url if _is_url(query_or_url) else f"ytsearch1:{query_or_url}"
    probe_options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "noplaylist": True,
    }
    with YoutubeDL(probe_options) as ydl:
        info = ydl.extract_info(search_target, download=False)

    entries = info.get("entries") if isinstance(info, dict) else None
    if entries:
        info = next((entry for entry in entries if entry), None)
    if not info:
        raise RuntimeError("No result found.")

    duration = int(info.get("duration") or 0)
    if duration and duration > MAX_DURATION:
        raise RuntimeError(f"Track is longer than the {MAX_DURATION // 60} minute limit.")

    source_url = info.get("webpage_url") or info.get("url") or query_or_url
    output_template = str(DOWNLOAD_DIR / "%(id)s.%(ext)s")
    download_options = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
    }
    with YoutubeDL(download_options) as ydl:
        final_info = ydl.extract_info(source_url, download=True)

    downloads = final_info.get("requested_downloads") or []
    if downloads and downloads[0].get("filepath"):
        file_path = downloads[0]["filepath"]
    else:
        file_path = YoutubeDL(download_options).prepare_filename(final_info)

    return file_path, {
        "title": final_info.get("title") or info.get("title") or "Unknown title",
        "uploader": final_info.get("uploader") or info.get("uploader") or "Unknown artist",
        "duration": int(final_info.get("duration") or duration or 0),
        "url": final_info.get("webpage_url") or source_url,
    }


async def _search(query: str, limit: int = 5):
    return await asyncio.to_thread(_search_sync, query, limit)


async def _download(query_or_url: str):
    return await asyncio.to_thread(_download_sync, query_or_url)


def _store_result(result: dict) -> str:
    _clean_old_results()
    key = uuid.uuid4().hex[:10]
    RESULTS[key] = {**result, "created_at": time.time()}
    return key


def _result_buttons(key: str, url: str, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Download audio", callback_data=f"mget:{key}", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton("Open YouTube", url=url, style=ButtonStyle.SUCCESS),
            ],
            [InlineKeyboardButton("Close", callback_data=f"mclose:{user_id}", style=ButtonStyle.DANGER)],
        ]
    )


def _player_buttons(chat_id: int, user_id: int, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Pause", callback_data=f"mpause:{chat_id}:{user_id}", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton("Resume", callback_data=f"mresume:{chat_id}:{user_id}", style=ButtonStyle.SUCCESS),
            ],
            [
                InlineKeyboardButton("Stop", callback_data=f"mstop:{chat_id}:{user_id}", style=ButtonStyle.DANGER),
                InlineKeyboardButton("Open YouTube", url=url, style=ButtonStyle.SUCCESS),
            ],
        ]
    )


def _caption(meta: dict) -> str:
    title = html.escape(meta.get("title") or "Unknown title")
    uploader = html.escape(meta.get("uploader") or "Unknown artist")
    duration = _duration(meta.get("duration"))
    url = html.escape(meta.get("url") or "")
    return (
        f"<b>{title}</b>\n\n"
        f"<b>Artist:</b> {uploader}\n"
        f"<b>Duration:</b> {duration}\n"
        f"<b>Source:</b> <a href=\"{url}\">YouTube</a>\n"
        f"<b>By:</b> {_bot_tag()}\n"
        f"<b>Assistant:</b> {_assistant_tag()}"
    )


def _playing_caption(meta: dict) -> str:
    return "<b>Playing in voice chat</b>\n\n" + _caption(meta)


async def _assistant_has_chat_access(chat_id: int) -> bool:
    try:
        await assistant_client.get_chat(chat_id)
        return True
    except Exception:
        return False


async def _cleanup_stream(chat_id: int) -> None:
    state = ACTIVE_STREAMS.pop(chat_id, None)
    if not state:
        return

    file_path = state.get("file_path")
    if file_path:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass


def _voice_stream(file_path: str):
    return types.MediaStream(
        media_path=file_path,
        audio_parameters=types.AudioQuality.HIGH,
        video_parameters=types.VideoQuality.HD_720p,
        audio_flags=types.MediaStream.Flags.REQUIRED,
        video_flags=types.MediaStream.Flags.IGNORE,
    )


async def _play_in_voice_chat(message: Message, query: str, status: Message) -> None:
    if not await _assistant_has_chat_access(message.chat.id):
        return await status.edit_text(
            f"Assistant {_assistant_tag()} is not in this group. Add {_assistant_tag()} to the group, start the voice chat, then use /mplay again."
        )

    file_path = None
    try:
        await status.edit_text("Downloading audio for voice chat...")
        file_path, meta = await _download(query)
        await _cleanup_stream(message.chat.id)
        await status.edit_text("Joining voice chat...")
        await pytgcalls.play(
            chat_id=message.chat.id,
            stream=_voice_stream(file_path),
            config=types.GroupCallConfig(auto_start=False),
        )
        ACTIVE_STREAMS[message.chat.id] = {"file_path": file_path, "meta": meta}
        await status.edit_text(
            _playing_caption(meta),
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_player_buttons(message.chat.id, message.from_user.id, meta.get("url")),
        )
    except exceptions.NoActiveGroupCall:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        await status.edit_text("No active voice chat found. Start the group voice chat first, then use /mplay again.")
    except exceptions.NoAudioSourceFound:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        await status.edit_text("Could not read audio from this track. Try another song or YouTube link.")
    except Exception as exc:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        await status.edit_text(
            f"Voice chat play failed: {html.escape(str(exc))}\n\n"
            f"Make sure {_assistant_tag()} is in this group and the voice chat is already started."
        )


async def _stop_voice_chat(chat_id: int) -> None:
    try:
        await pytgcalls.leave_call(chat_id, close=False)
    except Exception:
        pass
    await _cleanup_stream(chat_id)


async def _guard_owner(query: CallbackQuery, user_id: int) -> bool:
    if query.from_user.id == user_id:
        return True
    await query.answer("This music button is not for you.", show_alert=True)
    return False


@pytgcalls.on_update()
async def _music_call_updates(_, update: types.Update) -> None:
    if isinstance(update, types.StreamEnded):
        await _cleanup_stream(update.chat_id)


@bot.on_message(filters.command(["mhelp", "musichelp"]) & ~filters.forwarded)
async def music_help(_, message: Message):
    await message.reply_text(__help__)


@bot.on_message(filters.command(["msearch", "musicsearch"]) & ~filters.forwarded)
async def music_search(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /msearch song name")

    query = message.text.split(maxsplit=1)[1].strip()
    status = await message.reply_text("Searching music...")

    try:
        results = await _search(query, limit=5)
    except Exception as exc:
        return await status.edit_text(f"Search failed: {html.escape(str(exc))}")

    if not results:
        return await status.edit_text("No music results found.")

    lines = ["<b>Music search results</b>\n"]
    buttons = []
    for index, result in enumerate(results, start=1):
        key = _store_result(result)
        title = html.escape(result["title"])
        uploader = html.escape(result.get("uploader") or "Unknown artist")
        lines.append(f"{index}. <a href=\"{html.escape(result['url'])}\">{title}</a>\n   {uploader} | {_duration(result.get('duration'))}")
        buttons.append([InlineKeyboardButton(f"Download {index}", callback_data=f"mget:{key}", style=ButtonStyle.PRIMARY)])

    buttons.append([InlineKeyboardButton("Close", callback_data=f"mclose:{message.from_user.id}", style=ButtonStyle.DANGER)])
    await status.edit_text(
        "\n".join(lines),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@bot.on_message(filters.command(["mplay", "musicplay", "mmusicplay", "mmusic"]) & ~filters.forwarded)
async def music_play(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /mplay song name or YouTube URL")

    query = message.text.split(maxsplit=1)[1].strip()
    status = await message.reply_text("Searching music...")

    if _is_group(message):
        return await _play_in_voice_chat(message, query, status)

    try:
        results = await _search(query, limit=1)
    except Exception as exc:
        return await status.edit_text(f"Search failed: {html.escape(str(exc))}")

    if not results:
        return await status.edit_text("No music result found.")

    result = results[0]
    key = _store_result(result)
    await status.edit_text(
        _caption(result),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=_result_buttons(key, result["url"], message.from_user.id),
    )


@bot.on_message(filters.command(["mstop", "musicstop"]) & filters.group & ~filters.forwarded)
async def music_stop(_, message: Message):
    await _stop_voice_chat(message.chat.id)
    await message.reply_text("Stopped voice chat music.")


@bot.on_message(filters.command(["mpause", "musicpause"]) & filters.group & ~filters.forwarded)
async def music_pause(_, message: Message):
    try:
        await pytgcalls.pause(message.chat.id)
        await message.reply_text("Paused voice chat music.")
    except Exception as exc:
        await message.reply_text(f"Pause failed: {html.escape(str(exc))}")


@bot.on_message(filters.command(["mresume", "musicresume"]) & filters.group & ~filters.forwarded)
async def music_resume(_, message: Message):
    try:
        await pytgcalls.resume(message.chat.id)
        await message.reply_text("Resumed voice chat music.")
    except Exception as exc:
        await message.reply_text(f"Resume failed: {html.escape(str(exc))}")


@bot.on_message(filters.command(["msong", "song"]) & ~filters.forwarded)
async def music_song(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /msong song name or YouTube URL")

    query = message.text.split(maxsplit=1)[1].strip()
    status = await message.reply_text("Downloading audio...")
    file_path = None

    try:
        file_path, meta = await _download(query)
        await message.reply_audio(
            audio=file_path,
            caption=_caption(meta),
            parse_mode=enums.ParseMode.HTML,
            title=meta.get("title"),
            performer=meta.get("uploader"),
            duration=meta.get("duration") or None,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Open YouTube", url=meta.get("url"), style=ButtonStyle.SUCCESS)]]
            ),
        )
        await status.delete()
    except Exception as exc:
        await status.edit_text(f"Download failed: {html.escape(str(exc))}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


@bot.on_callback_query(filters.regex(r"^mget:"))
async def music_download_callback(_, query: CallbackQuery):
    key = query.data.split(":", 1)[1]
    result = RESULTS.get(key)
    if not result:
        return await query.answer("This music button expired.", show_alert=True)

    await query.answer("Downloading audio...")
    status = await query.message.reply_text("Downloading audio...")
    file_path = None

    try:
        file_path, meta = await _download(result["url"])
        await query.message.reply_audio(
            audio=file_path,
            caption=_caption(meta),
            parse_mode=enums.ParseMode.HTML,
            title=meta.get("title"),
            performer=meta.get("uploader"),
            duration=meta.get("duration") or None,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Open YouTube", url=meta.get("url"), style=ButtonStyle.SUCCESS)]]
            ),
        )
        await status.delete()
    except Exception as exc:
        await status.edit_text(f"Download failed: {html.escape(str(exc))}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


@bot.on_callback_query(filters.regex(r"^mpause:"))
async def music_pause_callback(_, query: CallbackQuery):
    _, chat_id, user_id = query.data.split(":", 2)
    if not await _guard_owner(query, int(user_id)):
        return
    await pytgcalls.pause(int(chat_id))
    await query.answer("Paused voice chat music.")


@bot.on_callback_query(filters.regex(r"^mresume:"))
async def music_resume_callback(_, query: CallbackQuery):
    _, chat_id, user_id = query.data.split(":", 2)
    if not await _guard_owner(query, int(user_id)):
        return
    await pytgcalls.resume(int(chat_id))
    await query.answer("Resumed voice chat music.")


@bot.on_callback_query(filters.regex(r"^mstop:"))
async def music_stop_callback(_, query: CallbackQuery):
    _, chat_id, user_id = query.data.split(":", 2)
    if not await _guard_owner(query, int(user_id)):
        return
    await _stop_voice_chat(int(chat_id))
    await query.answer("Stopped voice chat music.")
    await query.message.edit_text("Stopped voice chat music.")


@bot.on_callback_query(filters.regex(r"^mclose:"))
async def music_close_callback(_, query: CallbackQuery):
    user_id = int(query.data.split(":", 1)[1])
    if query.from_user.id != user_id:
        return await query.answer("This button is not for you.", show_alert=True)
    await query.message.delete()

import asyncio
import config
from AloneX import app, pbot, DEV_LIST, BOT_ID, OWNER_ID, SUDO_USERS, font
from telegram import Update, constants
from telegram.ext import ContextTypes
from AloneX.helpers.decorator import Command, sudos_only, protect_sudos, admin_check
from AloneX.helpers.utils import extract_user
from AloneX.db.chats import get_all_chats
from AloneX.db.gban import (
    add_gban_user, 
    remove_gban_user, 
    is_user_gbanned, 
    get_all_gbans,
    get_gban_reason,
    set_gban_status,
    get_gban_status
)
from AloneX.helpers.log_helper import log_action
from pyrogram import filters, StopPropagation
from pyrogram.types import ChatMemberUpdated, Message
from pyrogram.enums import ChatMemberStatus

global_action_lock = asyncio.Lock()

async def get_user_role(user_id: int) -> str:
    if user_id == OWNER_ID:
        return "Owner"
    if user_id in DEV_LIST:
        return "Dev"
    try:
        from AloneX.db.sudo import get_all_sudo_users
        if user_id in await get_all_sudo_users() or user_id in SUDO_USERS:
            return "Sudo"
    except:
        pass
    return "User"

async def get_all_sudo_ids():
    ids = set()
    if hasattr(config, 'OWNER_ID'):
        ids.add(config.OWNER_ID) if isinstance(config.OWNER_ID, int) else ids.update(config.OWNER_ID)
    if hasattr(config, 'DEV_LIST'):
        ids.update(config.DEV_LIST)
    if hasattr(config, 'SUDO_USERS'):
        ids.update(config.SUDO_USERS)
    try:
        from AloneX.db.sudo import get_all_sudo_users
        ids.update(await get_all_sudo_users())
    except:
        pass
    return list(ids)

async def notify_sudos(text: str, exclude_id: int = None):
    for sudo_id in await get_all_sudo_ids():
        if sudo_id != exclude_id:
            try:
                await pbot.send_message(sudo_id, text)
            except:
                pass

@Command(['gban', 'botban'])
@sudos_only
@protect_sudos
async def botBan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.effective_message
    actor = update.effective_user
    if global_action_lock.locked():
        return await m.reply_text(font(" Another action in progress..."))
    user_id = await extract_user(m, self=False)
    if not user_id:
        return await m.reply_text(
            " <b>Please reply to a user or provide their ID/username!</b>\n\n"
            "<b>Usage:</b> <code>/gban [user] [reason]</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/gban @username spam</code>\n"
            "• <code>/gban 123456789 scammer</code>\n"
            "• <code>/gban</code> (reply to user) <code>nsfw content</code>",
            parse_mode="HTML"
        )
    if user_id < 0:
        return await m.reply_text(font(" Cannot gban groups/channels!"))
    parts = m.text.strip().split(maxsplit=2)
    reason = parts[2] if len(parts) > 2 else "No reason provided"
    async with global_action_lock:
        if user_id == context.bot.id:
            return await m.reply_text(" I can't ban myself!")
        if await is_user_gbanned(user_id):
            try:
                user = await context.bot.get_chat(user_id)
                username = f"@{user.username}" if user.username else "No username"
                user_name = user.full_name
                user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"
            except:
                username = "No username"
                user_name = "Unknown User"
                user_mention = f"<code>{user_id}</code>"
            reason = await get_gban_reason(user_id)
            return await m.reply_text(
                f"<b> ᴜꜱᴇʀ ᴀʟʀᴇᴀᴅʏ ɢʙᴀɴɴᴇᴅ</b>\n\n"
                f" {user_mention}\n"
                f" <code>{user_id}</code>\n"
                f" {username}\n"
                f" ʀᴇᴀꜱᴏɴ: {reason}",
                parse_mode="HTML"
            )
        role = await get_user_role(actor.id)
        try:
            user = await context.bot.get_chat(user_id)
            username = f"@{user.username}" if user.username else "No username"
            user_name = user.full_name
            user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"
        except:
            username = "No username"
            user_name = "Unknown User"
            user_mention = f"<code>{user_id}</code>"
        start = (
            f"<b> Global Ban Started</b>\n\n"
            f" {user_mention}\n"
            f" <code>{user_id}</code>\n"
            f" {username}\n"
            f" Reason: {reason}\n\n"
            f" Banning in progress..."
        )
        msg = await m.reply_text(start, parse_mode="HTML")
        count = 0
        chats = await get_all_chats()
        for i, chat_id in enumerate(chats, 1):
            try:
                await context.bot.ban_chat_member(chat_id, user_id)
                count += 1
                if i % 30 == 0:
                    await asyncio.sleep(1.5)
            except:
                pass
        await add_gban_user(user_id, reason, user_name, username)
        done = (
            f"<b> GBAN Complete</b>\n\n"
            f" {user_mention}\n"
            f" <code>{user_id}</code>\n"
            f" {username}\n"
            f" Banned in: <b>149{count} chats</b>\n"
            f" Reason: {reason}"
        )
        await msg.edit_text(done, parse_mode="HTML")

        log_text = f" <b>#GBAN</b>\n" \
                   f" <b>{role}:</b> {html.escape(actor.full_name)} (<code>{actor.id}</code>)\n" \
                   f" <b>User:</b> {html.escape(user_name)} (<code>{user_id}</code>)\n" \
                   f" <b>Username:</b> {html.escape(username)}\n" \
                   f" <b>Chats:</b> {count}\n" \
                   f" <b>Reason:</b> {html.escape(reason)}"
        asyncio.create_task(log_action(context.bot, m.chat.id, "bans", log_text))
        notification = (
            f"** Global Ban Alert**\n\n"
            f" {role}: {actor.full_name} (`{actor.id}`)\n"
            f" {user_name} (`{user_id}`)\n"
            f" {username}\n"
            f" 149{count} chats\n"
            f" {reason}"
        )
        await notify_sudos(notification, exclude_id=actor.id)

@Command(['ungban', 'unbotban'])
@sudos_only
@protect_sudos
async def botUnban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.effective_message
    actor = update.effective_user
    if global_action_lock.locked():
        return await m.reply_text(font(" Another action in progress..."))
    user_id = await extract_user(m, self=False)
    if not user_id:
        return await m.reply_text(
            " <b>Please reply to a user or provide their ID/username!</b>\n\n"
            "<b>Usage:</b> <code>/ungban [user] [reason]</code>",
            parse_mode="HTML"
        )
    if user_id < 0:
        return await m.reply_text(font(" Cannot ungban groups/channels!"))
    parts = m.text.strip().split(maxsplit=2)
    reason = parts[2] if len(parts) > 2 else "No reason provided"
    async with global_action_lock:
        if user_id == context.bot.id:
            return await m.reply_text(" I'm not gbanned!")
        if not await is_user_gbanned(user_id):
            try:
                user = await context.bot.get_chat(user_id)
                username = f"@{user.username}" if user.username else "No username"
                user_name = user.full_name
                user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"
            except:
                username = "No username"
                user_name = "Unknown User"
                user_mention = f"<code>{user_id}</code>"
            return await m.reply_text(
                f"<b> ᴜꜱᴇʀ ɪꜱ ɴᴏᴛ ɢʙᴀɴɴᴇᴅ</b>\n\n"
                f" {user_mention}\n"
                f" <code>{user_id}</code>\n"
                f" {username}\n\n"
                f"ᴛʜɪꜱ ᴜꜱᴇʀ ɪꜱ ɴᴏᴛ ɪɴ ᴛʜᴇ ɢʙᴀɴ ʟɪꜱᴛ.",
                parse_mode="HTML"
            )
        role = await get_user_role(actor.id)
        try:
            user = await context.bot.get_chat(user_id)
            username = f"@{user.username}" if user.username else "No username"
            user_name = user.full_name
            user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"
        except:
            username = "No username"
            user_name = "Unknown User"
            user_mention = f"<code>{user_id}</code>"
        start = (
            f"<b> Global Unban Started</b>\n\n"
            f" {user_mention}\n"
            f" <code>{user_id}</code>\n"
            f" {username}\n"
            f" Reason: {reason}\n\n"
            f" Unbanning..."
        )
        msg = await m.reply_text(start, parse_mode="HTML")
        count = 0
        chats = await get_all_chats()
        for i, chat_id in enumerate(chats, 1):
            try:
                await context.bot.unban_chat_member(chat_id, user_id)
                count += 1
                if i % 30 == 0:
                    await asyncio.sleep(1.5)
            except:
                pass
        await remove_gban_user(user_id)
        done = (
            f"<b> UNGBAN Complete</b>\n\n"
            f" {user_mention}\n"
            f" <code>{user_id}</code>\n"
            f" {username}\n"
            f" Unbanned in: <b>149{count} chats</b>\n"
            f" Reason: {reason}"
        )
        await msg.edit_text(done, parse_mode="HTML")
        notification = (
            f"** Global Unban Alert**\n\n"
            f" {role}: {actor.full_name} (`{actor.id}`)\n"
            f" {user_name} (`{user_id}`)\n"
            f" {username}\n"
            f" 149{count} chats\n"
            f" {reason}"
        )
        await notify_sudos(notification, exclude_id=actor.id)

@Command(['gbanlist'])
@sudos_only
async def gban_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.effective_message
    bans = await get_all_gbans()
    if not bans:
        return await m.reply_text(font(" No gbanned users."))
    text = f"<b> Global Ban List ({len(bans)} users)</b>\n\n"
    valid_count = 0
    for ban in bans:
        uid = ban["user_id"]
        if uid < 0:
            continue
        valid_count += 1
        reason = ban.get("reason", "No reason")
        name = ban.get("user_name", "Unknown")
        username = ban.get("username", "No username")
        text += f"{valid_count}. <a href='tg://user?id={uid}'>{name}</a>\n   └ <code>{uid}</code> | {reason}\n\n"
    if valid_count == 0:
        return await m.reply_text(font(" No valid gbanned users."))
    if len(text) > 4000:
        from io import BytesIO
        file = BytesIO(text.encode())
        file.name = "gbanlist.txt"
        return await m.reply_document(document=file)
    await m.reply_text(text, parse_mode="HTML")

@Command(['gbanstat'])
@admin_check()
async def gban_stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.effective_message
    chat = update.effective_chat
    if chat.type == "private":
        return await m.reply_text(font(" This command only works in groups!"))
    args = context.args
    if not args:
        status = await get_gban_status(chat.id)
        status_text = "ᴇɴᴀʙʟᴇᴅ " if status else "ᴅɪꜱᴀʙʟᴇᴅ "
        return await m.reply_text(
            f"<b>ɢʟᴏʙᴀʟ ʙᴀɴ ꜱᴛᴀᴛᴜꜱ:</b> {status_text}\n\n"
            f"<b>ᴜꜱᴀɢᴇ:</b> <code>/gbanstat [on/off/yes/no]</code>",
            parse_mode="HTML"
        )
    arg = args[0].lower()
    if arg in ['on', 'yes', 'enable', 'true']:
        await set_gban_status(chat.id, True)
        return await m.reply_text(
            " <b>ɢʟᴏʙᴀʟ ʙᴀɴ ᴇɴғᴏʀᴄᴇᴍᴇɴᴛ ᴇɴᴀʙʟᴇᴅ!</b>\n\n"
            "ɢʙᴀɴɴᴇᴅ ᴜꜱᴇʀꜱ ᴡɪʟʟ ʙᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ʙᴀɴɴᴇᴅ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ.",
            parse_mode="HTML"
        )
    elif arg in ['off', 'no', 'disable', 'false']:
        await set_gban_status(chat.id, False)
        return await m.reply_text(
            " <b>ɢʟᴏʙᴀʟ ʙᴀɴ ᴇɴғᴏʀᴄᴇᴍᴇɴᴛ ᴅɪꜱᴀʙʟᴇᴅ!</b>\n\n"
            "ɢʙᴀɴɴᴇᴅ ᴜꜱᴇʀꜱ ᴡɪʟʟ <b>ɴᴏᴛ</b> ʙᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ʙᴀɴɴᴇᴅ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ.",
            parse_mode="HTML"
        )
    else:
        return await m.reply_text(
            " <b>ɪɴᴠᴀʟɪᴅ ᴀʀɢᴜᴍᴇɴᴛ!</b>\n\n"
            "<b>ᴜꜱᴀɢᴇ:</b> <code>/gbanstat [on/off/yes/no]</code>",
            parse_mode="HTML"
        )

@Command(['gbancheck', 'checkgban'])
@admin_check()
async def check_gban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.effective_message
    user_id = await extract_user(m, self=True)
    if not user_id:
        return await m.reply_text(
            " <b>Please reply to a user or provide their ID/username!</b>\n\n"
            "<b>Usage:</b> <code>/gbancheck [user]</code>\n"
            "Or reply to a message with <code>/gbancheck</code>",
            parse_mode="HTML"
        )
    try:
        user = await context.bot.get_chat(user_id)
        username = f"@{user.username}" if user.username else "No username"
        user_name = user.full_name
        user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"
    except:
        username = "No username"
        user_name = "Unknown User"
        user_mention = f"<code>{user_id}</code>"
    is_gbanned = await is_user_gbanned(user_id)
    if is_gbanned:
        reason = await get_gban_reason(user_id)
        return await m.reply_text(
            f"<b> ɢʙᴀɴ ꜱᴛᴀᴛᴜꜱ: ʙᴀɴɴᴇᴅ </b>\n\n"
            f" {user_mention}\n"
            f" <code>{user_id}</code>\n"
            f" {username}\n"
            f" ʀᴇᴀꜱᴏɴ: {reason}",
            parse_mode="HTML"
        )
    else:
        return await m.reply_text(
            f"<b> ɴᴏᴛ ɪɴ ɢʙᴀɴ ʟɪꜱᴛ</b>\n\n"
            f" {user_mention}\n"
            f" <code>{user_id}</code>\n"
            f" {username}\n\n"
            f"ᴛʜɪꜱ ᴜꜱᴇʀ ɪꜱ ɴᴏᴛ ɢʟᴏʙᴀʟʟʏ ʙᴀɴɴᴇᴅ.",
            parse_mode="HTML"
        )

@pbot.on_chat_member_updated(group=-1100)
async def auto_gban_join(client, update: ChatMemberUpdated):
    try:
        if not update.new_chat_member:
            return
        if not await get_gban_status(update.chat.id):
            return
        user = update.new_chat_member.user
        old = update.old_chat_member.status if update.old_chat_member else None
        new = update.new_chat_member.status
        if old in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED, None] and \
           new in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            if await is_user_gbanned(user.id):
                await client.ban_chat_member(update.chat.id, user.id)
    except:
        pass

@pbot.on_message(filters.group & ~filters.service, group=-1100)
@pbot.on_edited_message(filters.group & ~filters.service, group=-1100)
async def auto_gban_msg(client, message: Message):
    if not message.from_user:
        return
    if not await get_gban_status(message.chat.id):
        return
    if await is_user_gbanned(message.from_user.id):
        try:
            await message.delete()
        except:
            pass
        try:
            await client.ban_chat_member(message.chat.id, message.from_user.id)
        except:
            pass
        raise StopPropagation

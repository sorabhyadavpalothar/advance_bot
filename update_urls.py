# ================== UPDATE_URLS.PY ==================
import math
import json
import re
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import ITEMS_PER_PAGE


# ================== DB HELPER ==================
def get_all_users():
    try:
        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT phone, api_id, urls FROM users ORDER BY created_at DESC")
            rows = cursor.fetchall()
        return rows
    except Exception as e:
        print(f"❌ Get all users error: {e}")
        return []


def get_user_urls(phone: str):
    try:
        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT urls FROM users WHERE phone = ?", (phone,))
            row = cursor.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0]) if row[0] else []
        except Exception:
            return []
    except Exception as e:
        print(f"❌ Get user URLs error: {e}")
        return []


def update_user_urls(phone: str, urls: list):
    try:
        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET urls = ? WHERE phone = ?", (json.dumps(urls), phone))
            conn.commit()
        return True
    except Exception as e:
        print(f"❌ Update user URLs error: {e}")
        return False


# ================== MARKDOWN ESCAPE HELPER ==================
def escape_markdown(text: str) -> str:
    if not text:
        return text
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '-', '=', '|', '{', '}', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text


def format_url_display(url: str) -> str:
    if url.startswith('https://t.me/c/'):
        match = re.search(r'https://t\.me/c/(\d+)/(\d+)', url)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    elif url.startswith('https://t.me/'):
        match = re.search(r'https://t\.me/([^/]+)(?:/(\d+))?', url)
        if match:
            channel = match.group(1)
            message_id = match.group(2)
            return f"{channel}/{message_id}" if message_id else channel
    elif url.startswith('@'):
        return url[1:]
    elif re.match(r'^-100\d+$', url):
        return url
    return url


# ================== PAGINATION ==================
async def show_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page=1):
    try:
        users = get_all_users()
        total = len(users)

        if total == 0:
            await update.callback_query.message.edit_caption(
                caption="❌ No users found in database.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="back")]])
            )
            return

        pages = math.ceil(total / ITEMS_PER_PAGE)
        start = (page - 1) * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        users_slice = users[start:end]

        keyboard = []
        for phone, api_id, urls in users_slice:
            keyboard.append([InlineKeyboardButton(f"{phone} | {api_id}", callback_data=f"user_{phone}")])

        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("⬅ Prev", callback_data=f"userpageurl_{page-1}"))
        if page < pages:
            nav_buttons.append(InlineKeyboardButton("Next ➡", callback_data=f"userpageurl_{page+1}"))

        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="back")])

        await update.callback_query.message.edit_caption(
            caption=f"👥 Users List (Page {page}/{pages})\n\nSelect a user to manage URLs:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        print(f"❌ Show user list (URLs) error: {e}")
        await update.callback_query.message.edit_caption(
            caption="❌ Error loading user list.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
        )


# ================== SHOW USER URLS ==================
async def show_user_urls(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    try:
        urls = get_user_urls(phone)

        if urls is None:
            await update.callback_query.message.edit_caption(
                caption="❌ User not found.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="update_urls")]])
            )
            return

        safe_urls = []
        for i, url in enumerate(urls, start=1):
            formatted_url = format_url_display(url)
            safe_urls.append(f"{i}. {formatted_url}")

        urls_text = "\n".join(safe_urls) if safe_urls else "No URLs saved."

        keyboard = [
            [InlineKeyboardButton("➕ Add New URLs", callback_data=f"addurls_{phone}"),
            InlineKeyboardButton("🗑 Delete URLs", callback_data=f"deleteurls_{phone}")],
            [InlineKeyboardButton("⬅ Back to User List", callback_data="update_urls"),
            InlineKeyboardButton("⬅ Back to Main", callback_data="back")]
        ]

        try:
            await update.callback_query.message.edit_caption(
                caption=f"📱 User: `{phone}`\n\n🌐 URLs:\n{urls_text}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            await update.callback_query.message.edit_caption(
                caption=f"📱 User: {phone}\n\n🌐 URLs:\n{urls_text}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        print(f"❌ Show user URLs error: {e}")
        await update.callback_query.message.edit_caption(
            caption="❌ Error loading user URLs.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="update_urls")]])
        )


# ================== ADD NEW URLS ==================
async def start_add_urls(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    try:
        context.user_data["update_urls"] = {
            "phone": phone,
            "step": "add",
            "chat_id": update.effective_chat.id,
            "message_id": update.callback_query.message.message_id
        }

        await update.callback_query.message.edit_caption(
            caption="➕ Please *send me the new URLs* (separated by spaces or new lines):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
        )
    except Exception as e:
        print(f"❌ Start add URLs error: {e}")
        await update.callback_query.message.edit_caption(
            caption="❌ Error initiating URL addition.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="update_urls")]])
        )


async def save_new_urls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "update_urls" not in context.user_data:
        return

    phone = context.user_data["update_urls"]["phone"]
    chat_id = update.effective_chat.id

    try:
        text = (update.message.text or "").strip()
        if not text:
            warn_msg = await update.message.reply_text("⚠️ Please enter some URLs.")
            await asyncio.sleep(1)
            try:
                await update.message.delete()
                await warn_msg.delete()
            except Exception:
                pass
            return

        raw_parts = re.split(r"[\s\n]+", text)

        new_urls = []
        for u in raw_parts:
            u = u.strip()
            if not u:
                continue

            if re.match(r"^https://t\.me/[A-Za-z0-9_+/.-]+$", u):
                new_urls.append(u)
            elif re.match(r"^@[A-Za-z0-9_]{3,}$", u):
                new_urls.append(u)
            elif re.match(r"^-100\d+$", u):
                new_urls.append(u)

        if not new_urls:
            warn_msg = await update.message.reply_text(
                text="⚠️ No valid URLs/usernames detected. Supported formats:\n"
                     "• https://t.me/channel\n• @username\n• -1001234567890",
                parse_mode="Markdown"
            )

            # Auto-delete after 3s
            await asyncio.sleep(3)
            try:
                await update.message.delete()
                await warn_msg.delete()
            except Exception:
                pass
            return

        old_urls = get_user_urls(phone) or []
        final_urls = list(dict.fromkeys(old_urls + new_urls))  # remove duplicates
        success = update_user_urls(phone, final_urls)

        try:
            await update.message.delete()
        except Exception:
            pass

        if success:
            await show_user_urls(update, context, phone)
        else:
            error_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Failed to save URLs to database."
            )
            await asyncio.sleep(2)
            try:
                await error_msg.delete()
            except Exception:
                pass

        context.user_data.pop("update_urls", None)

    except Exception as e:
        print(f"❌ Save new URLs error: {e}")
        try:
            await update.message.delete()
        except Exception:
            pass
        
        error_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Failed to save URLs. Please try again."
        )
        await asyncio.sleep(2)
        try:
            await error_msg.delete()
        except Exception:
            pass


# ================== DELETE URLS ==================
async def start_delete_urls(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    try:
        urls = get_user_urls(phone)

        if urls is None:
            caption = "❌ User not found."
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
        else:
            if not urls:
                caption = "ℹ️ No URLs available to delete."
                markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
            else:
                caption = "🗑 Select a URL to delete:"
                keyboard = []
                for idx, u in enumerate(urls):
                    formatted_url = format_url_display(u)
                    label = f"{formatted_url[:30]}..." if len(formatted_url) > 30 else f"{formatted_url}"
                    keyboard.append([InlineKeyboardButton(label, callback_data=f"delurl_{phone}_{idx}")])
                keyboard.append([InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")])
                markup = InlineKeyboardMarkup(keyboard)

        await update.callback_query.message.edit_caption(caption=caption, reply_markup=markup)
    except Exception as e:
        print(f"❌ Start delete URLs error: {e}")
        await update.callback_query.message.edit_caption(
            caption="❌ Error loading URLs for deletion.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
        )


async def confirm_delete_url(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str, index: int):
    try:
        urls = get_user_urls(phone)

        if urls is None:
            await update.callback_query.message.edit_caption(
                caption="❌ User not found.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
            )
            return

        if 0 <= index < len(urls):
            urls.pop(index)
            success = update_user_urls(phone, urls)
            if not success:
                await update.callback_query.message.edit_caption(
                    caption="❌ Failed to delete URL from database.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
                )
                return

        await show_user_urls(update, context, phone)
    except Exception as e:
        print(f"❌ Confirm delete URL error: {e}")
        await update.callback_query.message.edit_caption(
            caption="❌ Error deleting URL.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
        )

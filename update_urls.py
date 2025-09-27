# ================== UPDATE_URLS.PY ==================
import math
import json
import re
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import ITEMS_PER_PAGE
from database import get_db_cursor, db_lock, update_user_urls as db_update_user_urls


# ================== DB HELPER ==================
def get_all_users():
    """Get all users with their basic info for URL management"""
    try:
        with db_lock:
            with get_db_cursor(commit=False) as cursor:
                if cursor is None:
                    return []
                
                cursor.execute("""
                    SELECT phone, api_id, urls 
                    FROM users 
                    ORDER BY created_at DESC
                """)
                rows = cursor.fetchall()
                
                # Convert to list of tuples for compatibility
                return [(row['phone'], row['api_id'], row['urls']) for row in rows]
    except Exception as e:
        print(f"❌ Get all users error: {e}")
        return []


def get_user_urls(phone: str):
    """Get URLs for a specific user"""
    try:
        with db_lock:
            with get_db_cursor(commit=False) as cursor:
                if cursor is None:
                    return None
                
                cursor.execute("SELECT urls FROM users WHERE phone = %s", (phone,))
                row = cursor.fetchone()
                
                if not row:
                    return None
                
                try:
                    urls_data = row['urls']
                    return json.loads(urls_data) if urls_data else []
                except (json.JSONDecodeError, TypeError):
                    print(f"⚠️ Invalid JSON data for user {phone}, returning empty list")
                    return []
    except Exception as e:
        print(f"❌ Get user URLs error: {e}")
        return []


def update_user_urls(phone: str, urls: list):
    """Update URLs for a specific user"""
    try:
        with db_lock:
            with get_db_cursor() as cursor:
                if cursor is None:
                    return False
                
                urls_json = json.dumps(urls) if urls else '[]'
                cursor.execute("UPDATE users SET urls = %s WHERE phone = %s", (urls_json, phone))
                return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ Update user URLs error: {e}")
        return False


def user_exists(phone: str):
    """Check if user exists in database"""
    try:
        with db_lock:
            with get_db_cursor(commit=False) as cursor:
                if cursor is None:
                    return False
                
                cursor.execute("SELECT COUNT(*) as count FROM users WHERE phone = %s", (phone,))
                result = cursor.fetchone()
                return result['count'] > 0 if result else False
    except Exception as e:
        print(f"❌ User exists check error: {e}")
        return False


# ================== MARKDOWN ESCAPE HELPER ==================
def escape_markdown(text: str) -> str:
    """Escape markdown special characters"""
    if not text:
        return text
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '-', '=', '|', '{', '}', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text


def format_url_display(url: str) -> str:
    """Format URL for display in messages"""
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


def validate_telegram_url(url: str) -> bool:
    """Validate if URL is a valid Telegram URL format"""
    url = url.strip()
    
    patterns = [
        r'^https://t\.me/c/\d+/\d+$',  # private channels
        r'^https://t\.me/[a-zA-Z0-9_]+/\d+$',  # public channels with message
        r'^https://t\.me/\+[a-zA-Z0-9_-]+$',  # invite links
        r'^https://t\.me/[a-zA-Z0-9_]+$',  # public channels/groups
        r'^@[a-zA-Z0-9_]{3,}$',  # username format
        r'^-100\d+$',  # Chat ID format
        r'^[a-zA-Z0-9_]{3,}$'  # Just username without @
    ]
    
    for pattern in patterns:
        if re.match(pattern, url):
            if pattern == r'^[a-zA-Z0-9_]{3,}$' and url.isdigit():
                continue  # Skip pure numbers for last pattern
            return True
    
    return False


# ================== PAGINATION ==================
async def show_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page=1):
    """Show paginated list of users for URL management"""
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
            # Count URLs for display
            url_count = 0
            if urls:
                try:
                    url_list = json.loads(urls) if isinstance(urls, str) else urls
                    url_count = len(url_list) if isinstance(url_list, list) else 0
                except:
                    url_count = 0
            
            display_text = f"{phone} | {api_id} ({url_count} URLs)"
            keyboard.append([InlineKeyboardButton(display_text, callback_data=f"user_{phone}")])

        # Navigation buttons
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
            caption="❌ Error loading user list. Please try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
        )


# ================== SHOW USER URLS ==================
async def show_user_urls(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    """Show URLs for a specific user"""
    try:
        if not user_exists(phone):
            await update.callback_query.message.edit_caption(
                caption="❌ User not found in database.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="update_urls")]])
            )
            return

        urls = get_user_urls(phone)

        if urls is None:
            await update.callback_query.message.edit_caption(
                caption="❌ Error loading user data.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="update_urls")]])
            )
            return

        safe_urls = []
        for i, url in enumerate(urls, start=1):
            formatted_url = format_url_display(url)
            safe_urls.append(f"{i}. {formatted_url}")

        urls_text = "\n".join(safe_urls) if safe_urls else "No URLs saved."
        url_count = len(urls)

        keyboard = [
            [InlineKeyboardButton("➕ Add New URLs", callback_data=f"addurls_{phone}"),
            InlineKeyboardButton("🗑 Delete URLs", callback_data=f"deleteurls_{phone}")],
            [InlineKeyboardButton("🔄 Refresh", callback_data=f"user_{phone}")],
            [InlineKeyboardButton("⬅ Back to User List", callback_data="update_urls"),
            InlineKeyboardButton("⬅ Back to Main", callback_data="back")]
        ]

        try:
            await update.callback_query.message.edit_caption(
                caption=f"📱 User: `{phone}`\n📊 Total URLs: `{url_count}`\n\n🌐 URLs:\n{urls_text}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            # Fallback without markdown if there are special characters
            await update.callback_query.message.edit_caption(
                caption=f"📱 User: {phone}\n📊 Total URLs: {url_count}\n\n🌐 URLs:\n{urls_text}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        print(f"❌ Show user URLs error: {e}")
        await update.callback_query.message.edit_caption(
            caption="❌ Error loading user URLs. Please try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="update_urls")]])
        )


# ================== ADD NEW URLS ==================
async def start_add_urls(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    """Start the process of adding new URLs"""
    try:
        if not user_exists(phone):
            await update.callback_query.message.edit_caption(
                caption="❌ User not found in database.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="update_urls")]])
            )
            return

        context.user_data["update_urls"] = {
            "phone": phone,
            "step": "add",
            "chat_id": update.effective_chat.id,
            "message_id": update.callback_query.message.message_id
        }

        await update.callback_query.message.edit_caption(
            caption="➕ Please *send me the new URLs* in any of these formats:\n\n"
                   "• `https://t.me/channel` (Public channel)\n"
                   "• `https://t.me/c/1234567890/123` (Private channel)\n"
                   "• `https://t.me/+InviteHash` (Invite link)\n"
                   "• `@username` (Username)\n"
                   "• `-1001234567890` (Chat ID)\n\n"
                   "*Send multiple URLs separated by spaces or new lines:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
        )
    except Exception as e:
        print(f"❌ Start add URLs error: {e}")
        await update.callback_query.message.edit_caption(
            caption="❌ Error initiating URL addition. Please try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="update_urls")]])
        )


async def save_new_urls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save new URLs sent by user"""
    if "update_urls" not in context.user_data:
        return

    phone = context.user_data["update_urls"]["phone"]
    chat_id = update.effective_chat.id
    message_id = context.user_data["update_urls"]["message_id"]

    try:
        text = (update.message.text or "").strip()
        if not text:
            warn_msg = await update.message.reply_text("⚠️ Please enter some URLs.")
            await asyncio.sleep(2)
            try:
                await update.message.delete()
                await warn_msg.delete()
            except Exception:
                pass
            return

        # Parse URLs from text
        raw_parts = re.split(r"[\s\n]+", text)
        new_urls = []
        invalid_urls = []

        for u in raw_parts:
            u = u.strip()
            if not u:
                continue

            if validate_telegram_url(u):
                new_urls.append(u)
            else:
                invalid_urls.append(u)

        if not new_urls:
            invalid_list = "\n".join([f"• {url}" for url in invalid_urls[:5]])  # Show max 5
            warn_msg = await update.message.reply_text(
                text=f"⚠️ No valid URLs detected.\n\n❌ Invalid URLs:\n{invalid_list}\n\n"
                     "✅ Supported formats:\n"
                     "• https://t.me/channel\n"
                     "• @username\n"
                     "• -1001234567890",
                parse_mode="Markdown"
            )

            await asyncio.sleep(4)
            try:
                await update.message.delete()
                await warn_msg.delete()
            except Exception:
                pass
            return

        # Get existing URLs and merge
        old_urls = get_user_urls(phone) or []
        combined_urls = old_urls + new_urls
        
        # Remove duplicates while preserving order
        final_urls = []
        seen = set()
        for url in combined_urls:
            if url not in seen:
                final_urls.append(url)
                seen.add(url)

        # Save to database
        success = update_user_urls(phone, final_urls)

        # Delete user's input message
        try:
            await update.message.delete()
        except Exception:
            pass

        if success:
            # Show success message briefly
            added_count = len(new_urls)
            total_count = len(final_urls)
            
            success_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Added {added_count} URLs successfully!\n📊 Total URLs: {total_count}"
            )
            
            await asyncio.sleep(1.5)
            try:
                await success_msg.delete()
            except Exception:
                pass

            # Update the main message to show updated URLs
            await context.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption="🔄 Updating URLs...",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Please wait...", callback_data="noop")]])
            )
            
            # Create a fake update object to refresh the display
            class FakeUpdate:
                def __init__(self):
                    self.callback_query = type('obj', (object,), {
                        'message': type('obj', (object,), {
                            'edit_caption': context.bot.edit_message_caption
                        })()
                    })()
            
            fake_update = FakeUpdate()
            await show_user_urls(fake_update, context, phone)
            
        else:
            error_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Failed to save URLs to database. Please try again."
            )
            await asyncio.sleep(2)
            try:
                await error_msg.delete()
            except Exception:
                pass

        # Clear user data
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
        
        context.user_data.pop("update_urls", None)


# ================== DELETE URLS ==================
async def start_delete_urls(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    """Start the process of deleting URLs"""
    try:
        if not user_exists(phone):
            await update.callback_query.message.edit_caption(
                caption="❌ User not found in database.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="update_urls")]])
            )
            return

        urls = get_user_urls(phone)

        if urls is None:
            caption = "❌ Error loading user data."
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
        elif not urls:
            caption = "ℹ️ No URLs available to delete."
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
        else:
            caption = f"🗑 Select a URL to delete:\n📊 Total: {len(urls)} URLs"
            keyboard = []
            
            for idx, u in enumerate(urls):
                formatted_url = format_url_display(u)
                # Truncate long URLs for button display
                if len(formatted_url) > 35:
                    label = f"{idx+1}. {formatted_url[:32]}..."
                else:
                    label = f"{idx+1}. {formatted_url}"
                keyboard.append([InlineKeyboardButton(label, callback_data=f"delurl_{phone}_{idx}")])
            
            # Add bulk actions
            if len(urls) > 1:
                keyboard.append([InlineKeyboardButton("🗑 Delete All URLs", callback_data=f"delallurls_{phone}")])
            
            keyboard.append([InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")])
            markup = InlineKeyboardMarkup(keyboard)

        await update.callback_query.message.edit_caption(caption=caption, reply_markup=markup)
        
    except Exception as e:
        print(f"❌ Start delete URLs error: {e}")
        await update.callback_query.message.edit_caption(
            caption="❌ Error loading URLs for deletion. Please try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
        )


async def confirm_delete_url(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str, index: int):
    """Delete a specific URL by index"""
    try:
        if not user_exists(phone):
            await update.callback_query.message.edit_caption(
                caption="❌ User not found in database.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="update_urls")]])
            )
            return

        urls = get_user_urls(phone)

        if urls is None:
            await update.callback_query.message.edit_caption(
                caption="❌ Error loading user data.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
            )
            return

        if 0 <= index < len(urls):
            deleted_url = urls[index]
            urls.pop(index)
            success = update_user_urls(phone, urls)
            
            if success:
                # Show success message briefly
                success_text = f"✅ URL deleted successfully!\n🗑 Removed: {format_url_display(deleted_url)}"
                await update.callback_query.answer(text="URL deleted successfully!")
            else:
                await update.callback_query.message.edit_caption(
                    caption="❌ Failed to delete URL from database. Please try again.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
                )
                return
        else:
            await update.callback_query.answer(text="❌ Invalid URL selection!", show_alert=True)

        # Refresh the user URLs display
        await show_user_urls(update, context, phone)
        
    except Exception as e:
        print(f"❌ Confirm delete URL error: {e}")
        await update.callback_query.message.edit_caption(
            caption="❌ Error deleting URL. Please try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
        )


async def confirm_delete_all_urls(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    """Delete all URLs for a user with confirmation"""
    try:
        if not user_exists(phone):
            await update.callback_query.message.edit_caption(
                caption="❌ User not found in database.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="update_urls")]])
            )
            return

        urls = get_user_urls(phone)
        
        if not urls:
            await update.callback_query.message.edit_caption(
                caption="ℹ️ No URLs to delete.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
            )
            return

        # Show confirmation
        keyboard = [
            [InlineKeyboardButton("❌ Yes, Delete All", callback_data=f"confirmdelall_{phone}"),
             InlineKeyboardButton("✅ Cancel", callback_data=f"deleteurls_{phone}")]
        ]

        await update.callback_query.message.edit_caption(
            caption=f"⚠️ Are you sure you want to delete ALL {len(urls)} URLs for user {phone}?\n\n"
                   "This action cannot be undone!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        print(f"❌ Confirm delete all URLs error: {e}")
        await update.callback_query.message.edit_caption(
            caption="❌ Error processing request. Please try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
        )


async def execute_delete_all_urls(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    """Actually delete all URLs after confirmation"""
    try:
        success = update_user_urls(phone, [])
        
        if success:
            await update.callback_query.answer(text="All URLs deleted successfully!")
            await show_user_urls(update, context, phone)
        else:
            await update.callback_query.message.edit_caption(
                caption="❌ Failed to delete URLs from database. Please try again.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
            )
    except Exception as e:
        print(f"❌ Execute delete all URLs error: {e}")
        await update.callback_query.message.edit_caption(
            caption="❌ Error deleting URLs. Please try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=f"user_{phone}")]])
        )


# ================== UTILITY FUNCTIONS ==================
async def get_url_statistics():
    """Get statistics about URLs across all users"""
    try:
        users = get_all_users()
        total_users = len(users)
        users_with_urls = 0
        total_urls = 0
        
        for phone, api_id, urls_data in users:
            if urls_data:
                try:
                    urls = json.loads(urls_data) if isinstance(urls_data, str) else urls_data
                    if urls and len(urls) > 0:
                        users_with_urls += 1
                        total_urls += len(urls)
                except:
                    continue
        
        return {
            'total_users': total_users,
            'users_with_urls': users_with_urls,
            'users_without_urls': total_users - users_with_urls,
            'total_urls': total_urls,
            'avg_urls_per_user': round(total_urls / users_with_urls, 2) if users_with_urls > 0 else 0
        }
    except Exception as e:
        print(f"❌ Get URL statistics error: {e}")
        return {}


def cleanup_invalid_urls(phone: str):
    """Clean up invalid URLs for a specific user"""
    try:
        urls = get_user_urls(phone)
        if not urls:
            return True
        
        valid_urls = [url for url in urls if validate_telegram_url(url)]
        
        if len(valid_urls) != len(urls):
            return update_user_urls(phone, valid_urls)
        
        return True
    except Exception as e:
        print(f"❌ Cleanup invalid URLs error: {e}")
        return False
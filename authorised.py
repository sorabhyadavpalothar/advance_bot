# ================== AUTHORISED.PY ==================
import asyncio
import os
import sqlite3
import re
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import add_user

# ================== TEMPORARY STATE STORAGE ==================
user_states = {}

# Ensure sessions folder exists
if not os.path.exists("sessions"):
    os.makedirs("sessions")

# ================== URL VALIDATION ==================
def parse_and_validate_urls(text):
    raw_urls = []
    for line in text.strip().split('\n'):
        raw_urls.extend(line.strip().split())
    
    validated_urls = []
    invalid_urls = []
    
    for url in raw_urls:
        url = url.strip()
        if not url:
            continue
            
        if validate_telegram_url(url):
            validated_urls.append(url)
        else:
            invalid_urls.append(url)
    
    return validated_urls, invalid_urls


def validate_telegram_url(url):
    url = url.strip()
    
    patterns = [
        r'^https://t\.me/c/\d+/\d+$',  # private channels
        r'^https://t\.me/[a-zA-Z0-9_]+/\d+$',  # public channels with message
        r'^https://t\.me/\+[a-zA-Z0-9_-]+$',  # invite links
        r'^https://t\.me/[a-zA-Z0-9_]+$',  # public channels/groups
        r'^@[a-zA-Z0-9_]{5,}$',  # username format
        r'^-?\d{10,}$',  # Chat ID format
        r'^[a-zA-Z0-9_]{5,}$'  # Just username without @
    ]
    
    for pattern in patterns:
        if re.match(pattern, url):
            if pattern == r'^[a-zA-Z0-9_]{5,}$' and url.isdigit():
                continue  # Skip pure numbers for last pattern
            return True
    
    return False


def format_url_display(url):
    if url.startswith('https://t.me/c/'):
        parts = url.split('/')
        return f"Private Channel: {parts[-2]} (Msg: {parts[-1]})"
    elif url.startswith('https://t.me/+'):
        return f"Invite Link: {url[-10:]}"
    elif url.startswith('https://t.me/'):
        parts = url.split('/')
        if len(parts) > 4:
            return f"@{parts[3]} (Msg: {parts[4]})"
        else:
            return f"@{parts[3]}"
    elif url.startswith('@'):
        return url
    elif url.startswith('-'):
        return f"Chat ID: {url}"
    else:
        return f"@{url}"


# ================== KEYBOARDS ==================
def cancel_back_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=f"manage_users"),
         InlineKeyboardButton("⬅️ Back Main Menu", callback_data="back")]
    ])


# ================== START ADD USER ==================
async def start_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    message_id = query.message.message_id

    user_states[user_id] = {"step": "api_id", "data": {}, "message_id": message_id, "client": None}

    await query.edit_message_caption(
        caption="👥 Add Users Section\n\nPlease *enter your API ID* below:",
        parse_mode="Markdown",
        reply_markup=cancel_back_buttons()
    )


# ================== AUTO DELETE HELPER ==================
async def auto_delete(context, chat_id, msg_id, delay=0.5):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception:
        pass


# ================== HANDLE USER INPUT ==================
async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE, main_menu_keyboard):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in user_states:
        return

    state = user_states[user_id]["step"]
    message_id = user_states[user_id]["message_id"]
    chat_id = update.message.chat_id
    user_msg_id = update.message.message_id

    try:
        # Auto delete user's sensitive input
        context.application.create_task(auto_delete(context, chat_id, user_msg_id, delay=0.5))

        # Step 1: API ID
        if state == "api_id":
            try:
                api_id = int(text)
                if api_id <= 0:
                    raise ValueError("API ID must be positive")
                user_states[user_id]["data"]["api_id"] = api_id
                user_states[user_id]["step"] = "api_hash"

                await context.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption="🔑 API ID saved.\n\nNow please *enter your API HASH*:",
                    parse_mode="Markdown",
                    reply_markup=cancel_back_buttons()
                )
            except ValueError:
                error_msg = await context.bot.send_message(
                    chat_id=chat_id, 
                    text="❌ Invalid API ID. Please enter a valid positive number."
                )
                context.application.create_task(auto_delete(context, chat_id, error_msg.message_id, delay=3))

        # Step 2: API HASH
        elif state == "api_hash":
            if len(text) < 10:
                error_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ API HASH seems too short. Please enter a valid API HASH."
                )
                context.application.create_task(auto_delete(context, chat_id, error_msg.message_id, delay=3))
                return

            user_states[user_id]["data"]["api_hash"] = text
            user_states[user_id]["step"] = "mobile"

            await context.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption="📱 API HASH saved.\n\nNow please *enter your Mobile Number with country code* (e.g., +919876543210):",
                parse_mode="Markdown",
                reply_markup=cancel_back_buttons()
            )

        # Step 3: Mobile Number → Send OTP
        elif state == "mobile":
            if not re.match(r'^\+\d{10,15}$', text):
                error_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Invalid phone format. Use: +countrycode followed by number (e.g., +919876543210)"
                )
                context.application.create_task(auto_delete(context, chat_id, error_msg.message_id, delay=3))
                return

            mobile = text
            data = user_states[user_id]["data"]
            api_id = data["api_id"]
            api_hash = data["api_hash"]

            client = None
            try:
                client = TelegramClient(f"sessions/{mobile}", api_id, api_hash)
                await client.connect()

                await client.send_code_request(mobile)
                user_states[user_id]["client"] = client
                user_states[user_id]["data"]["mobile"] = mobile
                user_states[user_id]["step"] = "otp"

                otp_msg = await context.bot.send_message(chat_id=chat_id, text="📩 OTP sent to your Telegram App / SMS!")
                context.application.create_task(auto_delete(context, chat_id, otp_msg.message_id, delay=1))

                await context.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption="📩 Now please *enter the 5-digit OTP* you received:",
                    parse_mode="Markdown",
                    reply_markup=cancel_back_buttons()
                )

            except Exception as e:
                print(f"❌ OTP send error: {e}")
                await context.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=f"❌ Failed to send OTP. Please check your API credentials and phone number.\n\nError: {str(e)[:100]}",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard()
                )
                if client:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                user_states.pop(user_id, None)

        # Step 4: OTP Verification
        elif state == "otp":
            if not re.match(r'^\d{5}$', text):
                error_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Invalid OTP format. Please enter exactly 5 digits."
                )
                context.application.create_task(auto_delete(context, chat_id, error_msg.message_id, delay=3))
                return

            otp = text
            client: TelegramClient = user_states[user_id]["client"]
            mobile = user_states[user_id]["data"]["mobile"]

            try:
                await client.sign_in(mobile, otp)

                if not await client.is_user_authorized():
                    raise SessionPasswordNeededError()

                data = user_states[user_id]["data"]

                # Save user into DB
                add_user(data["api_id"], data["api_hash"], data["mobile"])

                # Next step: URLs
                user_states[user_id]["step"] = "urls"

                await context.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=f"✅ User Authorized Successfully!\n\n"
                            f"• API ID: `{data['api_id']}`\n"
                            f"• API HASH: `{data['api_hash']}`\n"
                            f"• Mobile: `{data['mobile']}`\n\n"
                            f"📌 Now please send me *URLs/channels* in any of these formats:\n"
                            f"• `https://t.me/c/1234567890/123` (Private channel)\n"
                            f"• `https://t.me/channel/123` (Public channel)\n"
                            f"• `https://t.me/+InviteHash` (Invite link)\n"
                            f"• `@username` (Username)\n"
                            f"• `-1001234567890` (Chat ID)\n\n"
                            f"*Send multiple URLs separated by spaces or new lines:*",
                    parse_mode="Markdown",
                    reply_markup=cancel_back_buttons()
                )

            except SessionPasswordNeededError:
                error_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text="🔐 Your account has 2FA password enabled. Please enter your password manually through Telegram app first, then try again."
                )
                context.application.create_task(auto_delete(context, chat_id, error_msg.message_id, delay=5))
            except Exception as e:
                print(f"❌ OTP verification error: {e}")
                error_msg = await context.bot.send_message(
                    chat_id=chat_id, 
                    text=f"❌ OTP Verification Failed: {str(e)[:100]}"
                )
                context.application.create_task(auto_delete(context, chat_id, error_msg.message_id, delay=3))

        # Step 5: URLs input
        elif state == "urls":
            validated_urls, invalid_urls = parse_and_validate_urls(text)
            
            if not validated_urls:
                error_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ No valid URLs found. Please check the format and try again.\n\n"
                         "Supported formats:\n"
                         "• https://t.me/c/1234567890/123\n"
                         "• https://t.me/channel/123\n"
                         "• https://t.me/+InviteHash\n"
                         "• @username\n"
                         "• -1001234567890"
                )
                context.application.create_task(auto_delete(context, chat_id, error_msg.message_id, delay=5))
                return

            try:
                from database import update_user_urls
                mobile = user_states[user_id]["data"]["mobile"]
                update_user_urls(mobile, validated_urls)

                user_states[user_id]["step"] = "delay"

                # Format URLs for display
                url_list = "\n".join([f"• {format_url_display(url)}" for url in validated_urls])
                
                invalid_msg = ""
                if invalid_urls:
                    invalid_msg = f"\n\n⚠️ *Invalid URLs (ignored):*\n" + "\n".join([f"• {url}" for url in invalid_urls])

                await context.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=f"✅ URLs saved successfully!\n\n"
                            f"📌 *Valid URLs added ({len(validated_urls)}):*\n{url_list}"
                            f"{invalid_msg}\n\n"
                            f"⏱️ Now please enter the *delay in seconds* (e.g., `3600`):",
                    parse_mode="Markdown",
                    reply_markup=cancel_back_buttons()
                )
            except Exception as e:
                print(f"❌ Database error: {e}")
                error_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Failed to save URLs to database. Please try again."
                )
                context.application.create_task(auto_delete(context, chat_id, error_msg.message_id, delay=3))

        # Step 6: Delay input
        elif state == "delay":
            try:
                delay = int(text)
                if delay < 1:
                    raise ValueError("Delay must be positive")
                if delay > 86400:  # 24 hours max
                    raise ValueError("Delay too large (max 24 hours)")
                    
                mobile = user_states[user_id]["data"]["mobile"]

                # Update delay in DB
                conn = sqlite3.connect("users.db")
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET delay = ? WHERE phone = ?", (delay, mobile))
                conn.commit()
                conn.close()

                # Next step: forwarding choice
                user_states[user_id]["step"] = "forwarding"

                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶️ Start Auto Forwarding", callback_data="forward_start")],
                    [InlineKeyboardButton("⏭️ Skip", callback_data="forward_skip")]
                ])

                await context.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=f"✅ Delay set successfully!\n\n"
                            f"⏱️ Current delay: `{delay}` seconds ({delay//3600}h {(delay%3600)//60}m {delay%60}s)\n\n"
                            f"📡 Do you want to enable *Auto Forwarding* now?",
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )

            except ValueError as ve:
                error_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Invalid input: {str(ve)}. Please enter delay in *seconds* as a positive number (1-86400).",
                    parse_mode="Markdown"
                )
                context.application.create_task(auto_delete(context, chat_id, error_msg.message_id, delay=3))
            except Exception as e:
                print(f"❌ Database error during delay update: {e}")
                error_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Failed to save delay. Please try again."
                )
                context.application.create_task(auto_delete(context, chat_id, error_msg.message_id, delay=3))

    except Exception as e:
        print(f"❌ Handle user input error: {e}")
        try:
            await context.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption="❌ An error occurred during user setup. Returning to main menu.",
                reply_markup=main_menu_keyboard()
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ An error occurred. Returning to main menu.",
                reply_markup=main_menu_keyboard()
            )
        user_states.pop(user_id, None)


# ================== HANDLE FORWARDING CALLBACK ==================
async def handle_forwarding(update: Update, context: ContextTypes.DEFAULT_TYPE, main_menu_keyboard):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in user_states:
        return

    try:
        mobile = user_states[user_id]["data"]["mobile"]
        from database import set_forwarding

        if query.data == "forward_start":
            set_forwarding(mobile, True)
            await query.edit_message_caption(
                caption="✅ Auto Forwarding started successfully!\n\n🏠 Returning to main menu...",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )

        elif query.data == "forward_skip":
            set_forwarding(mobile, False)
            await query.edit_message_caption(
                caption="⏭️ Skipped. Auto Forwarding is disabled.\n\n🏠 Returning to main menu...",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )

        # Clear memory state after finishing
        user_states.pop(user_id, None)
    except Exception as e:
        print(f"❌ Handle forwarding error: {e}")
        user_states.pop(user_id, None)
        await query.edit_message_caption(
            caption="❌ An error occurred. Returning to main menu.",
            reply_markup=main_menu_keyboard()
        )
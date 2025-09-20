import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import update_user_urls, get_user_by_phone

# Temporary storage for step tracking
url_states = {}  # {user_id: {"step": "entering", "message_id": int, "phone": str}}

# Cancel / Back buttons
def cancel_back_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
         InlineKeyboardButton("⬅️ Back", callback_data="back")]
    ])


# Auto delete helper
async def auto_delete(context, chat_id, msg_id, delay=0.5):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception:
        pass


# Start Manage URLs Flow
async def start_manage_urls(update: Update, context: ContextTypes.DEFAULT_TYPE, phone):
    query = update.callback_query
    user_id = query.from_user.id
    message_id = query.message.message_id

    # Save state
    url_states[user_id] = {"step": "entering", "message_id": message_id, "phone": phone}

    # Fetch existing URLs
    user = get_user_by_phone(phone)
    existing_urls = []
    if user and user[6]:  # urls column index
        try:
            import json
            existing_urls = json.loads(user[6])
        except:
            existing_urls = []

    urls_text = "\n".join(existing_urls) if existing_urls else "None"

    await query.edit_message_caption(
        caption=f"🌐 Manage URLs Section\n\nCurrent URLs:\n{urls_text}\n\nPlease *enter your URLs* (comma separated):",
        parse_mode="Markdown",
        reply_markup=cancel_back_buttons()
    )


# Handle URLs Input
async def handle_urls_input(update: Update, context: ContextTypes.DEFAULT_TYPE, main_menu_keyboard):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in url_states:
        return

    state = url_states[user_id]["step"]
    phone = url_states[user_id]["phone"]
    message_id = url_states[user_id]["message_id"]
    chat_id = update.message.chat_id
    user_msg_id = update.message.message_id

    # Delete user input
    context.application.create_task(auto_delete(context, chat_id, user_msg_id, delay=0.5))

    if state == "entering":
        # Split URLs by comma
        urls = [u.strip() for u in text.split(",") if u.strip()]
        if not urls:
            await update.message.reply_text("❌ Invalid input! Please enter at least one valid URL.")
            context.application.create_task(auto_delete(context, chat_id, update.message.message_id, delay=1))
            return

        # Save to DB
        update_user_urls(phone, urls)

        # Show confirmation on same message
        await context.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=f"✅ URLs Updated Successfully!\n\n🌐 Saved URLs:\n" + "\n".join(urls),
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )

        # Clear state
        url_states.pop(user_id, None)
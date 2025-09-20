from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
import database

# State tracking for log channel input {admin_id: {"phone": str}}
log_channel_states = {}


def add_log_channel_keyboard(phone: str):
    """Keyboard for log channel management"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 Set Log Channel", callback_data=f"addlog_{phone}")],
        [InlineKeyboardButton("🗑 Remove Log Channel", callback_data=f"removelog_{phone}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"userdetails_{phone}")]
    ])


async def safe_edit_or_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    """Edit message if possible, otherwise reply"""
    if update.callback_query and update.callback_query.message:
        try:
            # Prefer editing text (works for most messages)
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        except Exception:
            try:
                # Fallback if the original was a media message with a caption
                await update.callback_query.edit_message_caption(
                    caption=text,
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
            except Exception:
                # If editing fails, answer the callback query and send new message
                await update.callback_query.answer()
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
    elif update.message:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        # Fallback: send message to the effective chat
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )


async def start_add_log_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    """Prompt admin to enter a log channel ID for the user."""
    try:
        admin_id = update.effective_user.id
        log_channel_states[admin_id] = {"phone": phone}

        await safe_edit_or_reply(
            update,
            context,
            (
                f"📡 **Set Log Channel for {phone}**\n\n"
                f"Enter the Log Channel ID where forwarding reports will be sent.\n\n"
                f"**Examples:**\n"
                f"• `-1001234567890` (for channels)\n"
                f"• `-987654321` (for groups)\n"
                f"• `123456789` (for private chats)\n\n"
                f"⚠️ **Important:** Make sure the bot is added as an **admin** in the target channel/group!"
            ),
            InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ])
        )
    except Exception as e:
        print(f"❌ Error starting log channel setup: {e}")
        await safe_edit_or_reply(
            update,
            context,
            "❌ Error initiating log channel setup.",
            InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
        )


async def save_log_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the entered log channel ID into the database."""
    admin_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if admin_id not in log_channel_states:
        return

    phone = log_channel_states[admin_id]["phone"]
    text = update.message.text.strip()

    try:
        # Validate and parse channel ID
        log_channel_id = int(text)

        # Basic validation
        if log_channel_id > 0:
            pass  # user/bot ID
        elif log_channel_id < -1000000000000:  # Supergroup/channel
            pass
        elif log_channel_id < 0:  # Regular group
            pass
        else:
            raise ValueError("Invalid ID format")

        # Test if bot can send messages to the channel
        try:
            await context.bot.send_message(
                chat_id=log_channel_id,
                text=f"✅ Log channel configured for user: {phone}\n\nThis channel will receive forwarding reports."
            )
            print(f"✅ Successfully sent test message to {log_channel_id}")
        except Exception as bot_error:
            await update.message.reply_text(
                f"❌ **Failed to send test message to channel/group!**\n\n"
                f"**Error:** {str(bot_error)}\n\n"
                f"**Please ensure:**\n"
                f"• The bot is added to the channel/group\n"
                f"• The bot has admin permissions\n"
                f"• The channel/group ID is correct\n\n"
                f"Try again with a different ID.",
                parse_mode="Markdown"
            )
            return

        # Update database
        success = database.update_user_log_channel(phone, log_channel_id)

        if success:
            user = database.get_user_by_phone(phone)
            if user:
                # Import and call show_user_details directly with a new message approach
                from user_manage import show_user_details_text, get_user_details_keyboard
                
                # Get user details text and keyboard
                details_text = show_user_details_text(user)
                details_keyboard = get_user_details_keyboard(user['id'])
                
                # Send success message first
                await update.message.reply_text(
                    f"✅ **Log Channel Updated Successfully!**\n\n"
                    f"📞 User: `{phone}`\n"
                    f"📡 Log Channel: `{log_channel_id}`",
                    parse_mode="Markdown"
                )
                
                # Then send user details
                await update.message.reply_text(
                    details_text,
                    parse_mode="Markdown",
                    reply_markup=details_keyboard
                )
            else:
                await update.message.reply_text(
                    f"✅ **Log Channel Updated Successfully!**\n\n"
                    f"📞 User: `{phone}`\n"
                    f"📡 Log Channel: `{log_channel_id}`\n\n"
                    f"Forwarding reports will now be sent to this channel.",
                    parse_mode="Markdown"
                )
        else:
            await update.message.reply_text(
                f"❌ Database update failed for user `{phone}`.\n\nPlease try again.",
                parse_mode="Markdown"
            )

    except ValueError:
        await update.message.reply_text(
            f"❌ **Invalid Channel ID Format**\n\n"
            f"Please enter a valid Telegram ID:\n"
            f"• Channel: `-1001234567890`\n"
            f"Try again:",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"❌ Error saving log channel: {e}")
        await update.message.reply_text(
            f"❌ **Failed to update log channel**\n\n"
            f"Error: {str(e)}\n\nPlease try again.",
            parse_mode="Markdown"
        )
    finally:
        # Always clean up state
        log_channel_states.pop(admin_id, None)


async def remove_log_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    """Remove log channel for a user"""
    try:
        success = database.update_user_log_channel(phone, None)

        if success:
            user = database.get_user_by_phone(phone)
            if user:
                # Import helper functions instead of trying to call show_user_details
                from user_manage import show_user_details_text, get_user_details_keyboard
                
                # Get user details text and keyboard
                details_text = show_user_details_text(user)
                details_keyboard = get_user_details_keyboard(user['id'])
                
                # Send updated user details
                await safe_edit_or_reply(
                    update,
                    context,
                    details_text,
                    details_keyboard
                )
            else:
                await safe_edit_or_reply(
                    update,
                    context,
                    f"✅ Log channel removed for user `{phone}`."
                )
        else:
            await safe_edit_or_reply(
                update,
                context,
                f"❌ Failed to remove log channel for user `{phone}`."
            )

    except Exception as e:
        print(f"❌ Error removing log channel: {e}")
        await safe_edit_or_reply(
            update,
            context,
            "❌ Error removing log channel.",
            InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
        )


def cleanup_state(admin_id: int):
    """Clean up state when user cancels or returns to main menu"""
    log_channel_states.pop(admin_id, None)
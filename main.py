# main.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from config import BOT_TOKEN, WELCOME_IMAGE, PRIMARY_ADMIN
import authorised
import update_urls
import user_manage
import add_log_channel
from database import init_db

import asyncio
from forwarder import run_forwarders, stop_forwarders


# ================== AUTH CHECK ==================
def is_authorized(user_id: int) -> bool:
    return user_id == PRIMARY_ADMIN


# ================== KEYBOARDS ==================
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Manage Users", callback_data="manage_users")],
        [InlineKeyboardButton("🔗 Update URLs", callback_data="update_urls")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("🚀 Features (Coming Soon)", callback_data="coming_soon")],
    ])


def back_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back", callback_data="back")]
    ])


# ================== START COMMAND ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        if not user:
            print("❌ No user information in start command")
            return

        if not is_authorized(user.id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return

        try:
            await update.message.reply_photo(
                photo=WELCOME_IMAGE,
                caption=f"👋 Welcome, {user.first_name}!\n\n"
                        f"Use the buttons below to manage your bot.",
                reply_markup=main_menu_keyboard(),
            )
        except Exception as e:
            print(f"❌ Failed to send welcome image: {e}")
            await update.message.reply_text(
                f"👋 Welcome, {user.first_name}!\n\n"
                f"Use the buttons below to manage your bot.",
                reply_markup=main_menu_keyboard()
            )
    except Exception as e:
        print(f"❌ Start command error: {e}")
        try:
            await update.message.reply_text("❌ An error occurred. Please try again.")
        except Exception:
            pass


# ================== CALLBACK HANDLER ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        if not query or not query.from_user:
            print("❌ No query or user information in callback")
            return

        user_id = query.from_user.id

        if not is_authorized(user_id):
            await query.answer("⛔ Unauthorized", show_alert=True)
            return

        await query.answer()

        # -------- Manage Users Flow --------
        if query.data == "manage_users":
            await query.edit_message_caption(
                caption="👥 Manage Users Menu:",
                reply_markup=user_manage.manage_users_keyboard()
            )

        elif query.data.startswith("userpage_"):
            try:
                page = int(query.data.split("_")[1])
                await user_manage.show_user_list(update, context, page)
            except (ValueError, IndexError):
                await query.edit_message_caption(
                    caption="❌ Invalid page number.",
                    reply_markup=user_manage.manage_users_keyboard()
                )

        elif query.data.startswith("userdetails_"):
            try:
                uid = int(query.data.split("_")[1])
                await user_manage.show_user_details(update, context, uid)
            except (ValueError, IndexError):
                await query.edit_message_caption(
                    caption="❌ Invalid user ID.",
                    reply_markup=user_manage.manage_users_keyboard()
                )

        elif query.data.startswith("delete_confirm_"):
            try:
                parts = query.data.split("_", 3)
                if len(parts) < 4:
                    raise ValueError("Invalid callback data format")
                _, _, uid, phone = parts
                await user_manage.confirm_delete_prompt(update, context, int(uid), phone)
            except (ValueError, IndexError):
                await query.edit_message_caption(
                    caption="❌ Invalid delete request.",
                    reply_markup=user_manage.manage_users_keyboard()
                )

        elif query.data.startswith("delete_yes_"):
            try:
                parts = query.data.split("_", 3)
                if len(parts) < 4:
                    raise ValueError("Invalid callback data format")
                _, _, uid, phone = parts
                await user_manage.confirm_delete(update, context, int(uid), phone)
            except (ValueError, IndexError):
                await query.edit_message_caption(
                    caption="❌ Delete operation failed.",
                    reply_markup=user_manage.manage_users_keyboard()
                )

        # -------- User Details Updates --------
        elif query.data.startswith("update_delay_"):
            try:
                parts = query.data.split("_", 3)
                if len(parts) < 4:
                    raise ValueError("Invalid callback data format")
                _, _, uid, phone = parts
                await user_manage.start_update_delay(update, context, int(uid), phone)
            except (ValueError, IndexError):
                await query.edit_message_caption(
                    caption="❌ Failed to initiate delay update.",
                    reply_markup=main_menu_keyboard()
                )

        elif query.data.startswith("update_forward_"):
            try:
                parts = query.data.split("_", 3)
                if len(parts) < 4:
                    raise ValueError("Invalid callback data format")
                _, _, uid, phone = parts
                await user_manage.toggle_forwarding(update, context, int(uid), phone)
            except (ValueError, IndexError):
                await query.edit_message_caption(
                    caption="❌ Failed to toggle forwarding.",
                    reply_markup=main_menu_keyboard()
                )

        elif query.data.startswith("update_expiry_"):
            try:
                parts = query.data.split("_", 3)
                if len(parts) < 4:
                    raise ValueError("Invalid callback data format")
                _, _, uid, phone = parts
                await user_manage.start_update_expiry(update, context, int(uid), phone)
            except (ValueError, IndexError):
                await query.edit_message_caption(
                    caption="❌ Failed to initiate expiry update.",
                    reply_markup=main_menu_keyboard()
                )

        elif query.data.startswith("update_urls_"):
            try:
                phone = query.data.split("_", 2)[2]
                if not phone:
                    raise ValueError("Empty phone number")
                await update_urls.show_user_urls(update, context, phone)
            except (IndexError, ValueError):
                await query.edit_message_caption(
                    caption="❌ Invalid phone number.",
                    reply_markup=main_menu_keyboard()
                )

        # -------- Log Channel Management --------
        elif query.data.startswith("addlog_"):
            try:
                phone = query.data.split("_", 1)[1]
                if not phone:
                    raise ValueError("Empty phone number")
                await add_log_channel.start_add_log_channel(update, context, phone)
            except (IndexError, ValueError):
                await query.edit_message_caption(
                    caption="❌ Invalid log channel request.",
                    reply_markup=main_menu_keyboard()
                )

        elif query.data.startswith("removelog_"):
            try:
                phone = query.data.split("_", 1)[1]
                if not phone:
                    raise ValueError("Empty phone number")
                await add_log_channel.remove_log_channel(update, context, phone)
            except (IndexError, ValueError):
                await query.edit_message_caption(
                    caption="❌ Invalid remove log channel request.",
                    reply_markup=main_menu_keyboard()
                )

        # -------- Add Users Flow --------
        elif query.data == "add_users":
            await authorised.start_add_user(update, context)

        # -------- Update URLs Flow --------
        elif query.data == "update_urls":
            await update_urls.show_user_list(update, context, page=1)

        elif query.data.startswith("userpageurl_"):
            try:
                page = int(query.data.split("_")[1])
                await update_urls.show_user_list(update, context, page)
            except (ValueError, IndexError):
                await update_urls.show_user_list(update, context, page=1)

        elif query.data.startswith("user_"):
            try:
                phone = query.data.split("_", 1)[1]
                if not phone:
                    raise ValueError("Empty phone number")
                await update_urls.show_user_urls(update, context, phone)
            except (IndexError, ValueError):
                await query.edit_message_caption(
                    caption="❌ Invalid user selection.",
                    reply_markup=main_menu_keyboard()
                )

        elif query.data.startswith("addurls_"):
            try:
                phone = query.data.split("_", 1)[1]
                if not phone:
                    raise ValueError("Empty phone number")
                await update_urls.start_add_urls(update, context, phone)
            except (IndexError, ValueError):
                await query.edit_message_caption(
                    caption="❌ Failed to initiate URL addition.",
                    reply_markup=main_menu_keyboard()
                )

        elif query.data.startswith("deleteurls_"):
            try:
                phone = query.data.split("_", 1)[1]
                if not phone:
                    raise ValueError("Empty phone number")
                await update_urls.start_delete_urls(update, context, phone)
            except (IndexError, ValueError):
                await query.edit_message_caption(
                    caption="❌ Failed to initiate URL deletion.",
                    reply_markup=main_menu_keyboard()
                )

        elif query.data.startswith("delurl_"):
            try:
                parts = query.data.split("_", 2)
                if len(parts) < 3:
                    raise ValueError("Invalid callback data format")
                _, phone, idx = parts
                if not phone:
                    raise ValueError("Empty phone number")
                await update_urls.confirm_delete_url(update, context, phone, int(idx))
            except (ValueError, IndexError):
                await query.edit_message_caption(
                    caption="❌ Failed to delete URL.",
                    reply_markup=main_menu_keyboard()
                )

        # -------- Settings & Coming Soon --------
        elif query.data == "settings":
            await query.edit_message_caption(
                caption="⚙️ Settings section.\n(Feature will be implemented soon!)",
                reply_markup=back_button(),
            )

        elif query.data == "coming_soon":
            await query.edit_message_caption(
                caption="🚀 Exciting Features are coming soon. Stay tuned!",
                reply_markup=back_button(),
            )

        # -------- Back / Cancel --------
        elif query.data == "back":
            # Clean up all states
            authorised.user_states.pop(user_id, None)
            add_log_channel.cleanup_state(user_id)
            await query.edit_message_caption(
                caption="🏠 Main Menu:\n\nChoose an option below:",
                reply_markup=main_menu_keyboard(),
            )

        elif query.data == "cancel":
            # Clean up all states
            authorised.user_states.pop(user_id, None)
            add_log_channel.cleanup_state(user_id)
            await query.edit_message_caption(
                caption="❌ Action cancelled.\n\n🏠 Back to Main Menu:",
                reply_markup=main_menu_keyboard(),
            )

        # -------- Forwarding Choice --------
        elif query.data in ["forward_start", "forward_skip"]:
            await authorised.handle_forwarding(update, context, main_menu_keyboard)

    except Exception as e:
        print(f"❌ Button handler error: {e}")
        try:
            if update.callback_query:
                await update.callback_query.edit_message_caption(
                    caption="❌ An error occurred. Returning to main menu.",
                    reply_markup=main_menu_keyboard()
                )
        except Exception:
            try:
                if update.callback_query and update.callback_query.message:
                    await update.callback_query.message.reply_text(
                        "❌ An error occurred. Returning to main menu.",
                        reply_markup=main_menu_keyboard()
                    )
            except Exception as nested_e:
                print(f"❌ Failed to send error message: {nested_e}")


# ================== MESSAGE HANDLER ==================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Check if update and user exist
        if not update or not update.effective_user:
            print("❌ No user information in message handler")
            return

        user = update.effective_user

        if not is_authorized(user.id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return

        # Handle user management text inputs
        from user_manage import user_edit_states, save_update_delay, save_update_expiry

        uid = user.id
        if uid in user_edit_states:
            state = user_edit_states.pop(uid)
            action = state["action"]
            phone = state["phone"]

            if action == "update_delay":
                await save_update_delay(update, context, phone, update.message.text)
            elif action == "update_expiry":
                await save_update_expiry(update, context, phone, update.message.text)
            return

        # Handle log channel input
        from add_log_channel import log_channel_states, save_log_channel
        if uid in log_channel_states:
            await save_log_channel(update, context)
            return

        # Add User Flow (API ID, HASH, Mobile, OTP, URLs, Delay)
        await authorised.handle_user_input(update, context, main_menu_keyboard)

        # Update URLs Flow (adding URLs)
        await update_urls.save_new_urls(update, context)

    except Exception as e:
        print(f"❌ Message handler error: {e}")
        try:
            if update and update.message:
                await update.message.reply_text(
                    "❌ An error occurred processing your message.",
                    reply_markup=main_menu_keyboard()
                )
        except Exception:
            pass


# ================== ERROR HANDLER ==================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to notify the developer."""
    print(f"❌ Exception while handling an update: {context.error}")
    
    # Try to send a user-friendly error message
    try:
        if update and isinstance(update, Update):
            if update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Something went wrong. Please try again.",
                    reply_markup=main_menu_keyboard()
                )
    except Exception:
        pass


# ================== MAIN ==================
def main():
    try:
        init_db()

        app = Application.builder().token(BOT_TOKEN).build()

        # Add error handler
        app.add_error_handler(error_handler)

        # Handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

        # Lifecycle hooks
        async def startup(_: Application):
            try:
                await run_forwarders()
                print("🚀 Forwarders started in background...")
            except Exception as e:
                print(f"❌ Failed to start forwarders: {e}")

        async def shutdown(_: Application):
            try:
                await stop_forwarders()
                print("🛑 Forwarders stopped, bot shutdown complete.")
            except Exception as e:
                print(f"❌ Error during shutdown: {e}")

        app.post_init = startup
        app.post_shutdown = shutdown

        print("🚀 Bot is running with forwarder...")
        app.run_polling()

    except Exception as e:
        print(f"❌ Critical error in main: {e}")


if __name__ == "__main__":
    main()
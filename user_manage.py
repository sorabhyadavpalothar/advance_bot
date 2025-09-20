# ================== USER_MANAGE.PY (Enhanced Version) ==================
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from database import (
    get_all_users,
    get_user_count,
    get_user_by_id,
    delete_user,
    update_user_delay,
    update_user_expiry_days,
    set_forwarding,
    get_user_by_phone,
)
import os
import asyncio
from datetime import datetime, timedelta

# Global state management with timeout handling
user_edit_states = {}  # temp storage for input states
message_cleanup_tasks = {}  # track cleanup tasks


# ================== HELPER FUNCTIONS ==================
async def safe_delete_message(message, delay=30):
    """Safely delete a message after delay"""
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception as e:
        print(f"Failed to delete message: {e}")


async def schedule_message_cleanup(message, delay=30):
    """Schedule message for cleanup"""
    task_id = f"{message.chat.id}_{message.message_id}"
    if task_id in message_cleanup_tasks:
        message_cleanup_tasks[task_id].cancel()
    
    message_cleanup_tasks[task_id] = asyncio.create_task(
        safe_delete_message(message, delay)
    )


def clear_user_state(user_id):
    """Clear user's edit state"""
    if user_id in user_edit_states:
        del user_edit_states[user_id]


def format_delay_display(delay):
    """Format delay in human readable format"""
    if delay < 60:
        return f"{delay} seconds"
    elif delay < 3600:
        minutes = delay // 60
        seconds = delay % 60
        return f"{minutes} minutes" + (f" {seconds}s" if seconds > 0 else "")
    else:
        hours = delay // 3600
        minutes = (delay % 3600) // 60
        return f"{hours} hours" + (f" {minutes}m" if minutes > 0 else "")


def format_expiry_display(expiry_date):
    """Format expiry date display"""
    if not expiry_date or expiry_date == 'Not set':
        return "❌ Not set"
    
    try:
        expiry_dt = datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S")
        current_dt = datetime.now()
        if expiry_dt > current_dt:
            days_left = (expiry_dt - current_dt).days
            return f"✅ {days_left} days left"
        else:
            days_expired = (current_dt - expiry_dt).days
            return f"❌ Expired {days_expired} days ago"
    except:
        return f"⚠️ {expiry_date}"


# ================== MENUS ==================
def manage_users_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add User", callback_data="add_users")],
        [InlineKeyboardButton("📋 View Users", callback_data="userpage_0")],
        [InlineKeyboardButton("⬅️ Back to Main", callback_data="back")],
    ])


async def show_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    try:
        query = update.callback_query
        users = get_all_users(offset=page * 5, limit=5)
        total = get_user_count()

        if not users:
            await query.edit_message_caption(
                caption="❌ No users found.", 
                reply_markup=manage_users_keyboard()
            )
            return

        keyboard = []
        for uid, phone, api_id in users:
            # Get user details for status indicators
            user = get_user_by_id(uid)
            status_icon = "🟢" if user and user.get('auto_forwarding') else "🔴"
            keyboard.append([InlineKeyboardButton(
                f"{status_icon} {phone}", 
                callback_data=f"userdetails_{uid}"
            )])

        # Navigation buttons
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"userpage_{page-1}"))
        if (page + 1) * 5 < total:
            nav.append(InlineKeyboardButton("Next ➡", callback_data=f"userpage_{page+1}"))
        if nav:
            keyboard.append(nav)

        keyboard.append([
            InlineKeyboardButton("⬅️ Back", callback_data="manage_users"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="back")
        ])

        await query.edit_message_caption(
            caption=(
                f"📋 **Users List** (Page {page+1})\n\n"
                f"👥 **Total Users:** {total}\n"
                f"🟢 = Active | 🔴 = Inactive\n\n"
                f"Select a user to view details:"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        print(f"❌ Show user list error: {e}")
        await query.edit_message_caption(
            caption="❌ Error loading user list. Please try again.",
            reply_markup=manage_users_keyboard()
        )


async def show_user_details(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int):
    try:
        query = update.callback_query
        user = get_user_by_id(uid)
        if not user:
            await query.edit_message_caption(
                caption="⚠️ User not found or has been deleted.", 
                reply_markup=manage_users_keyboard()
            )
            return

        # Format all display values
        log_channel_display = user.get('log_channel_id', 'Not set')
        if log_channel_display and log_channel_display != 'Not set':
            log_channel_display = f"`{log_channel_display}`"
        else:
            log_channel_display = "❌ Not set"

        # URLs display
        urls_display = "❌ No URLs"
        try:
            import json
            urls = json.loads(user.get('urls', '[]'))
            if urls:
                urls_display = f"✅ {len(urls)} URL(s)"
        except:
            urls_display = "⚠️ Invalid URL data"

        delay_display = format_delay_display(user.get('delay', 5))
        expiry_display = format_expiry_display(user.get('expiry_date'))
        forwarding_status = "✅ Enabled" if user.get('auto_forwarding') else "❌ Disabled"
        forwarding_icon = "🟢" if user.get('auto_forwarding') else "🔴"

        caption = (
            f"👤 **User Details**\n\n"
            f"📞 **Phone:** `{user['phone']}`\n"
            f"🆔 **API ID:** `{user['api_id']}`\n"
            f"⏱ **Delay:** {delay_display}\n"
            f"{forwarding_icon} **Forwarding:** {forwarding_status}\n"
            f"📅 **Expiry:** {expiry_display}\n"
            f"📡 **Log Channel:** {log_channel_display}\n"
            f"🔗 **URLs:** {urls_display}\n"
            f"📌 **Created:** {user.get('created_at', 'Unknown')}\n"
        )

        keyboard = [
            [InlineKeyboardButton(
                f"🔁 {'Disable' if user.get('auto_forwarding') else 'Enable'} Forwarding", 
                callback_data=f"update_forward_{uid}_{user['phone']}"
            )],
            [
                InlineKeyboardButton("⏱ Update Delay", callback_data=f"update_delay_{uid}_{user['phone']}"),
                InlineKeyboardButton("📅 Update Expiry", callback_data=f"update_expiry_{uid}_{user['phone']}")
            ],
            [
                InlineKeyboardButton("📡 Log Channel", callback_data=f"addlog_{user['phone']}"),
                InlineKeyboardButton("🔗 Manage URLs", callback_data=f"update_urls_{user['phone']}")
            ],
            [
                InlineKeyboardButton("⬅️ Back to List", callback_data="userpage_0"),
                InlineKeyboardButton("🗑 Delete User", callback_data=f"delete_confirm_{uid}_{user['phone']}")
            ],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back")],
        ]

        await query.edit_message_caption(
            caption=caption,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        print(f"❌ Show user details error: {e}")
        await query.edit_message_caption(
            caption="❌ Error loading user details. Please try again.",
            reply_markup=manage_users_keyboard()
        )


# ================== DELETE FUNCTIONS ==================
async def confirm_delete_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, uid, phone):
    try:
        query = update.callback_query
        user = get_user_by_id(uid)
        
        if not user:
            await query.edit_message_caption(
                caption="⚠️ User not found.", 
                reply_markup=manage_users_keyboard()
            )
            return

        # Get comprehensive user info
        urls_count = 0
        try:
            import json
            urls = json.loads(user.get('urls', '[]'))
            urls_count = len(urls)
        except:
            pass

        user_info = (
            f"\n**User Information:**\n"
            f"📞 Phone: `{phone}`\n"
            f"🆔 API ID: `{user['api_id']}`\n"
            f"🔗 URLs: {urls_count} configured\n"
            f"🔁 Forwarding: {'Enabled' if user.get('auto_forwarding') else 'Disabled'}\n"
            f"📅 Expiry: {format_expiry_display(user.get('expiry_date'))}\n"
        )

        keyboard = [[
            InlineKeyboardButton("✅ Yes, Delete", callback_data=f"delete_yes_{uid}_{phone}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"userdetails_{uid}"),
        ]]
        
        await query.edit_message_caption(
            caption=(
                f"⚠️ **Delete Confirmation**\n\n"
                f"Are you **absolutely sure** you want to delete this user?\n"
                f"{user_info}\n"
                f"**This will permanently:**\n"
                f"• Remove user from database\n"
                f"• Delete all session files\n"
                f"• Stop all forwarding processes\n"
                f"• Remove all configured URLs\n\n"
                f"**🚨 This action CANNOT be undone!**"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        print(f"❌ Delete prompt error: {e}")
        await query.edit_message_caption(
            caption="❌ Error showing delete confirmation.",
            reply_markup=manage_users_keyboard()
        )


async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, uid, phone):
    try:
        query = update.callback_query
        
        # Show processing message
        await query.edit_message_caption(
            caption=f"🔄 **Deleting user {phone}...**\n\nPlease wait...",
            parse_mode="Markdown"
        )

        # Delete from database first
        success = delete_user(uid)
        
        # Remove session files
        session_patterns = [
            f"sessions/{phone}.session",
            f"sessions/{phone}.session-journal", 
            f"sessions/{phone}",
            f"sessions/{phone}.db",
            f"sessions/{phone}.db-shm",
            f"sessions/{phone}.db-wal"
        ]
        
        removed_files = []
        for pattern in session_patterns:
            if os.path.exists(pattern):
                try:
                    if os.path.isdir(pattern):
                        import shutil
                        shutil.rmtree(pattern)
                        removed_files.append(f"{pattern}/ (directory)")
                    else:
                        os.remove(pattern)
                        removed_files.append(os.path.basename(pattern))
                except Exception as e:
                    print(f"⚠️ Failed to remove {pattern}: {e}")

        if success:
            status_message = (
                f"✅ **User Deleted Successfully**\n\n"
                f"📞 **Phone:** `{phone}`\n"
                f"🗑 **Database:** ✅ Removed\n"
                f"📁 **Session Files:** {len(removed_files)} removed"
            )
            
            if removed_files:
                status_message += f"\n\n**Cleaned Files:**"
                for i, file in enumerate(removed_files[:4]):  # Show max 4 files
                    status_message += f"\n• `{file}`"
                if len(removed_files) > 4:
                    status_message += f"\n• ... and {len(removed_files) - 4} more"
            
            keyboard = [[
                InlineKeyboardButton("📋 View Users", callback_data="userpage_0"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="back")
            ]]
            
        else:
            status_message = (
                f"❌ **Delete Failed**\n\n"
                f"📞 Phone: `{phone}`\n\n"
                f"Could not remove user from database. "
                f"Please check logs and try again."
            )
            keyboard = [[
                InlineKeyboardButton("🔄 Retry", callback_data=f"delete_confirm_{uid}_{phone}"),
                InlineKeyboardButton("⬅️ Back", callback_data=f"userdetails_{uid}")
            ]]

        await query.edit_message_caption(
            caption=status_message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        print(f"❌ Confirm delete error: {e}")
        await query.edit_message_caption(
            caption=(
                f"❌ **Error During Deletion**\n\n"
                f"Phone: `{phone}`\n"
                f"Error: {str(e)}\n\n"
                f"Please try again or contact support."
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Retry", callback_data=f"delete_confirm_{uid}_{phone}"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="back")
            ]])
        )


# ================== UPDATE DELAY ==================
async def start_update_delay(update: Update, context: ContextTypes.DEFAULT_TYPE, uid, phone):
    try:
        query = update.callback_query
        user_id = query.from_user.id
        
        # Clear any existing state
        clear_user_state(user_id)
        
        # Set new state with timeout
        user_edit_states[user_id] = {
            "action": "update_delay", 
            "phone": phone, 
            "uid": uid,
            "timestamp": datetime.now()
        }
        
        # Get current delay
        user = get_user_by_id(uid)
        current_delay = user.get('delay', 5) if user else 5
        current_display = format_delay_display(current_delay)
        
        await query.edit_message_caption(
            caption=(
                f"⏱ **Update Delay for {phone}**\n\n"
                f"**Current Delay:** {current_display}\n\n"
                f"Enter the new delay time:\n\n"
                f"**Supported Formats:**\n"
                f"• `30` or `30s` = 30 seconds\n"
                f"• `5m` = 5 minutes\n"
                f"• `2h` = 2 hours\n"
                f"• `1d` = 1 day\n\n"
                f"**Range:** 1 second to 7 days\n"
                f"**Timeout:** 60 seconds"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data=f"userdetails_{uid}")
            ]]),
        )
        
        # Set timeout for state cleanup
        asyncio.create_task(cleanup_expired_state(user_id, 60))
        
    except Exception as e:
        print(f"❌ Start update delay error: {e}")
        await query.edit_message_caption(
            caption="❌ Error starting delay update. Please try again.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Back", callback_data=f"userdetails_{uid}")
            ]])
        )


async def save_update_delay(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str, text: str):
    user_id = update.effective_user.id
    
    # Create response message first
    response = None
    try:
        delay_str = text.strip().lower()
        
        # Parse different time formats
        delay = parse_time_input(delay_str)
        
        if delay < 1:
            raise ValueError("Delay must be at least 1 second")
        if delay > 604800:  # 7 days max
            raise ValueError("Delay cannot exceed 7 days")
            
        # Update database
        success = update_user_delay(phone, delay)
        
        if success:
            delay_display = format_delay_display(delay)
            
            response = await update.message.reply_text(
                f"✅ **Delay Updated**\n\n"
                f"📞 **User:** `{phone}`\n"
                f"⏱ **New Delay:** {delay_display}\n\n"
                f"✨ Changes will take effect on next message.",
                parse_mode="Markdown"
            )
            
            # Return to user details
            user = get_user_by_phone(phone)
            if user:
                # Small delay to show success message
                await asyncio.sleep(1)
                await show_user_details(update, context, user['id'])
        else:
            response = await update.message.reply_text(
                "❌ **Update Failed**\n\n"
                "Could not update delay in database.\n"
                "Please try again.",
                parse_mode="Markdown"
            )
            
    except ValueError as ve:
        response = await update.message.reply_text(
            f"❌ **Invalid Format**\n\n"
            f"**Error:** {str(ve)}\n\n"
            f"**Examples:**\n"
            f"• `30` or `30s` = 30 seconds\n"
            f"• `5m` = 5 minutes\n"
            f"• `2h` = 2 hours\n"
            f"• `1d` = 1 day",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"❌ Save delay error: {e}")
        response = await update.message.reply_text(
            "❌ **System Error**\n\n"
            "Failed to process your request.\n"
            "Please try again later.",
            parse_mode="Markdown"
        )
    
    finally:
        # Clean up state and schedule message cleanup
        clear_user_state(user_id)
        
        # Delete user input immediately
        try:
            await update.message.delete()
        except:
            pass
            
        # Schedule response cleanup
        if response:
            await schedule_message_cleanup(response, 5)


# ================== UPDATE EXPIRY ==================
async def start_update_expiry(update: Update, context: ContextTypes.DEFAULT_TYPE, uid, phone):
    try:
        query = update.callback_query
        user_id = query.from_user.id
        
        # Clear any existing state
        clear_user_state(user_id)
        
        # Set new state
        user_edit_states[user_id] = {
            "action": "update_expiry", 
            "phone": phone, 
            "uid": uid,
            "timestamp": datetime.now()
        }
        
        # Get current expiry
        user = get_user_by_id(uid)
        current_expiry = format_expiry_display(user.get('expiry_date') if user else None)
        
        await query.edit_message_caption(
            caption=(
                f"📅 **Update Expiry for {phone}**\n\n"
                f"**Current Status:** {current_expiry}\n\n"
                f"Enter extension period from **today**:\n\n"
                f"**Supported Formats:**\n"
                f"• `7` or `7d` = 7 days\n"
                f"• `2w` = 2 weeks\n" 
                f"• `3m` = 3 months\n"
                f"• `1y` = 1 year\n\n"
                f"**Range:** 1 day to 10 years\n"
                f"**Timeout:** 60 seconds"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data=f"userdetails_{uid}")
            ]]),
        )
        
        # Set timeout for state cleanup
        asyncio.create_task(cleanup_expired_state(user_id, 60))
        
    except Exception as e:
        print(f"❌ Start update expiry error: {e}")
        await query.edit_message_caption(
            caption="❌ Error starting expiry update. Please try again.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Back", callback_data=f"userdetails_{uid}")
            ]])
        )


async def save_update_expiry(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str, text: str):
    user_id = update.effective_user.id
    response = None
    
    try:
        days_str = text.strip().lower()
        
        # Parse time period
        days = parse_period_input(days_str)
        
        if days < 1:
            raise ValueError("Extension must be at least 1 day")
        if days > 3650:  # 10 years max
            raise ValueError("Extension cannot exceed 10 years")
            
        # Update database
        success = update_user_expiry_days(phone, days)
        
        if success:
            # Calculate new expiry date
            expiry_date = datetime.now() + timedelta(days=days)
            period_display = format_period_display(days)
            
            response = await update.message.reply_text(
                f"✅ **Expiry Extended**\n\n"
                f"📞 **User:** `{phone}`\n"
                f"📅 **Extended:** {period_display}\n"
                f"🗓 **New Expiry:** {expiry_date.strftime('%Y-%m-%d')}\n\n"
                f"✨ User access updated successfully.",
                parse_mode="Markdown"
            )
            
            # Return to user details
            user = get_user_by_phone(phone)
            if user:
                await asyncio.sleep(1)
                await show_user_details(update, context, user['id'])
        else:
            response = await update.message.reply_text(
                "❌ **Update Failed**\n\n"
                "Could not update expiry in database.\n"
                "Please try again.",
                parse_mode="Markdown"
            )
            
    except ValueError as ve:
        response = await update.message.reply_text(
            f"❌ **Invalid Format**\n\n"
            f"**Error:** {str(ve)}\n\n"
            f"**Examples:**\n"
            f"• `30` or `30d` = 30 days\n"
            f"• `2w` = 2 weeks\n"
            f"• `6m` = 6 months\n"
            f"• `1y` = 1 year",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"❌ Save expiry error: {e}")
        response = await update.message.reply_text(
            "❌ **System Error**\n\n"
            "Failed to process your request.\n"
            "Please try again later.",
            parse_mode="Markdown"
        )
    
    finally:
        # Clean up state and messages
        clear_user_state(user_id)
        
        # Delete user input
        try:
            await update.message.delete()
        except:
            pass
            
        # Schedule response cleanup
        if response:
            await schedule_message_cleanup(response, 5)


# ================== FORWARDING TOGGLE ==================
async def toggle_forwarding(update: Update, context: ContextTypes.DEFAULT_TYPE, uid, phone):
    try:
        query = update.callback_query
        user = get_user_by_id(uid)
        
        if not user:
            await query.edit_message_caption(
                caption="❌ User not found or has been deleted.",
                reply_markup=manage_users_keyboard()
            )
            return
            
        current_status = bool(user.get("auto_forwarding", False))
        new_status = not current_status
        
        # Show processing
        await query.edit_message_caption(
            caption=f"🔄 **Updating forwarding status...**",
            parse_mode="Markdown"
        )
        
        success = set_forwarding(phone, new_status)
        
        if success:
            status_text = "✅ Enabled" if new_status else "❌ Disabled"
            status_emoji = "🟢" if new_status else "🔴"
            action_text = "started" if new_status else "stopped"
            
            # Send notification message
            notification = await query.message.reply_text(
                f"{status_emoji} **Forwarding {status_text.split()[1]}**\n\n"
                f"📞 **User:** `{phone}`\n"
                f"🔁 **Status:** {status_text}\n\n"
                f"✨ Forwarder has been {action_text} for this user.",
                parse_mode="Markdown"
            )
            
            # Schedule cleanup of notification
            await schedule_message_cleanup(notification, 3)
            
            # Return to user details with small delay
            await asyncio.sleep(0.5)
            await show_user_details(update, context, uid)
            
        else:
            await query.edit_message_caption(
                caption=(
                    f"❌ **Toggle Failed**\n\n"
                    f"Could not update forwarding status for `{phone}`.\n"
                    f"Please check database connection and try again."
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Retry", callback_data=f"update_forward_{uid}_{phone}"),
                    InlineKeyboardButton("⬅️ Back", callback_data=f"userdetails_{uid}")
                ]])
            )
    except Exception as e:
        print(f"❌ Toggle forwarding error: {e}")
        await query.edit_message_caption(
            caption="❌ System error while toggling forwarding. Please try again.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Back", callback_data=f"userdetails_{uid}")
            ]])
        )


# ================== UTILITY FUNCTIONS ==================
def parse_time_input(time_str):
    """Parse time input string to seconds"""
    time_str = time_str.strip().lower()
    
    # Remove 'seconds', 'minutes', etc. words
    for word in ['seconds', 'minutes', 'hours', 'days', 'second', 'minute', 'hour', 'day']:
        time_str = time_str.replace(word, '').strip()
    
    if time_str.endswith('s'):
        return int(time_str[:-1])
    elif time_str.endswith('m'):
        return int(time_str[:-1]) * 60
    elif time_str.endswith('h'):
        return int(time_str[:-1]) * 3600
    elif time_str.endswith('d'):
        return int(time_str[:-1]) * 86400
    else:
        return int(time_str)  # assume seconds


def parse_period_input(period_str):
    """Parse period input string to days"""
    period_str = period_str.strip().lower()
    
    # Remove words
    for word in ['days', 'weeks', 'months', 'years', 'day', 'week', 'month', 'year']:
        period_str = period_str.replace(word, '').strip()
    
    if period_str.endswith('d'):
        return int(period_str[:-1])
    elif period_str.endswith('w'):
        return int(period_str[:-1]) * 7
    elif period_str.endswith('m'):
        return int(period_str[:-1]) * 30
    elif period_str.endswith('y'):
        return int(period_str[:-1]) * 365
    else:
        return int(period_str)  # assume days


def format_period_display(days):
    """Format period in human readable format"""
    if days < 30:
        return f"{days} days"
    elif days < 365:
        months = days // 30
        remaining = days % 30
        return f"{months} months" + (f" {remaining} days" if remaining > 0 else "")
    else:
        years = days // 365
        remaining = days % 365
        return f"{years} years" + (f" {remaining} days" if remaining > 0 else "")


async def cleanup_expired_state(user_id, timeout):
    """Clean up expired user edit states"""
    try:
        await asyncio.sleep(timeout)
        if user_id in user_edit_states:
            state = user_edit_states[user_id]
            # Check if state is actually expired
            if datetime.now() - state.get('timestamp', datetime.now()) >= timedelta(seconds=timeout):
                clear_user_state(user_id)
                print(f"Cleaned up expired state for user {user_id}")
    except Exception as e:
        print(f"Error cleaning up state: {e}")


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for user edit operations"""
    user_id = update.effective_user.id
    
    if user_id not in user_edit_states:
        return  # No active edit state
    
    state = user_edit_states[user_id]
    action = state.get('action')
    phone = state.get('phone')
    
    # Check if state is expired (60 seconds timeout)
    if datetime.now() - state.get('timestamp', datetime.now()) > timedelta(seconds=60):
        clear_user_state(user_id)
        await update.message.reply_text(
            "⏱ **Session Expired**\n\n"
            "Your input session has timed out.\n"
            "Please try again from the menu.",
            parse_mode="Markdown"
        )
        return
    
    text = update.message.text.strip()
    
    if action == 'update_delay':
        await save_update_delay(update, context, phone, text)
    elif action == 'update_expiry':
        await save_update_expiry(update, context, phone, text)
    else:
        # Unknown action, clean up
        clear_user_state(user_id)


# ================== CALLBACK HANDLERS ==================
async def handle_user_management_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback handler for user management"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    try:
        if data == "manage_users":
            await query.edit_message_caption(
                caption="👥 **User Management**\n\nChoose an action:",
                parse_mode="Markdown",
                reply_markup=manage_users_keyboard()
            )
            
        elif data.startswith("userpage_"):
            page = int(data.split("_")[1])
            await show_user_list(update, context, page)
            
        elif data.startswith("userdetails_"):
            uid = int(data.split("_")[1])
            await show_user_details(update, context, uid)
            
        elif data.startswith("delete_confirm_"):
            parts = data.split("_", 2)
            uid = int(parts[2])
            phone = parts[3] if len(parts) > 3 else ""
            await confirm_delete_prompt(update, context, uid, phone)
            
        elif data.startswith("delete_yes_"):
            parts = data.split("_", 2)
            uid = int(parts[2])
            phone = parts[3] if len(parts) > 3 else ""
            await confirm_delete(update, context, uid, phone)
            
        elif data.startswith("update_forward_"):
            parts = data.split("_", 2)
            uid = int(parts[2])
            phone = parts[3] if len(parts) > 3 else ""
            await toggle_forwarding(update, context, uid, phone)
            
        elif data.startswith("update_delay_"):
            parts = data.split("_", 2)
            uid = int(parts[2])
            phone = parts[3] if len(parts) > 3 else ""
            await start_update_delay(update, context, uid, phone)
            
        elif data.startswith("update_expiry_"):
            parts = data.split("_", 2)
            uid = int(parts[2])
            phone = parts[3] if len(parts) > 3 else ""
            await start_update_expiry(update, context, uid, phone)
            
        else:
            # Unknown callback
            await query.edit_message_caption(
                caption="❌ Unknown action. Please try again.",
                reply_markup=manage_users_keyboard()
            )
            
    except Exception as e:
        print(f"❌ Callback handler error: {e}")
        await query.edit_message_caption(
            caption=(
                "❌ **System Error**\n\n"
                "An error occurred processing your request.\n"
                "Please try again or contact support."
            ),
            parse_mode="Markdown",
            reply_markup=manage_users_keyboard()
        )


# ================== INITIALIZATION ==================
def setup_user_management_handlers(application):
    """Setup handlers for user management"""
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(
        handle_user_management_callback, 
        pattern=r"^(manage_users|userpage_\d+|userdetails_\d+|delete_confirm_\d+_.*|delete_yes_\d+_.*|update_forward_\d+_.*|update_delay_\d+_.*|update_expiry_\d+_.*)$"
    ))
    
    # Text input handler for edit operations
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_text_input
    ))


# ================== CLEANUP ON SHUTDOWN ==================
async def cleanup_on_shutdown():
    """Clean up resources on bot shutdown"""
    try:
        # Cancel all cleanup tasks
        for task in message_cleanup_tasks.values():
            if not task.done():
                task.cancel()
        
        # Clear all states
        user_edit_states.clear()
        message_cleanup_tasks.clear()
        
        print("✅ User management cleanup completed")
    except Exception as e:
        print(f"❌ Cleanup error: {e}")


# ================== HEALTH CHECK ==================
def get_user_management_stats():
    """Get current user management statistics"""
    try:
        total_users = get_user_count()
        active_states = len(user_edit_states)
        cleanup_tasks = len([t for t in message_cleanup_tasks.values() if not t.done()])
        
        return {
            "total_users": total_users,
            "active_edit_sessions": active_states,
            "pending_cleanups": cleanup_tasks,
            "status": "healthy" if total_users >= 0 else "error"
        }
    except Exception as e:
        return {
            "total_users": -1,
            "active_edit_sessions": 0,
            "pending_cleanups": 0,
            "status": "error",
            "error": str(e)
        }


# ================== EXPORT FUNCTIONS ==================
__all__ = [
    'manage_users_keyboard',
    'show_user_list', 
    'show_user_details',
    'confirm_delete_prompt',
    'confirm_delete',
    'start_update_delay',
    'start_update_expiry', 
    'toggle_forwarding',
    'handle_text_input',
    'handle_user_management_callback',
    'setup_user_management_handlers',
    'cleanup_on_shutdown',
    'get_user_management_stats'
]
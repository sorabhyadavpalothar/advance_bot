# forwarder.py
import asyncio
import os
import time
import re
import json
import signal
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest, ForwardMessagesRequest
from telethon.errors import (
    ChatAdminRequiredError,
    UserBannedInChannelError,
    FloodWaitError,
    ChannelPrivateError,
    AuthKeyError,
    SessionPasswordNeededError,
)
from telegram import Bot
import database
from config import ADMIN_LOG_CHANNEL, BOT_TOKEN

# =============================
# URL Parsing
# =============================
def parse_telegram_url(url):
    try:
        url = url.strip()
        patterns = [
            (r"https?://t\.me/c/(-?\d+)/(\d+)/?$", "private_topic"),
            (r"https?://t\.me/c/(-?\d+)/?$", "private_channel"),
            (r"https?://t\.me/([^/c][^/]+)/(\d+)/?$", "public_topic"),
            (r"https?://t\.me/([^/c][^/]+)/?$", "public"),
            (r"^@([^/]+)/?$", "username"),
            (r"^(-?\d+)$", "chat_id"),
        ]
        for pattern, url_type in patterns:
            match = re.match(pattern, url)
            if match:
                if url_type == "private_topic":
                    chat_id = int(match.group(1))
                    if chat_id > 0:
                        chat_id = int("-100" + str(chat_id))
                    topic_id = int(match.group(2))
                    return str(chat_id), topic_id, url_type, chat_id
                elif url_type == "private_channel":
                    chat_id = int(match.group(1))
                    if chat_id > 0:
                        chat_id = int("-100" + str(chat_id))
                    return str(chat_id), None, url_type, chat_id
                elif url_type == "public_topic":
                    username = match.group(1)
                    topic_id = int(match.group(2))
                    return username, topic_id, url_type, None
                elif url_type in ["public", "username"]:
                    username = match.group(1)
                    return username, None, url_type, None
                elif url_type == "chat_id":
                    chat_id = int(match.group(1))
                    return str(chat_id), None, url_type, chat_id
        return url, None, "unknown", None
    except Exception as e:
        print(f"❌ Parse URL error: {e}")
        return url, None, "unknown", None


# =============================
# Resolve Entity
# =============================
async def resolve_entity_advanced(client, group_identifier, chat_id=None, url_type="unknown"):
    try:
        if url_type in ["private_channel", "private_topic"]:
            if chat_id:
                return await client.get_entity(chat_id)
        elif url_type == "chat_id":
            return await client.get_entity(int(group_identifier))
        else:
            if not group_identifier.startswith("@") and not group_identifier.lstrip("-").isdigit():
                return await client.get_entity("@" + group_identifier)
            return await client.get_entity(group_identifier)
    except Exception as e:
        print(f"❌ Resolve entity error for {group_identifier}: {e}")
        raise


# =============================
# Forwarding Logic
# =============================
async def forward_messages_enhanced(client, urls, loop_count):
    try:
        print("🔍 Fetching latest message from Saved Messages...")

        saved_messages = await client(
            GetHistoryRequest(
                peer="me",
                offset_id=0,
                offset_date=None,
                add_offset=0,
                limit=1,
                max_id=0,
                min_id=0,
                hash=0,
            )
        )

        if not saved_messages.messages:
            print("❌ No messages found in Saved Messages")
            return 0, len(urls)

        latest_message = saved_messages.messages[0]
        message_preview = (
            latest_message.message[:50] + "..."
            if latest_message.message and len(latest_message.message) > 50
            else latest_message.message or "[Media/File]"
        )

        print(f"📨 Message preview: {message_preview}")
        print(f"🚀 Forwarding to {len(urls)} targets...")

        success_count = 0
        failed_count = 0

        for i, group_url in enumerate(urls, 1):
            try:
                group_identifier, topic_id, url_type, chat_id = parse_telegram_url(group_url)
                entity = await resolve_entity_advanced(client, group_identifier, chat_id, url_type)

                if topic_id:
                    await client(
                        ForwardMessagesRequest(
                            from_peer="me",
                            id=[latest_message.id],
                            to_peer=entity,
                            top_msg_id=topic_id,
                        )
                    )
                    print(f"[{i}] ✓ FORWARDED to topic {topic_id}")
                else:
                    await client.forward_messages(
                        entity=entity, messages=latest_message.id, from_peer="me"
                    )
                    print(f"[{i}] ✓ FORWARDED")

                success_count += 1
                # Small delay between forwards to avoid flooding
                await asyncio.sleep(0.1)

            except FloodWaitError as e:
                wait_time = e.seconds
                print(f"⚠ FLOOD WAIT - Waiting {wait_time}s...")
                await asyncio.sleep(wait_time + 1)
                failed_count += 1
            except (ChannelPrivateError, ChatAdminRequiredError, UserBannedInChannelError) as e:
                print(f"❌ ACCESS DENIED for URL {group_url}: {e}")
                failed_count += 1
            except Exception as e:
                print(f"❌ FAILED for URL {group_url}: {e}")
                failed_count += 1

        return success_count, failed_count

    except Exception as e:
        print(f"❌ Critical error in forward_messages_enhanced: {e}")
        return 0, len(urls)


# =============================
# Worker (per user)
# =============================
async def user_worker(user_conf, bot_logger, stop_event: asyncio.Event):
    api_id = int(user_conf["api_id"])
    api_hash = user_conf["api_hash"]
    phone = user_conf["phone"]
    urls = json.loads(user_conf.get("urls") or "[]")
    delay = int(user_conf.get("delay") or 5)
    user_log_channel = user_conf.get("log_channel_id") or None
    auto_forwarding = bool(user_conf.get("auto_forwarding"))

    if not auto_forwarding:
        print(f"⏸ User {phone}: auto_forwarding is OFF. Worker stopped.")
        return

    if not urls:
        print(f"⚠️ User {phone}: No URLs configured. Worker stopped.")
        return

    session_path = f"sessions/{phone}"
    os.makedirs("sessions", exist_ok=True)

    client = None
    try:
        client = TelegramClient(session_path, api_id, api_hash)
        
        # Configure client to handle connection issues better
        await client.start()
        
        if not await client.is_user_authorized():
            print(f"❌ User {phone}: Not authorized, skipping...")
            return

        print(f"✅ User {phone}: Worker started successfully")
        
        loop_count = 1
        consecutive_errors = 0
        max_consecutive_errors = 5

        while not stop_event.is_set():
            try:
                start = time.time()
                success, failed = await forward_messages_enhanced(client, urls, loop_count)

                summary = (
                    f"📨 Saved Messages\n"
                    f"👤 User: {phone}\n"
                    f"📊 Total Targets: {len(urls)}\n"
                    f"✅ Success: {success}\n"
                    f"❌ Failed: {failed}\n"
                    f"⏰ Time: {time.strftime('%H:%M:%S')}"
                )

                try:
                    await bot_logger.send_message(ADMIN_LOG_CHANNEL, summary)
                    if user_log_channel:
                        await bot_logger.send_message(int(user_log_channel), summary)
                except Exception as e:
                    print(f"⚠️ Failed to log for {phone}: {e}")

                loop_count += 1
                consecutive_errors = 0  # Reset error counter on success
                elapsed = time.time() - start
                wait_time = max(0, delay - elapsed)
                
                # Use asyncio.wait_for with timeout to handle stop_event properly
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=wait_time)
                    break  # Stop event was set
                except asyncio.TimeoutError:
                    pass  # Timeout is normal, continue to next iteration

            except (AuthKeyError, SessionPasswordNeededError) as e:
                print(f"❌ Authentication error for {phone}: {e}")
                try:
                    error_summary = (
                        f"🚨 Authentication Error\n"
                        f"👤 User: {phone}\n"
                        f"❌ Error: Session expired or 2FA required\n"
                        f"⏰ Time: {time.strftime('%H:%M:%S')}"
                    )
                    await bot_logger.send_message(ADMIN_LOG_CHANNEL, error_summary)
                except Exception:
                    pass
                break

            except Exception as e:
                consecutive_errors += 1
                print(f"❌ Error in worker for {phone} (attempt {consecutive_errors}/{max_consecutive_errors}): {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    print(f"🛑 Too many consecutive errors for {phone}, stopping worker...")
                    try:
                        error_summary = (
                            f"🚨 Worker Error Alert\n"
                            f"👤 User: {phone}\n"
                            f"❌ Error: Too many consecutive failures\n"
                            f"📝 Last Error: {str(e)[:100]}\n"
                            f"⏰ Time: {time.strftime('%H:%M:%S')}"
                        )
                        await bot_logger.send_message(ADMIN_LOG_CHANNEL, error_summary)
                    except Exception:
                        pass
                    break
                
                # Exponential backoff for retries
                wait_time = min(300, 10 * (2 ** consecutive_errors))  # Max 5 minutes
                print(f"⏱️ {phone}: Waiting {wait_time}s before retry...")
                
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=wait_time)
                    break  # Stop event was set during wait
                except asyncio.TimeoutError:
                    pass  # Continue to retry

    except Exception as e:
        print(f"❌ Critical error in worker for {phone}: {e}")
        try:
            error_summary = (
                f"🚨 Critical Worker Error\n"
                f"👤 User: {phone}\n"
                f"❌ Error: {str(e)[:100]}\n"
                f"⏰ Time: {time.strftime('%H:%M:%S')}"
            )
            await bot_logger.send_message(ADMIN_LOG_CHANNEL, error_summary)
        except Exception:
            pass
    finally:
        if client:
            try:
                print(f"🔌 {phone}: Disconnecting client...")
                if client.is_connected():
                    await client.disconnect()
                print(f"✅ {phone}: Client disconnected successfully")
            except Exception as e:
                print(f"⚠️ {phone}: Failed to disconnect client: {e}")


# =============================
# Supervisor
# =============================
_running_tasks = {}
_stop_events = {}
_user_configs = {}
_stop_main = asyncio.Event()
_bot_logger = None


async def supervisor():
    global _running_tasks, _stop_events, _user_configs, _bot_logger
    
    # Initialize bot logger
    _bot_logger = Bot(token=BOT_TOKEN)
    
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    while not _stop_main.is_set():
        try:
            db_users = database.get_all_users(offset=0, limit=1000)
            current_phones = {u[1] for u in db_users}

            # Stop removed users
            for phone in list(_running_tasks.keys()):
                if phone not in current_phones:
                    print(f"🛑 Stopping worker for {phone}")
                    try:
                        _stop_events[phone].set()
                        # Wait a bit for graceful shutdown
                        try:
                            await asyncio.wait_for(_running_tasks[phone], timeout=5.0)
                        except asyncio.TimeoutError:
                            _running_tasks[phone].cancel()
                    except Exception as e:
                        print(f"⚠️ Error stopping worker for {phone}: {e}")
                    finally:
                        _running_tasks.pop(phone, None)
                        _stop_events.pop(phone, None)
                        _user_configs.pop(phone, None)

            # Start/restart users
            for row in db_users:
                try:
                    uid, phone, api_id = row
                    user_conf = database.get_user_by_id(uid)
                    if not user_conf:
                        continue

                    # Check if user config changed or worker doesn't exist
                    config_changed = user_conf != _user_configs.get(phone)
                    worker_missing = phone not in _running_tasks
                    worker_done = phone in _running_tasks and _running_tasks[phone].done()

                    if config_changed or worker_missing or worker_done:
                        # Stop existing worker if it exists
                        if phone in _running_tasks:
                            print(f"🔄 Restarting worker for {phone}")
                            try:
                                _stop_events[phone].set()
                                try:
                                    await asyncio.wait_for(_running_tasks[phone], timeout=5.0)
                                except asyncio.TimeoutError:
                                    _running_tasks[phone].cancel()
                            except Exception as e:
                                print(f"⚠️ Error restarting worker for {phone}: {e}")
                            finally:
                                _running_tasks.pop(phone, None)
                                _stop_events.pop(phone, None)

                        # Start new worker
                        if user_conf.get("auto_forwarding"):
                            stop_event = asyncio.Event()
                            task = asyncio.create_task(user_worker(user_conf, _bot_logger, stop_event))
                            _running_tasks[phone] = task
                            _stop_events[phone] = stop_event
                            _user_configs[phone] = user_conf.copy()
                            print(f"✅ Started worker for {phone}")

                except Exception as e:
                    print(f"⚠️ Error processing user {phone}: {e}")
                    continue

            consecutive_errors = 0  # Reset error counter on successful iteration

        except Exception as e:
            consecutive_errors += 1
            print(f"⚠️ DB poll failed (attempt {consecutive_errors}/{max_consecutive_errors}): {e}")
            
            if consecutive_errors >= max_consecutive_errors:
                print("🚨 Too many consecutive supervisor errors, stopping...")
                break

        # Wait for next iteration or stop signal
        try:
            await asyncio.wait_for(_stop_main.wait(), timeout=3.0)
            break  # Stop signal received
        except asyncio.TimeoutError:
            pass  # Normal timeout, continue loop

    print("🛑 Supervisor stopping workers...")
    
    # Stop all workers gracefully
    for phone, stop_event in list(_stop_events.items()):
        try:
            print(f"🛑 Stopping {phone}...")
            stop_event.set()
        except Exception as e:
            print(f"⚠️ Error setting stop event for {phone}: {e}")
    
    # Wait for workers to finish
    if _running_tasks:
        print("⏱️ Waiting for workers to finish...")
        try:
            await asyncio.wait_for(
                asyncio.gather(*_running_tasks.values(), return_exceptions=True),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            print("⚠️ Some workers didn't stop gracefully, cancelling...")
            for phone, task in _running_tasks.items():
                try:
                    task.cancel()
                except Exception as e:
                    print(f"⚠️ Error cancelling task for {phone}: {e}")
    
    print("✅ All workers stopped.")


# =============================
# Public API for main.py
# =============================
async def run_forwarders():
    try:
        database.init_db()
        print("🚀 Starting forwarder supervisor...")
        asyncio.create_task(supervisor())
        print("✅ Forwarder supervisor started")
    except Exception as e:
        print(f"❌ Failed to start forwarders: {e}")
        raise


async def stop_forwarders():
    try:
        print("🛑 Stopping forwarders...")
        _stop_main.set()
        
        # Wait a bit for graceful shutdown
        await asyncio.sleep(2.0)
        
    except Exception as e:
        print(f"❌ Error stopping forwarders: {e}")
    finally:
        print("✅ Forwarder stop sequence completed")
# ================== DATABASE.PY ==================
import sqlite3
import json
from datetime import datetime, timedelta
import threading

DB_NAME = "users.db"

# Thread-safe database connection
db_lock = threading.Lock()

def get_db_connection():
    """Get a thread-safe database connection"""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    return conn


def init_db():
    """Initialize the database with required tables"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_id TEXT NOT NULL,
                    api_hash TEXT NOT NULL,
                    phone TEXT UNIQUE NOT NULL,
                    delay INTEGER DEFAULT 5,
                    auto_forwarding BOOLEAN DEFAULT 0,
                    urls TEXT DEFAULT '[]',
                    log_channel_id TEXT,
                    expiry_date TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Check if log_channel_id column exists, if not add it
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'log_channel_id' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN log_channel_id TEXT")
                print("✅ Added log_channel_id column to users table")

            conn.commit()
            conn.close()
            print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")


def add_user(api_id, api_hash, phone):
    """Add a new user to the database"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()

            expiry_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                INSERT OR REPLACE INTO users (api_id, api_hash, phone, expiry_date)
                VALUES (?, ?, ?, ?)
            """, (api_id, api_hash, phone, expiry_date))

            conn.commit()
            conn.close()
            return True
    except Exception as e:
        print(f"❌ Database error in add_user: {e}")
        return False


def get_user_by_phone(phone):
    """Get user data by phone number"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE phone = ?", (phone,))
            row = cursor.fetchone()
            conn.close()
            return _to_dict(row) if row else None
    except Exception as e:
        print(f"❌ Database error in get_user_by_phone: {e}")
        return None


def get_user_by_id(uid):
    """Get user data by user ID"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (uid,))
            row = cursor.fetchone()
            conn.close()
            return _to_dict(row) if row else None
    except Exception as e:
        print(f"❌ Database error in get_user_by_id: {e}")
        return None


def get_all_users(offset=0, limit=10):
    """Get all users with pagination for management interface"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, phone, api_id FROM users ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
            rows = cursor.fetchall()
            conn.close()
            return [(row[0], row[1], row[2]) for row in rows]
    except Exception as e:
        print(f"❌ Database error in get_all_users: {e}")
        return []


def get_all_users_full():
    """Get all users with full data for forwarder system"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY id")
            rows = cursor.fetchall()
            conn.close()
            return [_to_dict(row) for row in rows] if rows else []
    except Exception as e:
        print(f"❌ Database error in get_all_users_full: {e}")
        return []


def get_user_count():
    """Get total number of users"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            count = cursor.fetchone()[0]
            conn.close()
            return count
    except Exception as e:
        print(f"❌ Database error in get_user_count: {e}")
        return 0


def delete_user(uid):
    """Delete a user by ID"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (uid,))
            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()
            return rows_affected > 0
    except Exception as e:
        print(f"❌ Database error in delete_user: {e}")
        return False


def update_user_urls(phone, urls):
    """Update URLs for a user"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            urls_json = json.dumps(urls) if isinstance(urls, list) else urls
            cursor.execute("UPDATE users SET urls = ? WHERE phone = ?", (urls_json, phone))
            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()
            return rows_affected > 0
    except Exception as e:
        print(f"❌ Database error in update_user_urls: {e}")
        return False


def set_forwarding(phone, status: bool):
    """Enable or disable auto-forwarding for a user"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET auto_forwarding = ? WHERE phone = ?", (1 if status else 0, phone))
            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()
            return rows_affected > 0
    except Exception as e:
        print(f"❌ Database error in set_forwarding: {e}")
        return False


def update_user_delay(phone, delay: int):
    """Update forwarding delay for a user"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET delay = ? WHERE phone = ?", (delay, phone))
            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()
            return rows_affected > 0
    except Exception as e:
        print(f"❌ Database error in update_user_delay: {e}")
        return False


def update_user_expiry_days(phone, days: int):
    """Update user expiry by adding days from current date"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            new_expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("UPDATE users SET expiry_date = ? WHERE phone = ?", (new_expiry, phone))
            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()
            return rows_affected > 0
    except Exception as e:
        print(f"❌ Database error in update_user_expiry_days: {e}")
        return False


def update_user_expiry_date(phone, expiry_date: str):
    """Update user expiry with specific date"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET expiry_date = ? WHERE phone = ?", (expiry_date, phone))
            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()
            return rows_affected > 0
    except Exception as e:
        print(f"❌ Database error in update_user_expiry_date: {e}")
        return False


def update_user_log_channel(phone: str, log_channel_id):
    """Update log channel ID for a user. Pass None to remove."""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET log_channel_id = ? WHERE phone = ?", (log_channel_id, phone))
            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()
            return rows_affected > 0
    except Exception as e:
        print(f"❌ Database error in update_user_log_channel: {e}")
        return False


def get_expired_users():
    """Get list of users whose accounts have expired"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("SELECT * FROM users WHERE expiry_date < ?", (current_time,))
            rows = cursor.fetchall()
            conn.close()
            return [_to_dict(row) for row in rows] if rows else []
    except Exception as e:
        print(f"❌ Database error in get_expired_users: {e}")
        return []


def get_active_users():
    """Get list of users whose accounts are still active"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("SELECT * FROM users WHERE expiry_date > ?", (current_time,))
            rows = cursor.fetchall()
            conn.close()
            return [_to_dict(row) for row in rows] if rows else []
    except Exception as e:
        print(f"❌ Database error in get_active_users: {e}")
        return []


def update_user_api_credentials(phone: str, api_id: str, api_hash: str):
    """Update API credentials for a user"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET api_id = ?, api_hash = ? WHERE phone = ?", (api_id, api_hash, phone))
            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()
            return rows_affected > 0
    except Exception as e:
        print(f"❌ Database error in update_user_api_credentials: {e}")
        return False


def user_exists(phone: str):
    """Check if user exists in database"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users WHERE phone = ?", (phone,))
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0
    except Exception as e:
        print(f"❌ Database error in user_exists: {e}")
        return False


def get_users_with_forwarding_enabled():
    """Get users who have auto-forwarding enabled"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE auto_forwarding = 1")
            rows = cursor.fetchall()
            conn.close()
            return [_to_dict(row) for row in rows] if rows else []
    except Exception as e:
        print(f"❌ Database error in get_users_with_forwarding_enabled: {e}")
        return []


def cleanup_expired_users(auto_delete=False):
    """Get or optionally delete expired users"""
    try:
        expired_users = get_expired_users()
        
        if auto_delete and expired_users:
            with db_lock:
                conn = get_db_connection()
                cursor = conn.cursor()
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("DELETE FROM users WHERE expiry_date < ?", (current_time,))
                deleted_count = cursor.rowcount
                conn.commit()
                conn.close()
                print(f"🧹 Cleaned up {deleted_count} expired users")
                return deleted_count
                
        return len(expired_users)
    except Exception as e:
        print(f"❌ Database error in cleanup_expired_users: {e}")
        return 0


def get_database_stats():
    """Get database statistics"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Total users
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            # Active users
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("SELECT COUNT(*) FROM users WHERE expiry_date > ?", (current_time,))
            active_users = cursor.fetchone()[0]
            
            # Users with forwarding enabled
            cursor.execute("SELECT COUNT(*) FROM users WHERE auto_forwarding = 1")
            forwarding_users = cursor.fetchone()[0]
            
            # Users with URLs configured
            cursor.execute("SELECT COUNT(*) FROM users WHERE urls != '[]' AND urls IS NOT NULL")
            users_with_urls = cursor.fetchone()[0]
            
            # Users with log channels
            cursor.execute("SELECT COUNT(*) FROM users WHERE log_channel_id IS NOT NULL")
            users_with_log = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_users': total_users,
                'active_users': active_users,
                'expired_users': total_users - active_users,
                'forwarding_enabled': forwarding_users,
                'users_with_urls': users_with_urls,
                'users_with_log_channels': users_with_log
            }
    except Exception as e:
        print(f"❌ Database error in get_database_stats: {e}")
        return {}


def _to_dict(row):
    """Convert SQLite row to dictionary"""
    if not row:
        return None
    
    keys = ["id", "api_id", "api_hash", "phone", "delay", "auto_forwarding", "urls",
            "log_channel_id", "expiry_date", "created_at"]
    
    # Handle both sqlite3.Row and tuple
    if hasattr(row, 'keys'):
        return dict(row)
    else:
        # Pad row with None values if it's shorter than expected
        row_list = list(row) + [None] * (len(keys) - len(row))
        return dict(zip(keys, row_list))


# Database maintenance functions
def backup_database(backup_path: str = None):
    """Create a backup of the database"""
    try:
        if not backup_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"backup_users_{timestamp}.db"
        
        with db_lock:
            # Copy database file
            import shutil
            shutil.copy2(DB_NAME, backup_path)
            print(f"✅ Database backed up to: {backup_path}")
            return backup_path
    except Exception as e:
        print(f"❌ Database backup error: {e}")
        return None


def optimize_database():
    """Optimize database performance"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("VACUUM")
            cursor.execute("ANALYZE")
            conn.commit()
            conn.close()
            print("✅ Database optimized")
            return True
    except Exception as e:
        print(f"❌ Database optimization error: {e}")
        return False
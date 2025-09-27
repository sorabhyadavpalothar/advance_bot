# ================== DATABASE.PY ==================
import mysql.connector
from mysql.connector import Error
import json
from datetime import datetime, timedelta
import threading
from contextlib import contextmanager

# MySQL connection configuration
DB_CONFIG = {
    'host': '157.173.220.167',
    'database': 'mydatabase',
    'user': 'root',
    'password': 'Raja@1234@@#',
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
    'autocommit': True
}

# Thread-safe database connection
db_lock = threading.Lock()

def get_db_connection():
    """Get a MySQL database connection"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"❌ MySQL connection error: {e}")
        return None

@contextmanager
def get_db_cursor(commit=True):
    """Context manager for database operations"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if conn is None:
            yield None
            return
            
        cursor = conn.cursor(dictionary=True)
        yield cursor
        
        if commit:
            conn.commit()
    except Error as e:
        if conn:
            conn.rollback()
        print(f"❌ Database error: {e}")
        raise  # Re-raise the exception instead of yielding None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def init_db():
    """Initialize the database with required tables"""
    try:
        with db_lock:
            with get_db_cursor() as cursor:
                if cursor is None:
                    print("❌ Failed to get database cursor")
                    return
                
                # Create users table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        api_id VARCHAR(255) NOT NULL,
                        api_hash VARCHAR(255) NOT NULL,
                        phone VARCHAR(20) UNIQUE NOT NULL,
                        delay INT DEFAULT 5,
                        auto_forwarding BOOLEAN DEFAULT FALSE,
                        urls TEXT,
                        log_channel_id VARCHAR(255),
                        expiry_date DATETIME,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_phone (phone),
                        INDEX idx_expiry_date (expiry_date),
                        INDEX idx_auto_forwarding (auto_forwarding)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                
                print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

def add_user(api_id, api_hash, phone):
    """Add a new user to the database"""
    try:
        with db_lock:
            with get_db_cursor() as cursor:
                if cursor is None:
                    return False
                
                expiry_date = datetime.now() + timedelta(days=30)
                
                cursor.execute("""
                    INSERT INTO users (api_id, api_hash, phone, urls, expiry_date)
                    VALUES (%(api_id)s, %(api_hash)s, %(phone)s, %(urls)s, %(expiry_date)s)
                    ON DUPLICATE KEY UPDATE
                    api_id = VALUES(api_id),
                    api_hash = VALUES(api_hash),
                    expiry_date = VALUES(expiry_date)
                """, {
                    'api_id': api_id,
                    'api_hash': api_hash,
                    'phone': phone,
                    'urls': '[]',
                    'expiry_date': expiry_date
                })
                
                return True
    except Exception as e:
        print(f"❌ Database error in add_user: {e}")
        return False

def get_user_by_phone(phone):
    """Get user data by phone number"""
    try:
        with db_lock:
            with get_db_cursor(commit=False) as cursor:
                if cursor is None:
                    return None
                
                cursor.execute("SELECT * FROM users WHERE phone = %s", (phone,))
                return cursor.fetchone()
    except Exception as e:
        print(f"❌ Database error in get_user_by_phone: {e}")
        return None

def get_user_by_id(uid):
    """Get user data by user ID"""
    try:
        with db_lock:
            with get_db_cursor(commit=False) as cursor:
                if cursor is None:
                    return None
                
                cursor.execute("SELECT * FROM users WHERE id = %s", (uid,))
                return cursor.fetchone()
    except Exception as e:
        print(f"❌ Database error in get_user_by_id: {e}")
        return None

def get_all_users(offset=0, limit=10):
    """Get all users with pagination for management interface"""
    try:
        with db_lock:
            with get_db_cursor(commit=False) as cursor:
                if cursor is None:
                    return []
                
                cursor.execute("""
                    SELECT id, phone, api_id 
                    FROM users 
                    ORDER BY id DESC 
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                
                rows = cursor.fetchall()
                return [(row['id'], row['phone'], row['api_id']) for row in rows]
    except Exception as e:
        print(f"❌ Database error in get_all_users: {e}")
        return []

def get_all_users_full():
    """Get all users with full data for forwarder system"""
    try:
        with db_lock:
            with get_db_cursor(commit=False) as cursor:
                if cursor is None:
                    return []
                
                cursor.execute("SELECT * FROM users ORDER BY id")
                return cursor.fetchall()
    except Exception as e:
        print(f"❌ Database error in get_all_users_full: {e}")
        return []

def get_user_count():
    """Get total number of users"""
    try:
        with db_lock:
            with get_db_cursor(commit=False) as cursor:
                if cursor is None:
                    return 0
                
                cursor.execute("SELECT COUNT(*) as count FROM users")
                result = cursor.fetchone()
                return result['count'] if result else 0
    except Exception as e:
        print(f"❌ Database error in get_user_count: {e}")
        return 0

def delete_user(uid):
    """Delete a user by ID"""
    try:
        with db_lock:
            with get_db_cursor() as cursor:
                if cursor is None:
                    return False
                
                cursor.execute("DELETE FROM users WHERE id = %s", (uid,))
                return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ Database error in delete_user: {e}")
        return False

def update_user_urls(phone, urls):
    """Update URLs for a user"""
    try:
        with db_lock:
            with get_db_cursor() as cursor:
                if cursor is None:
                    return False
                
                urls_json = json.dumps(urls) if isinstance(urls, list) else urls
                cursor.execute("UPDATE users SET urls = %s WHERE phone = %s", (urls_json, phone))
                return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ Database error in update_user_urls: {e}")
        return False

def set_forwarding(phone, status: bool):
    """Enable or disable auto-forwarding for a user"""
    try:
        with db_lock:
            with get_db_cursor() as cursor:
                if cursor is None:
                    return False
                
                cursor.execute("UPDATE users SET auto_forwarding = %s WHERE phone = %s", (status, phone))
                return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ Database error in set_forwarding: {e}")
        return False

def update_user_delay(phone, delay: int):
    """Update forwarding delay for a user"""
    try:
        with db_lock:
            with get_db_cursor() as cursor:
                if cursor is None:
                    return False
                
                cursor.execute("UPDATE users SET delay = %s WHERE phone = %s", (delay, phone))
                return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ Database error in update_user_delay: {e}")
        return False

def update_user_expiry_days(phone, days: int):
    """Update user expiry by adding days from current date"""
    try:
        with db_lock:
            with get_db_cursor() as cursor:
                if cursor is None:
                    return False
                
                new_expiry = datetime.now() + timedelta(days=days)
                cursor.execute("UPDATE users SET expiry_date = %s WHERE phone = %s", (new_expiry, phone))
                return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ Database error in update_user_expiry_days: {e}")
        return False

def update_user_expiry_date(phone, expiry_date: str):
    """Update user expiry with specific date"""
    try:
        with db_lock:
            with get_db_cursor() as cursor:
                if cursor is None:
                    return False
                
                cursor.execute("UPDATE users SET expiry_date = %s WHERE phone = %s", (expiry_date, phone))
                return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ Database error in update_user_expiry_date: {e}")
        return False

def update_user_log_channel(phone: str, log_channel_id):
    """Update log channel ID for a user. Pass None to remove."""
    try:
        with db_lock:
            with get_db_cursor() as cursor:
                if cursor is None:
                    return False
                
                cursor.execute("UPDATE users SET log_channel_id = %s WHERE phone = %s", (log_channel_id, phone))
                return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ Database error in update_user_log_channel: {e}")
        return False

def get_expired_users():
    """Get list of users whose accounts have expired"""
    try:
        with db_lock:
            with get_db_cursor(commit=False) as cursor:
                if cursor is None:
                    return []
                
                current_time = datetime.now()
                cursor.execute("SELECT * FROM users WHERE expiry_date < %s", (current_time,))
                return cursor.fetchall()
    except Exception as e:
        print(f"❌ Database error in get_expired_users: {e}")
        return []

def get_active_users():
    """Get list of users whose accounts are still active"""
    try:
        with db_lock:
            with get_db_cursor(commit=False) as cursor:
                if cursor is None:
                    return []
                
                current_time = datetime.now()
                cursor.execute("SELECT * FROM users WHERE expiry_date > %s", (current_time,))
                return cursor.fetchall()
    except Exception as e:
        print(f"❌ Database error in get_active_users: {e}")
        return []

def update_user_api_credentials(phone: str, api_id: str, api_hash: str):
    """Update API credentials for a user"""
    try:
        with db_lock:
            with get_db_cursor() as cursor:
                if cursor is None:
                    return False
                
                cursor.execute("""
                    UPDATE users SET api_id = %s, api_hash = %s WHERE phone = %s
                """, (api_id, api_hash, phone))
                return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ Database error in update_user_api_credentials: {e}")
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
        print(f"❌ Database error in user_exists: {e}")
        return False

def get_users_with_forwarding_enabled():
    """Get users who have auto-forwarding enabled"""
    try:
        with db_lock:
            with get_db_cursor(commit=False) as cursor:
                if cursor is None:
                    return []
                
                cursor.execute("SELECT * FROM users WHERE auto_forwarding = TRUE")
                return cursor.fetchall()
    except Exception as e:
        print(f"❌ Database error in get_users_with_forwarding_enabled: {e}")
        return []

def cleanup_expired_users(auto_delete=False):
    """Get or optionally delete expired users"""
    try:
        expired_users = get_expired_users()
        
        if auto_delete and expired_users:
            with db_lock:
                with get_db_cursor() as cursor:
                    if cursor is None:
                        return 0
                    
                    current_time = datetime.now()
                    cursor.execute("DELETE FROM users WHERE expiry_date < %s", (current_time,))
                    deleted_count = cursor.rowcount
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
            with get_db_cursor(commit=False) as cursor:
                if cursor is None:
                    return {}
                
                stats = {}
                current_time = datetime.now()
                
                # Total users
                cursor.execute("SELECT COUNT(*) as count FROM users")
                result = cursor.fetchone()
                stats['total_users'] = result['count'] if result else 0
                
                # Active users
                cursor.execute("SELECT COUNT(*) as count FROM users WHERE expiry_date > %s", (current_time,))
                result = cursor.fetchone()
                stats['active_users'] = result['count'] if result else 0
                
                # Users with forwarding enabled
                cursor.execute("SELECT COUNT(*) as count FROM users WHERE auto_forwarding = TRUE")
                result = cursor.fetchone()
                stats['forwarding_enabled'] = result['count'] if result else 0
                
                # Users with URLs configured
                cursor.execute("SELECT COUNT(*) as count FROM users WHERE urls != '[]' AND urls IS NOT NULL")
                result = cursor.fetchone()
                stats['users_with_urls'] = result['count'] if result else 0
                
                # Users with log channels
                cursor.execute("SELECT COUNT(*) as count FROM users WHERE log_channel_id IS NOT NULL")
                result = cursor.fetchone()
                stats['users_with_log_channels'] = result['count'] if result else 0
                
                stats['expired_users'] = stats['total_users'] - stats['active_users']
                
                return stats
    except Exception as e:
        print(f"❌ Database error in get_database_stats: {e}")
        return {}

# Database maintenance functions
def backup_database(backup_path: str = None):
    """Create a backup of the database using mysqldump"""
    try:
        import subprocess
        import os
        
        if not backup_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"backup_telegram_bot_py_{timestamp}.sql"
        
        # Build mysqldump command
        cmd = [
            'mysqldump',
            f"--host={DB_CONFIG['host']}",
            f"--user={DB_CONFIG['user']}",
        ]
        
        if DB_CONFIG['password']:
            cmd.append(f"--password={DB_CONFIG['password']}")
        
        cmd.extend([
            '--single-transaction',
            '--routines',
            '--triggers',
            DB_CONFIG['database']
        ])
        
        with open(backup_path, 'w') as backup_file:
            result = subprocess.run(cmd, stdout=backup_file, stderr=subprocess.PIPE, text=True)
            
        if result.returncode == 0:
            print(f"✅ Database backed up to: {backup_path}")
            return backup_path
        else:
            print(f"❌ Backup failed: {result.stderr}")
            return None
            
    except Exception as e:
        print(f"❌ Database backup error: {e}")
        return None

def optimize_database():
    """Optimize database performance"""
    try:
        with db_lock:
            with get_db_cursor() as cursor:
                if cursor is None:
                    return False
                
                cursor.execute("OPTIMIZE TABLE users")
                cursor.execute("ANALYZE TABLE users")
                print("✅ Database optimized")
                return True
    except Exception as e:
        print(f"❌ Database optimization error: {e}")
        return False

def test_connection():
    """Test database connection"""
    try:
        conn = get_db_connection()
        if conn:
            conn.close()
            print("✅ Database connection successful")
            return True
        else:
            print("❌ Database connection failed")
            return False
    except Exception as e:
        print(f"❌ Database connection test error: {e}")
        return False

# Additional utility functions for MySQL
def get_database_info():
    """Get MySQL database information"""
    try:
        with get_db_cursor(commit=False) as cursor:
            if cursor is None:
                return {}
            
            info = {}
            
            # MySQL version
            cursor.execute("SELECT VERSION() as version")
            result = cursor.fetchone()
            info['mysql_version'] = result['version'] if result else 'Unknown'
            
            # Database size
            cursor.execute("""
                SELECT 
                    ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS size_mb
                FROM information_schema.tables 
                WHERE table_schema = %s
            """, (DB_CONFIG['database'],))
            result = cursor.fetchone()
            info['database_size_mb'] = result['size_mb'] if result else 0
            
            # Table count
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM information_schema.tables 
                WHERE table_schema = %s
            """, (DB_CONFIG['database'],))
            result = cursor.fetchone()
            info['table_count'] = result['count'] if result else 0
            
            return info
    except Exception as e:
        print(f"❌ Database info error: {e}")
        return {}

def reset_database():
    """Reset database by dropping and recreating the users table"""
    try:
        with db_lock:
            with get_db_cursor() as cursor:
                if cursor is None:
                    return False
                
                cursor.execute("DROP TABLE IF EXISTS users")
                print("✅ Users table dropped")
                
        # Recreate the table
        init_db()
        return True
    except Exception as e:
        print(f"❌ Database reset error: {e}")
        return False
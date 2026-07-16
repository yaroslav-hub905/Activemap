"""
ActivityMap Bot — Database Layer (SQLite)
"""
import sqlite3
import os
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "activitymap.db")

CATEGORIES = {
    "coffee": ("☕", "Кофе"),
    "walk": ("🚶", "Прогулка"),
    "bar": ("🍺", "Бар"),
    "sport": ("⚽", "Спорт"),
    "concert": ("🎵", "Концерт"),
    "language": ("🗣️", "Языковой обмен"),
    "games": ("🎮", "Игры"),
    "cinema": ("🎬", "Кино"),
    "other": ("✨", "Другое"),
}

PIN_LIFETIME_HOURS = 12

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Создать таблицы при первом запуске."""
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            tg_id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT NOT NULL,
            age INTEGER NOT NULL CHECK(age >= 18 AND age <= 80),
            city TEXT NOT NULL,
            lat REAL,
            lng REAL,
            is_banned INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(tg_id),
            category TEXT NOT NULL,
            description TEXT,
            time_text TEXT NOT NULL,
            city TEXT NOT NULL,
            lat REAL,
            lng REAL,
            is_active INTEGER NOT NULL DEFAULT 1,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS interests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER NOT NULL REFERENCES activities(id),
            from_user INTEGER NOT NULL REFERENCES users(tg_id),
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(activity_id, from_user)
        );
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER NOT NULL,
            reported_user INTEGER NOT NULL,
            activity_id INTEGER,
            reason TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_activities_city_active
            ON activities(city, is_active, expires_at);
        CREATE INDEX IF NOT EXISTS idx_activities_user
            ON activities(user_id, is_active);
        """)
        cols = [r[1] for r in db.execute("PRAGMA table_info(interests)").fetchall()]
        if "status" not in cols:
            db.execute("ALTER TABLE interests ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")

        user_cols = [r[1] for r in db.execute("PRAGMA table_info(users)").fetchall()]
        if "lat" not in user_cols:
            db.execute("ALTER TABLE users ADD COLUMN lat REAL")
        if "lng" not in user_cols:
            db.execute("ALTER TABLE users ADD COLUMN lng REAL")
        if "photo" not in user_cols:
            db.execute("ALTER TABLE users ADD COLUMN photo TEXT")

        activity_cols = [r[1] for r in db.execute("PRAGMA table_info(activities)").fetchall()]
        if "lat" not in activity_cols:
            db.execute("ALTER TABLE activities ADD COLUMN lat REAL")
        if "lng" not in activity_cols:
            db.execute("ALTER TABLE activities ADD COLUMN lng REAL")
        print(f"[DB] Инициализирована: {DB_PATH}")

def get_user(tg_id: int) -> sqlite3.Row | None:
    with get_db() as db:
        return db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)).fetchone()

def upsert_user(tg_id: int, username: str | None,
                 name: str, age: int, city: str,
                 lat: float | None = None, lng: float | None = None) -> None:
    with get_db() as db:
        db.execute("""
            INSERT INTO users (tg_id, username, name, age, city, lat, lng)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tg_id) DO UPDATE SET
                username = excluded.username,
                name = excluded.name,
                age = excluded.age,
                city = excluded.city,
                lat = COALESCE(excluded.lat, users.lat),
                lng = COALESCE(excluded.lng, users.lng)
        """, (tg_id, username, name, age, city, lat, lng))

def update_user_city(tg_id: int, city: str) -> None:
    with get_db() as db:
        db.execute("UPDATE users SET city = ? WHERE tg_id = ?", (city, tg_id))

def update_user_location(tg_id: int, lat: float, lng: float) -> None:
    with get_db() as db:
        db.execute("UPDATE users SET lat = ?, lng = ? WHERE tg_id = ?", (lat, lng, tg_id))

def update_username(tg_id: int, username: str | None) -> None:
    with get_db() as db:
        db.execute("UPDATE users SET username = ? WHERE tg_id = ?", (username, tg_id))

def update_user_photo(tg_id: int, photo: str | None) -> None:
    """Сохранить/удалить аватар пользователя (base64 data URL или None)."""
    with get_db() as db:
        db.execute("UPDATE users SET photo = ? WHERE tg_id = ?", (photo, tg_id))

def get_active_activity(user_id: int) -> sqlite3.Row | None:
    with get_db() as db:
        return db.execute("""
            SELECT a.*, u.name, u.age, u.username, u.photo
            FROM activities a
            JOIN users u ON u.tg_id = a.user_id
            WHERE a.user_id = ?
              AND a.is_active = 1
            ORDER BY a.created_at DESC
            LIMIT 1
        """, (user_id,)).fetchone()

def create_activity(user_id: int, category: str, description: str,
                     time_text: str, city: str,
                     lat: float | None = None, lng: float | None = None) -> int:
    expires_at = (datetime.utcnow() + timedelta(hours=PIN_LIFETIME_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as db:
        db.execute("""
            UPDATE activities SET is_active = 0
            WHERE user_id = ? AND is_active = 1
        """, (user_id,))
        cur = db.execute("""
            INSERT INTO activities
                (user_id, category, description, time_text, city, lat, lng, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, category, description or "", time_text, city, lat, lng, expires_at))
        return cur.lastrowid

def deactivate_activity(activity_id: int, user_id: int) -> bool:
    with get_db() as db:
        cur = db.execute("""
            UPDATE activities SET is_active = 0
            WHERE id = ? AND user_id = ?
        """, (activity_id, user_id))
        return cur.rowcount > 0

def get_activities_in_city(city: str, category: str | None = None,
                            limit: int = 20) -> list[sqlite3.Row]:
    with get_db() as db:
        if category:
            return db.execute("""
                SELECT a.*, u.name, u.age, u.username, u.photo,
                       (SELECT COUNT(*) FROM interests i WHERE i.activity_id = a.id) AS interest_count
                FROM activities a
                JOIN users u ON u.tg_id = a.user_id
                WHERE a.city LIKE ?
                  AND a.category = ?
                  AND a.is_active = 1
                  AND u.is_banned = 0
                ORDER BY a.created_at DESC
                LIMIT ?
            """, (f"%{city}%", category, limit)).fetchall()
        else:
            return db.execute("""
                SELECT a.*, u.name, u.age, u.username, u.photo,
                       (SELECT COUNT(*) FROM interests i WHERE i.activity_id = a.id) AS interest_count
                FROM activities a
                JOIN users u ON u.tg_id = a.user_id
                WHERE a.city LIKE ?
                  AND a.is_active = 1
                  AND u.is_banned = 0
                ORDER BY a.created_at DESC
                LIMIT ?
            """, (f"%{city}%", limit)).fetchall()

def get_all_active_activities(limit: int = 500) -> list[sqlite3.Row]:
    with get_db() as db:
        return db.execute("""
            SELECT a.*, u.name, u.age, u.username, u.photo,
                   (SELECT COUNT(*) FROM interests i WHERE i.activity_id = a.id) AS interest_count
            FROM activities a
            JOIN users u ON u.tg_id = a.user_id
            WHERE a.is_active = 1
              AND u.is_banned = 0
            ORDER BY a.created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()

def get_city_stats(city: str) -> dict:
    with get_db() as db:
        row = db.execute("""
            SELECT
                COUNT(*) as total_pins,
                COUNT(DISTINCT user_id) as unique_users
            FROM activities
            WHERE city LIKE ?
              AND created_at >= datetime('now', '-1 day')
        """, (f"%{city}%",)).fetchone()
        return dict(row) if row else {"total_pins": 0, "unique_users": 0}

def add_interest(activity_id: int, from_user: int) -> bool:
    try:
        with get_db() as db:
            db.execute("""
                INSERT INTO interests (activity_id, from_user)
                VALUES (?, ?)
            """, (activity_id, from_user))
        return True
    except sqlite3.IntegrityError:
        return False

def get_interest_count(activity_id: int) -> int:
    with get_db() as db:
        row = db.execute("SELECT COUNT(*) FROM interests WHERE activity_id = ?", (activity_id,)).fetchone()
        return row[0]

def get_requests_for_user(tg_id: int) -> dict:
    with get_db() as db:
        received = db.execute("""
            SELECT
                i.id, i.activity_id, i.from_user, i.status, i.created_at,
                u.name AS from_name,
                u.age AS from_age,
                u.city AS from_city,
                u.username AS from_username,
                u.photo AS from_photo,
                a.category, a.description, a.time_text
            FROM interests i
            JOIN activities a ON a.id = i.activity_id
            JOIN users u ON u.tg_id = i.from_user
            WHERE a.user_id = ?
            ORDER BY i.created_at DESC
        """, (tg_id,)).fetchall()

        sent = db.execute("""
            SELECT
                i.id, i.activity_id, i.from_user, i.status, i.created_at,
                u.name AS to_name,
                u.age AS to_age,
                u.city AS to_city,
                u.username AS to_username,
                u.photo AS to_photo,
                a.category, a.description, a.time_text
            FROM interests i
            JOIN activities a ON a.id = i.activity_id
            JOIN users u ON u.tg_id = a.user_id
            WHERE i.from_user = ?
            ORDER BY i.created_at DESC
        """, (tg_id,)).fetchall()

        return {
            "received": [dict(r) for r in received],
            "sent": [dict(r) for r in sent],
        }

def update_interest_status(interest_id: int, activity_owner_id: int, status: str) -> bool:
    assert status in ("accepted", "declined")
    with get_db() as db:
        cur = db.execute("""
            UPDATE interests
            SET status = ?
            WHERE id = ?
              AND activity_id IN (
                  SELECT id FROM activities WHERE user_id = ?
              )
        """, (status, interest_id, activity_owner_id))
        return cur.rowcount > 0

def add_report(reporter_id: int, reported_user: int,
               activity_id: int | None, reason: str) -> None:
    with get_db() as db:
        db.execute("""
            INSERT INTO reports (reporter_id, reported_user, activity_id, reason)
            VALUES (?, ?, ?, ?)
        """, (reporter_id, reported_user, activity_id, reason))

        count = db.execute(
            "SELECT COUNT(*) FROM reports WHERE reported_user = ?",
            (reported_user,)
        ).fetchone()[0]
        if count >= 3:
            db.execute("UPDATE users SET is_banned = 1 WHERE tg_id = ?", (reported_user,))

def cleanup_expired() -> int:
    with get_db() as db:
        cur = db.execute("""
            UPDATE activities SET is_active = 0
            WHERE is_active = 1 AND expires_at < datetime('now')
        """)
        return cur.rowcount


BELGIUM_CITIES = ["Брюссель", "Антверпен", "Гент", "Брюгге", "Льеж", "Лёвен", "Намюр", "Шарлеруа"]

def update_user_name(tg_id: int, name: str) -> None:
    with get_db() as db:
        db.execute("UPDATE users SET name = ? WHERE tg_id = ?", (name, tg_id))

def update_user_age(tg_id: int, age: int) -> None:
    with get_db() as db:
        db.execute("UPDATE users SET age = ? WHERE tg_id = ?", (age, tg_id))

def deactivate_all_activities(user_id: int) -> int:
    """Деактивировать все активные метки пользователя."""
    with get_db() as db:
        cur = db.execute("""
            UPDATE activities SET is_active = 0
            WHERE user_id = ? AND is_active = 1
        """, (user_id,))
        return cur.rowcount

import sqlite3
from contextlib import closing
from pathlib import Path

from backend.database.migrate import apply_migrations

DATABASE_PATH = Path(__file__).parent / "mydb.db"

AUTOINCREMENT_TABLES = {
    "games": "id",
    "achievements": "achievement_id",
}


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection

def get_autoincrement(table_name: str) -> int:
    primary_key = AUTOINCREMENT_TABLES.get(table_name)
    if primary_key is None:
        raise ValueError(f"Unsupported autoincrement table: {table_name}")

    with closing(get_connection()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        maximum = connection.execute(
            f"SELECT COALESCE(MAX({primary_key}), 0) FROM {table_name}"  # names come from AUTOINCREMENT_TABLES  # nosec B608
        ).fetchone()[0]
        connection.commit()
    return maximum + 1

def reset_autoincrement(table_name: str) -> int:
    primary_key = AUTOINCREMENT_TABLES.get(table_name)
    if primary_key is None:
        raise ValueError(f"Unsupported autoincrement table: {table_name}")

    with closing(get_connection()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        maximum = connection.execute(
            f"SELECT COALESCE(MAX({primary_key}), 0) FROM {table_name}"  # names come from AUTOINCREMENT_TABLES  # nosec B608
        ).fetchone()[0]
        cursor = connection.execute(
            "UPDATE sqlite_sequence SET seq = ? WHERE name = ?",
            (maximum, table_name),
        )
        if cursor.rowcount == 0:
            connection.execute(
                "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)",
                (table_name, maximum),
            )
        connection.commit()
    return maximum + 1


def initialize_database() -> None:
    with closing(get_connection()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                genre TEXT NOT NULL,
                release_year INTEGER NOT NULL,
                release_date TEXT NULL,
                description TEXT NULL,
                cover_image_url TEXT NULL,
                image_url TEXT NULL,
                screenshot_url TEXT NULL,
                developer_name TEXT NULL,
                publisher_name TEXT NULL,
                website_url TEXT NULL,
                trailer_url TEXT NULL,
                screenshots TEXT NULL,
                platforms TEXT NOT NULL,
                gamemodes TEXT NULL,
                editions TEXT NULL,
                user_rating REAL NULL DEFAULT 0,
                critic_rating REAL NULL DEFAULT 0,
                wishlisted BOOLEAN NULL DEFAULT 0,
                hoursplayed REAL NULL,
                esrb TEXT NULL,
                minimum_system_requirements TEXT NULL,
                recommended_system_requirements TEXT NULL
            );

            CREATE TABLE IF NOT EXISTS achievements (
                achievement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                image_url TEXT,
                points INTEGER NULL DEFAULT 0,
                unlocked BOOLEAN NOT NULL DEFAULT 0,
                date_unlocked TEXT,
                status TEXT NOT NULL DEFAULT 'Locked',
                achievement_type TEXT NOT NULL DEFAULT 'Bronze',
                game_id INTEGER NOT NULL,
                FOREIGN KEY (game_id) REFERENCES games (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS uploads (
                id TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL UNIQUE,
                content_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            -- Keyed by username so accounts configured in AUTH_USERS can have a profile too.
            CREATE TABLE IF NOT EXISTS user_profiles (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                display_name TEXT NULL,
                bio TEXT NULL,
                location TEXT NULL,
                avatar_url TEXT NULL,
                cover_url TEXT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_favorite_games (
                username TEXT NOT NULL COLLATE NOCASE,
                game_id INTEGER NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (username, game_id),
                FOREIGN KEY (game_id) REFERENCES games (id) ON DELETE CASCADE
            );

            -- Which library game each imported IGDB release became.
            CREATE TABLE IF NOT EXISTS igdb_games (
                igdb_id INTEGER PRIMARY KEY,
                game_id INTEGER NOT NULL UNIQUE,
                imported_by TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                FOREIGN KEY (game_id) REFERENCES games (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_wishlist_games (
                username TEXT NOT NULL COLLATE NOCASE,
                game_id INTEGER NOT NULL,
                added_at TEXT NOT NULL,
                PRIMARY KEY (username, game_id),
                FOREIGN KEY (game_id) REFERENCES games (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE,
                category TEXT NOT NULL,
                subject TEXT NOT NULL,
                message TEXT NOT NULL,
                page_url TEXT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                reply TEXT NULL,
                replied_by TEXT NULL,
                replied_at TEXT NULL,
                email_status TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NULL,
                link TEXT NULL,
                created_at TEXT NOT NULL,
                read_at TEXT NULL
            );
            CREATE INDEX IF NOT EXISTS notifications_by_user ON notifications (username, read_at);

            -- Each side hides a message on its own; the row goes once both have.
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL COLLATE NOCASE,
                recipient TEXT NOT NULL COLLATE NOCASE,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                reply_to INTEGER NULL,
                created_at TEXT NOT NULL,
                read_at TEXT NULL,
                sender_deleted BOOLEAN NOT NULL DEFAULT 0,
                recipient_deleted BOOLEAN NOT NULL DEFAULT 0,
                FOREIGN KEY (reply_to) REFERENCES messages (id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS messages_by_recipient ON messages (recipient, read_at);
            CREATE INDEX IF NOT EXISTS messages_by_sender ON messages (sender);

            -- Tokens issued before sessions_valid_after (epoch seconds) are rejected.
            CREATE TABLE IF NOT EXISTS user_security (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                sessions_valid_after INTEGER NOT NULL DEFAULT 0
            );

            -- Only a SHA-256 of each reset token is stored.
            CREATE TABLE IF NOT EXISTS password_resets (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL COLLATE NOCASE,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                used_at TEXT NULL
            );

            CREATE TABLE IF NOT EXISTS user_two_factor (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                method TEXT NULL,
                secret TEXT NULL,
                enabled_at TEXT NULL,
                pending_method TEXT NULL,
                pending_secret TEXT NULL,
                last_totp_step INTEGER NULL
            );

            CREATE TABLE IF NOT EXISTS two_factor_recovery_codes (
                username TEXT NOT NULL COLLATE NOCASE,
                code_hash TEXT NOT NULL,
                used_at TEXT NULL,
                PRIMARY KEY (username, code_hash)
            );

            -- One row per sign-in challenge or email setup code.
            CREATE TABLE IF NOT EXISTS two_factor_challenges (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL COLLATE NOCASE,
                method TEXT NOT NULL,
                code_hash TEXT NULL,
                expires_at INTEGER NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                sends INTEGER NOT NULL DEFAULT 0,
                sent_at INTEGER NULL,
                completed_at INTEGER NULL
            );

            -- One review per user and game; comments are free-form and unlimited.
            CREATE TABLE IF NOT EXISTS game_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                username TEXT NOT NULL COLLATE NOCASE,
                rating INTEGER NOT NULL,
                body TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (game_id, username),
                FOREIGN KEY (game_id) REFERENCES games (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS game_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                username TEXT NOT NULL COLLATE NOCASE,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (game_id) REFERENCES games (id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS game_comments_by_game ON game_comments (game_id);

            -- Geoblock, VPN and lockdown rules, stored as one JSON document.
            CREATE TABLE IF NOT EXISTS access_settings (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        game_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(games)")
        }
        for column in (
            "developer_name",
            "publisher_name",
            "website_url",
            "trailer_url",
            "screenshots",
            "minimum_system_requirements",
            "recommended_system_requirements",
        ):
            if column not in game_columns:
                connection.execute(f"ALTER TABLE games ADD COLUMN {column} TEXT NULL")
        profile_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(user_profiles)")
        }
        if "email" not in profile_columns:
            connection.execute("ALTER TABLE user_profiles ADD COLUMN email TEXT NULL")
        connection.execute(
            """
            UPDATE games SET esrb = CASE esrb
                WHEN 'Everyone' THEN 'e'
                WHEN 'Everyone 10+' THEN 'e10'
                WHEN 'Teen' THEN 't'
                WHEN 'Mature 17+' THEN 'm'
                WHEN 'Adults Only 18+' THEN 'ao'
                WHEN 'Rating Pending' THEN 'rp'
                WHEN 'Rating Pending Likely Mature 17+' THEN 'rp'
            END
            WHERE esrb IN (
                'Everyone', 'Everyone 10+', 'Teen', 'Mature 17+',
                'Adults Only 18+', 'Rating Pending',
                'Rating Pending Likely Mature 17+'
            )
            """
        )
        connection.commit()
        apply_migrations(connection)


def seed_database() -> None:
    with closing(get_connection()) as connection:
        seed_sql = Path(__file__).with_name("seed.sql").read_text(encoding="utf-8")
        connection.executescript(seed_sql)
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
            f"SELECT COALESCE(MAX({primary_key}), 0) FROM {table_name}"
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
            f"SELECT COALESCE(MAX({primary_key}), 0) FROM {table_name}"
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
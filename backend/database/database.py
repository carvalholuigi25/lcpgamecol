import sqlite3
from contextlib import closing
from pathlib import Path

from backend.database.migrate import apply_migrations
from schemas.schemas import GamesESRB

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
        # seed_database()


def seed_database() -> None:
    games = [
        (
            "The Legend of Zelda: Breath of the Wild",
            "Action-adventure",
            2017,
            "2017-03-03",
            "An open-world adventure game set in the kingdom of Hyrule.",
            "https://example.com/zelda_cover.jpg",
            "https://example.com/zelda_image.jpg",
            "https://example.com/zelda_image_screenshot.jpg",
            "Nintendo Switch",
            "Single Player, Multiplayer",
            "Standard, Deluxe",
            9.5,
            9.2,
            True,
            50.5,
            GamesESRB.E10
        ),
        (
            "God of War",
            "Action-adventure",
            2018,
            "2018-04-20",
            "A story-driven action game following Kratos and his son Atreus.",
            "https://example.com/godofwar_cover.jpg",
            "https://example.com/godofwar_image.jpg",
            "https://example.com/godofwar_image_screenshot.jpg",
            "PlayStation 4",
            "Single Player",
            "Standard, Collector's Edition",
            9.8,
            9.6,
            False,
            30.0,
            GamesESRB.AO
        ),
        (
            "Red Dead Redemption 2",
            "Action-adventure",
            2018,
            "2018-10-26",
            "An epic tale of life in America's unforgiving heartland.",
            "https://example.com/rdr2_cover.jpg",
            "https://example.com/rdr2_image.jpg",
            "https://example.com/rdr2_screenshot.jpg",
            "PlayStation 4, Xbox One, PC",
            "Single Player, Online",
            "Standard, Ultimate Edition",
            9.7,
            9.5,
            True,
            100.0,
            GamesESRB.AO
        ),
    ]

    with closing(get_connection()) as connection:
        game_count = connection.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        if game_count == 0:
            connection.executemany(
                """
                INSERT INTO games (title, genre, release_year, release_date, description, cover_image_url, image_url, screenshot_url, platforms, gamemodes, editions, user_rating, critic_rating, wishlisted, hoursplayed, esrb)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                games,
            )

        achievement_count = connection.execute(
            "SELECT COUNT(*) FROM achievements"
        ).fetchone()[0]
        if achievement_count == 0:
            game_ids = {
                row["title"]: row["id"]
                for row in connection.execute("SELECT id, title FROM games")
            }
            achievements = [
                ("Master Explorer 2", "Discover all locations in Hyrule.", 50, False, None, "Locked", "Platinum", game_ids.get(games[0][0])),
                ("Legendary Hero", "Complete the main questline.", 100, False, None, "Locked", "Gold", game_ids.get(games[0][0])),
                ("God of War", "Defeat all Valkyries.", 75, False, None, "Locked", "Silver", game_ids.get(games[1][0])),
                ("Outlaw", "Complete all story missions.", 80, False, None, "Locked", "Bronze", game_ids.get(games[2][0])),
            ]
            connection.executemany(
                """
                INSERT INTO achievements (title, description, points, unlocked, date_unlocked, status, achievement_type, game_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                achievements,
            )

        connection.commit()
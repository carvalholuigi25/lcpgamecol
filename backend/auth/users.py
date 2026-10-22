"""Registered user accounts: password hashing, password policy and storage.

Generate a hash for AUTH_USERS (instead of a plaintext password) with:

    python -m backend.auth.users hash
"""

import getpass
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from backend.database import database

HASH_SCHEME = "scrypt"
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_KEY_LENGTH = 32
SCRYPT_SALT_BYTES = 16

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$")
PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "12"))
PASSWORD_MAX_LENGTH = 128
COMMON_PASSWORDS = frozenset(
    {
        "123456789012", "1234567890123", "qwertyuiop12", "qwertyuiopas",
        "password1234", "password12345", "passwordpassword", "iloveyou1234",
        "letmein12345", "welcome12345", "administrator", "admin1234567",
        "changeme1234", "football1234", "baseball1234", "monkey123456",
        "dragon123456", "sunshine1234", "princess1234", "trustno1trustno1",
        "abc123456789", "qwerty123456", "1q2w3e4r5t6y", "zaq12wsxcde3",
        "superman1234", "starwars1234", "passw0rd1234", "p@ssw0rd1234",
        "gamelibrary1", "lcpgamecol123",
    }
)


class UsernameTakenError(Exception):
    pass


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SCRYPT_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_KEY_LENGTH,
    )
    return f"{HASH_SCHEME}${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def is_password_hash(value: str) -> bool:
    return value.startswith(f"{HASH_SCHEME}$")


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = encoded.split("$")
        if scheme != HASH_SCHEME:
            return False
        expected = bytes.fromhex(digest)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def username_problem(username: str) -> str | None:
    if not USERNAME_PATTERN.fullmatch(username):
        return (
            "Usernames must be 3 to 32 characters and use only letters, numbers, "
            "dots, hyphens, or underscores, starting with a letter or number."
        )
    return None


def password_problem(password: str, username: str = "") -> str | None:
    """Return why a new password is unacceptable, or None when it is fine."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Use at least {PASSWORD_MIN_LENGTH} characters."
    if len(password) > PASSWORD_MAX_LENGTH:
        return f"Use {PASSWORD_MAX_LENGTH} characters or fewer."
    if password != password.strip():
        return "The password must not start or end with spaces."
    lowered = password.lower()
    if username and username.lower() in lowered:
        return "The password must not contain the username."
    if lowered in COMMON_PASSWORDS or len(set(lowered)) < 5:
        return "This password is too common or predictable."
    has_letter = any(character.isalpha() for character in password)
    has_other = any(not character.isalpha() for character in password)
    if not (has_letter and has_other):
        return "Mix letters with numbers, spaces, or symbols."
    return None


def get_user(username: str) -> sqlite3.Row | None:
    # Avoid creating an empty database file just to look a user up.
    if not Path(database.DATABASE_PATH).exists():
        return None
    try:
        with closing(database.get_connection()) as connection:
            return connection.execute(
                "SELECT username, password_hash, role FROM users WHERE username = ?",
                (username,),
            ).fetchone()
    except sqlite3.OperationalError:
        return None


def create_user(username: str, password: str, role: str) -> None:
    with closing(database.get_connection()) as connection:
        try:
            connection.execute(
                """
                INSERT INTO users (username, password_hash, role, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    username,
                    hash_password(password),
                    role,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError:
            raise UsernameTakenError(username) from None


def main() -> int:
    if sys.argv[1:] != ["hash"]:
        print("usage: python -m backend.auth.users hash", file=sys.stderr)
        return 2
    password = getpass.getpass("Password: ")
    problem = password_problem(password)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    if getpass.getpass("Repeat password: ") != password:
        print("The passwords do not match.", file=sys.stderr)
        return 1
    print(hash_password(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

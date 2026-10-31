"""Moderation rules for reviews and comments.

Administrators keep a list of blocked words. A post that uses one is either held
for review (shown only to its author and administrators until approved) or
refused, depending on blocked_words_action. Users can also report posts; once a
post has report_threshold open reports it is hidden until an administrator
looks at it. The rules are stored as one JSON document in access_settings.
"""

import re
from contextlib import closing
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.database import database

SETTINGS_KEY = "moderation"
BLOCKED_WORDS_MAX = 500
BLOCKED_WORD_MAX_LENGTH = 50

STATUS_VISIBLE = "visible"
# Used a blocked word: waits for an administrator.
STATUS_PENDING = "pending"
# Hidden by an administrator, or by reports until one looks at it.
STATUS_HIDDEN = "hidden"

REPORT_REASONS = ("spam", "offensive", "spoilers", "off_topic", "other")


class ModerationError(Exception):
    """A post was refused; the message is safe to show to the user."""


class ModerationSettings(BaseModel):
    blocked_words: list[str] = Field(default_factory=list, max_length=BLOCKED_WORDS_MAX)
    blocked_words_action: Literal["hold", "reject"] = "hold"
    report_threshold: int = Field(default=3, ge=1, le=50)

    @field_validator("blocked_words")
    @classmethod
    def normalize_words(cls, words: list[str]) -> list[str]:
        cleaned = []
        for word in words:
            word = " ".join(word.split()).lower()
            if len(word) > BLOCKED_WORD_MAX_LENGTH:
                raise ValueError(f"Blocked words must be {BLOCKED_WORD_MAX_LENGTH} characters or fewer.")
            if word and word not in cleaned:
                cleaned.append(word)
        return sorted(cleaned)


def load_settings() -> ModerationSettings:
    with closing(database.get_connection()) as connection:
        row = connection.execute("SELECT value FROM access_settings WHERE name = ?", (SETTINGS_KEY,)).fetchone()
    try:
        return ModerationSettings.model_validate_json(row["value"]) if row else ModerationSettings()
    except ValueError:
        return ModerationSettings()


def save_settings(settings: ModerationSettings, updated_by: str) -> ModerationSettings:
    with closing(database.get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO access_settings (name, value, updated_by, updated_at) VALUES (?, ?, ?, ?)
            ON CONFLICT (name) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (SETTINGS_KEY, settings.model_dump_json(), updated_by, datetime.now(UTC).isoformat(timespec="seconds")),
        )
        connection.commit()
    return settings


def blocked_words_in(text: str, words: list[str]) -> list[str]:
    """The blocked words used in text, matched as whole words and ignoring case."""
    return [word for word in words if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE)]


def screen(text: str, settings: ModerationSettings | None = None) -> str:
    """Return the status a new or edited post gets, or raise ModerationError to refuse it."""
    settings = settings or load_settings()
    if not blocked_words_in(text, settings.blocked_words):
        return STATUS_VISIBLE
    if settings.blocked_words_action == "reject":
        raise ModerationError("Your post uses words that are not allowed here. Please rephrase it.")
    return STATUS_PENDING

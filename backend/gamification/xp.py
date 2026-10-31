"""Experience points (XP), levels and ranks.

Features call award() after their own change is saved. Each action pays once per
(action, ref), for example one review per game, so undoing and redoing something
never pays twice; XP is never taken back. Some actions also have a daily cap so
they can't be farmed (comments, feedback).

Levels grow a little further apart each time: reaching level L takes
LEVEL_STEP_XP * L * (L - 1) / 2 XP in total (100 for level 2, 300 for level 3...).
Ranks are names for level ranges.
"""

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime

from backend.database.database import get_connection
from backend.realtime.hub import hub

LEVEL_STEP_XP = 100
ONCE = "once"
RECENT_EVENTS = 10
LEADERBOARD_MAX = 50

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Action:
    xp: int
    label: str
    daily_limit: int | None = None


ACTIONS = {
    "daily_visit": Action(10, "Visit the library (once a day)"),
    "review": Action(50, "Review a game"),
    "comment": Action(10, "Comment on a game", daily_limit=5),
    "wishlist": Action(5, "Add a game to your wishlist"),
    "favorite": Action(10, "Pick a favorite game"),
    "feedback": Action(20, "Send feedback", daily_limit=3),
    "profile": Action(25, "Complete your profile"),
    "two_factor": Action(100, "Turn on two-step sign-in"),
}

# (first level, name), lowest first.
RANKS = (
    (1, "Rookie"),
    (3, "Explorer"),
    (5, "Adventurer"),
    (8, "Veteran"),
    (12, "Elite"),
    (16, "Champion"),
    (20, "Legend"),
)


def xp_for_level(level: int) -> int:
    return LEVEL_STEP_XP * level * (level - 1) // 2


def level_for(xp: int) -> int:
    level = 1
    while xp_for_level(level + 1) <= xp:
        level += 1
    return level


def rank_for(level: int) -> str:
    return next(name for first, name in reversed(RANKS) if level >= first)


def next_rank(level: int) -> dict | None:
    for first, name in RANKS:
        if first > level:
            return {"name": name, "level": first}
    return None


def summary(xp: int) -> dict:
    level = level_for(xp)
    floor, ceiling = xp_for_level(level), xp_for_level(level + 1)
    return {
        "xp": xp,
        "level": level,
        "rank": rank_for(level),
        "next_rank": next_rank(level),
        "level_xp": floor,
        "next_level_xp": ceiling,
        "progress": round((xp - floor) / (ceiling - floor) * 100),
    }


def total_xp(connection, username: str) -> int:
    return connection.execute(
        "SELECT COALESCE(SUM(xp), 0) FROM user_xp_events WHERE username = ?", (username,)
    ).fetchone()[0]


def award(username: str, action: str, ref: object = ONCE) -> int:
    """Give a user the XP for an action, unless they already got it; return the XP added.

    Never raises: a failure here must not undo the change that earned the XP.
    """
    rule = ACTIONS[action]
    now = datetime.now(UTC)
    try:
        with closing(get_connection()) as connection:
            if rule.daily_limit is not None:
                today = connection.execute(
                    "SELECT COUNT(*) FROM user_xp_events WHERE username = ? AND action = ? AND created_at >= ?",
                    (username, action, now.date().isoformat()),
                ).fetchone()[0]
                if today >= rule.daily_limit:
                    return 0
            before = total_xp(connection, username)
            cursor = connection.execute(
                "INSERT OR IGNORE INTO user_xp_events (username, action, ref, xp, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, action, str(ref), rule.xp, now.isoformat(timespec="seconds")),
            )
            if cursor.rowcount == 0:
                return 0
            connection.commit()
    except sqlite3.Error as error:
        logger.warning("XP for %s (%s) was not saved: %s", username, action, error)
        return 0

    after = summary(before + rule.xp)
    hub.publish("xpChanged", {**after, "gained": rule.xp, "action": action}, username=username)
    if after["level"] > level_for(before):
        # Imported here so loading this module doesn't load the signed-in routes.
        from routes.users.notifications import notify

        notify(username, "level_up", f"You reached level {after['level']}", f"Your rank: {after['rank']}.", "/profile")
    return rule.xp


def describe(username: str) -> dict:
    with closing(get_connection()) as connection:
        xp = total_xp(connection, username)
        events = connection.execute(
            "SELECT action, xp, created_at FROM user_xp_events WHERE username = ? ORDER BY id DESC LIMIT ?",
            (username, RECENT_EVENTS),
        ).fetchall()
    return {
        **summary(xp),
        "recent": [
            {"action": row["action"], "label": ACTIONS[row["action"]].label if row["action"] in ACTIONS else row["action"],
             "xp": row["xp"], "created_at": row["created_at"]}
            for row in events
        ],
        "actions": [
            {"action": name, "label": rule.label, "xp": rule.xp, "daily_limit": rule.daily_limit}
            for name, rule in ACTIONS.items()
        ],
        "ranks": [{"name": name, "level": first} for first, name in RANKS],
    }


def leaderboard(limit: int) -> list[dict]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT e.username, p.display_name, p.avatar_url, SUM(e.xp) AS xp FROM user_xp_events e
            LEFT JOIN user_profiles p ON p.username = e.username
            GROUP BY e.username ORDER BY xp DESC, MIN(e.created_at) LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {"position": index + 1, "username": row["username"], "display_name": row["display_name"],
         "avatar_url": row["avatar_url"], **summary(row["xp"])}
        for index, row in enumerate(rows)
    ]

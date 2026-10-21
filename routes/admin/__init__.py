from collections import Counter
from contextlib import closing

from fastapi import APIRouter, Depends

from backend.auth.auth import require_admin
from backend.database.database import get_connection

router = APIRouter(dependencies=[Depends(require_admin)])


def _split_values(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


@router.get("/admin/dashboard", tags=["admin"])
def get_dashboard_summary() -> dict:
    with closing(get_connection()) as connection:
        games = connection.execute(
            """
            SELECT id, title, genre, release_year, platforms, user_rating,
                   critic_rating, wishlisted, hoursplayed
            FROM games ORDER BY id
            """
        ).fetchall()
        achievements = connection.execute(
            """
            SELECT achievement_type, unlocked
            FROM achievements
            """
        ).fetchall()

    genres = Counter(
        genre
        for game in games
        for genre in _split_values(game["genre"])
    )
    platforms = Counter(
        platform
        for game in games
        for platform in _split_values(game["platforms"])
    )
    releases = Counter(str(game["release_year"]) for game in games)
    achievement_types = Counter(row["achievement_type"] or "Uncategorized" for row in achievements)
    unlocked = sum(bool(row["unlocked"]) for row in achievements)

    def average(field: str) -> float:
        ratings = [float(game[field] or 0) for game in games if game[field] and float(game[field]) > 0]
        return round(sum(ratings) / len(ratings), 1) if ratings else 0

    return {
        "overview": {
            "games": len(games),
            "achievements": len(achievements),
            "unlocked_achievements": unlocked,
            "achievement_completion": round(unlocked / len(achievements) * 100) if achievements else 0,
            "wishlist": sum(bool(game["wishlisted"]) for game in games),
            "hours_played": round(sum(float(game["hoursplayed"] or 0) for game in games), 1),
            "average_user_rating": average("user_rating"),
            "average_critic_rating": average("critic_rating"),
        },
        "release_years": [
            {"label": label, "count": count}
            for label, count in sorted(releases.items())
        ],
        "genres": [
            {"label": label, "count": count}
            for label, count in genres.most_common(6)
        ],
        "platforms": [
            {"label": label, "count": count}
            for label, count in platforms.most_common(6)
        ],
        "achievement_types": [
            {"label": label, "count": count}
            for label, count in achievement_types.most_common()
        ],
        "recent_games": [
            {"id": game["id"], "title": game["title"], "release_year": game["release_year"]}
            for game in reversed(games[-5:])
        ],
    }
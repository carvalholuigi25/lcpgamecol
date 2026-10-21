from contextlib import closing

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth.auth import require_admin
from backend.database.database import get_connection, reset_autoincrement
from routes.achievements.schemas import Achievement, AchievementCreate
from routes.games.routes import get_game

router = APIRouter()


def achievement_from_row(row) -> Achievement:
    return Achievement(**dict(row))


@router.get("/games/{game_id}/achievements", response_model=list[Achievement], tags=["achievements"])
def list_achievements(
    game_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
) -> list[Achievement]:
    get_game(game_id)
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT * FROM achievements
            WHERE game_id = ?
            ORDER BY achievement_id
            LIMIT ? OFFSET ?
            """,
            (game_id, limit, skip),
        ).fetchall()
    return [achievement_from_row(row) for row in rows]


@router.post(
    "/games/{game_id}/achievements",
    response_model=Achievement,
    status_code=201,
    tags=["achievements"],
    dependencies=[Depends(require_admin)],
)
def create_achievement(game_id: int, achievement: AchievementCreate) -> Achievement:
    get_game(game_id)
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO achievements
                (title, description, image_url, points, unlocked, date_unlocked, status, achievement_type, game_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*achievement.model_dump().values(), game_id),
        )
        connection.commit()
        achievement_id = cursor.lastrowid
    return Achievement(achievement_id=achievement_id, game_id=game_id, **achievement.model_dump())


@router.put(
    "/games/{game_id}/achievements/{achievement_id}",
    response_model=Achievement,
    tags=["achievements"],
    dependencies=[Depends(require_admin)],
)
def update_achievement(game_id: int, achievement_id: int, achievement: AchievementCreate) -> Achievement:
    get_game(game_id)
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            UPDATE achievements
            SET title = ?, description = ?, image_url = ?, points = ?, unlocked = ?, date_unlocked = ?, status = ?, achievement_type = ?
            WHERE achievement_id = ? AND game_id = ?
            """,
            (*achievement.model_dump().values(), achievement_id, game_id),
        )
        connection.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Achievement not found")
    return Achievement(achievement_id=achievement_id, game_id=game_id, **achievement.model_dump())


@router.delete(
    "/games/{game_id}/achievements/{achievement_id}",
    status_code=204,
    tags=["achievements"],
    dependencies=[Depends(require_admin)],
)
def delete_achievement(game_id: int, achievement_id: int) -> None:
    get_game(game_id)
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            "DELETE FROM achievements WHERE achievement_id = ? AND game_id = ?",
            (achievement_id, game_id),
        )
        connection.commit()
        reset_autoincrement("achievements")
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Achievement not found")


@router.delete(
    "/games/{game_id}/achievements",
    status_code=204,
    tags=["achievements"],
    dependencies=[Depends(require_admin)],
)
def delete_all_achievements(game_id: int) -> None:
    get_game(game_id)
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            "DELETE FROM achievements WHERE game_id = ?", (game_id,)
        )
        connection.commit()
        reset_autoincrement("achievements")
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="No achievements found to delete")


@router.post(
    "/achievements/reset-autoincrement",
    response_model=dict[str, int | str],
    tags=["achievements"],
    dependencies=[Depends(require_admin)],
)
def reset_achievements_autoincrement() -> dict[str, int | str]:
    return {
        "table": "achievements",
        "next_id": reset_autoincrement("achievements"),
    }
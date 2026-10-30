"""Reviews and comments on library games, shown in the game details dialog.

Every signed-in user can leave one review per game (1 to 5 stars and optional text)
and any number of comments. Authors can delete what they wrote; administrators can
delete anyone's review or comment, which is how they moderate the discussion.
"""

from contextlib import closing

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator

from backend.auth import auth
from backend.auth.auth import Principal, get_current_principal
from backend.database.database import get_connection
from backend.realtime.hub import hub
from routes.users.notifications import now

REVIEW_RATING_MAX = 5
REVIEW_BODY_MAX_LENGTH = 2000
COMMENT_BODY_MAX_LENGTH = 1000

router = APIRouter(tags=["reviews"])
CURRENT_PRINCIPAL = Depends(get_current_principal)


class ReviewWrite(BaseModel):
    rating: int = Field(ge=1, le=REVIEW_RATING_MAX)
    body: str | None = Field(default=None, max_length=REVIEW_BODY_MAX_LENGTH)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=COMMENT_BODY_MAX_LENGTH)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Write a comment before posting it.")
        return value


def _require_game(connection, game_id: int) -> None:
    if connection.execute("SELECT 1 FROM games WHERE id = ?", (game_id,)).fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")


def _review(row) -> dict:
    return {
        "id": row["id"],
        "game_id": row["game_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "rating": row["rating"],
        "body": row["body"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _comment(row) -> dict:
    return {
        "id": row["id"],
        "game_id": row["game_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "body": row["body"],
        "created_at": row["created_at"],
    }


REVIEW_SELECT = """
    SELECT r.*, p.display_name FROM game_reviews r
    LEFT JOIN user_profiles p ON p.username = r.username
"""
COMMENT_SELECT = """
    SELECT c.*, p.display_name FROM game_comments c
    LEFT JOIN user_profiles p ON p.username = c.username
"""


def _check_can_delete(row, principal: Principal, what: str) -> None:
    if row["username"].lower() != principal.username.lower() and principal.role != auth.ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You can only delete your own {what}.",
        )


@router.get("/games/{game_id}/reviews")
def list_reviews(
    game_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = CURRENT_PRINCIPAL,
) -> dict:
    with closing(get_connection()) as connection:
        _require_game(connection, game_id)
        count, average = connection.execute(
            "SELECT COUNT(*), AVG(rating) FROM game_reviews WHERE game_id = ?", (game_id,)
        ).fetchone()
        rows = connection.execute(
            f"{REVIEW_SELECT} WHERE r.game_id = ? ORDER BY r.updated_at DESC, r.id DESC LIMIT ?",  # nosec B608
            (game_id, limit),
        ).fetchall()
        mine = connection.execute(
            f"{REVIEW_SELECT} WHERE r.game_id = ? AND r.username = ?",  # nosec B608
            (game_id, principal.username),
        ).fetchone()
    return {
        "count": count,
        "average": round(average, 1) if average is not None else None,
        "rating_max": REVIEW_RATING_MAX,
        "mine": _review(mine) if mine else None,
        "items": [_review(row) for row in rows],
    }


@router.put("/games/{game_id}/reviews/mine")
def save_my_review(game_id: int, body: ReviewWrite, principal: Principal = CURRENT_PRINCIPAL) -> dict:
    timestamp = now()
    with closing(get_connection()) as connection:
        _require_game(connection, game_id)
        connection.execute(
            """
            INSERT INTO game_reviews (game_id, username, rating, body, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (game_id, username) DO UPDATE SET
                rating = excluded.rating, body = excluded.body, updated_at = excluded.updated_at
            """,
            (game_id, principal.username, body.rating, body.body, timestamp, timestamp),
        )
        connection.commit()
        row = connection.execute(
            f"{REVIEW_SELECT} WHERE r.game_id = ? AND r.username = ?",  # nosec B608
            (game_id, principal.username),
        ).fetchone()
    hub.publish("reviewsChanged", {"game_id": game_id})
    return _review(row)


@router.delete("/games/{game_id}/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(game_id: int, review_id: int, principal: Principal = CURRENT_PRINCIPAL) -> Response:
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM game_reviews WHERE id = ? AND game_id = ?", (review_id, game_id)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
        _check_can_delete(row, principal, "reviews")
        connection.execute("DELETE FROM game_reviews WHERE id = ?", (review_id,))
        connection.commit()
    hub.publish("reviewsChanged", {"game_id": game_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/games/{game_id}/comments")
def list_comments(game_id: int, limit: int = Query(default=50, ge=1, le=200)) -> dict:
    with closing(get_connection()) as connection:
        _require_game(connection, game_id)
        count = connection.execute(
            "SELECT COUNT(*) FROM game_comments WHERE game_id = ?", (game_id,)
        ).fetchone()[0]
        rows = connection.execute(
            f"{COMMENT_SELECT} WHERE c.game_id = ? ORDER BY c.id DESC LIMIT ?",  # nosec B608
            (game_id, limit),
        ).fetchall()
    return {"count": count, "items": [_comment(row) for row in rows]}


@router.post("/games/{game_id}/comments", status_code=status.HTTP_201_CREATED)
def post_comment(game_id: int, body: CommentCreate, principal: Principal = CURRENT_PRINCIPAL) -> dict:
    with closing(get_connection()) as connection:
        _require_game(connection, game_id)
        cursor = connection.execute(
            "INSERT INTO game_comments (game_id, username, body, created_at) VALUES (?, ?, ?, ?)",
            (game_id, principal.username, body.body, now()),
        )
        connection.commit()
        row = connection.execute(f"{COMMENT_SELECT} WHERE c.id = ?", (cursor.lastrowid,)).fetchone()  # nosec B608
    hub.publish("commentsChanged", {"game_id": game_id})
    return _comment(row)


@router.delete("/games/{game_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(game_id: int, comment_id: int, principal: Principal = CURRENT_PRINCIPAL) -> Response:
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM game_comments WHERE id = ? AND game_id = ?", (comment_id, game_id)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
        _check_can_delete(row, principal, "comments")
        connection.execute("DELETE FROM game_comments WHERE id = ?", (comment_id,))
        connection.commit()
    hub.publish("commentsChanged", {"game_id": game_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)

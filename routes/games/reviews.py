"""Reviews and comments on library games, shown in the game details dialog.

Every signed-in user can leave one review per game (1 to 5 stars and optional text)
and any number of comments. Text may be rich text from the editor; it is cleaned by
backend/moderation/rich_text.py and the length limits count the text, not the markup.
Authors can delete what they wrote; administrators can delete anyone's.

Posts are moderated (routes/games/moderation.py): one with a blocked word waits for
an administrator, and reports can hide it. Posts that are not visible are listed
only for their author and administrators, and don't count in the rating.
"""

from contextlib import closing

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator

from backend.auth import auth
from backend.auth.auth import Principal, get_current_principal
from backend.database.database import get_connection
from backend.gamification import xp
from backend.moderation import moderation, rich_text
from backend.realtime.hub import hub
from routes.games import moderation as moderation_routes
from routes.users.notifications import now

REVIEW_RATING_MAX = 5
REVIEW_BODY_MAX_LENGTH = 2000
COMMENT_BODY_MAX_LENGTH = 1000
# Room for the editor's markup on top of the text limit.
MARKUP_ALLOWANCE = 4

router = APIRouter(tags=["reviews"])
CURRENT_PRINCIPAL = Depends(get_current_principal)


def _clean_body(value: str | None, max_length: int) -> str | None:
    """Clean rich text and check its text length; None when there is no text."""
    cleaned, text = rich_text.clean((value or "").strip())
    if len(text) > max_length:
        raise ValueError(f"Keep it to {max_length} characters or fewer.")
    return cleaned if text.strip() else None


class ReviewWrite(BaseModel):
    rating: int = Field(ge=1, le=REVIEW_RATING_MAX)
    body: str | None = Field(default=None, max_length=REVIEW_BODY_MAX_LENGTH * MARKUP_ALLOWANCE)

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: str | None) -> str | None:
        return _clean_body(value, REVIEW_BODY_MAX_LENGTH)


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=COMMENT_BODY_MAX_LENGTH * MARKUP_ALLOWANCE)

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: str) -> str:
        cleaned = _clean_body(value, COMMENT_BODY_MAX_LENGTH)
        if cleaned is None:
            raise ValueError("Write a comment before posting it.")
        return cleaned


def _screen(body: str | None) -> str:
    try:
        return moderation.screen(rich_text.plain_text(body or ""))
    except moderation.ModerationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from None


def _visible_to(principal: Principal, alias: str) -> tuple[str, tuple]:
    """An extra WHERE clause (and its parameters) for the posts this user may see."""
    if principal.role == auth.ROLE_ADMIN:
        return "", ()
    return f" AND ({alias}.status = 'visible' OR {alias}.username = ?)", (principal.username,)


def _require_game(connection, game_id: int) -> None:
    if connection.execute("SELECT 1 FROM games WHERE id = ?", (game_id,)).fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")


def _moderation_fields(row, principal: Principal, reports: dict[int, int], mine: set[int]) -> dict:
    fields = {"status": row["status"], "reported": row["id"] in mine}
    if principal.role == auth.ROLE_ADMIN:
        fields["open_reports"] = reports.get(row["id"], 0)
    return fields


def _review(row, principal: Principal, reports: dict[int, int] | None = None, mine: set[int] | None = None) -> dict:
    return {
        "id": row["id"],
        "game_id": row["game_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "rating": row["rating"],
        "body": row["body"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        **_moderation_fields(row, principal, reports or {}, mine or set()),
    }


def _comment(row, principal: Principal, reports: dict[int, int] | None = None, mine: set[int] | None = None) -> dict:
    return {
        "id": row["id"],
        "game_id": row["game_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "body": row["body"],
        "created_at": row["created_at"],
        **_moderation_fields(row, principal, reports or {}, mine or set()),
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


def _held(kind: str, game_id: int, principal: Principal, body: str | None) -> None:
    moderation_routes.alert_admins(
        f"A {kind} by {principal.username} waits for review",
        rich_text.plain_text(body or "")[:140] or None,
    )


@router.get("/games/{game_id}/reviews")
def list_reviews(
    game_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = CURRENT_PRINCIPAL,
) -> dict:
    visible, parameters = _visible_to(principal, "r")
    with closing(get_connection()) as connection:
        _require_game(connection, game_id)
        count, average = connection.execute(
            "SELECT COUNT(*), AVG(rating) FROM game_reviews WHERE game_id = ? AND status = 'visible'", (game_id,)
        ).fetchone()
        rows = connection.execute(
            f"{REVIEW_SELECT} WHERE r.game_id = ?{visible} ORDER BY r.updated_at DESC, r.id DESC LIMIT ?",  # nosec B608
            (game_id, *parameters, limit),
        ).fetchall()
        mine = connection.execute(
            f"{REVIEW_SELECT} WHERE r.game_id = ? AND r.username = ?",  # nosec B608
            (game_id, principal.username),
        ).fetchone()
        ids = [row["id"] for row in rows]
        reports = moderation_routes.open_report_counts(connection, "review", ids)
        reported = moderation_routes.reported_by(connection, "review", principal.username, ids)
    return {
        "count": count,
        "average": round(average, 1) if average is not None else None,
        "rating_max": REVIEW_RATING_MAX,
        "mine": _review(mine, principal) if mine else None,
        "items": [_review(row, principal, reports, reported) for row in rows],
    }


@router.put("/games/{game_id}/reviews/mine")
def save_my_review(game_id: int, body: ReviewWrite, principal: Principal = CURRENT_PRINCIPAL) -> dict:
    timestamp = now()
    new_status = _screen(body.body)
    with closing(get_connection()) as connection:
        _require_game(connection, game_id)
        # A review an administrator hid stays hidden when its author edits it.
        connection.execute(
            """
            INSERT INTO game_reviews (game_id, username, rating, body, created_at, updated_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (game_id, username) DO UPDATE SET
                rating = excluded.rating, body = excluded.body, updated_at = excluded.updated_at,
                status = CASE WHEN game_reviews.status = 'hidden' THEN 'hidden' ELSE excluded.status END
            """,
            (game_id, principal.username, body.rating, body.body, timestamp, timestamp, new_status),
        )
        connection.commit()
        row = connection.execute(
            f"{REVIEW_SELECT} WHERE r.game_id = ? AND r.username = ?",  # nosec B608
            (game_id, principal.username),
        ).fetchone()
    hub.publish("reviewsChanged", {"game_id": game_id})
    if row["status"] == moderation.STATUS_VISIBLE:
        xp.award(principal.username, "review", game_id)
    elif new_status == moderation.STATUS_PENDING:
        _held("review", game_id, principal, body.body)
    return _review(row, principal)


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
        moderation_routes.forget_reports(connection, "review", review_id)
        game_title = connection.execute("SELECT title FROM games WHERE id = ?", (game_id,)).fetchone()["title"]
        connection.commit()
    moderation_routes.tell_author(row, "review", "removed", game_title, None, principal.username)
    hub.publish("reviewsChanged", {"game_id": game_id})
    hub.publish("moderationChanged", {})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/games/{game_id}/comments")
def list_comments(
    game_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = CURRENT_PRINCIPAL,
) -> dict:
    visible, parameters = _visible_to(principal, "c")
    with closing(get_connection()) as connection:
        _require_game(connection, game_id)
        count = connection.execute(
            "SELECT COUNT(*) FROM game_comments WHERE game_id = ? AND status = 'visible'", (game_id,)
        ).fetchone()[0]
        rows = connection.execute(
            f"{COMMENT_SELECT} WHERE c.game_id = ?{visible} ORDER BY c.id DESC LIMIT ?",  # nosec B608
            (game_id, *parameters, limit),
        ).fetchall()
        ids = [row["id"] for row in rows]
        reports = moderation_routes.open_report_counts(connection, "comment", ids)
        reported = moderation_routes.reported_by(connection, "comment", principal.username, ids)
    return {"count": count, "items": [_comment(row, principal, reports, reported) for row in rows]}


@router.post("/games/{game_id}/comments", status_code=status.HTTP_201_CREATED)
def post_comment(game_id: int, body: CommentCreate, principal: Principal = CURRENT_PRINCIPAL) -> dict:
    new_status = _screen(body.body)
    with closing(get_connection()) as connection:
        _require_game(connection, game_id)
        cursor = connection.execute(
            "INSERT INTO game_comments (game_id, username, body, created_at, status) VALUES (?, ?, ?, ?, ?)",
            (game_id, principal.username, body.body, now(), new_status),
        )
        connection.commit()
        row = connection.execute(f"{COMMENT_SELECT} WHERE c.id = ?", (cursor.lastrowid,)).fetchone()  # nosec B608
    hub.publish("commentsChanged", {"game_id": game_id})
    if new_status == moderation.STATUS_VISIBLE:
        xp.award(principal.username, "comment", row["id"])
    else:
        _held("comment", game_id, principal, body.body)
    return _comment(row, principal)


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
        moderation_routes.forget_reports(connection, "comment", comment_id)
        game_title = connection.execute("SELECT title FROM games WHERE id = ?", (game_id,)).fetchone()["title"]
        connection.commit()
    moderation_routes.tell_author(row, "comment", "removed", game_title, None, principal.username)
    hub.publish("commentsChanged", {"game_id": game_id})
    hub.publish("moderationChanged", {})
    return Response(status_code=status.HTTP_204_NO_CONTENT)

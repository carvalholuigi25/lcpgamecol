-- Migration 0002_add_permissions_and_discussion_reactions
-- Persist fine-grained user grants, post locks, and emoji reactions.

ALTER TABLE game_reviews ADD COLUMN locked BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE game_comments ADD COLUMN locked BOOLEAN NOT NULL DEFAULT 0;

CREATE TABLE user_permissions (
    username TEXT NOT NULL COLLATE NOCASE,
    permission TEXT NOT NULL,
    PRIMARY KEY (username, permission)
);

CREATE TABLE content_reactions (
    kind TEXT NOT NULL,
    item_id INTEGER NOT NULL,
    username TEXT NOT NULL COLLATE NOCASE,
    emoji TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (kind, item_id, username)
);
CREATE INDEX content_reactions_by_item ON content_reactions (kind, item_id);

CREATE TRIGGER content_reactions_after_review_delete
AFTER DELETE ON game_reviews
BEGIN
    DELETE FROM content_reactions WHERE kind = 'review' AND item_id = OLD.id;
END;

CREATE TRIGGER content_reactions_after_comment_delete
AFTER DELETE ON game_comments
BEGIN
    DELETE FROM content_reactions WHERE kind = 'comment' AND item_id = OLD.id;
END;

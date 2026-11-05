-- Migration 0001_add_game_category_trailers
-- Generated 2026-11-05 17:33:57 UTC by backend/database/migrate.py
--
-- + games.category TEXT NULL
-- + games.trailers TEXT NULL

ALTER TABLE games ADD COLUMN category TEXT NULL;

ALTER TABLE games ADD COLUMN trailers TEXT NULL;


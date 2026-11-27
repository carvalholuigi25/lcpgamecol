-- Migration 0003_add_game_store_and_map_urls
-- Generated 2026-11-13 08:23:12 UTC by backend/database/migrate.py
--
-- + games.store_url TEXT NULL
-- + games.map_url TEXT NULL

ALTER TABLE games ADD COLUMN store_url TEXT NULL;

ALTER TABLE games ADD COLUMN map_url TEXT NULL;

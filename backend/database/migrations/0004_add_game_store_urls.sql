-- Migration 0004_add_game_store_urls
-- Generated 2026-11-20 09:18:49 UTC by backend/database/migrate.py
--
-- + games.store_urls TEXT NULL

ALTER TABLE games ADD COLUMN store_urls TEXT NULL;


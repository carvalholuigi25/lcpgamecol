BEGIN IMMEDIATE;

INSERT INTO games (
    title, genre, release_year, release_date, description,
    cover_image_url, image_url, screenshot_url, platforms, gamemodes,
    editions, user_rating, critic_rating, wishlisted, hoursplayed, esrb
)
SELECT
    'The Legend of Zelda: Breath of the Wild',
    'Action-adventure',
    2017,
    '2017-03-03',
    'An open-world adventure game set in the kingdom of Hyrule.',
    'https://example.com/zelda_cover.jpg',
    'https://example.com/zelda_image.jpg',
    'https://example.com/zelda_image_screenshot.jpg',
    'Nintendo Switch',
    'Single Player, Multiplayer',
    'Standard, Deluxe',
    9.5,
    9.2,
    1,
    50.5,
    'e10'
WHERE NOT EXISTS (
    SELECT 1 FROM games
    WHERE title = 'The Legend of Zelda: Breath of the Wild'
);

INSERT INTO games (
    title, genre, release_year, release_date, description,
    cover_image_url, image_url, screenshot_url, platforms, gamemodes,
    editions, user_rating, critic_rating, wishlisted, hoursplayed, esrb
)
SELECT
    'God of War',
    'Action-adventure',
    2018,
    '2018-04-20',
    'A story-driven action game following Kratos and his son Atreus.',
    'https://example.com/godofwar_cover.jpg',
    'https://example.com/godofwar_image.jpg',
    'https://example.com/godofwar_image_screenshot.jpg',
    'PlayStation 4',
    'Single Player',
    'Standard, Collector''s Edition',
    9.8,
    9.6,
    0,
    30.0,
    'ao'
WHERE NOT EXISTS (
    SELECT 1 FROM games WHERE title = 'God of War'
);

INSERT INTO games (
    title, genre, release_year, release_date, description,
    cover_image_url, image_url, screenshot_url, platforms, gamemodes,
    editions, user_rating, critic_rating, wishlisted, hoursplayed, esrb
)
SELECT
    'Red Dead Redemption 2',
    'Action-adventure',
    2018,
    '2018-10-26',
    'An epic tale of life in America''s unforgiving heartland.',
    'https://example.com/rdr2_cover.jpg',
    'https://example.com/rdr2_image.jpg',
    'https://example.com/rdr2_screenshot.jpg',
    'PlayStation 4, Xbox One, PC',
    'Single Player, Online',
    'Standard, Ultimate Edition',
    9.7,
    9.5,
    1,
    100.0,
    'ao'
WHERE NOT EXISTS (
    SELECT 1 FROM games WHERE title = 'Red Dead Redemption 2'
);

INSERT INTO achievements (
    title, description, points, unlocked, date_unlocked, status,
    achievement_type, game_id
)
SELECT
    'Master Explorer 2',
    'Discover all locations in Hyrule.',
    50,
    0,
    NULL,
    'Locked',
    'Platinum',
    games.id
FROM games
WHERE games.title = 'The Legend of Zelda: Breath of the Wild'
  AND NOT EXISTS (
      SELECT 1 FROM achievements
      WHERE achievements.title = 'Master Explorer 2'
        AND achievements.game_id = games.id
  );

INSERT INTO achievements (
    title, description, points, unlocked, date_unlocked, status,
    achievement_type, game_id
)
SELECT
    'Legendary Hero',
    'Complete the main questline.',
    100,
    0,
    NULL,
    'Locked',
    'Gold',
    games.id
FROM games
WHERE games.title = 'The Legend of Zelda: Breath of the Wild'
  AND NOT EXISTS (
      SELECT 1 FROM achievements
      WHERE achievements.title = 'Legendary Hero'
        AND achievements.game_id = games.id
  );

INSERT INTO achievements (
    title, description, points, unlocked, date_unlocked, status,
    achievement_type, game_id
)
SELECT
    'God of War',
    'Defeat all Valkyries.',
    75,
    0,
    NULL,
    'Locked',
    'Silver',
    games.id
FROM games
WHERE games.title = 'God of War'
  AND NOT EXISTS (
      SELECT 1 FROM achievements
      WHERE achievements.title = 'God of War'
        AND achievements.game_id = games.id
  );

INSERT INTO achievements (
    title, description, points, unlocked, date_unlocked, status,
    achievement_type, game_id
)
SELECT
    'Outlaw',
    'Complete all story missions.',
    80,
    0,
    NULL,
    'Locked',
    'Bronze',
    games.id
FROM games
WHERE games.title = 'Red Dead Redemption 2'
  AND NOT EXISTS (
      SELECT 1 FROM achievements
      WHERE achievements.title = 'Outlaw'
        AND achievements.game_id = games.id
  );

COMMIT;

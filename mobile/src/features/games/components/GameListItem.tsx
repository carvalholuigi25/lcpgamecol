import { Image } from 'expo-image';
import { Link } from 'expo-router';
import { memo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useTheme, type Theme } from '@/theme';

import { formatRating, gameCoverUrl, type Game } from '../services';

export const GAME_ROW_HEIGHT = 96;

function GameListItemBase({ game }: { game: Game }) {
  const theme = useTheme();
  const styles = makeStyles(theme);
  const cover = gameCoverUrl(game);
  const rating = formatRating(game.user_rating);
  const subtitle = [game.genre, game.release_year || null].filter(Boolean).join(' · ');

  return (
    <Link href={{ pathname: '/games/[gameId]', params: { gameId: String(game.id) } }} asChild>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={game.title}
        // `Link asChild` merges styles by spreading objects, so a style *function* (or array)
        // would be dropped: keep the outer style static and apply pressed feedback inside.
        style={styles.pressable}
      >
        {({ pressed }) => (
          <View style={[styles.row, pressed && styles.pressed]}>
            {cover ? (
              <Image
                source={cover}
                style={styles.cover}
                contentFit="cover"
                transition={150}
                recyclingKey={String(game.id)}
                accessibilityIgnoresInvertColors
              />
            ) : (
              <View style={[styles.cover, styles.coverFallback]}>
                <Text style={styles.coverInitial}>{game.title.charAt(0).toUpperCase()}</Text>
              </View>
            )}
            <View style={styles.text}>
              <Text style={styles.title} numberOfLines={2}>
                {game.title}
              </Text>
              {subtitle ? (
                <Text style={styles.muted} numberOfLines={1}>
                  {subtitle}
                </Text>
              ) : null}
              {game.developer_name ? (
                <Text style={styles.muted} numberOfLines={1}>
                  {game.developer_name}
                </Text>
              ) : null}
            </View>
            {rating ? (
              <View style={styles.badge}>
                <Text style={styles.badgeText}>★ {rating}</Text>
              </View>
            ) : null}
          </View>
        )}
      </Pressable>
    </Link>
  );
}

/** One row of the games list; tapping it opens /games/[gameId]. */
export const GameListItem = memo(GameListItemBase);

function makeStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    pressable: { width: '100%' },
    row: {
      height: GAME_ROW_HEIGHT,
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.md,
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.sm,
      backgroundColor: colors.background,
    },
    pressed: { backgroundColor: colors.primarySoft },
    cover: { width: 56, height: 76, borderRadius: radius.sm, backgroundColor: colors.surface },
    coverFallback: {
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: 1,
      borderColor: colors.border,
    },
    coverInitial: { ...typography.title, color: colors.muted },
    text: { flex: 1, gap: 2 },
    title: { ...typography.body, fontWeight: '600', color: colors.text },
    muted: { ...typography.caption, color: colors.muted },
    badge: {
      paddingHorizontal: spacing.sm,
      paddingVertical: 2,
      borderRadius: radius.pill,
      backgroundColor: colors.primarySoft,
    },
    badgeText: { ...typography.caption, fontWeight: '600', color: colors.primary },
  });
}

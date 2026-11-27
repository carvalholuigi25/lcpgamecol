import { Image } from 'expo-image';
import { Link } from 'expo-router';
import { memo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useTheme, type Theme } from '@/theme';

import { formatRating, gameCoverUrl, type Game } from '../services';

/** Cover-first tile for the games grid; tapping it opens /games/[gameId]. */
function GameCardBase({ game, width }: { game: Game; width: number }) {
  const theme = useTheme();
  const styles = makeStyles(theme);
  const cover = gameCoverUrl(game);
  const rating = formatRating(game.user_rating);
  const meta = [game.release_year || null, game.genre].filter(Boolean).join(' · ');

  return (
    <Link href={{ pathname: '/games/[gameId]', params: { gameId: String(game.id) } }} asChild>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={game.title}
        // `Link asChild` merges styles by spreading objects, so a style *function* (or array)
        // would be dropped: keep a flat object here and apply pressed feedback inside.
        style={{ width }}
      >
        {({ pressed }) => (
          <View style={[styles.card, pressed && styles.pressed]}>
            <View style={styles.coverBox}>
              {cover ? (
                <Image
                  source={cover}
                  style={StyleSheet.absoluteFill}
                  contentFit="cover"
                  transition={150}
                  recyclingKey={String(game.id)}
                  accessibilityIgnoresInvertColors
                />
              ) : (
                <Text style={styles.initial}>{game.title.charAt(0).toUpperCase()}</Text>
              )}
              {rating ? (
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>★ {rating}</Text>
                </View>
              ) : null}
            </View>
            <Text style={styles.title} numberOfLines={2}>
              {game.title}
            </Text>
            {meta ? (
              <Text style={styles.meta} numberOfLines={1}>
                {meta}
              </Text>
            ) : null}
          </View>
        )}
      </Pressable>
    </Link>
  );
}

export const GameCard = memo(GameCardBase);

function makeStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    card: { gap: spacing.xs },
    pressed: { opacity: 0.75, transform: [{ scale: 0.98 }] },
    coverBox: {
      aspectRatio: 3 / 4,
      borderRadius: radius.md,
      overflow: 'hidden',
      backgroundColor: colors.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: colors.border,
      alignItems: 'center',
      justifyContent: 'center',
    },
    initial: { ...typography.display, color: colors.muted },
    badge: {
      position: 'absolute',
      top: spacing.xs,
      right: spacing.xs,
      paddingHorizontal: spacing.sm,
      paddingVertical: 2,
      borderRadius: radius.pill,
      backgroundColor: colors.background,
    },
    badgeText: { ...typography.caption, fontWeight: '700', color: colors.primary },
    title: { ...typography.label, fontWeight: '600', color: colors.text },
    meta: { ...typography.caption, color: colors.muted },
  });
}

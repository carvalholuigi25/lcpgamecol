import { Image } from 'expo-image';
import { Link, Stack, useLocalSearchParams } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { resolveAssetUrl } from '@/api';
import { useSession } from '@/auth';
import { Avatar, Button, Loading, makeStyles, Pill } from '@/components';
import { formatRating } from '@/features/games';
import {
  initials,
  loadUserProfile,
  ROLE_ADMIN,
  sameUser,
  type GameSummary,
  type UserProfile,
} from '@/features/users';
import { useRequest } from '@/hooks/useRequest';
import { useTheme, type Theme } from '@/theme';

const COVER_HEIGHT = 160;
const AVATAR_SIZE = 96;

export default function UserDetailsScreen() {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const { userId } = useLocalSearchParams<{ userId: string }>();
  const { user: viewer } = useSession();

  const { data, error, errorStatus, loading, refreshing, refresh, retry } = useRequest<UserProfile>(
    userId ? `user:${userId}:${viewer?.role ?? ''}` : null,
    (signal) => loadUserProfile(userId!, viewer, signal),
  );

  if (loading) return <Loading label={t('Loading…')} />;

  if (!data) {
    const notFound = errorStatus === 404 || !userId;
    return (
      <View style={[shared.screen, shared.centered]}>
        <Text style={shared.title}>
          {notFound ? t('User not found') : t('Could not load this profile.')}
        </Text>
        {!notFound && error ? <Text style={shared.muted}>{error}</Text> : null}
        {!notFound ? <Button label={t('Try again')} onPress={retry} /> : null}
      </View>
    );
  }

  return (
    <>
      <Stack.Screen options={{ title: data.displayName }} />
      <Profile
        profile={data}
        isMe={sameUser(data.username, viewer?.username)}
        refreshing={refreshing}
        onRefresh={refresh}
      />
    </>
  );
}

function Profile({
  profile,
  isMe,
  refreshing,
  onRefresh,
}: {
  profile: UserProfile;
  isMe: boolean;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeProfileStyles(theme);
  const { level } = profile;

  const facts: [string, string][] = [];
  if (profile.location) facts.push([t('Location'), profile.location]);
  if (profile.email) facts.push([t('Email'), profile.email]);
  if (profile.createdAt) {
    const date = new Date(profile.createdAt.replace(' ', 'T'));
    if (!Number.isNaN(date.getTime())) {
      facts.push([
        t('Member since'),
        date.toLocaleDateString(i18n.language, { dateStyle: 'medium' }),
      ]);
    }
  }
  if (profile.hoursInFavorites) {
    facts.push([t('Hours in favorites'), String(profile.hoursInFavorites)]);
  }

  return (
    <ScrollView
      style={shared.screen}
      contentContainerStyle={{ paddingBottom: theme.spacing.xxl }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      {/* Cover + overlapping avatar */}
      <View style={styles.cover}>
        {profile.coverUrl ? (
          <Image source={profile.coverUrl} style={StyleSheet.absoluteFill} contentFit="cover" />
        ) : null}
      </View>
      <View style={styles.identity}>
        <Avatar
          uri={profile.avatarUrl}
          label={initials(profile.displayName)}
          size={AVATAR_SIZE}
          ring
        />
        <Text style={shared.heading} accessibilityRole="header">
          {profile.displayName}
        </Text>
        <Text style={shared.muted}>@{profile.username}</Text>
        <View style={[shared.row, { justifyContent: 'center' }]}>
          {isMe ? <Pill label={t('You')} tone="primary" /> : null}
          {profile.role ? (
            <Pill
              label={profile.role === ROLE_ADMIN ? t('Admin') : t('Viewer')}
              tone={profile.role === ROLE_ADMIN ? 'primary' : 'neutral'}
            />
          ) : null}
          {profile.twoFactorEnabled ? <Pill label={t('2FA on')} /> : null}
        </View>
      </View>

      <View style={[shared.container, { gap: theme.spacing.lg }]}>
        {/* Level card */}
        <View style={styles.card}>
          <View style={styles.levelRow}>
            <View style={styles.levelBadge}>
              <Text style={styles.levelNumber}>{level.level}</Text>
            </View>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={shared.title}>{level.rank}</Text>
              <Text style={shared.muted}>
                {t('Level {level} · {xp} XP', { level: level.level, xp: level.xp })}
              </Text>
            </View>
          </View>
          {level.progress !== null ? (
            <View style={{ gap: theme.spacing.xs }}>
              <View
                style={styles.track}
                accessibilityRole="progressbar"
                accessibilityValue={{ min: 0, max: 100, now: level.progress }}
              >
                <View style={[styles.fill, { width: `${level.progress}%` }]} />
              </View>
              <Text style={shared.muted}>
                {level.nextRank
                  ? t('{progress}% to the next level · next rank: {rank}', {
                      progress: level.progress,
                      rank: level.nextRank,
                    })
                  : t('{progress}% to the next level', { progress: level.progress })}
              </Text>
            </View>
          ) : null}
        </View>

        {profile.bio ? <Text style={shared.body}>{profile.bio}</Text> : null}

        {facts.length > 0 ? (
          <View style={styles.card}>
            {facts.map(([label, value], index) => (
              <View key={label} style={[styles.fact, index > 0 && styles.factDivider]}>
                <Text style={shared.muted}>{label}</Text>
                <Text style={styles.factValue} selectable>
                  {value}
                </Text>
              </View>
            ))}
          </View>
        ) : null}

        <GameShelf title={t('Favorite games')} games={profile.favorites} />
        {profile.wishlist ? <GameShelf title={t('Wishlist')} games={profile.wishlist} /> : null}

        {profile.limited ? (
          <Text style={[shared.muted, { textAlign: 'center' }]}>
            {t('Full profiles are visible to administrators.')}
          </Text>
        ) : null}
      </View>
    </ScrollView>
  );
}

/** Horizontal row of game covers linking to their details. */
function GameShelf({ title, games }: { title: string; games: GameSummary[] }) {
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeProfileStyles(theme);
  if (games.length === 0) return null;

  return (
    <View style={{ gap: theme.spacing.sm }}>
      <Text style={shared.title}>
        {title} <Text style={shared.muted}>{games.length}</Text>
      </Text>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: theme.spacing.md }}
      >
        {games.map((game) => {
          const cover = resolveAssetUrl(game.cover_image_url);
          const rating = formatRating(game.user_rating);
          return (
            <Link
              key={game.id}
              href={{ pathname: '/games/[gameId]', params: { gameId: String(game.id) } }}
              asChild
            >
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={game.title}
                style={styles.tile}
              >
                <View style={styles.tileCover}>
                  {cover ? (
                    <Image source={cover} style={StyleSheet.absoluteFill} contentFit="cover" />
                  ) : (
                    <Text style={shared.title}>{game.title.charAt(0)}</Text>
                  )}
                </View>
                <Text style={styles.tileTitle} numberOfLines={2}>
                  {game.title}
                </Text>
                <Text style={shared.muted} numberOfLines={1}>
                  {[game.release_year || null, rating ? `★ ${rating}` : null]
                    .filter(Boolean)
                    .join(' · ')}
                </Text>
              </Pressable>
            </Link>
          );
        })}
      </ScrollView>
    </View>
  );
}

function makeProfileStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    cover: { height: COVER_HEIGHT, backgroundColor: colors.primarySoft, overflow: 'hidden' },
    identity: {
      alignItems: 'center',
      gap: spacing.xs,
      marginTop: -AVATAR_SIZE / 2,
      paddingHorizontal: spacing.lg,
    },
    card: {
      gap: spacing.md,
      padding: spacing.lg,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
    },
    levelRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    levelBadge: {
      width: 48,
      height: 48,
      borderRadius: 24,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.primary,
    },
    levelNumber: { ...typography.title, color: colors.onPrimary },
    track: {
      height: 8,
      borderRadius: radius.pill,
      backgroundColor: colors.primarySoft,
      overflow: 'hidden',
    },
    fill: { height: '100%', borderRadius: radius.pill, backgroundColor: colors.primary },
    fact: { gap: 2 },
    factDivider: {
      paddingTop: spacing.md,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: colors.border,
    },
    factValue: { ...typography.body, color: colors.text },
    tile: { width: 112, gap: spacing.xs },
    tileCover: {
      width: 112,
      aspectRatio: 3 / 4,
      borderRadius: radius.md,
      overflow: 'hidden',
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: colors.border,
    },
    tileTitle: { ...typography.label, fontWeight: '600', color: colors.text },
  });
}

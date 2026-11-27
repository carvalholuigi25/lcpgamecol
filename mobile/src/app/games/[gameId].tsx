import { Image } from 'expo-image';
import * as Linking from 'expo-linking';
import { Stack, useLocalSearchParams } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { resolveAssetUrl } from '@/api';
import { Chip, Loading, makeStyles } from '@/components';
import {
  formatRating,
  GameListActions,
  GameMediaGallery,
  GameReviews,
  gameCoverUrl,
  toNameList,
  useGame,
  type Game,
} from '@/features/games';
import { useTheme, type Theme } from '@/theme';

export default function GameDetailsScreen() {
  const { t } = useTranslation();
  const theme = useTheme();
  const styles = makeStyles(theme);
  const { gameId } = useLocalSearchParams<{ gameId: string }>();
  const { game, loading, error, notFound, retry } = useGame(gameId);

  if (loading) return <Loading label={t('Loading…')} />;

  if (!game) {
    return (
      <View style={[styles.screen, styles.centered]}>
        <Text style={styles.title}>
          {notFound ? t('Game not found') : t('Could not load this game.')}
        </Text>
        {!notFound && error ? <Text style={styles.muted}>{error}</Text> : null}
        {!notFound ? <Chip label={t('Try again')} styles={styles} onPress={retry} /> : null}
      </View>
    );
  }

  return (
    <>
      <Stack.Screen options={{ title: game.title }} />
      <GameDetails game={game} />
    </>
  );
}

function GameDetails({ game }: { game: Game }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeDetailStyles(theme);

  const cover = gameCoverUrl(game);
  const hero = resolveAssetUrl(game.screenshot_url || game.image_url);
  const userRating = formatRating(game.user_rating);
  const criticRating = formatRating(game.critic_rating);
  const platforms = toNameList(game.platforms);
  const modes = toNameList(game.gamemodes).filter((mode) => mode.toLowerCase() !== 'all');
  const editions = toNameList(game.editions);

  const facts: [string, string | null | undefined][] = [
    [t('Genre'), game.genre],
    [t('Category'), game.category],
    [t('Released'), game.release_date || (game.release_year ? String(game.release_year) : null)],
    [t('Developer'), game.developer_name],
    [t('Publisher'), game.publisher_name],
    [t('Hours played'), game.hoursplayed ? String(game.hoursplayed) : null],
  ];

  const links: [string, string | null | undefined][] = [
    [t('Website'), game.website_url],
    [t('Store'), game.store_url || game.store_urls?.[0]],
  ];

  return (
    <ScrollView
      style={shared.screen}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
      keyboardShouldPersistTaps="handled"
      automaticallyAdjustKeyboardInsets
    >
      {hero ? (
        <Image source={hero} style={styles.hero} contentFit="cover" transition={200} />
      ) : null}

      <View style={[shared.container, styles.header]}>
        {cover ? (
          <Image
            source={cover}
            style={[styles.cover, hero ? styles.coverOverlap : null]}
            contentFit="cover"
            transition={200}
          />
        ) : null}
        <View style={styles.headerText}>
          <Text style={shared.heading} accessibilityRole="header">
            {game.title}
          </Text>
          <View style={shared.row}>
            {userRating ? <Badge styles={styles} label={`★ ${userRating} ${t('users')}`} /> : null}
            {criticRating ? (
              <Badge styles={styles} label={`★ ${criticRating} ${t('critics')}`} />
            ) : null}
            {game.esrb ? <Badge styles={styles} label={game.esrb.toUpperCase()} /> : null}
          </View>
        </View>
      </View>

      <View style={shared.container}>
        <GameListActions gameId={game.id} />

        {game.description ? <Text style={shared.body}>{game.description}</Text> : null}

        <View style={styles.facts}>
          {facts
            .filter(([, value]) => value)
            .map(([label, value]) => (
              <View key={label} style={styles.fact}>
                <Text style={shared.muted}>{label}</Text>
                <Text style={styles.factValue}>{value}</Text>
              </View>
            ))}
        </View>

        <GameMediaGallery game={game} />

        <TagSection title={t('Platforms')} tags={platforms} styles={shared} />
        <TagSection title={t('Game modes')} tags={modes} styles={shared} />
        <TagSection title={t('Editions')} tags={editions} styles={shared} />

        {links.some(([, url]) => url) ? (
          <>
            <Text style={shared.label}>{t('Links')}</Text>
            <View style={shared.row}>
              {links.map(([label, url]) =>
                url ? (
                  <Chip
                    key={label}
                    label={label}
                    styles={shared}
                    onPress={() => void Linking.openURL(url)}
                  />
                ) : null,
              )}
            </View>
          </>
        ) : null}

        {game.minimum_system_requirements ? (
          <>
            <Text style={shared.label}>{t('Minimum requirements')}</Text>
            <Text style={shared.body}>{game.minimum_system_requirements}</Text>
          </>
        ) : null}
        {game.recommended_system_requirements ? (
          <>
            <Text style={shared.label}>{t('Recommended requirements')}</Text>
            <Text style={shared.body}>{game.recommended_system_requirements}</Text>
          </>
        ) : null}

        <GameReviews gameId={game.id} />
      </View>
    </ScrollView>
  );
}

function TagSection({
  title,
  tags,
  styles,
}: {
  title: string;
  tags: string[];
  styles: ReturnType<typeof makeStyles>;
}) {
  if (tags.length === 0) return null;
  return (
    <>
      <Text style={styles.label}>{title}</Text>
      <View style={styles.row}>
        {tags.map((tag) => (
          <View key={tag} style={styles.chip}>
            <Text style={styles.chipText}>{tag}</Text>
          </View>
        ))}
      </View>
    </>
  );
}

function Badge({ label, styles }: { label: string; styles: ReturnType<typeof makeDetailStyles> }) {
  return (
    <View style={styles.badge}>
      <Text style={styles.badgeText}>{label}</Text>
    </View>
  );
}

function makeDetailStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    // Readable column on tablets / web; the hero is capped so it never fills the screen.
    content: { width: '100%', maxWidth: 760, alignSelf: 'center', paddingBottom: spacing.xl },
    hero: { width: '100%', aspectRatio: 16 / 9, maxHeight: 360, backgroundColor: colors.surface },
    // Only the cover overlaps the hero; the title stays below it on the screen background
    // (it used to be pulled up over the image, where it was unreadable).
    header: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md, paddingBottom: 0 },
    coverOverlap: { marginTop: -spacing.xxl * 2 },
    headerText: { flex: 1, minWidth: 0, gap: spacing.sm },
    cover: {
      width: 96,
      height: 132,
      borderRadius: radius.md,
      borderWidth: 2,
      borderColor: colors.background,
      backgroundColor: colors.surface,
    },
    badge: {
      paddingHorizontal: spacing.sm,
      paddingVertical: 2,
      borderRadius: radius.pill,
      backgroundColor: colors.primarySoft,
    },
    badgeText: { ...typography.caption, fontWeight: '600', color: colors.primary },
    facts: { flexDirection: 'row', flexWrap: 'wrap', rowGap: spacing.md, marginTop: spacing.sm },
    fact: { width: '50%', paddingRight: spacing.sm, gap: 2 },
    factValue: { ...typography.label, color: colors.text },
  });
}

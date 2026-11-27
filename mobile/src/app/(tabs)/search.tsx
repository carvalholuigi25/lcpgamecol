import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ActivityIndicator,
  FlatList,
  StyleSheet,
  Text,
  TextInput,
  View,
  type ListRenderItem,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useSession } from '@/auth';
import { Button, Chip, makeStyles } from '@/components';
import { GameListItem, useGamesList, type Game } from '@/features/games';
import { fetchAdminUsers, fetchLeaderboard, filterUsers, isAdmin, UserRow } from '@/features/users';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useRequest } from '@/hooks/useRequest';
import { useTheme, type Theme } from '@/theme';

type Scope = 'games' | 'people';

/** One person in the results, whichever list (admin users / leaderboard) it came from. */
type Person = {
  username: string;
  display_name: string | null;
  avatar_url: string | null;
  email?: string | null;
  level: number;
  rank: string;
};

const gameKey = (game: Game) => String(game.id);
const renderGame: ListRenderItem<Game> = ({ item }) => <GameListItem game={item} />;

// Search tab: one query box over games (server-side title search, paged) and people
// (admins search every account; everyone else searches the community leaderboard).
export default function SearchScreen() {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeScreenStyles(theme);
  const [scope, setScope] = useState<Scope>('games');
  const [query, setQuery] = useState('');
  const search = useDebouncedValue(query.trim(), 350);

  return (
    <SafeAreaView style={shared.screen} edges={['top']}>
      <View style={styles.toolbar}>
        <Text style={shared.heading}>{t('Search')}</Text>
        <View style={styles.searchBox}>
          <Text style={styles.searchIcon} accessibilityElementsHidden>
            ⌕
          </Text>
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder={scope === 'games' ? t('Search games') : t('Search users')}
            placeholderTextColor={theme.colors.muted}
            accessibilityLabel={scope === 'games' ? t('Search games') : t('Search users')}
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="search"
            clearButtonMode="while-editing"
            style={styles.searchInput}
            testID="search-input"
          />
        </View>
        <View style={shared.row} accessibilityRole="tablist">
          <Chip
            label={t('Games')}
            selected={scope === 'games'}
            onPress={() => setScope('games')}
            styles={shared}
          />
          <Chip
            label={t('People')}
            selected={scope === 'people'}
            onPress={() => setScope('people')}
            styles={shared}
          />
        </View>
      </View>

      {scope === 'games' ? (
        search ? (
          <GameResults search={search} onClear={() => setQuery('')} />
        ) : (
          <Hint text={t('Search your collection by title.')} />
        )
      ) : (
        <PeopleResults search={search} onClear={() => setQuery('')} />
      )}
    </SafeAreaView>
  );
}

/** Mounted only for a non-empty query, so an empty box never loads the whole collection. */
function GameResults({ search, onClear }: { search: string; onClear: () => void }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeScreenStyles(theme);
  const { items, status, error, refreshing, loadingMore, hasMore, refresh, retry, loadMore } =
    useGamesList({ search });

  if (status === 'loading') return <Spinner />;
  if (status === 'error') {
    return <ErrorState title={t('Could not load games.')} message={error} onRetry={retry} />;
  }

  return (
    <FlatList
      data={items}
      keyExtractor={gameKey}
      renderItem={renderGame}
      onEndReached={loadMore}
      onEndReachedThreshold={0.6}
      refreshing={refreshing}
      onRefresh={refresh}
      keyboardDismissMode="on-drag"
      keyboardShouldPersistTaps="handled"
      removeClippedSubviews
      ItemSeparatorComponent={() => <View style={styles.gameSeparator} />}
      ListHeaderComponent={
        items.length ? (
          <Text style={[shared.muted, styles.count]}>
            {hasMore
              ? t('Results for “{query}”', { query: search })
              : t('{count} results for “{query}”', { count: items.length, query: search })}
          </Text>
        ) : undefined
      }
      ListFooterComponent={
        loadingMore ? (
          <ActivityIndicator style={styles.footer} color={theme.colors.primary} />
        ) : error && hasMore ? (
          <View style={[styles.footer, { alignItems: 'center', gap: theme.spacing.sm }]}>
            <Text style={shared.muted}>{error}</Text>
            <Chip label={t('Try again')} styles={shared} onPress={loadMore} />
          </View>
        ) : (
          <View style={styles.footer} />
        )
      }
      ListEmptyComponent={
        <Empty text={t('No games match “{query}”', { query: search })} onClear={onClear} />
      }
    />
  );
}

/**
 * The API has no user search endpoint, so this filters the list the viewer may read:
 * every account for admins, the XP leaderboard for everyone else. Loaded once per scope.
 */
function PeopleResults({ search, onClear }: { search: string; onClear: () => void }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const styles = makeScreenStyles(theme);
  const { user } = useSession();
  const admin = isAdmin(user);

  const { data, error, loading, refreshing, refresh, retry } = useRequest<Person[]>(
    admin ? 'search-admin-users' : 'search-leaderboard',
    async (signal) =>
      admin
        ? (await fetchAdminUsers(signal)).map((u) => ({
            ...u,
            level: u.rank.level,
            rank: u.rank.rank,
          }))
        : await fetchLeaderboard(signal),
  );

  const people = useMemo(() => filterUsers(data ?? [], search), [data, search]);

  if (loading) return <Spinner />;
  if (!data) {
    return <ErrorState title={t('Could not load users.')} message={error} onRetry={retry} />;
  }

  return (
    <FlatList
      data={people}
      keyExtractor={(p) => p.username}
      refreshing={refreshing}
      onRefresh={refresh}
      keyboardDismissMode="on-drag"
      keyboardShouldPersistTaps="handled"
      ItemSeparatorComponent={() => <View style={styles.userSeparator} />}
      renderItem={({ item }) => (
        <UserRow
          username={item.username}
          displayName={item.display_name}
          avatarUrl={item.avatar_url}
          detail={t('Level {level} · {rank}', { level: item.level, rank: item.rank })}
          highlighted={item.username === user?.username}
        />
      )}
      ListEmptyComponent={
        search ? (
          <Empty text={t('No users match “{query}”', { query: search })} onClear={onClear} />
        ) : (
          <Hint text={t('Nobody has earned XP yet.')} />
        )
      }
    />
  );
}

function Spinner() {
  const theme = useTheme();
  return (
    <View style={makeStyles(theme).centered}>
      <ActivityIndicator size="large" color={theme.colors.primary} />
    </View>
  );
}

function Hint({ text }: { text: string }) {
  const theme = useTheme();
  const shared = makeStyles(theme);
  return (
    <View
      style={[shared.centered, { justifyContent: 'flex-start', paddingTop: theme.spacing.xxl }]}
    >
      <Text style={[shared.muted, { textAlign: 'center' }]}>{text}</Text>
    </View>
  );
}

function Empty({ text, onClear }: { text: string; onClear: () => void }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  return (
    <View style={[shared.centered, { paddingTop: theme.spacing.xxl * 2 }]}>
      <Text style={[shared.title, { textAlign: 'center' }]}>{text}</Text>
      <Button variant="link" label={t('Clear search')} onPress={onClear} />
    </View>
  );
}

function ErrorState({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string | null;
  onRetry: () => void;
}) {
  const { t } = useTranslation();
  const shared = makeStyles(useTheme());
  return (
    <View style={shared.centered}>
      <Text style={shared.title}>{title}</Text>
      {message ? <Text style={[shared.muted, { textAlign: 'center' }]}>{message}</Text> : null}
      <Button label={t('Try again')} onPress={onRetry} />
    </View>
  );
}

function makeScreenStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    toolbar: {
      gap: spacing.md,
      paddingHorizontal: spacing.lg,
      paddingTop: spacing.md,
      paddingBottom: spacing.md,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: colors.border,
    },
    searchBox: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      paddingHorizontal: spacing.md,
      borderRadius: radius.pill,
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.border,
    },
    searchIcon: { ...typography.body, color: colors.muted },
    searchInput: { ...typography.body, flex: 1, color: colors.text, paddingVertical: spacing.sm },
    count: { paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: spacing.xs },
    gameSeparator: {
      height: StyleSheet.hairlineWidth,
      backgroundColor: colors.border,
      marginLeft: spacing.lg + 56 + spacing.md,
    },
    userSeparator: {
      height: StyleSheet.hairlineWidth,
      backgroundColor: colors.border,
      marginLeft: spacing.lg,
    },
    footer: { paddingVertical: spacing.xl },
  });
}

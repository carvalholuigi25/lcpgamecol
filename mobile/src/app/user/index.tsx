import { Stack } from 'expo-router';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FlatList, StyleSheet, Text, TextInput, View } from 'react-native';

import { useSession } from '@/auth';
import { Button, Loading, makeStyles, Pill } from '@/components';
import {
  fetchAdminUsers,
  fetchLeaderboard,
  filterUsers,
  isAdmin,
  ROLE_ADMIN,
  sameUser,
  UserRow,
  type AdminUser,
  type LeaderboardEntry,
} from '@/features/users';
import { useRequest } from '@/hooks/useRequest';
import { useTheme, type Theme } from '@/theme';

const MEDALS = ['🥇', '🥈', '🥉'];

// Users screen. Admins manage every account (GET /admin/users); everyone else sees the
// community XP leaderboard, the only user list the API opens to non-admins.
export default function UsersScreen() {
  const { t } = useTranslation();
  const { user } = useSession();
  const admin = isAdmin(user);

  return (
    <>
      <Stack.Screen options={{ title: admin ? t('Users') : t('Community') }} />
      {admin ? <AdminUsers /> : <Leaderboard me={user?.username ?? null} />}
    </>
  );
}

function AdminUsers() {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeScreenStyles(theme);
  const [query, setQuery] = useState('');
  const { data, error, loading, refreshing, refresh, retry } = useRequest<AdminUser[]>(
    'admin-users',
    fetchAdminUsers,
  );

  const users = useMemo(() => filterUsers(data ?? [], query), [data, query]);

  if (loading) return <Loading label={t('Loading…')} />;
  if (!data) return <ErrorState message={error} onRetry={retry} />;

  const admins = data.filter((u) => u.role === ROLE_ADMIN).length;

  return (
    <View style={shared.screen}>
      <View style={styles.toolbar}>
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder={t('Search by name, username or email')}
          placeholderTextColor={theme.colors.muted}
          accessibilityLabel={t('Search users')}
          autoCapitalize="none"
          autoCorrect={false}
          clearButtonMode="while-editing"
          style={styles.search}
        />
        <Text style={shared.muted}>
          {t('{count} users · {admins} admins', { count: data.length, admins })}
        </Text>
      </View>
      <FlatList
        data={users}
        keyExtractor={(u) => u.username}
        refreshing={refreshing}
        onRefresh={refresh}
        keyboardDismissMode="on-drag"
        ItemSeparatorComponent={() => <View style={styles.separator} />}
        renderItem={({ item }) => (
          <UserRow
            username={item.username}
            displayName={item.display_name}
            avatarUrl={item.avatar_url}
            detail={t('Level {level} · {rank}', { level: item.rank.level, rank: item.rank.rank })}
            trailing={
              <>
                <Pill
                  label={item.role === ROLE_ADMIN ? t('Admin') : t('Viewer')}
                  tone={item.role === ROLE_ADMIN ? 'primary' : 'neutral'}
                />
                {item.two_factor_enabled ? <Pill label={t('2FA')} /> : null}
              </>
            }
          />
        )}
        ListEmptyComponent={
          <View style={[shared.centered, { paddingTop: theme.spacing.xxl }]}>
            <Text style={shared.muted}>{t('No users match “{query}”', { query })}</Text>
          </View>
        }
      />
    </View>
  );
}

function Leaderboard({ me }: { me: string | null }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeScreenStyles(theme);
  const { data, error, loading, refreshing, refresh, retry } = useRequest<LeaderboardEntry[]>(
    'leaderboard',
    fetchLeaderboard,
  );

  if (loading) return <Loading label={t('Loading…')} />;
  if (!data) return <ErrorState message={error} onRetry={retry} />;

  return (
    <FlatList
      style={shared.screen}
      data={data}
      keyExtractor={(entry) => entry.username}
      refreshing={refreshing}
      onRefresh={refresh}
      ListHeaderComponent={
        <View style={styles.toolbar}>
          <Text style={shared.title}>{t('Top players')}</Text>
          <Text style={shared.muted}>{t('Earn XP by visiting, reviewing and rating games.')}</Text>
        </View>
      }
      ItemSeparatorComponent={() => <View style={styles.separator} />}
      renderItem={({ item }) => (
        <UserRow
          username={item.username}
          displayName={item.display_name}
          avatarUrl={item.avatar_url}
          detail={t('Level {level} · {rank}', { level: item.level, rank: item.rank })}
          highlighted={sameUser(item.username, me)}
          leading={
            <Text style={styles.position}>{MEDALS[item.position - 1] ?? item.position}</Text>
          }
          trailing={<Text style={styles.xp}>{t('{xp} XP', { xp: item.xp })}</Text>}
        />
      )}
      ListEmptyComponent={
        <View style={[shared.centered, { paddingTop: theme.spacing.xxl }]}>
          <Text style={shared.muted}>{t('Nobody has earned XP yet.')}</Text>
        </View>
      }
    />
  );
}

function ErrorState({ message, onRetry }: { message: string | null; onRetry: () => void }) {
  const { t } = useTranslation();
  const shared = makeStyles(useTheme());
  return (
    <View style={[shared.screen, shared.centered]}>
      <Text style={shared.title}>{t('Could not load users.')}</Text>
      {message ? <Text style={[shared.muted, { textAlign: 'center' }]}>{message}</Text> : null}
      <Button label={t('Try again')} onPress={onRetry} />
    </View>
  );
}

function makeScreenStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    toolbar: {
      gap: spacing.sm,
      padding: spacing.lg,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: colors.border,
    },
    search: {
      ...typography.body,
      color: colors.text,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm,
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
    },
    separator: {
      height: StyleSheet.hairlineWidth,
      backgroundColor: colors.border,
      marginLeft: spacing.lg,
    },
    position: {
      ...typography.title,
      width: 32,
      textAlign: 'center',
      color: colors.muted,
    },
    xp: { ...typography.label, fontWeight: '700', color: colors.primary },
  });
}

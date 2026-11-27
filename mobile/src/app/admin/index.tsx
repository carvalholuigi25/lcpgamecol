import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { Button, Loading, makeStyles } from '@/components';
import {
  BarList,
  Card,
  fetchDashboard,
  fetchFeedback,
  fetchModerationQueue,
  SectionLink,
  StatTile,
  type Dashboard,
} from '@/features/admin';
import { formatRating } from '@/features/games';
import { useRequest } from '@/hooks/useRequest';
import { useTheme } from '@/theme';

type AdminHome = {
  dashboard: Dashboard;
  /** Null when that section could not be loaded; the link still works. */
  moderation: number | null;
  feedback: number | null;
};

async function loadAdminHome(signal: AbortSignal): Promise<AdminHome> {
  const [dashboard, queue, inbox] = await Promise.allSettled([
    fetchDashboard(signal),
    fetchModerationQueue(signal),
    fetchFeedback('open', signal),
  ]);
  if (dashboard.status === 'rejected') throw dashboard.reason;
  return {
    dashboard: dashboard.value,
    moderation:
      queue.status === 'fulfilled'
        ? queue.value.counts.pending + queue.value.counts.reported
        : null,
    feedback: inbox.status === 'fulfilled' ? inbox.value.counts.open : null,
  };
}

// Admin hub: collection stats, plus the sections that need an administrator's attention.
export default function AdminScreen() {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const { data, error, loading, refreshing, refresh, retry } = useRequest(
    'admin-home',
    loadAdminHome,
  );

  if (loading) return <Loading label={t('Loading…')} />;
  if (!data) {
    return (
      <View style={[shared.screen, shared.centered]}>
        <Text style={shared.title}>{t('Could not load the dashboard.')}</Text>
        {error ? <Text style={[shared.muted, { textAlign: 'center' }]}>{error}</Text> : null}
        <Button label={t('Try again')} onPress={retry} />
      </View>
    );
  }

  const { overview } = data.dashboard;

  return (
    <ScrollView
      style={shared.screen}
      contentContainerStyle={[shared.container, { paddingBottom: theme.spacing.xxl }]}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
    >
      <Text style={shared.label}>{t('Manage')}</Text>
      <SectionLink
        title={t('Moderation')}
        description={t('Held, hidden and reported reviews and comments.')}
        {...(data.moderation ? { badge: data.moderation } : {})}
        onPress={() => router.push('/admin/moderation')}
      />
      <SectionLink
        title={t('Feedback')}
        description={t('Read and answer what players send you.')}
        {...(data.feedback ? { badge: data.feedback } : {})}
        onPress={() => router.push('/admin/feedback')}
      />
      <SectionLink
        title={t('Users')}
        description={t('Roles, permissions, password resets and two-factor sign-in.')}
        onPress={() => router.push('/user')}
      />

      <Text style={shared.label}>{t('Collection')}</Text>
      <View style={shared.row}>
        <StatTile label={t('Games')} value={overview.games} />
        <StatTile label={t('Hours played')} value={overview.hours_played} />
        <StatTile label={t('Wishlist')} value={overview.wishlist} />
        <StatTile
          label={t('Achievements unlocked')}
          value={`${overview.achievement_completion}%`}
        />
        <StatTile
          label={t('Average user rating')}
          value={formatRating(overview.average_user_rating) ?? '–'}
        />
        <StatTile
          label={t('Average critic rating')}
          value={formatRating(overview.average_critic_rating) ?? '–'}
        />
      </View>

      <BarList title={t('Top genres')} buckets={data.dashboard.genres} />
      <BarList title={t('Top platforms')} buckets={data.dashboard.platforms} />

      {data.dashboard.recent_games.length > 0 ? (
        <Card>
          <Text style={shared.title} accessibilityRole="header">
            {t('Recently added')}
          </Text>
          {data.dashboard.recent_games.map((game) => (
            <Pressable
              key={game.id}
              accessibilityRole="link"
              onPress={() =>
                router.push({ pathname: '/games/[gameId]', params: { gameId: String(game.id) } })
              }
            >
              <Text style={shared.body}>
                {game.title}
                {game.release_year ? (
                  <Text style={shared.muted}> · {game.release_year}</Text>
                ) : null}
              </Text>
            </Pressable>
          ))}
        </Card>
      ) : null}
    </ScrollView>
  );
}

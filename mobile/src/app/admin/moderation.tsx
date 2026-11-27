import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import { Button, Chip, Loading, makeStyles, Pill } from '@/components';
import {
  ActionButton,
  confirmAction,
  fetchModerationQueue,
  moderatePost,
  notify,
  plainText,
  type ModerationAction,
  type ModerationItem,
  type ModerationQueue,
} from '@/features/admin';
import { errorMessage } from '@/features/games';
import { useRequest } from '@/hooks/useRequest';
import { useTheme, type Theme } from '@/theme';

type Filter = 'all' | 'pending' | 'hidden' | 'reported';

const matches = (item: ModerationItem, filter: Filter) =>
  filter === 'all' || (filter === 'reported' ? item.open_reports > 0 : item.status === filter);

const itemKey = (item: Pick<ModerationItem, 'kind' | 'id'>) => `${item.kind}:${item.id}`;

export default function ModerationScreen() {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const [filter, setFilter] = useState<Filter>('all');
  const [busy, setBusy] = useState<string | null>(null);
  const { data, error, loading, refreshing, refresh, retry } = useRequest<ModerationQueue>(
    'admin-moderation',
    fetchModerationQueue,
  );

  const items = useMemo(
    () => (data?.items ?? []).filter((item) => matches(item, filter)),
    [data, filter],
  );

  async function act(item: ModerationItem, action: ModerationAction) {
    if (action === 'remove') {
      const ok = await confirmAction({
        title: t('Remove this post?'),
        message: t('It is deleted for good and its author is notified.'),
        confirmLabel: t('Remove'),
        cancelLabel: t('Cancel'),
        destructive: true,
      });
      if (!ok) return;
    }
    setBusy(itemKey(item));
    try {
      await moderatePost(item, action);
      refresh();
    } catch (e) {
      notify(t('Could not update this post.'), errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <Loading label={t('Loading…')} />;
  if (!data) {
    return (
      <View style={[shared.screen, shared.centered]}>
        <Text style={shared.title}>{t('Could not load the moderation queue.')}</Text>
        {error ? <Text style={[shared.muted, { textAlign: 'center' }]}>{error}</Text> : null}
        <Button label={t('Try again')} onPress={retry} />
      </View>
    );
  }

  const filters: { key: Filter; label: string }[] = [
    { key: 'all', label: t('All ({count})', { count: data.items.length }) },
    { key: 'pending', label: t('Pending ({count})', { count: data.counts.pending }) },
    { key: 'reported', label: t('Reported ({count})', { count: data.counts.reported }) },
    { key: 'hidden', label: t('Hidden ({count})', { count: data.counts.hidden }) },
  ];

  return (
    <FlatList
      style={shared.screen}
      contentContainerStyle={{ padding: theme.spacing.lg, gap: theme.spacing.md }}
      data={items}
      keyExtractor={itemKey}
      refreshing={refreshing}
      onRefresh={refresh}
      ListHeaderComponent={
        <View style={shared.row}>
          {filters.map((f) => (
            <Chip
              key={f.key}
              label={f.label}
              selected={filter === f.key}
              onPress={() => setFilter(f.key)}
              styles={shared}
            />
          ))}
        </View>
      }
      renderItem={({ item }) => (
        <QueueItem item={item} busy={busy === itemKey(item)} onAction={(a) => void act(item, a)} />
      )}
      ListEmptyComponent={
        <View style={[shared.centered, { paddingTop: theme.spacing.xxl }]}>
          <Text style={shared.title}>{t('All clear')}</Text>
          <Text style={shared.muted}>{t('Nothing is waiting for review.')}</Text>
        </View>
      }
    />
  );
}

function QueueItem({
  item,
  busy,
  onAction,
}: {
  item: ModerationItem;
  busy: boolean;
  onAction: (action: ModerationAction) => void;
}) {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeItemStyles(theme);
  const text = plainText(item.body);
  const locked = !!item.locked;
  const statusLabel = { visible: t('Visible'), pending: t('Pending'), hidden: t('Hidden') }[
    item.status
  ];

  return (
    <View style={[styles.card, busy && { opacity: 0.5 }]}>
      <View style={shared.row}>
        <Pill label={item.kind === 'review' ? t('Review') : t('Comment')} />
        <Pill label={statusLabel} tone={item.status === 'visible' ? 'neutral' : 'warning'} />
        {item.open_reports > 0 ? (
          <Pill label={t('{count} reports', { count: item.open_reports })} tone="warning" />
        ) : null}
        {locked ? <Pill label={t('Locked')} /> : null}
      </View>

      <Pressable
        accessibilityRole="link"
        onPress={() =>
          router.push({ pathname: '/games/[gameId]', params: { gameId: String(item.game_id) } })
        }
      >
        <Text style={shared.title}>{item.game_title}</Text>
      </Pressable>
      <Pressable
        accessibilityRole="link"
        onPress={() =>
          router.push({ pathname: '/user/[userId]', params: { userId: item.username } })
        }
      >
        <Text style={shared.muted}>
          {item.display_name || item.username} · @{item.username}
          {item.rating ? ` · ★ ${item.rating}` : ''}
        </Text>
      </Pressable>

      {text ? (
        <Text style={shared.body} numberOfLines={8} selectable>
          {text}
        </Text>
      ) : null}

      {item.reports.length > 0 ? (
        <View style={styles.reports}>
          {item.reports.map((report, index) => (
            <Text key={`${report.reporter}-${index}`} style={shared.muted}>
              <Text style={{ fontWeight: '600' }}>@{report.reporter}</Text>: {report.reason}
              {report.details ? ` — ${report.details}` : ''}
            </Text>
          ))}
        </View>
      ) : null}

      <View style={shared.row}>
        {item.status !== 'visible' || item.open_reports > 0 ? (
          <ActionButton
            label={item.status === 'visible' ? t('Dismiss reports') : t('Approve')}
            tone="primary"
            disabled={busy}
            onPress={() => onAction('approve')}
          />
        ) : null}
        {item.status !== 'hidden' ? (
          <ActionButton label={t('Hide')} disabled={busy} onPress={() => onAction('hide')} />
        ) : null}
        <ActionButton
          label={locked ? t('Unlock') : t('Lock')}
          disabled={busy}
          onPress={() => onAction(locked ? 'unlock' : 'lock')}
        />
        <ActionButton
          label={t('Remove')}
          tone="danger"
          disabled={busy}
          onPress={() => onAction('remove')}
        />
      </View>
    </View>
  );
}

function makeItemStyles({ colors, spacing, radius }: Theme) {
  return StyleSheet.create({
    card: {
      gap: spacing.sm,
      padding: spacing.lg,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
    },
    reports: {
      gap: spacing.xs,
      paddingLeft: spacing.md,
      borderLeftWidth: 2,
      borderLeftColor: colors.warning,
    },
  });
}

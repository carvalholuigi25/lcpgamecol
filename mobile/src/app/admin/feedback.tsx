import { router } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { Button, Chip, Loading, makeStyles, Pill } from '@/components';
import {
  ActionButton,
  confirmAction,
  deleteFeedback,
  FEEDBACK_STATUS_LABELS,
  FEEDBACK_STATUSES,
  fetchFeedback,
  notify,
  updateFeedback,
  type Feedback,
  type FeedbackInbox,
  type FeedbackStatus,
} from '@/features/admin';
import { errorMessage } from '@/features/games';
import { useRequest } from '@/hooks/useRequest';
import { useTheme, type Theme } from '@/theme';

const REPLY_MAX = 4000;

export default function FeedbackScreen() {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const [status, setStatus] = useState<FeedbackStatus | null>('open');
  const [expanded, setExpanded] = useState<number | null>(null);
  const { data, error, loading, refreshing, refresh, retry } = useRequest<FeedbackInbox>(
    `admin-feedback:${status ?? 'all'}`,
    (signal) => fetchFeedback(status, signal),
  );

  if (loading) return <Loading label={t('Loading…')} />;
  if (!data) {
    return (
      <View style={[shared.screen, shared.centered]}>
        <Text style={shared.title}>{t('Could not load feedback.')}</Text>
        {error ? <Text style={[shared.muted, { textAlign: 'center' }]}>{error}</Text> : null}
        <Button label={t('Try again')} onPress={retry} />
      </View>
    );
  }

  const total = FEEDBACK_STATUSES.reduce((sum, key) => sum + data.counts[key], 0);

  return (
    <FlatList
      style={shared.screen}
      contentContainerStyle={{ padding: theme.spacing.lg, gap: theme.spacing.md }}
      data={data.items}
      keyExtractor={(item) => String(item.id)}
      refreshing={refreshing}
      onRefresh={refresh}
      keyboardShouldPersistTaps="handled"
      ListHeaderComponent={
        <View style={{ gap: theme.spacing.sm }}>
          <View style={shared.row}>
            {FEEDBACK_STATUSES.map((key) => (
              <Chip
                key={key}
                label={`${t(FEEDBACK_STATUS_LABELS[key])} (${data.counts[key]})`}
                selected={status === key}
                onPress={() => setStatus(key)}
                styles={shared}
              />
            ))}
            <Chip
              label={`${t('All')} (${total})`}
              selected={status === null}
              onPress={() => setStatus(null)}
              styles={shared}
            />
          </View>
          {!data.email_enabled ? (
            <Text style={shared.muted}>
              {t('Email is not set up: replies are only shown in the app.')}
            </Text>
          ) : null}
        </View>
      }
      renderItem={({ item }) => (
        <FeedbackItem
          item={item}
          expanded={expanded === item.id}
          onToggle={() => setExpanded((id) => (id === item.id ? null : item.id))}
          onChanged={refresh}
        />
      )}
      ListEmptyComponent={
        <View style={[shared.centered, { paddingTop: theme.spacing.xxl }]}>
          <Text style={shared.muted}>{t('No feedback here.')}</Text>
        </View>
      }
    />
  );
}

function FeedbackItem({
  item,
  expanded,
  onToggle,
  onChanged,
}: {
  item: Feedback;
  expanded: boolean;
  onToggle: () => void;
  onChanged: () => void;
}) {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeItemStyles(theme);
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);

  const created = new Date(item.created_at.replace(' ', 'T'));
  const date = Number.isNaN(created.getTime())
    ? item.created_at
    : created.toLocaleDateString(i18n.language, { dateStyle: 'medium' });

  async function run(task: () => Promise<unknown>, failure: string) {
    setBusy(true);
    try {
      await task();
      onChanged();
      return true;
    } catch (e) {
      notify(failure, errorMessage(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function sendReply() {
    const text = reply.trim();
    if (!text) return;
    if (await run(() => updateFeedback(item.id, { reply: text }), t('Could not send the reply.'))) {
      setReply('');
    }
  }

  async function remove() {
    const ok = await confirmAction({
      title: t('Delete this feedback?'),
      message: item.subject,
      confirmLabel: t('Delete'),
      cancelLabel: t('Cancel'),
      destructive: true,
    });
    if (ok) await run(() => deleteFeedback(item.id), t('Could not delete this feedback.'));
  }

  return (
    <View style={[styles.card, busy && { opacity: 0.6 }]}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        onPress={onToggle}
        style={{ gap: theme.spacing.xs }}
      >
        <View style={shared.row}>
          <Pill
            label={t(FEEDBACK_STATUS_LABELS[item.status])}
            tone={item.status === 'open' ? 'warning' : 'neutral'}
          />
          <Pill label={t(capitalize(item.category))} />
        </View>
        <Text style={shared.title}>{item.subject}</Text>
        <Text style={shared.muted}>
          @{item.username} · {date}
        </Text>
        <Text style={shared.body} numberOfLines={expanded ? undefined : 2} selectable={expanded}>
          {item.message}
        </Text>
      </Pressable>

      {expanded ? (
        <View style={{ gap: theme.spacing.sm }}>
          {item.page_url ? (
            <Text style={shared.muted}>{t('Page: {page}', { page: item.page_url })}</Text>
          ) : null}
          <Pressable
            accessibilityRole="link"
            onPress={() =>
              router.push({ pathname: '/user/[userId]', params: { userId: item.username } })
            }
          >
            <Text style={styles.link}>{t('View profile')}</Text>
          </Pressable>

          {item.reply ? (
            <View style={styles.reply}>
              <Text style={shared.muted}>
                {t('Reply from {name}', { name: item.replied_by ?? '' })}
                {item.email_status ? ` · ${item.email_status}` : ''}
              </Text>
              <Text style={shared.body} selectable>
                {item.reply}
              </Text>
            </View>
          ) : null}

          <TextInput
            value={reply}
            onChangeText={setReply}
            placeholder={item.reply ? t('Write a new reply') : t('Write a reply')}
            placeholderTextColor={theme.colors.muted}
            accessibilityLabel={t('Reply')}
            multiline
            maxLength={REPLY_MAX}
            style={styles.input}
          />
          <Button
            label={t('Send reply')}
            onPress={() => void sendReply()}
            loading={busy}
            disabled={!reply.trim()}
          />

          <Text style={shared.muted}>{t('Status')}</Text>
          <View style={shared.row}>
            {FEEDBACK_STATUSES.map((key) => (
              <Chip
                key={key}
                label={t(FEEDBACK_STATUS_LABELS[key])}
                selected={item.status === key}
                onPress={() => {
                  if (key !== item.status && !busy) {
                    void run(
                      () => updateFeedback(item.id, { status: key }),
                      t('Could not change the status.'),
                    );
                  }
                }}
                styles={shared}
              />
            ))}
          </View>
          <View style={[shared.row, { justifyContent: 'flex-end' }]}>
            <ActionButton
              label={t('Delete')}
              tone="danger"
              disabled={busy}
              onPress={() => void remove()}
            />
          </View>
        </View>
      ) : null}
    </View>
  );
}

const capitalize = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

function makeItemStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    card: {
      gap: spacing.sm,
      padding: spacing.lg,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
    },
    link: { ...typography.label, color: colors.primary },
    reply: {
      gap: spacing.xs,
      paddingLeft: spacing.md,
      borderLeftWidth: 2,
      borderLeftColor: colors.primary,
    },
    input: {
      ...typography.body,
      minHeight: 88,
      textAlignVertical: 'top',
      color: colors.text,
      padding: spacing.md,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.background,
    },
  });
}

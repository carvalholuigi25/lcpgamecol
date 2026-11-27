import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '@/api';
import { Button, Chip, makeStyles, TextField } from '@/components';
import { notify } from '@/features/admin/confirm';
import { useTheme, type Theme } from '@/theme';

import {
  REPORT_DETAILS_MAX_LENGTH,
  REPORT_REASONS,
  reportReview,
  STANDARD_REACTIONS,
  toggleReviewReaction,
  type ReactionSummary,
  type ReportReason,
  type Review,
} from '../reviews';
import { errorMessage } from '../services';

/** Emoji reaction pills with counts; the user's own reaction is highlighted. */
export function ReviewReactions({ review }: { review: Review }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const styles = makeActionStyles(theme);
  // The server's answer to the last toggle; wins over what the list loaded.
  const [summary, setSummary] = useState<ReactionSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const { reactions, my_reaction: mine } = summary ?? review;
  const disabled = busy || review.locked || review.status !== 'visible';

  const counts = new Map(reactions.map(({ emoji, count }) => [emoji, count]));
  const pills = [
    ...STANDARD_REACTIONS.map(({ emoji, label }) => ({ emoji, label: t(label) })),
    // Custom emojis someone picked on the web.
    ...reactions
      .filter(({ emoji }) => !STANDARD_REACTIONS.some((standard) => standard.emoji === emoji))
      .map(({ emoji }) => ({ emoji, label: emoji })),
  ];

  async function toggle(emoji: string) {
    setBusy(true);
    try {
      setSummary(await toggleReviewReaction(review.game_id, review.id, emoji));
    } catch (error) {
      notify(t('Your reaction could not be saved.'), t(errorMessage(error)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.reactions}>
      {pills.map(({ emoji, label }) => {
        const count = counts.get(emoji) ?? 0;
        const selected = mine === emoji;
        return (
          <Pressable
            key={emoji}
            accessibilityRole="button"
            accessibilityLabel={`${label} ${count}`}
            accessibilityState={{ selected, disabled }}
            disabled={disabled}
            onPress={() => void toggle(emoji)}
            style={({ pressed }) => [
              styles.pill,
              selected && styles.pillSelected,
              pressed && styles.pressed,
              disabled && !busy && styles.disabled,
            ]}
          >
            <Text style={styles.emoji}>{emoji}</Text>
            {count > 0 ? (
              <Text style={[styles.count, selected && styles.countSelected]}>{count}</Text>
            ) : null}
          </Pressable>
        );
      })}
    </View>
  );
}

/**
 * "Report" for someone else's review: opens a reason picker with optional details.
 * Shows "Reported" once this user has reported it. `onHidden` runs when the report
 * hid the review, so the list can reload.
 */
export function ReportReview({ review, onHidden }: { review: Review; onHidden: () => void }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeActionStyles(theme);
  const [reported, setReported] = useState(review.reported);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<ReportReason | null>(null);
  const [details, setDetails] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (reported) return <Text style={shared.muted}>{t('Reported')}</Text>;

  if (!open) {
    return <Chip label={t('Report')} styles={shared} onPress={() => setOpen(true)} />;
  }

  async function send() {
    if (!reason) return;
    setSending(true);
    setError(null);
    try {
      const result = await reportReview(review.game_id, review.id, reason, details);
      setReported(true);
      notify(t('Thanks for the report. An administrator will take a look.'));
      if (result.hidden) onHidden();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setReported(true); // "You already reported this review."
        notify(t(err.detail));
      } else {
        setError(t(errorMessage(err)));
      }
    } finally {
      setSending(false);
    }
  }

  return (
    <View style={styles.reportForm}>
      <Text style={styles.reportTitle}>{t('Why are you reporting this?')}</Text>
      <View style={shared.row} accessibilityRole="radiogroup">
        {REPORT_REASONS.map((option) => (
          <Chip
            key={option.reason}
            label={t(option.label)}
            selected={reason === option.reason}
            styles={shared}
            onPress={() => setReason(option.reason)}
          />
        ))}
      </View>
      <TextField
        label={t('Details (optional)')}
        value={details}
        onChangeText={setDetails}
        maxLength={REPORT_DETAILS_MAX_LENGTH}
        error={error}
      />
      <Button
        label={t('Send report')}
        onPress={() => void send()}
        loading={sending}
        disabled={!reason}
      />
      <Button
        label={t('Cancel')}
        variant="link"
        onPress={() => setOpen(false)}
        disabled={sending}
      />
    </View>
  );
}

function makeActionStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    reactions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
    pill: {
      minHeight: 32,
      minWidth: 44,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.xs,
      paddingHorizontal: spacing.sm,
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.background,
    },
    pillSelected: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
    pressed: { opacity: 0.7 },
    disabled: { opacity: 0.5 },
    emoji: { fontSize: 15 },
    count: { ...typography.caption, fontWeight: '600', color: colors.muted },
    countSelected: { color: colors.primary },
    reportForm: {
      width: '100%',
      gap: spacing.sm,
      paddingTop: spacing.sm,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: colors.border,
    },
    reportTitle: { ...typography.label, color: colors.text },
  });
}

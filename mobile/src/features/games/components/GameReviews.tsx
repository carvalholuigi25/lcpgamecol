import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { useSession } from '@/auth';
import { Button, Chip, makeStyles, TextField } from '@/components';
import { confirmAction, notify } from '@/features/admin/confirm';
import { isAdmin } from '@/features/users';
import { useRequest } from '@/hooks/useRequest';
import { useTheme, type Theme } from '@/theme';

import {
  deleteReview,
  fetchReviews,
  htmlToText,
  REVIEW_BODY_MAX_LENGTH,
  saveMyReview,
  type Review,
} from '../reviews';
import { errorMessage } from '../services';
import { ReportReview, ReviewReactions } from './ReviewActions';

/** Rating summary, the signed-in user's own review editor, and everyone else's reviews. */
export function GameReviews({ gameId }: { gameId: number }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeReviewStyles(theme);
  const { user } = useSession();
  const reviews = useRequest(`reviews:${gameId}`, (signal) => fetchReviews(gameId, signal));
  const data = reviews.data;

  let content;
  if (reviews.loading) {
    content = <ActivityIndicator color={theme.colors.primary} style={styles.spinner} />;
  } else if (!data) {
    // 409: "Reviews are locked until the game is released." — nothing to retry.
    content = (
      <View style={styles.message}>
        <Text style={shared.muted}>
          {reviews.errorStatus === 409 && reviews.error
            ? t(reviews.error)
            : t('Reviews could not be loaded.')}
        </Text>
        {reviews.errorStatus !== 409 ? (
          <Chip label={t('Try again')} styles={shared} onPress={reviews.retry} />
        ) : null}
      </View>
    );
  } else {
    const others = data.items.filter((review) => review.id !== data.mine?.id);
    content = (
      <>
        <Text style={shared.muted}>
          {data.average !== null
            ? t(
                data.count === 1
                  ? '{average} out of 5 from {count} review'
                  : '{average} out of 5 from {count} reviews',
                { average: data.average, count: data.count },
              )
            : t('No reviews yet.')}
        </Text>
        <MyReview
          key={data.mine?.updated_at ?? 'new'}
          gameId={gameId}
          mine={data.mine}
          ratingMax={data.rating_max}
          onChanged={reviews.refresh}
        />
        {others.map((review) => (
          <ReviewCard
            key={review.id}
            review={review}
            ratingMax={data.rating_max}
            canDelete={isAdmin(user)}
            onDelete={() => void removeReview(review, reviews.refresh, t)}
            onReportHid={reviews.refresh}
          />
        ))}
      </>
    );
  }

  return (
    <View style={styles.section}>
      <Text style={[shared.title, styles.heading]} accessibilityRole="header">
        {t('Reviews')}
      </Text>
      {content}
    </View>
  );
}

async function removeReview(
  review: Review,
  onDone: () => void,
  t: ReturnType<typeof useTranslation>['t'],
) {
  const confirmed = await confirmAction({
    title: t('Delete this review?'),
    confirmLabel: t('Delete'),
    cancelLabel: t('Cancel'),
    destructive: true,
  });
  if (!confirmed) return;
  try {
    await deleteReview(review.game_id, review.id);
    onDone();
  } catch (error) {
    notify(t('The review could not be deleted.'), t(errorMessage(error)));
  }
}

function MyReview({
  gameId,
  mine,
  ratingMax,
  onChanged,
}: {
  gameId: number;
  mine: Review | null;
  ratingMax: number;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeReviewStyles(theme);
  // Re-mounted (via `key`) whenever the saved review changes, so these start from it.
  const [editing, setEditing] = useState(!mine);
  const [rating, setRating] = useState(mine?.rating ?? 0);
  const [text, setText] = useState(htmlToText(mine?.body));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (mine?.locked || (mine && !editing)) {
    return (
      <ReviewCard
        review={mine}
        ratingMax={ratingMax}
        own
        onEdit={mine.locked ? undefined : () => setEditing(true)}
        onDelete={mine.locked ? undefined : () => void removeReview(mine, onChanged, t)}
      />
    );
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const saved = await saveMyReview(gameId, rating, text);
      if (saved.status === 'pending') {
        notify(t('Thanks! Your review will show once an administrator approves it.'));
      }
      onChanged();
    } catch (err) {
      setError(t(errorMessage(err)));
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={styles.card}>
      <Text style={shared.label}>{t('Your review')}</Text>
      <StarPicker value={rating} max={ratingMax} onChange={setRating} theme={theme} />
      <TextField
        label={t('Review')}
        value={text}
        onChangeText={setText}
        multiline
        maxLength={REVIEW_BODY_MAX_LENGTH}
        textAlignVertical="top"
        style={styles.input}
        error={error}
      />
      <Button
        label={mine ? t('Update review') : t('Post review')}
        onPress={() => void save()}
        loading={saving}
        disabled={rating < 1}
      />
      {mine ? (
        <Button
          label={t('Cancel')}
          variant="link"
          onPress={() => setEditing(false)}
          disabled={saving}
        />
      ) : null}
    </View>
  );
}

function ReviewCard({
  review,
  ratingMax,
  own = false,
  canDelete = own,
  onEdit,
  onDelete,
  onReportHid,
}: {
  review: Review;
  ratingMax: number;
  own?: boolean;
  canDelete?: boolean;
  onEdit?: (() => void) | undefined;
  onDelete?: (() => void) | undefined;
  /** Reload after this user's report hid the review (others' reviews only). */
  onReportHid?: () => void;
}) {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeReviewStyles(theme);
  const body = htmlToText(review.body);
  const date = review.updated_at?.slice(0, 10);

  return (
    <View style={[styles.card, own && styles.cardOwn]}>
      <View style={styles.cardHeader}>
        <Text style={styles.author} numberOfLines={1}>
          {own ? t('Your review') : review.display_name || review.username}
        </Text>
        <Text style={shared.muted}>{date}</Text>
      </View>
      <Stars value={review.rating} max={ratingMax} styles={styles} />
      {review.status !== 'visible' ? (
        <Text style={styles.status}>
          {review.status === 'pending' ? t('Waiting for review') : t('Hidden')}
        </Text>
      ) : null}
      {body ? <Text style={shared.body}>{body}</Text> : null}
      <ReviewReactions review={review} />
      {onEdit || (canDelete && onDelete) || !own ? (
        <View style={[shared.row, styles.actions]}>
          {onEdit ? <Chip label={t('Edit')} styles={shared} onPress={onEdit} /> : null}
          {canDelete && onDelete ? (
            <Chip
              label={own ? t('Delete my review') : t('Delete')}
              styles={shared}
              onPress={onDelete}
            />
          ) : null}
          {!own ? <ReportReview review={review} onHidden={onReportHid ?? (() => {})} /> : null}
        </View>
      ) : null}
    </View>
  );
}

function Stars({
  value,
  max,
  styles,
}: {
  value: number;
  max: number;
  styles: ReturnType<typeof makeReviewStyles>;
}) {
  return (
    <Text style={styles.stars} accessibilityLabel={`${value} / ${max}`}>
      {'★'.repeat(value)}
      <Text style={styles.starsEmpty}>{'★'.repeat(Math.max(0, max - value))}</Text>
    </Text>
  );
}

function StarPicker({
  value,
  max,
  onChange,
  theme,
}: {
  value: number;
  max: number;
  onChange: (value: number) => void;
  theme: Theme;
}) {
  const styles = makeReviewStyles(theme);
  return (
    <View
      style={styles.picker}
      accessibilityRole="adjustable"
      accessibilityValue={{ min: 0, max, now: value }}
    >
      {Array.from({ length: max }, (_, i) => i + 1).map((star) => (
        <Pressable
          key={star}
          accessibilityRole="button"
          accessibilityLabel={`${star} / ${max}`}
          accessibilityState={{ selected: star <= value }}
          hitSlop={4}
          onPress={() => onChange(star)}
        >
          <Text style={[styles.pickerStar, star <= value && styles.pickerStarOn]}>★</Text>
        </Pressable>
      ))}
    </View>
  );
}

function makeReviewStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    section: { gap: spacing.md, marginTop: spacing.lg },
    heading: { marginBottom: -spacing.xs },
    spinner: { marginVertical: spacing.lg },
    message: { gap: spacing.sm, alignItems: 'flex-start' },
    card: {
      gap: spacing.sm,
      padding: spacing.md,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
    },
    cardOwn: { borderColor: colors.primary },
    cardHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: spacing.sm,
    },
    author: { ...typography.label, fontWeight: '600', color: colors.text, flexShrink: 1 },
    stars: { fontSize: 16, color: colors.warning, letterSpacing: 2 },
    starsEmpty: { color: colors.border },
    status: { ...typography.caption, fontWeight: '600', color: colors.danger },
    input: { minHeight: 100 },
    actions: { alignItems: 'center' },
    picker: { flexDirection: 'row', gap: spacing.xs },
    pickerStar: { fontSize: 32, color: colors.border },
    pickerStarOn: { color: colors.warning },
  });
}

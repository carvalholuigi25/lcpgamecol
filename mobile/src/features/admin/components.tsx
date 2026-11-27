import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useTheme, type Theme } from '@/theme';

import { barShares, type CountBucket } from './services';

/** A headline number with its label (dashboard overview). */
export function StatTile({ label, value }: { label: string; value: string | number }) {
  const styles = makeStyles(useTheme());
  return (
    <View style={styles.tile} accessible accessibilityLabel={`${label}: ${value}`}>
      <Text style={styles.tileValue}>{value}</Text>
      <Text style={styles.muted} numberOfLines={2}>
        {label}
      </Text>
    </View>
  );
}

/** Ranked single-series bars; label and count in text inks, the bar carries the size. */
export function BarList({ title, buckets }: { title: string; buckets: CountBucket[] }) {
  const styles = makeStyles(useTheme());
  if (buckets.length === 0) return null;
  const shares = barShares(buckets);

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle} accessibilityRole="header">
        {title}
      </Text>
      {buckets.map((bucket, index) => (
        <View
          key={bucket.label}
          style={styles.barRow}
          accessible
          accessibilityLabel={`${bucket.label}: ${bucket.count}`}
        >
          <View style={styles.barLabels}>
            <Text style={styles.body} numberOfLines={1}>
              {bucket.label}
            </Text>
            <Text style={styles.count}>{bucket.count}</Text>
          </View>
          <View style={styles.track}>
            <View style={[styles.fill, { width: `${Math.max(shares[index] ?? 0, 2)}%` }]} />
          </View>
        </View>
      ))}
    </View>
  );
}

/** A tappable card leading to an admin section, with an optional attention badge. */
export function SectionLink({
  title,
  description,
  badge,
  onPress,
}: {
  title: string;
  description: string;
  badge?: number;
  onPress: () => void;
}) {
  const styles = makeStyles(useTheme());
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={badge ? `${title}, ${badge}` : title}
      onPress={onPress}
      style={({ pressed }) => [styles.card, styles.section, pressed && styles.pressed]}
    >
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={styles.cardTitle}>{title}</Text>
        <Text style={styles.muted}>{description}</Text>
      </View>
      {badge ? (
        <View style={styles.badge}>
          <Text style={styles.badgeText}>{badge > 99 ? '99+' : badge}</Text>
        </View>
      ) : null}
      <Text style={styles.chevron}>›</Text>
    </Pressable>
  );
}

/** Small outlined action button for list rows (Approve, Hide, …). */
export function ActionButton({
  label,
  onPress,
  tone = 'neutral',
  disabled,
}: {
  label: string;
  onPress: () => void;
  tone?: 'neutral' | 'primary' | 'danger';
  disabled?: boolean;
}) {
  const theme = useTheme();
  const styles = makeStyles(theme);
  const color = {
    neutral: theme.colors.text,
    primary: theme.colors.primary,
    danger: theme.colors.danger,
  }[tone];
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!disabled }}
      disabled={disabled}
      onPress={onPress}
      hitSlop={4}
      style={({ pressed }) => [
        styles.action,
        { borderColor: color },
        pressed && styles.pressed,
        disabled && styles.disabled,
      ]}
    >
      <Text style={[styles.actionText, { color }]}>{label}</Text>
    </Pressable>
  );
}

/** Bordered surface used for every admin panel. */
export function Card({ children }: { children: ReactNode }) {
  return <View style={makeStyles(useTheme()).card}>{children}</View>;
}

function makeStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    card: {
      gap: spacing.md,
      padding: spacing.lg,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
    },
    cardTitle: { ...typography.title, color: colors.text },
    body: { ...typography.body, color: colors.text, flex: 1 },
    muted: { ...typography.caption, color: colors.muted },
    tile: {
      flexGrow: 1,
      flexBasis: '45%',
      gap: spacing.xs,
      padding: spacing.md,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
    },
    tileValue: { ...typography.display, color: colors.text },
    barRow: { gap: spacing.xs },
    barLabels: { flexDirection: 'row', alignItems: 'baseline', gap: spacing.sm },
    count: { ...typography.label, color: colors.muted },
    track: { height: 8, borderRadius: 4, backgroundColor: colors.background, overflow: 'hidden' },
    fill: { height: '100%', borderRadius: 4, backgroundColor: colors.primary },
    section: { flexDirection: 'row', alignItems: 'center' },
    badge: {
      minWidth: 24,
      height: 24,
      paddingHorizontal: spacing.xs,
      borderRadius: radius.pill,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.danger,
    },
    badgeText: { ...typography.caption, fontWeight: '700', color: colors.onPrimary },
    chevron: { ...typography.title, color: colors.muted },
    action: {
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.xs + 2,
      borderRadius: radius.pill,
      borderWidth: 1,
    },
    actionText: { ...typography.label, fontWeight: '600' },
    pressed: { opacity: 0.7 },
    disabled: { opacity: 0.4 },
  });
}

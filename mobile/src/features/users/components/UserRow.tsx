import { Link } from 'expo-router';
import { memo, type ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { resolveAssetUrl } from '@/api';
import { Avatar } from '@/components';
import { useTheme, type Theme } from '@/theme';

import { initials } from '../services';

type UserRowProps = {
  username: string;
  displayName: string | null;
  avatarUrl: string | null;
  /** Extra line under the name (e.g. "Level 5 · Adventurer"). */
  detail?: string;
  /** Left of the avatar (leaderboard position). */
  leading?: ReactNode;
  /** Right side (pills, XP). */
  trailing?: ReactNode;
  highlighted?: boolean;
};

/** One user in a list; tapping it opens /user/[userId]. */
function UserRowBase({
  username,
  displayName,
  avatarUrl,
  detail,
  leading,
  trailing,
  highlighted,
}: UserRowProps) {
  const theme = useTheme();
  const styles = makeStyles(theme);
  const name = displayName || username;

  return (
    <Link href={{ pathname: '/user/[userId]', params: { userId: username } }} asChild>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={name}
        // `Link asChild` merges styles by spreading objects, so a style *function* (or array)
        // would be dropped: keep the outer style static and apply pressed feedback inside.
        style={styles.pressable}
      >
        {({ pressed }) => (
          <View style={[styles.row, highlighted && styles.highlighted, pressed && styles.pressed]}>
            {leading}
            <Avatar uri={resolveAssetUrl(avatarUrl)} label={initials(name)} />
            <View style={styles.text}>
              <Text style={styles.name} numberOfLines={1}>
                {name}
              </Text>
              <Text style={styles.muted} numberOfLines={1}>
                @{username}
                {detail ? ` · ${detail}` : ''}
              </Text>
            </View>
            {trailing ? <View style={styles.trailing}>{trailing}</View> : null}
          </View>
        )}
      </Pressable>
    </Link>
  );
}

export const UserRow = memo(UserRowBase);

function makeStyles({ colors, spacing, typography }: Theme) {
  return StyleSheet.create({
    pressable: { width: '100%' },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.md,
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.md,
      backgroundColor: colors.background,
    },
    highlighted: { backgroundColor: colors.primarySoft },
    pressed: { opacity: 0.7 },
    text: { flex: 1, gap: 2 },
    name: { ...typography.body, fontWeight: '600', color: colors.text },
    muted: { ...typography.caption, color: colors.muted },
    trailing: { alignItems: 'flex-end', gap: spacing.xs },
  });
}

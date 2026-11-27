import { Text, View } from 'react-native';

import { useTheme } from '@/theme';

/** Small rounded label (role, rank, level, …). */
export function Pill({
  label,
  tone = 'neutral',
}: {
  label: string;
  tone?: 'neutral' | 'primary' | 'warning';
}) {
  const { colors, spacing, radius, typography } = useTheme();
  const palette = {
    neutral: { bg: colors.surface, fg: colors.muted, border: colors.border },
    primary: { bg: colors.primarySoft, fg: colors.primary, border: colors.primarySoft },
    warning: { bg: colors.surface, fg: colors.text, border: colors.warning },
  }[tone];

  return (
    <View
      style={{
        paddingHorizontal: spacing.sm,
        paddingVertical: 2,
        borderRadius: radius.pill,
        borderWidth: 1,
        borderColor: palette.border,
        backgroundColor: palette.bg,
      }}
    >
      <Text style={{ ...typography.caption, fontWeight: '600', color: palette.fg }}>{label}</Text>
    </View>
  );
}

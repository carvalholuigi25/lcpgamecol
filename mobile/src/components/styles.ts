import { StyleSheet } from 'react-native';

import type { Theme } from '@/theme';

/** Shared screen styles built from the current theme tokens. */
export function makeStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    screen: { flex: 1, backgroundColor: colors.background },
    container: {
      padding: spacing.lg,
      gap: spacing.md,
    },
    containerHome: {
      padding: spacing.lg,
      gap: spacing.md,
      flex: 1,
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
    },
    centered: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      padding: spacing.lg,
      gap: spacing.md,
    },
    heading: { ...typography.display, color: colors.text },
    title: { ...typography.title, color: colors.text },
    body: { ...typography.body, color: colors.text },
    muted: { ...typography.caption, color: colors.muted },
    label: { ...typography.label, color: colors.text, marginTop: spacing.md },
    row: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
    chip: {
      paddingVertical: spacing.xs + 2,
      paddingHorizontal: spacing.md,
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
    },
    chipSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
    chipText: { ...typography.label, color: colors.text },
    chipTextSelected: { color: colors.onPrimary },
  });
}

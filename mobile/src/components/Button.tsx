import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';

import { useTheme, type Theme } from '@/theme';

type ButtonProps = {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'link';
  loading?: boolean;
  disabled?: boolean;
};

/** Full-width primary action, or a plain text "link" button. */
export function Button({ label, onPress, variant = 'primary', loading, disabled }: ButtonProps) {
  const theme = useTheme();
  const styles = makeStyles(theme);
  const inactive = disabled || loading;
  const primary = variant === 'primary';

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!inactive, busy: !!loading }}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [
        primary ? styles.primary : styles.link,
        pressed && styles.pressed,
        inactive && styles.disabled,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={primary ? theme.colors.onPrimary : theme.colors.primary} />
      ) : (
        <Text style={primary ? styles.primaryText : styles.linkText}>{label}</Text>
      )}
    </Pressable>
  );
}

function makeStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    primary: {
      minHeight: 48,
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: radius.md,
      backgroundColor: colors.primary,
      paddingHorizontal: spacing.lg,
    },
    link: { alignItems: 'center', paddingVertical: spacing.sm },
    pressed: { opacity: 0.8 },
    disabled: { opacity: 0.5 },
    primaryText: { ...typography.body, fontWeight: '600', color: colors.onPrimary },
    linkText: { ...typography.label, color: colors.primary },
  });
}

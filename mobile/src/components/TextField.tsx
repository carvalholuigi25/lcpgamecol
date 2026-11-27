import type { ComponentRef, ReactNode, Ref } from 'react';
import { StyleSheet, Text, TextInput, View, type TextInputProps } from 'react-native';

import { useTheme, type Theme } from '@/theme';

type TextFieldProps = TextInputProps & {
  label: string;
  error?: string | null;
  /** Rendered inside the field on the right (e.g. a show/hide password toggle). */
  accessory?: ReactNode;
  ref?: Ref<ComponentRef<typeof TextInput>>;
};

/** Labelled, themed text input with an inline error message. */
export function TextField({ label, error, accessory, style, ref, ...inputProps }: TextFieldProps) {
  const theme = useTheme();
  const styles = makeStyles(theme);

  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <View style={[styles.box, error ? styles.boxError : null]}>
        <TextInput
          ref={ref}
          accessibilityLabel={label}
          placeholderTextColor={theme.colors.muted}
          style={[styles.input, style]}
          {...inputProps}
        />
        {accessory}
      </View>
      {error ? (
        <Text style={styles.error} accessibilityLiveRegion="polite">
          {error}
        </Text>
      ) : null}
    </View>
  );
}

function makeStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    field: { gap: spacing.xs },
    label: { ...typography.label, color: colors.text },
    box: {
      flexDirection: 'row',
      alignItems: 'center',
      borderWidth: 1,
      borderColor: colors.border,
      borderRadius: radius.md,
      backgroundColor: colors.surface,
      paddingHorizontal: spacing.md,
    },
    boxError: { borderColor: colors.danger },
    input: { ...typography.body, flex: 1, color: colors.text, paddingVertical: spacing.md },
    error: { ...typography.caption, color: colors.danger },
  });
}

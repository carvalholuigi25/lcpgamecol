import { useState } from 'react';
import { FlatList, Modal, Pressable, StyleSheet, Text } from 'react-native';

import { useTheme, type Theme } from '@/theme';

export type DropdownOption<T extends string> = { value: T; label: string };

type DropdownProps<T extends string> = {
  /** Accessible name for the trigger and the option list. */
  label: string;
  value: T;
  options: DropdownOption<T>[];
  onChange: (value: T) => void;
};

/** Themed select: a field-like trigger that opens a modal list of options. */
export function Dropdown<T extends string>({ label, value, options, onChange }: DropdownProps<T>) {
  const theme = useTheme();
  const styles = makeStyles(theme);
  const [open, setOpen] = useState(false);
  const current = options.find((option) => option.value === value);

  function select(next: T) {
    setOpen(false);
    if (next !== value) onChange(next);
  }

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityValue={{ text: current?.label }}
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen(true)}
        style={({ pressed }) => [styles.trigger, pressed && styles.pressed]}
      >
        <Text style={styles.triggerText} numberOfLines={1}>
          {current?.label ?? ''}
        </Text>
        <Text style={styles.caret}>▾</Text>
      </Pressable>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable
          style={styles.backdrop}
          accessibilityRole="button"
          accessibilityLabel="Close"
          onPress={() => setOpen(false)}
        >
          {/* Inner Pressable swallows taps so they don't close the sheet. */}
          <Pressable style={styles.sheet} accessibilityLabel={label} onPress={() => {}}>
            <Text style={styles.sheetTitle}>{label}</Text>
            <FlatList
              data={options}
              keyExtractor={(option) => option.value}
              renderItem={({ item }) => {
                const selected = item.value === value;
                return (
                  <Pressable
                    accessibilityRole="menuitem"
                    accessibilityState={{ selected }}
                    onPress={() => select(item.value)}
                    style={({ pressed }) => [
                      styles.option,
                      selected && styles.optionSelected,
                      pressed && styles.pressed,
                    ]}
                  >
                    <Text style={[styles.optionText, selected && styles.optionTextSelected]}>
                      {item.label}
                    </Text>
                    {selected ? <Text style={styles.check}>✓</Text> : null}
                  </Pressable>
                );
              }}
            />
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

function makeStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    trigger: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: spacing.sm,
      borderWidth: 1,
      borderColor: colors.border,
      borderRadius: radius.md,
      backgroundColor: colors.surface,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.md,
    },
    triggerText: { ...typography.body, flex: 1, color: colors.text },
    caret: { ...typography.body, color: colors.muted },
    pressed: { opacity: 0.7 },
    backdrop: {
      flex: 1,
      justifyContent: 'center',
      padding: spacing.xl,
      backgroundColor: 'rgba(0, 0, 0, 0.4)',
    },
    sheet: {
      width: '100%',
      maxWidth: 420,
      maxHeight: '70%',
      alignSelf: 'center',
      borderRadius: radius.lg,
      backgroundColor: colors.surface,
      paddingVertical: spacing.sm,
    },
    sheetTitle: {
      ...typography.label,
      color: colors.muted,
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.sm,
    },
    option: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.md,
    },
    optionSelected: { backgroundColor: colors.primarySoft },
    optionText: { ...typography.body, color: colors.text },
    optionTextSelected: { color: colors.primary, fontWeight: '600' },
    check: { ...typography.body, color: colors.primary },
  });
}

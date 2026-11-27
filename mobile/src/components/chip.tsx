import { Pressable, Text } from 'react-native';

import type { makeStyles } from './styles';

type ChipProps = {
  label: string;
  selected?: boolean;
  onPress?: () => void;
  styles: ReturnType<typeof makeStyles>;
};

/** Pill-shaped button used for option pickers (theme, language) and quick links. */
export function Chip({ label, selected = false, onPress, styles }: ChipProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </Pressable>
  );
}

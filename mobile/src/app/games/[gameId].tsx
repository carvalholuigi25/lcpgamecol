import { useTheme } from '@/theme';
import { useNavigation } from '@react-navigation/native';
import { View, Text, StyleSheet, Pressable } from 'react-native';

export default function GamesDetailsScreen(props: { route: { params: { gameId: string } } }) {
  const theme = useTheme();
  const mstyles = makeStyles(theme);
  const navigation: any = useNavigation();

  return (
    <View style={styles.container}>
      <Text>Games Details Screen (id: {props.route.params.gameId})</Text>
      <Chip
        key="games"
        label="Games"
        selected={false}
        onPress={() => {
          navigation.navigate('Games');
        }}
        styles={mstyles}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});

function Chip({
  label,
  selected,
  onPress,
  styles,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  styles: ReturnType<typeof makeStyles>;
}) {
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

function makeStyles({ colors, spacing, radius, typography }: ReturnType<typeof useTheme>) {
  return StyleSheet.create({
    container: { padding: spacing.lg, gap: spacing.md },
    heading: { ...typography.display, color: colors.text },
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

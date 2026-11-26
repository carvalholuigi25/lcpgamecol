import { Image } from 'expo-image';
import { StyleSheet, Text, View } from 'react-native';

import { useTheme } from '@/theme';

/** Round user picture, falling back to initials on a tinted circle. */
export function Avatar({
  uri,
  label,
  size = 44,
  ring = false,
}: {
  uri: string | null;
  /** Initials shown when there is no picture. */
  label: string;
  size?: number;
  /** Draw a background-coloured ring (for avatars overlapping a cover image). */
  ring?: boolean;
}) {
  const { colors } = useTheme();
  const box = {
    width: size,
    height: size,
    borderRadius: size / 2,
    backgroundColor: colors.primarySoft,
    ...(ring ? { borderWidth: 3, borderColor: colors.background } : {}),
  };

  return (
    <View style={[styles.box, box]} accessibilityElementsHidden importantForAccessibility="no">
      {uri ? (
        <Image source={uri} style={StyleSheet.absoluteFill} contentFit="cover" transition={150} />
      ) : (
        <Text style={{ color: colors.primary, fontWeight: '700', fontSize: size * 0.38 }}>
          {label}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
});

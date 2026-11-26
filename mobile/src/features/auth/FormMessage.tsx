import { Text } from 'react-native';

import { useTheme } from '@/theme';

/** Form-level error or success message, announced to screen readers. */
export function FormMessage({
  message,
  tone = 'error',
  testID,
}: {
  message: string | null;
  tone?: 'error' | 'success';
  testID?: string;
}) {
  const { colors, typography } = useTheme();
  if (!message) return null;
  return (
    <Text
      style={{ ...typography.body, color: tone === 'error' ? colors.danger : colors.primary }}
      accessibilityLiveRegion="polite"
      testID={testID}
    >
      {message}
    </Text>
  );
}

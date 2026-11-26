import { useState, type ComponentProps } from 'react';
import { useTranslation } from 'react-i18next';
import { Pressable, Text } from 'react-native';

import { TextField } from '@/components';
import { useTheme } from '@/theme';

type PasswordFieldProps = Omit<ComponentProps<typeof TextField>, 'secureTextEntry' | 'accessory'>;

/** TextField for passwords with a Show/Hide toggle. */
export function PasswordField(props: PasswordFieldProps) {
  const { t } = useTranslation();
  const theme = useTheme();
  const [visible, setVisible] = useState(false);

  return (
    <TextField
      autoCapitalize="none"
      autoCorrect={false}
      {...props}
      secureTextEntry={!visible}
      accessory={
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={visible ? t('Hide password') : t('Show password')}
          onPress={() => setVisible((v) => !v)}
          hitSlop={8}
        >
          <Text style={{ ...theme.typography.label, color: theme.colors.primary }}>
            {visible ? t('Hide') : t('Show')}
          </Text>
        </Pressable>
      }
    />
  );
}

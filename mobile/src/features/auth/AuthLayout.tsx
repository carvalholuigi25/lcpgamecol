import { Image } from 'expo-image';
import type { ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { makeStyles } from '@/components';
import { useTheme } from '@/theme';

type AuthLayoutProps = {
  title: string;
  subtitle?: string;
  children: ReactNode;
  /** Links under the form (e.g. "Create an account"). */
  footer?: ReactNode;
};

/** Shared frame for the sign-in, register and forgot-password screens. */
export function AuthLayout({ title, subtitle, children, footer }: AuthLayoutProps) {
  const theme = useTheme();
  const styles = makeStyles(theme);

  return (
    <SafeAreaView style={styles.screen}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={{
            flexGrow: 1,
            justifyContent: 'center',
            padding: theme.spacing.xl,
            gap: theme.spacing.xl,
            width: '100%',
            maxWidth: 480,
            alignSelf: 'center',
          }}
          keyboardShouldPersistTaps="handled"
        >
          <View style={{ alignItems: 'center', gap: theme.spacing.sm }}>
            <Image
              source={require('../../../assets/splash-icon.png')}
              style={{ width: 72, height: 72 }}
              contentFit="contain"
            />
            <Text style={styles.heading} accessibilityRole="header">
              {title}
            </Text>
            {subtitle ? (
              <Text style={[styles.muted, { textAlign: 'center' }]}>{subtitle}</Text>
            ) : null}
          </View>
          {children}
          {footer ? <View style={{ gap: theme.spacing.xs }}>{footer}</View> : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

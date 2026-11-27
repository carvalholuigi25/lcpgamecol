import { router } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { TwoFactorChallenge } from '@/auth';
import { Button } from '@/components';
import { AuthLayout, LoginForm, TwoFactorForm } from '@/features/auth';

// Sign-in screen: username + password (and a 2FA code when the account uses it).
// Once signed in, the route guards in _layout.tsx move the user to /home.
// Registering and password recovery live on their own screens.
export default function LoginScreen() {
  const { t } = useTranslation();
  const [challenge, setChallenge] = useState<TwoFactorChallenge | null>(null);

  if (challenge) {
    return (
      <AuthLayout title={t('Two-step verification')} subtitle={t('Game Shelf')}>
        <TwoFactorForm challenge={challenge} onCancel={() => setChallenge(null)} />
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title={t('Sign in')}
      subtitle={t('Game Shelf')}
      footer={
        <>
          <Button
            variant="link"
            label={t('Forgot your password?')}
            onPress={() => router.push('/forgot-password')}
          />
          <Button
            variant="link"
            label={t('Create an account')}
            onPress={() => router.push('/register')}
          />
        </>
      }
    >
      <LoginForm onTwoFactor={setChallenge} />
    </AuthLayout>
  );
}

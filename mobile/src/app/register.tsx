import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components';
import { AuthLayout, RegisterForm } from '@/features/auth';

function backToSignIn() {
  if (router.canGoBack()) router.back();
  else router.replace('/login');
}

// Create-account screen. After registering, the new account is signed in and the route
// guards in _layout.tsx move on to /home.
export default function RegisterScreen() {
  const { t } = useTranslation();

  return (
    <AuthLayout
      title={t('Create an account')}
      subtitle={t('Start your game collection.')}
      footer={
        <Button
          variant="link"
          label={t('Already have an account? Sign in')}
          onPress={backToSignIn}
        />
      }
    >
      <RegisterForm onNeedsSignIn={backToSignIn} />
    </AuthLayout>
  );
}

import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components';
import { AuthLayout, ForgotPasswordForm } from '@/features/auth';

function backToSignIn() {
  if (router.canGoBack()) router.back();
  else router.replace('/login');
}

// Password recovery screen: request a reset link, paste it, choose a new password.
export default function ForgotPasswordScreen() {
  const { t } = useTranslation();

  return (
    <AuthLayout
      title={t('Reset your password')}
      subtitle={t('We will email you a link to choose a new password.')}
      footer={<Button variant="link" label={t('Back to sign in')} onPress={backToSignIn} />}
    >
      <ForgotPasswordForm onBackToSignIn={backToSignIn} />
    </AuthLayout>
  );
}

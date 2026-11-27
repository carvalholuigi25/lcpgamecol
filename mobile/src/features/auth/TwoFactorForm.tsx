import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Text, View } from 'react-native';

import { useSession, type TwoFactorChallenge } from '@/auth';
import { Button, makeStyles, TextField } from '@/components';
import { useTheme } from '@/theme';

import { authErrorMessage } from './authErrorMessage';
import { FormMessage } from './FormMessage';

type TwoFactorFormProps = {
  challenge: TwoFactorChallenge;
  onSignedIn?: () => void;
  onCancel: () => void;
};

/** Second step when the account has two-factor sign-in: POST /auth/two-factor/verify. */
export function TwoFactorForm({ challenge, onSignedIn, onCancel }: TwoFactorFormProps) {
  const { t } = useTranslation();
  const theme = useTheme();
  const styles = makeStyles(theme);
  const { verifyTwoFactor, resendTwoFactorCode } = useSession();

  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const byEmail = challenge.method === 'email';

  async function submit() {
    if (!code.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await verifyTwoFactor(challenge.challenge_token, code);
      onSignedIn?.();
    } catch (err) {
      setError(authErrorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setError(null);
    try {
      await resendTwoFactorCode(challenge.challenge_token);
      setNotice(t('A new code is on its way.'));
    } catch (err) {
      setError(authErrorMessage(err, t));
    }
  }

  return (
    <View style={{ gap: theme.spacing.md }}>
      <Text style={styles.body}>
        {byEmail
          ? t('Enter the code we sent to {email}.', { email: challenge.email ?? '' })
          : t('Enter the code from your authenticator app, or a recovery code.')}
      </Text>
      <TextField
        label={t('Code')}
        value={code}
        onChangeText={setCode}
        autoFocus
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="one-time-code"
        textContentType="oneTimeCode"
        keyboardType={byEmail ? 'number-pad' : 'default'}
        returnKeyType="go"
        onSubmitEditing={() => void submit()}
        maxLength={32}
        editable={!busy}
        testID="two-factor-code"
      />
      <FormMessage message={error} />
      <FormMessage tone="success" message={notice} />

      <Button
        label={t('Verify')}
        onPress={() => void submit()}
        loading={busy}
        disabled={!code.trim()}
      />
      {byEmail ? (
        <Button variant="link" label={t('Resend code')} onPress={() => void resend()} />
      ) : null}
      <Button variant="link" label={t('Back to sign in')} onPress={onCancel} />
    </View>
  );
}

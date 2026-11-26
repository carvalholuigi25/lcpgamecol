import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Text, View } from 'react-native';

import {
  checkResetToken,
  confirmPasswordReset,
  extractResetToken,
  requestPasswordReset,
} from '@/auth';
import { Button, makeStyles, TextField } from '@/components';
import { useTheme } from '@/theme';

import { authErrorMessage } from './authErrorMessage';
import { FormMessage } from './FormMessage';
import { PasswordField } from './PasswordField';

type Step =
  | { name: 'request' }
  | { name: 'enterLink'; notice: string | null }
  | { name: 'newPassword'; token: string; username: string | null }
  | { name: 'done'; username: string };

/**
 * Password recovery in three steps:
 * 1. POST /auth/password-reset/request — email a reset link,
 * 2. paste that link (or its token) — GET /auth/password-reset/check,
 * 3. choose a new password — POST /auth/password-reset/confirm.
 */
export function ForgotPasswordForm({ onBackToSignIn }: { onBackToSignIn: () => void }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const styles = makeStyles(theme);
  const [step, setStep] = useState<Step>({ name: 'request' });
  const [identifier, setIdentifier] = useState('');
  const [link, setLink] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<void>) {
    setError(null);
    setBusy(true);
    try {
      await action();
      setSubmitted(false);
    } catch (err) {
      setError(authErrorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }

  const sendLink = () => {
    setSubmitted(true);
    if (!identifier.trim() || busy) return;
    void run(async () => {
      const notice = await requestPasswordReset(identifier);
      setStep({ name: 'enterLink', notice });
    });
  };

  const checkLink = () => {
    setSubmitted(true);
    const token = extractResetToken(link);
    if (!token || busy) return;
    void run(async () => {
      const result = await checkResetToken(token);
      if (!result.valid) {
        setError(t('This reset link is invalid or has expired.'));
        return;
      }
      setStep({ name: 'newPassword', token, username: result.username });
    });
  };

  const savePassword = (token: string) => {
    setSubmitted(true);
    if (!password || password !== confirm || busy) return;
    void run(async () => {
      const username = await confirmPasswordReset(token, password);
      setStep({ name: 'done', username });
    });
  };

  if (step.name === 'done') {
    return (
      <View style={{ gap: theme.spacing.md }}>
        <FormMessage
          tone="success"
          message={t('Your password was changed, {name}. Sign in with the new one.', {
            name: step.username,
          })}
        />
        <Button label={t('Back to sign in')} onPress={onBackToSignIn} />
      </View>
    );
  }

  if (step.name === 'newPassword') {
    return (
      <View style={{ gap: theme.spacing.md }}>
        {step.username ? (
          <Text style={styles.body}>
            {t('Choose a new password for {name}.', { name: step.username })}
          </Text>
        ) : null}
        <PasswordField
          label={t('New password')}
          value={password}
          onChangeText={setPassword}
          error={submitted && !password ? t('Choose a password.') : null}
          autoComplete="new-password"
          textContentType="newPassword"
          editable={!busy}
          maxLength={128}
          testID="reset-password"
        />
        <PasswordField
          label={t('Confirm password')}
          value={confirm}
          onChangeText={setConfirm}
          error={
            submitted && password && confirm !== password ? t('The passwords do not match.') : null
          }
          autoComplete="new-password"
          textContentType="newPassword"
          returnKeyType="go"
          onSubmitEditing={() => savePassword(step.token)}
          editable={!busy}
          maxLength={128}
          testID="reset-confirm"
        />
        <FormMessage message={error} testID="reset-error" />
        <Button
          label={t('Change password')}
          onPress={() => savePassword(step.token)}
          loading={busy}
        />
      </View>
    );
  }

  if (step.name === 'enterLink') {
    return (
      <View style={{ gap: theme.spacing.md }}>
        <FormMessage tone="success" message={step.notice} />
        <Text style={styles.body}>
          {t('Open the email and paste the reset link (or its code) here.')}
        </Text>
        <TextField
          label={t('Reset link or code')}
          value={link}
          onChangeText={setLink}
          error={submitted && !link.trim() ? t('Paste the link from the email.') : null}
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="go"
          onSubmitEditing={checkLink}
          editable={!busy}
          testID="reset-link"
        />
        <FormMessage message={error} testID="reset-error" />
        <Button label={t('Continue')} onPress={checkLink} loading={busy} />
        <Button
          variant="link"
          label={t('Send another link')}
          onPress={() => setStep({ name: 'request' })}
        />
      </View>
    );
  }

  return (
    <View style={{ gap: theme.spacing.md }}>
      <TextField
        label={t('Username or email')}
        value={identifier}
        onChangeText={setIdentifier}
        error={submitted && !identifier.trim() ? t('Enter your username or email.') : null}
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="email"
        keyboardType="email-address"
        returnKeyType="send"
        onSubmitEditing={sendLink}
        editable={!busy}
        maxLength={254}
        testID="reset-identifier"
      />
      <FormMessage message={error} testID="reset-error" />
      <Button label={t('Send reset link')} onPress={sendLink} loading={busy} />
      <Button
        variant="link"
        label={t('I already have a link')}
        onPress={() => setStep({ name: 'enterLink', notice: null })}
      />
    </View>
  );
}

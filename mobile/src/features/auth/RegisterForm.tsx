import { useRef, useState, type ComponentRef } from 'react';
import { useTranslation } from 'react-i18next';
import { TextInput, View } from 'react-native';

import { register, useSession } from '@/auth';
import { Button, TextField } from '@/components';
import { useTheme } from '@/theme';

import { authErrorMessage } from './authErrorMessage';
import { FormMessage } from './FormMessage';
import { PasswordField } from './PasswordField';

// Same rule as USERNAME_PATTERN in backend/auth/users.py. The password policy (length,
// common passwords, …) is configurable on the server, so its message is shown as-is.
const USERNAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$/;

/** POST /auth/register, then sign in with the new account. */
export function RegisterForm({ onNeedsSignIn }: { onNeedsSignIn: () => void }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const { signIn } = useSession();
  const passwordRef = useRef<ComponentRef<typeof TextInput>>(null);
  const confirmRef = useRef<ComponentRef<typeof TextInput>>(null);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const name = username.trim();
  const usernameError = !submitted
    ? null
    : !name
      ? t('Choose a username.')
      : !USERNAME_PATTERN.test(name)
        ? t(
            'Use 3 to 32 letters, numbers, dots, hyphens or underscores, starting with a letter or number.',
          )
        : null;
  const passwordError = submitted && !password ? t('Choose a password.') : null;
  const confirmError =
    submitted && password && confirm !== password ? t('The passwords do not match.') : null;

  async function submit() {
    setSubmitted(true);
    setError(null);
    if (busy || !USERNAME_PATTERN.test(name) || !password || confirm !== password) return;
    setBusy(true);
    try {
      await register(name, password);
    } catch (err) {
      setError(authErrorMessage(err, t));
      setBusy(false);
      return;
    }
    try {
      // New accounts have no two-factor sign-in; the route guards then move on to /home.
      const result = await signIn(name, password);
      if (result.kind === 'twoFactor') onNeedsSignIn();
    } catch {
      // The account exists; let the user sign in by hand.
      onNeedsSignIn();
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={{ gap: theme.spacing.md }}>
      <TextField
        label={t('Username')}
        value={username}
        onChangeText={setUsername}
        error={usernameError}
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="username-new"
        textContentType="username"
        returnKeyType="next"
        submitBehavior="submit"
        onSubmitEditing={() => passwordRef.current?.focus()}
        editable={!busy}
        maxLength={32}
        testID="register-username"
      />
      <PasswordField
        ref={passwordRef}
        label={t('Password')}
        value={password}
        onChangeText={setPassword}
        error={passwordError}
        autoComplete="new-password"
        textContentType="newPassword"
        returnKeyType="next"
        submitBehavior="submit"
        onSubmitEditing={() => confirmRef.current?.focus()}
        editable={!busy}
        maxLength={128}
        testID="register-password"
      />
      <PasswordField
        ref={confirmRef}
        label={t('Confirm password')}
        value={confirm}
        onChangeText={setConfirm}
        error={confirmError}
        autoComplete="new-password"
        textContentType="newPassword"
        returnKeyType="go"
        onSubmitEditing={() => void submit()}
        editable={!busy}
        maxLength={128}
        testID="register-confirm"
      />
      <FormMessage message={error} testID="register-error" />
      <Button label={t('Create account')} onPress={() => void submit()} loading={busy} />
    </View>
  );
}

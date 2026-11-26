import { useRef, useState, type ComponentRef } from 'react';
import { useTranslation } from 'react-i18next';
import { TextInput, View } from 'react-native';

import { useSession, type TwoFactorChallenge } from '@/auth';
import { Button, TextField } from '@/components';
import { useTheme } from '@/theme';

import { authErrorMessage } from './authErrorMessage';
import { FormMessage } from './FormMessage';
import { PasswordField } from './PasswordField';

type LoginFormProps = {
  /** Called after a successful sign-in (navigation is handled by the route guards). */
  onSignedIn?: () => void;
  onTwoFactor: (challenge: TwoFactorChallenge) => void;
};

/** Username + password form for POST /auth/token. */
export function LoginForm({ onSignedIn, onTwoFactor }: LoginFormProps) {
  const { t } = useTranslation();
  const theme = useTheme();
  const { signIn } = useSession();
  const passwordRef = useRef<ComponentRef<typeof TextInput>>(null);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const usernameError = submitted && !username.trim() ? t('Enter your username.') : null;
  const passwordError = submitted && !password ? t('Enter your password.') : null;

  async function submit() {
    setSubmitted(true);
    setError(null);
    if (!username.trim() || !password || busy) return;
    setBusy(true);
    try {
      const result = await signIn(username, password);
      if (result.kind === 'twoFactor') onTwoFactor(result.challenge);
      else onSignedIn?.();
    } catch (err) {
      setError(authErrorMessage(err, t));
      setPassword('');
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
        autoComplete="username"
        textContentType="username"
        returnKeyType="next"
        submitBehavior="submit"
        onSubmitEditing={() => passwordRef.current?.focus()}
        editable={!busy}
        testID="login-username"
      />
      <PasswordField
        ref={passwordRef}
        label={t('Password')}
        value={password}
        onChangeText={setPassword}
        error={passwordError}
        autoComplete="current-password"
        textContentType="password"
        returnKeyType="go"
        onSubmitEditing={() => void submit()}
        editable={!busy}
        testID="login-password"
      />

      <FormMessage message={error} testID="login-error" />

      <Button label={t('Sign in')} onPress={() => void submit()} loading={busy} />
    </View>
  );
}

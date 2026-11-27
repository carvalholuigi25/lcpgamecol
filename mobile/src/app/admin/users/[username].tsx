import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Platform,
  RefreshControl,
  ScrollView,
  Share,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';

import { resolveAssetUrl } from '@/api';
import { useSession } from '@/auth';
import { Avatar, Button, Chip, Loading, makeStyles, Pill } from '@/components';
import {
  ActionButton,
  Card,
  confirmAction,
  createPasswordResetLink,
  isConfigured,
  loadAccount,
  notify,
  toggle,
  turnOffTwoFactor,
  updatePermissions,
  updateRole,
  type PasswordResetLink,
} from '@/features/admin';
import { errorMessage } from '@/features/games';
import { initials, ROLE_ADMIN, sameUser } from '@/features/users';
import { useRequest } from '@/hooks/useRequest';
import { useTheme, type Theme } from '@/theme';

type Loaded = Awaited<ReturnType<typeof loadAccount>>;

// Manage one account: role, granted permissions, password reset link and 2FA reset.
export default function ManageAccountScreen() {
  const { t } = useTranslation();
  const shared = makeStyles(useTheme());
  const { username } = useLocalSearchParams<{ username: string }>();
  const { data, error, errorStatus, loading, refreshing, refresh, retry } = useRequest<Loaded>(
    username ? `admin-account:${username}` : null,
    (signal) => loadAccount(username!, signal),
  );

  if (loading) return <Loading label={t('Loading…')} />;
  if (!data) {
    const notFound = errorStatus === 404 || !username;
    return (
      <View style={[shared.screen, shared.centered]}>
        <Text style={shared.title}>
          {notFound ? t('User not found') : t('Could not load this account.')}
        </Text>
        {!notFound && error ? <Text style={shared.muted}>{error}</Text> : null}
        {!notFound ? <Button label={t('Try again')} onPress={retry} /> : null}
      </View>
    );
  }

  return (
    <>
      <Stack.Screen options={{ title: t('Manage {name}', { name: data.account.username }) }} />
      {/* Keyed so local edits reset when a refresh brings new server data. */}
      <Manage
        key={JSON.stringify([data.account.role, data.account.two_factor_enabled, data.grants])}
        data={data}
        refreshing={refreshing}
        onRefresh={refresh}
      />
    </>
  );
}

function Manage({
  data,
  refreshing,
  onRefresh,
}: {
  data: Loaded;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeScreenStyles(theme);
  const { user: me } = useSession();
  const { account, permissions } = data;
  const configured = isConfigured(account);
  const isMe = sameUser(account.username, me?.username);
  const isAdminAccount = account.role === ROLE_ADMIN;
  const name = account.display_name || account.username;

  const [grants, setGrants] = useState(data.grants);
  const [busy, setBusy] = useState<string | null>(null);
  const [resetLink, setResetLink] = useState<PasswordResetLink | null>(null);
  const grantsChanged =
    grants.length !== data.grants.length || grants.some((g) => !data.grants.includes(g));

  async function run(key: string, task: () => Promise<unknown>, failure: string) {
    setBusy(key);
    try {
      await task();
      return true;
    } catch (e) {
      notify(failure, errorMessage(e));
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function changeRole(role: 'admin' | 'viewer') {
    if (role === account.role) return;
    const ok = await confirmAction({
      title:
        role === ROLE_ADMIN
          ? t('Make {name} an administrator?', { name })
          : t('Remove administrator access from {name}?', { name }),
      message: t('Their current sessions end and they sign in again with the new role.'),
      confirmLabel: t('Change role'),
      cancelLabel: t('Cancel'),
      destructive: role !== ROLE_ADMIN,
    });
    if (
      ok &&
      (await run('role', () => updateRole(account.username, role), t('Could not change the role.')))
    ) {
      onRefresh();
    }
  }

  async function savePermissions() {
    if (
      await run(
        'permissions',
        () => updatePermissions(account.username, grants),
        t('Could not save permissions.'),
      )
    ) {
      onRefresh();
    }
  }

  async function resetPassword() {
    const ok = await confirmAction({
      title: t('Create a password reset link for {name}?', { name }),
      message: t('Anyone with the link can set a new password until it expires.'),
      confirmLabel: t('Create link'),
      cancelLabel: t('Cancel'),
    });
    if (!ok) return;
    setBusy('reset');
    try {
      setResetLink(await createPasswordResetLink(account.username));
    } catch (e) {
      notify(t('Could not create the link.'), errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function disableTwoFactor() {
    const ok = await confirmAction({
      title: t('Turn off two-factor sign-in for {name}?', { name }),
      message: t('Only do this when they lost both their device and their recovery codes.'),
      confirmLabel: t('Turn off'),
      cancelLabel: t('Cancel'),
      destructive: true,
    });
    if (
      ok &&
      (await run(
        '2fa',
        () => turnOffTwoFactor(account.username),
        t('Could not turn off two-factor sign-in.'),
      ))
    ) {
      onRefresh();
    }
  }

  return (
    <ScrollView
      style={shared.screen}
      contentContainerStyle={[shared.container, { paddingBottom: theme.spacing.xxl }]}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      keyboardShouldPersistTaps="handled"
    >
      {/* Who */}
      <View style={styles.identity}>
        <Avatar uri={resolveAssetUrl(account.avatar_url)} label={initials(name)} size={64} />
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={shared.title}>{name}</Text>
          <Text style={shared.muted}>
            @{account.username}
            {account.email ? ` · ${account.email}` : ''}
          </Text>
          <View style={shared.row}>
            {isMe ? <Pill label={t('You')} tone="primary" /> : null}
            <Pill label={configured ? t('Configured account') : t('Registered account')} />
          </View>
        </View>
      </View>
      <Button
        variant="link"
        label={t('View profile')}
        onPress={() =>
          router.push({ pathname: '/user/[userId]', params: { userId: account.username } })
        }
      />

      {/* Role */}
      <Card>
        <Text style={shared.title} accessibilityRole="header">
          {t('Role')}
        </Text>
        <View style={shared.row}>
          {(['viewer', 'admin'] as const).map((role) => (
            <Chip
              key={role}
              label={role === ROLE_ADMIN ? t('Admin') : t('Viewer')}
              selected={account.role === role}
              onPress={() => {
                if (!configured && !busy && !(isMe && role !== ROLE_ADMIN)) void changeRole(role);
              }}
              styles={shared}
            />
          ))}
        </View>
        <Text style={shared.muted}>
          {configured
            ? t('This role is managed in the server configuration.')
            : isMe
              ? t('You cannot remove your own administrator access.')
              : t('Administrators can manage users, moderation and feedback.')}
        </Text>
      </Card>

      {/* Permissions */}
      <Card>
        <Text style={shared.title} accessibilityRole="header">
          {t('Permissions')}
        </Text>
        {isAdminAccount ? (
          <Text style={shared.muted}>{t('Administrators can already do everything below.')}</Text>
        ) : null}
        {permissions.map((permission, index) => (
          <View key={permission.key} style={[styles.permission, index > 0 && styles.divider]}>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={shared.body}>{t(permission.label)}</Text>
              <Text style={shared.muted}>{t(permission.description)}</Text>
            </View>
            <Switch
              accessibilityLabel={t(permission.label)}
              value={isAdminAccount || grants.includes(permission.key)}
              disabled={isAdminAccount || busy === 'permissions'}
              onValueChange={() => setGrants((g) => toggle(g, permission.key))}
              trackColor={{ true: theme.colors.primary, false: theme.colors.border }}
              {...(Platform.OS === 'android' ? { thumbColor: theme.colors.surface } : {})}
            />
          </View>
        ))}
        {!isAdminAccount ? (
          <Button
            label={t('Save permissions')}
            onPress={() => void savePermissions()}
            loading={busy === 'permissions'}
            disabled={!grantsChanged || !!busy}
          />
        ) : null}
      </Card>

      {/* Security */}
      <Card>
        <Text style={shared.title} accessibilityRole="header">
          {t('Security')}
        </Text>

        <View style={{ gap: theme.spacing.sm }}>
          <Text style={shared.body}>{t('Password')}</Text>
          {configured ? (
            <Text style={shared.muted}>
              {t(
                'This account is configured in AUTH_USERS; change its password in the server settings.',
              )}
            </Text>
          ) : resetLink ? (
            <View style={{ gap: theme.spacing.xs }}>
              <Text style={shared.muted}>
                {resetLink.emailed
                  ? t('The link was also emailed to them. It expires in {minutes} minutes.', {
                      minutes: Math.round(resetLink.expires_in / 60),
                    })
                  : t('Send them this link. It expires in {minutes} minutes.', {
                      minutes: Math.round(resetLink.expires_in / 60),
                    })}
              </Text>
              <Text style={styles.link} selectable>
                {resetLink.link}
              </Text>
              {Platform.OS !== 'web' ? (
                <View style={shared.row}>
                  <ActionButton
                    label={t('Share link')}
                    tone="primary"
                    onPress={() => void Share.share({ message: resetLink.link })}
                  />
                </View>
              ) : null}
            </View>
          ) : (
            <View style={shared.row}>
              <ActionButton
                label={t('Create password reset link')}
                disabled={!!busy}
                onPress={() => void resetPassword()}
              />
            </View>
          )}
        </View>

        <View style={[{ gap: theme.spacing.sm }, styles.divider]}>
          <Text style={shared.body}>{t('Two-factor sign-in')}</Text>
          {account.two_factor_enabled ? (
            <View style={shared.row}>
              <ActionButton
                label={t('Turn off two-factor sign-in')}
                tone="danger"
                disabled={!!busy}
                onPress={() => void disableTwoFactor()}
              />
            </View>
          ) : (
            <Text style={shared.muted}>{t('Not turned on.')}</Text>
          )}
        </View>
      </Card>
    </ScrollView>
  );
}

function makeScreenStyles({ colors, spacing, typography }: Theme) {
  return StyleSheet.create({
    identity: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    permission: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    divider: {
      paddingTop: spacing.md,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: colors.border,
    },
    link: { ...typography.caption, color: colors.primary },
  });
}

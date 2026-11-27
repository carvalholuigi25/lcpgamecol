import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '@/api';
import { notify } from '@/features/admin/confirm';
import { useRequest } from '@/hooks/useRequest';
import { useTheme, type Theme } from '@/theme';

import { fetchMyGameLists, setFavorite, setWishlisted } from '../lists';
import { errorMessage } from '../services';

type ListKind = 'wishlist' | 'favorite';

/** Wishlist and favorite toggles for one game, saved straight to the user's lists. */
export function GameListActions({ gameId }: { gameId: number }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const styles = makeListStyles(theme);
  const lists = useRequest('game-lists', fetchMyGameLists);
  // What the server answered after a toggle; wins over the initial lists.
  const [state, setState] = useState<{ wishlisted?: boolean; favorite?: boolean }>({});
  const [busy, setBusy] = useState<ListKind | null>(null);

  const wishlisted = state.wishlisted ?? lists.data?.wishlist.includes(gameId) ?? false;
  const favorite = state.favorite ?? lists.data?.favorites.includes(gameId) ?? false;
  const ready = !!lists.data;

  async function toggle(kind: ListKind) {
    setBusy(kind);
    try {
      const next =
        kind === 'wishlist'
          ? await setWishlisted(gameId, !wishlisted)
          : await setFavorite(gameId, !favorite);
      setState({ wishlisted: next.wishlisted, favorite: next.favorite });
    } catch (error) {
      const full = error instanceof ApiError && error.status === 409;
      notify(
        full
          ? t('You can pick up to {count} favorite games.', { count: lists.data?.favorites_max })
          : t(errorMessage(error)),
      );
    } finally {
      setBusy(null);
    }
  }

  if (lists.error && !lists.data) return null; // lists are optional on this screen

  return (
    <View style={styles.row}>
      <Toggle
        icon={wishlisted ? '🔖' : '＋'}
        label={wishlisted ? t('On your wishlist') : t('Add to wishlist')}
        a11yLabel={wishlisted ? t('Remove from wishlist') : t('Add to wishlist')}
        on={wishlisted}
        busy={busy === 'wishlist'}
        disabled={!ready || busy !== null}
        onPress={() => void toggle('wishlist')}
        styles={styles}
        theme={theme}
      />
      <Toggle
        icon={favorite ? '♥' : '♡'}
        label={favorite ? t('In your favorites') : t('Add to favorites')}
        a11yLabel={favorite ? t('Remove from favorites') : t('Add to favorites')}
        on={favorite}
        busy={busy === 'favorite'}
        disabled={!ready || busy !== null}
        onPress={() => void toggle('favorite')}
        styles={styles}
        theme={theme}
      />
    </View>
  );
}

function Toggle({
  icon,
  label,
  a11yLabel,
  on,
  busy,
  disabled,
  onPress,
  styles,
  theme,
}: {
  icon: string;
  label: string;
  a11yLabel: string;
  on: boolean;
  busy: boolean;
  disabled: boolean;
  onPress: () => void;
  styles: ReturnType<typeof makeListStyles>;
  theme: Theme;
}) {
  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityLabel={a11yLabel}
      accessibilityState={{ checked: on, disabled, busy }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.toggle,
        on && styles.toggleOn,
        pressed && styles.pressed,
        disabled && !busy && styles.disabled,
      ]}
    >
      {busy ? (
        <ActivityIndicator
          size="small"
          color={on ? theme.colors.onPrimary : theme.colors.primary}
        />
      ) : (
        <Text style={[styles.icon, on && styles.textOn]}>{icon}</Text>
      )}
      <Text style={[styles.text, on && styles.textOn]} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

function makeListStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    row: { flexDirection: 'row', gap: spacing.sm },
    toggle: {
      flex: 1,
      minHeight: 44,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.xs,
      paddingHorizontal: spacing.md,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.primary,
      backgroundColor: colors.surface,
    },
    toggleOn: { backgroundColor: colors.primary },
    pressed: { opacity: 0.8 },
    disabled: { opacity: 0.5 },
    icon: { ...typography.body, color: colors.primary },
    text: { ...typography.label, fontWeight: '600', color: colors.primary, flexShrink: 1 },
    textOn: { color: colors.onPrimary },
  });
}

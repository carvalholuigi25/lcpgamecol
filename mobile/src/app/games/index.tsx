import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type ListRenderItem,
} from 'react-native';

import { Button, Chip, makeStyles } from '@/components';
import { GAME_SORTS, GameCard, GameListItem, useGamesList, type Game } from '@/features/games';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useTheme, type Theme } from '@/theme';

type Layout = 'grid' | 'list';

const GRID_MIN_CARD = 150;
const MAX_COLUMNS = 6;

const keyExtractor = (game: Game) => String(game.id);
const renderRow: ListRenderItem<Game> = ({ item }) => <GameListItem game={item} />;

/** Vertical space between grid rows (FlatList ignores `rowGap` across its row cells). */
function GridRowSpacer() {
  const { spacing } = useTheme();
  return <View style={{ height: spacing.md }} />;
}

export default function GamesScreen() {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeScreenStyles(theme);
  // Measure the list area itself (not the window): split views, web scrollbars and
  // rotation all change the space actually available to the grid.
  const [width, setWidth] = useState(0);

  const [layout, setLayout] = useState<Layout>('grid');
  const [sortIndex, setSortIndex] = useState(0);
  const [query, setQuery] = useState('');
  const search = useDebouncedValue(query.trim(), 350);
  const { sort, order } = GAME_SORTS[sortIndex] ?? GAME_SORTS[0]!;

  const games = useGamesList({ sort, ...(order ? { order } : {}), search });
  const { items, total, status, error, refreshing, loadingMore, hasMore } = games;
  const { refresh, retry, loadMore } = games;

  // Responsive grid: as many ≥150px columns as fit (2…6). Floor the card width so
  // rounding never pushes the last column past the gutter.
  const gutter = theme.spacing.lg;
  const gap = theme.spacing.md;
  const inner = Math.max(0, width - gutter * 2);
  const columns = Math.min(
    MAX_COLUMNS,
    Math.max(2, Math.floor((inner + gap) / (GRID_MIN_CARD + gap))),
  );
  const cardWidth = Math.floor((inner - gap * (columns - 1)) / columns);

  const renderCard = useCallback<ListRenderItem<Game>>(
    ({ item }) => <GameCard game={item} width={cardWidth} />,
    [cardWidth],
  );

  const countLabel = useMemo(() => {
    if (status !== 'ready') return '';
    if (search) {
      return hasMore
        ? t('Results for “{query}”', { query: search })
        : t('{count} results for “{query}”', { count: items.length, query: search });
    }
    return total !== null ? t('{count} games', { count: total }) : '';
  }, [status, search, hasMore, items.length, total, t]);

  const footer = () => {
    if (loadingMore)
      return <ActivityIndicator style={styles.footer} color={theme.colors.primary} />;
    if (error && hasMore) {
      return (
        <View style={[styles.footer, { alignItems: 'center', gap: theme.spacing.sm }]}>
          <Text style={shared.muted}>{error}</Text>
          <Chip label={t('Try again')} styles={shared} onPress={loadMore} />
        </View>
      );
    }
    return <View style={styles.footer} />;
  };

  let body: React.ReactNode;
  if (status === 'loading') {
    body = (
      <View style={shared.centered}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
      </View>
    );
  } else if (status === 'error') {
    body = (
      <View style={shared.centered}>
        <Text style={shared.title}>{t('Could not load games.')}</Text>
        <Text style={[shared.muted, { textAlign: 'center' }]}>{error}</Text>
        <Button label={t('Try again')} onPress={retry} />
      </View>
    );
  } else {
    const common = {
      data: items,
      keyExtractor,
      onEndReached: loadMore,
      onEndReachedThreshold: 0.6,
      refreshing,
      onRefresh: refresh,
      ListFooterComponent: footer,
      ListEmptyComponent: (
        <View style={[shared.centered, { paddingTop: theme.spacing.xxl * 2 }]}>
          <Text style={shared.title}>
            {search ? t('No games match “{query}”', { query: search }) : t('No games yet')}
          </Text>
          {search ? (
            <Button variant="link" label={t('Clear search')} onPress={() => setQuery('')} />
          ) : null}
        </View>
      ),
      keyboardDismissMode: 'on-drag' as const,
      keyboardShouldPersistTaps: 'handled' as const,
      initialNumToRender: 12,
      windowSize: 11,
    };
    body =
      layout === 'grid' ? (
        width === 0 ? null : (
          <FlatList
            key={`grid-${columns}`}
            {...common}
            numColumns={columns}
            renderItem={renderCard}
            columnWrapperStyle={{ gap }}
            contentContainerStyle={{ paddingHorizontal: gutter, paddingVertical: gap }}
            ItemSeparatorComponent={GridRowSpacer}
          />
        )
      ) : (
        <FlatList
          key="list"
          {...common}
          renderItem={renderRow}
          ItemSeparatorComponent={() => <View style={styles.separator} />}
          removeClippedSubviews
        />
      );
  }

  return (
    <View style={shared.screen}>
      <View style={styles.toolbar}>
        <View style={styles.searchRow}>
          <View style={styles.searchBox}>
            <Text style={styles.searchIcon} accessibilityElementsHidden>
              ⌕
            </Text>
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder={t('Search games')}
              placeholderTextColor={theme.colors.muted}
              accessibilityLabel={t('Search games')}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="search"
              clearButtonMode="while-editing"
              style={styles.searchInput}
              testID="games-search"
            />
          </View>
          <View style={styles.toggle} accessibilityRole="radiogroup">
            {(['grid', 'list'] as const).map((mode) => (
              <Pressable
                key={mode}
                accessibilityRole="radio"
                accessibilityLabel={mode === 'grid' ? t('Grid view') : t('List view')}
                accessibilityState={{ selected: layout === mode }}
                onPress={() => setLayout(mode)}
                style={[styles.toggleItem, layout === mode && styles.toggleItemActive]}
              >
                <Text style={[styles.toggleText, layout === mode && styles.toggleTextActive]}>
                  {mode === 'grid' ? '▦' : '☰'}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>

        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.sorts}
        >
          {GAME_SORTS.map((option, index) => (
            <Chip
              key={option.sort}
              label={t(option.label)}
              selected={index === sortIndex}
              onPress={() => setSortIndex(index)}
              styles={shared}
            />
          ))}
        </ScrollView>
        {countLabel ? <Text style={[shared.muted, styles.count]}>{countLabel}</Text> : null}
      </View>
      <View style={styles.body} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
        {body}
      </View>
    </View>
  );
}

function makeScreenStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    toolbar: {
      gap: spacing.sm,
      paddingTop: spacing.md,
      paddingBottom: spacing.sm,
      backgroundColor: colors.background,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: colors.border,
    },
    searchRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      paddingHorizontal: spacing.lg,
    },
    searchBox: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      paddingHorizontal: spacing.md,
      borderRadius: radius.pill,
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.border,
    },
    searchIcon: { ...typography.body, color: colors.muted },
    searchInput: { ...typography.body, flex: 1, color: colors.text, paddingVertical: spacing.sm },
    toggle: {
      flexDirection: 'row',
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
      overflow: 'hidden',
    },
    toggleItem: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
    toggleItemActive: { backgroundColor: colors.primary },
    toggleText: { ...typography.body, color: colors.text },
    toggleTextActive: { color: colors.onPrimary },
    sorts: { gap: spacing.sm, paddingHorizontal: spacing.lg },
    count: { paddingHorizontal: spacing.lg },
    separator: {
      height: StyleSheet.hairlineWidth,
      backgroundColor: colors.border,
      marginLeft: spacing.lg + 56 + spacing.md,
    },
    footer: { paddingVertical: spacing.xl },
    body: { flex: 1 },
  });
}

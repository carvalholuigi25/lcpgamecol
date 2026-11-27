import { Image } from 'expo-image';
import * as Linking from 'expo-linking';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { makeStyles } from '@/components';
import { useTheme, type Theme } from '@/theme';

import { galleryImages, gameTrailers, type Trailer } from '../media';
import type { Game } from '../services';

const THUMB_WIDTH = 220;
const THUMB_HEIGHT = Math.round((THUMB_WIDTH * 9) / 16);

/** Horizontal strips of screenshots (tap for a full-screen viewer) and trailers. */
export function GameMediaGallery({ game }: { game: Game }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const shared = makeStyles(theme);
  const styles = makeGalleryStyles(theme);
  const images = galleryImages(game);
  const trailers = gameTrailers(game);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);

  if (images.length === 0 && trailers.length === 0) return null;

  return (
    <>
      {images.length > 0 ? (
        <>
          <Text style={shared.label}>{t('Screenshots')}</Text>
          <FlatList
            horizontal
            data={images}
            keyExtractor={(url) => url}
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.strip}
            renderItem={({ item, index }) => (
              <Pressable
                accessibilityRole="imagebutton"
                accessibilityLabel={`${t('Screenshots')} ${index + 1} / ${images.length}`}
                onPress={() => setViewerIndex(index)}
                style={({ pressed }) => pressed && styles.pressed}
              >
                <Image source={item} style={styles.thumb} contentFit="cover" transition={150} />
              </Pressable>
            )}
          />
        </>
      ) : null}

      {trailers.length > 0 ? (
        <>
          <Text style={shared.label}>{t('Trailers')}</Text>
          <FlatList
            horizontal
            data={trailers}
            keyExtractor={(trailer) => trailer.url}
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.strip}
            renderItem={({ item, index }) => (
              <TrailerThumb trailer={item} label={`${t('Trailer')} ${index + 1}`} styles={styles} />
            )}
          />
        </>
      ) : null}

      <ImageViewer images={images} index={viewerIndex} onClose={() => setViewerIndex(null)} />
    </>
  );
}

function TrailerThumb({
  trailer,
  label,
  styles,
}: {
  trailer: Trailer;
  label: string;
  styles: ReturnType<typeof makeGalleryStyles>;
}) {
  // Trailers open in the YouTube app or the browser: inline YouTube playback needs a
  // WebView, which is a native module that Expo Go doesn't bundle.
  return (
    <Pressable
      accessibilityRole="link"
      accessibilityLabel={label}
      onPress={() => void Linking.openURL(trailer.url)}
      style={({ pressed }) => pressed && styles.pressed}
    >
      <View style={styles.thumb}>
        {trailer.thumbnail ? (
          <Image source={trailer.thumbnail} style={StyleSheet.absoluteFill} contentFit="cover" />
        ) : null}
        <View style={styles.playOverlay}>
          <View style={styles.playButton}>
            <Text style={styles.playIcon}>▶</Text>
          </View>
        </View>
      </View>
    </Pressable>
  );
}

/** Full-screen, swipeable screenshot viewer. `index` null keeps it closed. */
function ImageViewer({
  images,
  index,
  onClose,
}: {
  images: string[];
  index: number | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const theme = useTheme();
  const styles = makeGalleryStyles(theme);
  const insets = useSafeAreaInsets();
  const { width, height } = useWindowDimensions();
  const [current, setCurrent] = useState(0);
  const [openedAt, setOpenedAt] = useState<number | null>(null);

  // Reset the counter whenever the viewer opens on a new image (derived, no effect needed).
  if (index !== openedAt) {
    setOpenedAt(index);
    if (index !== null) setCurrent(index);
  }

  const onScrollEnd = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    setCurrent(Math.round(event.nativeEvent.contentOffset.x / width));
  };

  return (
    <Modal
      visible={index !== null}
      animationType="fade"
      onRequestClose={onClose}
      supportedOrientations={['portrait', 'landscape']}
    >
      <View style={styles.viewer}>
        {index !== null ? (
          <FlatList
            key={width} // re-layout pages after a rotation
            horizontal
            pagingEnabled
            data={images}
            keyExtractor={(url) => url}
            initialScrollIndex={current}
            getItemLayout={(_, i) => ({ length: width, offset: width * i, index: i })}
            onMomentumScrollEnd={onScrollEnd}
            showsHorizontalScrollIndicator={false}
            renderItem={({ item }) => (
              <Image source={item} style={{ width, height }} contentFit="contain" />
            )}
          />
        ) : null}
        <View style={[styles.viewerBar, { top: insets.top + 8 }]} pointerEvents="box-none">
          <Text style={styles.viewerCounter}>
            {current + 1} / {images.length}
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t('Close')}
            onPress={onClose}
            hitSlop={12}
            style={styles.viewerClose}
          >
            <Text style={styles.viewerCloseText}>✕</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

function makeGalleryStyles({ colors, spacing, radius, typography }: Theme) {
  return StyleSheet.create({
    strip: { gap: spacing.sm },
    thumb: {
      width: THUMB_WIDTH,
      height: THUMB_HEIGHT,
      borderRadius: radius.md,
      overflow: 'hidden',
      backgroundColor: colors.surface,
    },
    pressed: { opacity: 0.8 },
    playOverlay: {
      position: 'absolute',
      inset: 0,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: 'rgba(0,0,0,0.25)',
    },
    playButton: {
      width: 48,
      height: 48,
      borderRadius: 24,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: 'rgba(0,0,0,0.6)',
    },
    playIcon: { color: '#fff', fontSize: 20, marginLeft: 3 },
    viewer: { flex: 1, backgroundColor: '#000' },
    viewerBar: {
      position: 'absolute',
      left: spacing.lg,
      right: spacing.lg,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    viewerCounter: { ...typography.label, color: '#fff' },
    viewerClose: {
      width: 40,
      height: 40,
      borderRadius: 20,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: 'rgba(255,255,255,0.15)',
    },
    viewerCloseText: { color: '#fff', fontSize: 18 },
  });
}

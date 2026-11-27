import { resolveAssetUrl } from '@/api';

import type { Game } from './services';

export type Trailer = {
  /** The link to open (YouTube watch page or any other video URL). */
  url: string;
  /** Preview image, when the video is on YouTube. */
  thumbnail: string | null;
};

/**
 * Screenshots for the gallery: the `screenshots` list, falling back to the single
 * `screenshot_url`. Resolved against the asset base URL, without duplicates.
 */
export function galleryImages(game: Pick<Game, 'screenshots' | 'screenshot_url'>): string[] {
  const sources = game.screenshots?.length ? game.screenshots : [game.screenshot_url];
  const urls = sources.map((value) => resolveAssetUrl(value)).filter((url): url is string => !!url);
  return [...new Set(urls)];
}

/** Trailers for the gallery: the `trailers` list, falling back to the single `trailer_url`. */
export function gameTrailers(game: Pick<Game, 'trailers' | 'trailer_url'>): Trailer[] {
  const sources = game.trailers?.length ? game.trailers : [game.trailer_url];
  const urls = [...new Set(sources.map((value) => value?.trim()).filter((url) => !!url))];
  return urls.map((url) => {
    const id = youtubeId(url!);
    return {
      url: url!,
      thumbnail: id ? `https://img.youtube.com/vi/${id}/hqdefault.jpg` : null,
    };
  });
}

/** The video id of a youtube.com/watch, youtu.be, /embed/ or /shorts/ link; null otherwise. */
export function youtubeId(url: string): string | null {
  const match =
    /(?:youtube(?:-nocookie)?\.com\/(?:watch\?(?:.*&)?v=|embed\/|shorts\/|v\/)|youtu\.be\/)([\w-]{11})/i.exec(
      url,
    );
  return match?.[1] ?? null;
}

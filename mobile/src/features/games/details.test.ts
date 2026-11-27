import { api } from '@/api';

import { setFavorite, setWishlisted } from './lists';
import { galleryImages, gameTrailers, youtubeId } from './media';
import {
  htmlToText,
  reportReview,
  saveMyReview,
  textToHtml,
  toggleReviewReaction,
} from './reviews';

describe('youtubeId', () => {
  it('reads watch, short, embed and shorts links', () => {
    expect(youtubeId('https://www.youtube.com/watch?v=PIF_fqFZEuk')).toBe('PIF_fqFZEuk');
    expect(youtubeId('https://www.youtube.com/watch?feature=x&v=PIF_fqFZEuk')).toBe('PIF_fqFZEuk');
    expect(youtubeId('https://youtu.be/PIF_fqFZEuk?t=3')).toBe('PIF_fqFZEuk');
    expect(youtubeId('https://www.youtube.com/embed/PIF_fqFZEuk')).toBe('PIF_fqFZEuk');
    expect(youtubeId('https://www.youtube.com/shorts/PIF_fqFZEuk')).toBe('PIF_fqFZEuk');
    expect(youtubeId('https://vimeo.com/123')).toBeNull();
  });
});

describe('galleryImages / gameTrailers', () => {
  it('prefers the lists, falls back to the single fields, and drops blanks and duplicates', () => {
    expect(
      galleryImages({
        screenshots: ['https://a/1.jpg', 'https://a/1.jpg', ''],
        screenshot_url: 'x',
      }),
    ).toEqual(['https://a/1.jpg']);
    expect(galleryImages({ screenshots: [], screenshot_url: 'https://a/2.jpg' })).toEqual([
      'https://a/2.jpg',
    ]);
    expect(galleryImages({ screenshots: [], screenshot_url: '' })).toEqual([]);

    expect(gameTrailers({ trailers: [], trailer_url: 'https://youtu.be/PIF_fqFZEuk' })).toEqual([
      {
        url: 'https://youtu.be/PIF_fqFZEuk',
        thumbnail: 'https://img.youtube.com/vi/PIF_fqFZEuk/hqdefault.jpg',
      },
    ]);
    expect(gameTrailers({ trailers: ['https://example.com/t.mp4'], trailer_url: '' })).toEqual([
      { url: 'https://example.com/t.mp4', thumbnail: null },
    ]);
  });
});

describe('review text', () => {
  it('turns editor HTML into plain text with line breaks', () => {
    expect(htmlToText('<p>Great <strong>game</strong> &amp; fun</p><p>Line&nbsp;2</p>')).toBe(
      'Great game & fun\nLine 2',
    );
    expect(htmlToText('<ul><li data-list="bullet">a</li><li>b</li></ul>')).toBe('• a\n• b');
    expect(htmlToText('plain <3 text')).toBe('plain <3 text');
    expect(htmlToText(null)).toBe('');
  });

  it('escapes plain text into paragraphs and round-trips', () => {
    expect(textToHtml('  ')).toBe('');
    expect(textToHtml('I <3 it\n\nA & B')).toBe('<p>I &lt;3 it</p><p><br></p><p>A &amp; B</p>');
    expect(htmlToText(textToHtml('I <3 it\nA & B'))).toBe('I <3 it\nA & B');
  });
});

describe('requests', () => {
  const put = jest.spyOn(api, 'put').mockResolvedValue({});
  const post = jest.spyOn(api, 'post').mockResolvedValue({});
  const del = jest.spyOn(api, 'delete').mockResolvedValue({});
  beforeEach(() => {
    put.mockClear();
    post.mockClear();
    del.mockClear();
  });

  it('adds with PUT and removes with DELETE', async () => {
    await setWishlisted(7, true);
    await setFavorite(7, false);
    expect(put).toHaveBeenCalledWith('/games/7/wishlist');
    expect(del).toHaveBeenCalledWith('/games/7/favorite');
  });

  it('saves a review with HTML body, or null when empty', async () => {
    await saveMyReview(7, 4, 'Nice');
    await saveMyReview(7, 5, '   ');
    expect(put).toHaveBeenNthCalledWith(1, '/games/7/reviews/mine', {
      rating: 4,
      body: '<p>Nice</p>',
    });
    expect(put).toHaveBeenNthCalledWith(2, '/games/7/reviews/mine', { rating: 5, body: null });
  });

  it('toggles a reaction and reports a review with optional details', async () => {
    await toggleReviewReaction(7, 3, '👍');
    await reportReview(7, 3, 'spoilers', '  ');
    await reportReview(7, 3, 'other', ' Off-topic ad ');
    expect(post).toHaveBeenNthCalledWith(1, '/games/7/reviews/3/reactions', { emoji: '👍' });
    expect(post).toHaveBeenNthCalledWith(2, '/games/7/reviews/3/report', {
      reason: 'spoilers',
      details: null,
    });
    expect(post).toHaveBeenNthCalledWith(3, '/games/7/reviews/3/report', {
      reason: 'other',
      details: 'Off-topic ad',
    });
  });
});

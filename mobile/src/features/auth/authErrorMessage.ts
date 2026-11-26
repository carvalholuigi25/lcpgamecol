import type { TFunction } from 'i18next';

import { ApiError, NetworkError } from '@/api';

/** Turn a failed sign-in request into a message for the form. */
export function authErrorMessage(error: unknown, t: TFunction): string {
  if (error instanceof NetworkError) return t('Could not reach the server.');
  if (error instanceof ApiError) {
    if (error.isRateLimited) {
      return error.retryAfter
        ? t('Too many attempts. Try again in {seconds} seconds.', { seconds: error.retryAfter })
        : t('Too many attempts. Try again later.');
    }
    if (error.isUnauthorized) return t('Incorrect username or password.');
    if (error.isValidation) return t('Check the fields and try again.');
    return error.detail;
  }
  return t('Something went wrong. Try again.');
}

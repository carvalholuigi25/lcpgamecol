/** One entry of a FastAPI 422 response ("detail": [{loc, msg, type}, ...]). */
export type ValidationIssue = {
  loc: (string | number)[];
  msg: string;
  type: string;
};

/** The server answered with a non-2xx status. */
export class ApiError extends Error {
  override readonly name = 'ApiError';
  readonly status: number;
  /** FastAPI's `detail` when it is a string, otherwise a generic message. */
  readonly detail: string;
  /** Field errors from a 422 response. */
  readonly issues: ValidationIssue[];
  /** Seconds from a Retry-After header (429 lockouts and rate limits). */
  readonly retryAfter: number | null;
  readonly body: unknown;

  constructor(status: number, body: unknown, retryAfter: number | null = null) {
    const detail = extractDetail(status, body);
    super(detail);
    this.status = status;
    this.detail = detail;
    this.issues = extractIssues(body);
    this.retryAfter = retryAfter;
    this.body = body;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isValidation(): boolean {
    return this.status === 422;
  }

  get isRateLimited(): boolean {
    return this.status === 429;
  }
}

/** The request never got a response (offline, DNS, TLS, CORS, timeout). */
export class NetworkError extends Error {
  override readonly name = 'NetworkError';
  override readonly cause: unknown;

  constructor(cause: unknown) {
    super('The server could not be reached.');
    this.cause = cause;
  }
}

/** The refresh token was missing, expired, reused or revoked: the user must sign in again. */
export class SessionExpiredError extends Error {
  override readonly name = 'SessionExpiredError';

  constructor() {
    super('Your session has expired. Please sign in again.');
  }
}

function extractDetail(status: number, body: unknown): string {
  if (isRecord(body)) {
    if (typeof body.detail === 'string') return body.detail;
    const [first] = extractIssues(body);
    if (first) return first.msg;
  }
  if (typeof body === 'string' && body.trim()) return body.trim();
  return `Request failed with status ${status}`;
}

function extractIssues(body: unknown): ValidationIssue[] {
  if (!isRecord(body) || !Array.isArray(body.detail)) return [];
  return body.detail.filter(
    (item): item is ValidationIssue =>
      isRecord(item) && typeof item.msg === 'string' && Array.isArray(item.loc),
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export type TokenPair = {
  accessToken: string;
  refreshToken: string;
};

/** Where the client keeps its tokens; one implementation per platform. */
export type TokenStore = {
  /** True on the web build: auth rides on HttpOnly cookies, not on headers. */
  readonly usesCookies: boolean;
  getAccessToken(): Promise<string | null>;
  getRefreshToken(): Promise<string | null>;
  setTokens(tokens: TokenPair): Promise<void>;
  clear(): Promise<void>;
};

/** In-memory store for tests. */
export function createMemoryTokenStore(initial?: Partial<TokenPair>): TokenStore {
  let access = initial?.accessToken ?? null;
  let refresh = initial?.refreshToken ?? null;
  return {
    usesCookies: false,
    getAccessToken: async () => access,
    getRefreshToken: async () => refresh,
    setTokens: async (tokens) => {
      access = tokens.accessToken;
      refresh = tokens.refreshToken;
    },
    clear: async () => {
      access = null;
      refresh = null;
    },
  };
}

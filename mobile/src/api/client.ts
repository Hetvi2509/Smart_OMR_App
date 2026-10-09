/**
 * The app's only route to the database.
 *
 * Nothing here knows a Postgres connection string: every call goes to the
 * backend API, which holds the Neon credentials in its own environment.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';

export const DEFAULT_PORT = 8000;
const BASE_URL_KEY = 'omr.baseUrl';
const TOKEN_KEY = 'omr.token';

/**
 * Guess the API host from the Expo dev server, or use a fixed production URL.
 *
 * Two situations, two different right answers:
 *
 * - A deployed backend (Render, etc.) has one fixed https:// address that is
 *   the same for every phone that installs the app. That address is read
 *   from app.json's `extra.apiUrl`, set at build time -- see api/DEPLOY.md.
 *
 * - Local development has no fixed address: the API runs on whichever LAN IP
 *   the developer's machine happens to have that day. In Expo Go the app
 *   bundle is served from that same machine, so its host is read off the dev
 *   server's own URL instead of being typed in anywhere. `localhost` would
 *   resolve to the phone itself, so it is only ever right on web.
 *
 * `extra.apiUrl` takes priority when set, so a production build never
 * depends on LAN auto-detection succeeding.
 */
export function guessBaseUrl(): string {
  const configured = (Constants.expoConfig?.extra as { apiUrl?: string } | undefined)?.apiUrl;
  if (configured) return configured.replace(/\/+$/, '');

  // Expo has moved this field between releases, so several shapes are read
  // rather than relying on whichever one the current SDK exposes.
  const loose = Constants as unknown as {
    expoConfig?: { hostUri?: string };
    expoGoConfig?: { debuggerHost?: string };
    manifest2?: { extra?: { expoGo?: { debuggerHost?: string } } };
  };
  const candidates = [
    loose.expoConfig?.hostUri,
    loose.expoGoConfig?.debuggerHost,
    loose.manifest2?.extra?.expoGo?.debuggerHost,
  ].filter(Boolean) as string[];

  for (const entry of candidates) {
    const host = entry.split('/')[0].split(':')[0];
    if (host && host !== 'localhost' && host !== '127.0.0.1') {
      return `http://${host}:${DEFAULT_PORT}`;
    }
  }
  return `http://localhost:${DEFAULT_PORT}`;
}

let baseUrl: string | null = null;
let token: string | null = null;

export async function loadSession(): Promise<{ baseUrl: string; token: string | null }> {
  const [savedUrl, savedToken] = await Promise.all([
    AsyncStorage.getItem(BASE_URL_KEY),
    AsyncStorage.getItem(TOKEN_KEY),
  ]);
  baseUrl = savedUrl || guessBaseUrl();
  token = savedToken;
  return { baseUrl, token };
}

export function getBaseUrl(): string {
  return baseUrl || guessBaseUrl();
}

export async function setBaseUrl(url: string): Promise<void> {
  // Tolerate "192.168.1.5", "192.168.1.5:8000" and a full URL: a user typing
  // an address into Settings should not have to remember the scheme.
  let clean = url.trim().replace(/\/+$/, '');
  if (clean && !/^https?:\/\//i.test(clean)) clean = `http://${clean}`;
  if (clean && !/:\d+$/.test(clean) && !/^https:/i.test(clean)) {
    clean = `${clean}:${DEFAULT_PORT}`;
  }
  baseUrl = clean;
  await AsyncStorage.setItem(BASE_URL_KEY, clean);
}

export async function setToken(value: string | null): Promise<void> {
  token = value;
  if (value) await AsyncStorage.setItem(TOKEN_KEY, value);
  else await AsyncStorage.removeItem(TOKEN_KEY);
}

export function getToken(): string | null {
  return token;
}

/** An API error carrying the status, so callers can branch on 401 vs 422. */
export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

/** Pull a human sentence out of FastAPI's several error shapes. */
function messageFrom(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string; loc?: string[] } | undefined;
    if (first?.msg) {
      const field = first.loc?.filter((l) => l !== 'body').join('.');
      return field ? `${field}: ${first.msg}` : first.msg;
    }
  }
  if (detail && typeof detail === 'object') {
    const d = detail as { message?: string; msg?: string };
    if (d.message) return d.message;
    if (d.msg) return d.msg;
  }
  return fallback;
}

type Options = {
  method?: string;
  body?: unknown;
  // Multipart bodies are passed through untouched so the boundary is correct.
  form?: FormData;
  timeoutMs?: number;
};

export async function request<T>(path: string, opts: Options = {}): Promise<T> {
  const { method = 'GET', body, form, timeoutMs } = opts;
  const url = `${getBaseUrl()}${path}`;

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  // A scan uploads a photo and runs the vision pipeline plus OCR, so it needs
  // far longer than a normal read. Without a cap a dead host hangs forever.
  const limit = timeoutMs ?? (form ? 120_000 : 20_000);

  // React Native's networking layer does not handle an AbortSignal on a
  // multipart body: attaching one makes the upload fail immediately, before
  // any bytes leave the device, so the server never sees the request at all.
  // An upload therefore races a timer instead of being aborted. That leaks
  // the underlying request on timeout, which is the lesser problem -- the
  // alternative is that the photo is never sent.
  const controller = form ? null : new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;

  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      controller?.abort();
      reject(Object.assign(new Error('timeout'), { name: 'AbortError' }));
    }, limit);
  });

  let response: Response;
  try {
    response = await Promise.race([
      fetch(url, {
        method,
        headers,
        body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
        ...(controller ? { signal: controller.signal } : {}),
      }),
      timeout,
    ]);
  } catch (err) {
    clearTimeout(timer);
    if ((err as Error).name === 'AbortError') {
      throw new ApiError(
        `The server took too long to respond (over ${Math.round(limit / 1000)}s).`,
        0,
      );
    }
    // A failed multipart POST is not necessarily a network problem: the same
    // app has usually just loaded the dashboard from this address. Report the
    // underlying error verbatim rather than guessing at a cause -- a wrong
    // guess ("weak Wi-Fi") sends people to fix something that is not broken.
    if (form) {
      const detail = (err as Error)?.message || String(err);
      throw new ApiError(`Upload failed: ${detail}`, 0);
    }
    // Almost always a wrong API address or a backend that is not running --
    // the single most common setup problem, so the message says what to do.
    throw new ApiError(
      `Cannot reach the server at ${getBaseUrl()}. Check that the backend is ` +
        `running and that the API address in Settings is correct.`,
      0,
    );
  }
  clearTimeout(timer);

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }

  if (!response.ok) {
    const detail = (parsed as { detail?: unknown })?.detail ?? parsed;
    throw new ApiError(
      messageFrom(detail, `Request failed (${response.status}).`),
      response.status,
      detail,
    );
  }
  return parsed as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'POST', form }),
};

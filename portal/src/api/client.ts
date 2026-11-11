import { UserSession } from '../types';

const SESSION_KEY = 'rempart_session';

/**
 * Local-demo identity overrides. `npm run dev:local` (see package.json) sets
 * VITE_DEMO_ROLE / VITE_DEMO_TENANT so the portal starts already pointing at a
 * persona that can read the frozen dataset served by `scripts/serve_local.py`.
 * When they are unset the portal keeps its historical judge default.
 */
const DEMO_ROLE = import.meta.env.VITE_DEMO_ROLE as string | undefined;
const DEMO_TENANT = import.meta.env.VITE_DEMO_TENANT as string | undefined;

const DEFAULT_SESSION: UserSession = {
  role: (DEMO_ROLE as UserSession['role']) ?? 'demo',
  tenant_id: DEMO_TENANT ?? 'demo-tenant-shoplite',
  username: 'judge-demo'
};

export function getSession(): UserSession {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    // ignore parse errors
  }
  return DEFAULT_SESSION;
}

export function saveSession(session: UserSession): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY);
}

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

const ERROR_BANNER_ID = 'rempart-api-error';

/**
 * Surface a failed call instead of hiding it behind fake data.
 *
 * The portal has no global error boundary for data fetches, so the API layer
 * renders a dismissible banner: a judge sees the real failure (and the real
 * status code) rather than a page that silently shows invented rows.
 */
export function showApiError(message: string): void {
  if (typeof document === 'undefined') return;
  let banner = document.getElementById(ERROR_BANNER_ID);
  if (!banner) {
    banner = document.createElement('div');
    banner.id = ERROR_BANNER_ID;
    banner.setAttribute('data-testid', 'api-error-banner');
    banner.setAttribute('role', 'alert');
    banner.style.cssText =
      'position:fixed;top:0;left:0;right:0;z-index:1000;padding:10px 16px;' +
      'background:#7f1d1d;color:#fff;font:14px/1.4 system-ui,sans-serif;' +
      'display:flex;gap:12px;align-items:center;justify-content:center';
    document.body.appendChild(banner);
  }
  const text = document.createElement('span');
  text.textContent = `API error — ${message}`;
  const close = document.createElement('button');
  close.textContent = 'Dismiss';
  close.setAttribute('aria-label', 'Dismiss API error');
  close.style.cssText = 'background:transparent;border:1px solid #fff;color:#fff;cursor:pointer';
  close.onclick = () => banner?.remove();
  banner.replaceChildren(text, close);
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined>;
}

function buildUrl(endpoint: string, params?: RequestOptions['params']): string {
  const baseUrl = import.meta.env.VITE_API_URL || '';
  let url = `${baseUrl}${endpoint}`;
  if (!params) return url;
  const search = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined) search.append(k, String(v));
  });
  const qs = search.toString();
  if (qs) url += (url.includes('?') ? '&' : '?') + qs;
  return url;
}

function buildHeaders(session: UserSession): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json'
  };
  if (session.token) {
    headers.Authorization = `Bearer ${session.token}`;
    return headers;
  }
  // No raw JWT: the portal declares its persona through headers. This is a
  // development/demo shim only — the hosted API authenticates with Cognito.
  if (session.role) headers['X-Rempart-Role'] = session.role;
  if (session.tenant_id) headers['X-Rempart-Tenant'] = session.tenant_id;
  headers['X-Demo-Role'] = session.role ?? DEFAULT_SESSION.role;
  if (session.tenant_id) headers['X-Demo-Tenant'] = session.tenant_id;
  return headers;
}

async function parseError(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return await res.text();
  }
}

export async function apiRequest<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const url = buildUrl(endpoint, options.params);
  let res: Response;
  try {
    res = await fetch(url, {
      method: options.method || 'GET',
      headers: buildHeaders(getSession()),
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined
    });
  } catch (cause) {
    // Unreachable backend: say so loudly instead of inventing rows.
    const detail = cause instanceof Error ? cause.message : String(cause);
    const message = `${endpoint}: API unreachable (${detail}). Is scripts/serve_local.py running?`;
    showApiError(message);
    throw new ApiError(0, message, cause);
  }

  if (!res.ok) {
    const errBody = await parseError(res);
    const detail =
      typeof errBody === 'object' && errBody && 'error' in errBody
        ? String((errBody as { error: unknown }).error)
        : `HTTP ${res.status}`;
    const error = new ApiError(res.status, `${endpoint}: ${detail}`, errBody);
    showApiError(`${error.status} on ${endpoint} — ${detail}`);
    throw error;
  }

  return (await res.json()) as T;
}

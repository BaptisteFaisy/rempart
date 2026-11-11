import { UserSession } from '../types';

const SESSION_KEY = 'rempart_session';

export function getSession(): UserSession {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    // ignore parse errors
  }
  return { role: 'demo', tenant_id: 'demo-tenant-shoplite', username: 'judge-demo' };
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

interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined>;
}

export async function apiRequest<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const baseUrl = import.meta.env.VITE_API_URL || '';
  const session = getSession();

  let url = `${baseUrl}${endpoint}`;
  if (options.params) {
    const search = new URLSearchParams();
    Object.entries(options.params).forEach(([k, v]) => {
      if (v !== undefined) search.append(k, String(v));
    });
    const qs = search.toString();
    if (qs) url += (url.includes('?') ? '&' : '?') + qs;
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json'
  };

  if (session.token) {
    headers.Authorization = `Bearer ${session.token}`;
  } else if (session.role) {
    // Development/demo fallback header passed to API when no raw JWT exists
    headers['X-Rempart-Role'] = session.role;
    if (session.tenant_id) headers['X-Rempart-Tenant'] = session.tenant_id;
  }

  const res = await fetch(url, {
    method: options.method || 'GET',
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined
  });

  if (!res.ok) {
    let errBody: unknown;
    try {
      errBody = await res.json();
    } catch {
      errBody = await res.text();
    }
    throw new ApiError(res.status, `HTTP ${res.status} on ${endpoint}`, errBody);
  }

  return (await res.json()) as T;
}

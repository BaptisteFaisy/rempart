import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiRequest, getSession, saveSession, clearSession, ApiError } from '../api/client';

interface FetchCall {
  url: string;
  init: RequestInit;
}

function mockFetch(response: { ok: boolean; status: number; body: unknown }) {
  const calls: FetchCall[] = [];
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, init });
    return {
      ok: response.ok,
      status: response.status,
      json: async () => response.body,
      text: async () => JSON.stringify(response.body)
    } as unknown as Response;
  });
  vi.stubGlobal('fetch', fn);
  return { fn, calls };
}

describe('session helpers', () => {
  beforeEach(() => localStorage.clear());

  it('returns default demo session when localStorage is empty', () => {
    const s = getSession();
    expect(s.role).toBe('demo');
    expect(s.tenant_id).toBe('demo-tenant-shoplite');
  });

  it('round-trips session through localStorage', () => {
    saveSession({ role: 'analyst', tenant_id: 'tenant-acme', token: 'jwt-123' });
    const s = getSession();
    expect(s.role).toBe('analyst');
    expect(s.tenant_id).toBe('tenant-acme');
    expect(s.token).toBe('jwt-123');
  });

  it('clears session back to demo default', () => {
    saveSession({ role: 'platform_admin' });
    clearSession();
    expect(getSession().role).toBe('demo');
  });
});

describe('apiRequest', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it('calls the right URL with GET by default', async () => {
    const { calls } = mockFetch({ ok: true, status: 200, body: { tenants: [] } });
    const res = await apiRequest<{ tenants: unknown[] }>('/v1/tenants');
    expect(res).toEqual({ tenants: [] });
    expect(calls[0].url).toBe('/v1/tenants');
    expect(calls[0].init.method).toBe('GET');
  });

  it('adds Authorization Bearer header from stored token', async () => {
    saveSession({ role: 'analyst', token: 'jwt-abc' });
    const { calls } = mockFetch({ ok: true, status: 200, body: {} });
    await apiRequest('/v1/findings');
    const headers = calls[0].init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer jwt-abc');
  });

  it('falls back to demo headers when no token is set', async () => {
    saveSession({ role: 'client_security', tenant_id: 'tenant-acme' });
    const { calls } = mockFetch({ ok: true, status: 200, body: {} });
    await apiRequest('/v1/findings');
    const headers = calls[0].init.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
    expect(headers['X-Rempart-Role']).toBe('client_security');
    expect(headers['X-Rempart-Tenant']).toBe('tenant-acme');
  });

  it('serializes query params, skipping undefined values', async () => {
    const { calls } = mockFetch({ ok: true, status: 200, body: { findings: [] } });
    await apiRequest('/v1/findings', {
      params: { status: 'pending_validation', tenant_id: 'demo', priority: undefined }
    });
    expect(calls[0].url).toContain('status=pending_validation');
    expect(calls[0].url).toContain('tenant_id=demo');
    expect(calls[0].url).not.toContain('priority');
  });

  it('sends POST with JSON body', async () => {
    const { calls } = mockFetch({ ok: true, status: 200, body: { decision_id: 'd1' } });
    await apiRequest('/v1/findings/f1/decision', {
      method: 'POST',
      body: { action: 'confirmed', justification: 'verified IDOR' }
    });
    expect(calls[0].init.method).toBe('POST');
    expect(JSON.parse(calls[0].init.body as string)).toEqual({
      action: 'confirmed',
      justification: 'verified IDOR'
    });
  });

  it('throws ApiError with status on non-OK responses', async () => {
    mockFetch({ ok: false, status: 403, body: { error: 'forbidden' } });
    await expect(apiRequest('/v1/tenants/other')).rejects.toMatchObject({
      name: 'ApiError',
      status: 403
    });
    try {
      await apiRequest('/v1/tenants/other');
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
    }
  });
});

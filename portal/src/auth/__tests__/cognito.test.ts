import { describe, expect, it } from 'vitest';
import {
  ROLES,
  cognitoConfig,
  decodeTokenPayload,
  hasAuthorizationCode,
  isCognitoEnabled,
  roleFromGroups,
  sessionFromIdToken
} from '../cognito';

/** Build an unsigned JWT: the browser only reads claims, the API verifies. */
function fakeIdToken(payload: Record<string, unknown>): string {
  const encode = (value: unknown) =>
    btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return `${encode({ alg: 'RS256', typ: 'JWT' })}.${encode(payload)}.signature`;
}

describe('roleFromGroups', () => {
  it('picks the first group that maps to a known Rempart role', () => {
    expect(roleFromGroups(['analyst', 'client_dev'])).toBe('analyst');
  });

  it('skips unknown groups and keeps looking', () => {
    expect(roleFromGroups(['some-other-group', 'client_security'])).toBe('client_security');
  });

  it('returns null when nothing matches or the claim is absent', () => {
    expect(roleFromGroups(['unknown'])).toBeNull();
    expect(roleFromGroups(undefined)).toBeNull();
    expect(roleFromGroups('analyst')).toBeNull();
  });

  it('accepts every role the backend resolve_principal knows', () => {
    expect(ROLES).toContain('platform_admin');
    expect(ROLES).toContain('demo');
    expect(ROLES).toHaveLength(7);
  });
});

describe('decodeTokenPayload', () => {
  it('reads the claims of a well-formed token', () => {
    const token = fakeIdToken({ sub: 'user-1', 'custom:tenant_id': 'tenant-a' });
    expect(decodeTokenPayload(token)).toMatchObject({
      sub: 'user-1',
      'custom:tenant_id': 'tenant-a'
    });
  });

  it('returns null instead of throwing on garbage', () => {
    expect(decodeTokenPayload('not-a-jwt')).toBeNull();
    expect(decodeTokenPayload('a.!!!notbase64!!!.c')).toBeNull();
    expect(decodeTokenPayload('')).toBeNull();
  });
});

describe('sessionFromIdToken', () => {
  it('maps claims to a session, preferring the access token', () => {
    const idToken = fakeIdToken({
      sub: 'user-1',
      username: 'alice',
      'cognito:groups': ['analyst'],
      'custom:tenant_id': 'tenant-a'
    });
    const session = sessionFromIdToken(idToken, 'access-token');
    expect(session).toEqual({
      role: 'analyst',
      tenant_id: 'tenant-a',
      token: 'access-token',
      username: 'alice'
    });
  });

  it('falls back to the id token when no access token is given', () => {
    const idToken = fakeIdToken({ sub: 'user-1', 'cognito:groups': ['executive'] });
    expect(sessionFromIdToken(idToken)?.token).toBe(idToken);
  });

  it('falls back to the read-only demo role when no group matches', () => {
    const idToken = fakeIdToken({ sub: 'user-1', 'cognito:groups': ['unknown-group'] });
    expect(sessionFromIdToken(idToken)?.role).toBe('demo');
  });

  it('returns null for an undecodable token', () => {
    expect(sessionFromIdToken('garbage')).toBeNull();
  });
});

describe('configuration and redirect detection', () => {
  it('reports Cognito disabled when no client id is configured', () => {
    // Les variables VITE_* ne sont pas définies dans l'environnement de test :
    // c'est précisément le mode démo, celui des juges sans compte AWS.
    expect(cognitoConfig()).toBeNull();
    expect(isCognitoEnabled()).toBe(false);
  });

  it('detects an authorization response in the query string', () => {
    const original = window.location.search;
    Object.defineProperty(window, 'location', {
      value: { ...window.location, search: '?code=abc&state=xyz' },
      writable: true
    });
    expect(hasAuthorizationCode()).toBe(true);

    Object.defineProperty(window, 'location', {
      value: { ...window.location, search: '' },
      writable: true
    });
    expect(hasAuthorizationCode()).toBe(false);

    Object.defineProperty(window, 'location', {
      value: { ...window.location, search: original },
      writable: true
    });
  });
});

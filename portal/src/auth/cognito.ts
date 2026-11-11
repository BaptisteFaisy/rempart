/**
 * Cognito OIDC authorization-code + PKCE flow (EF-POR-01).
 *
 * The role and tenant shown in the UI come from the **id token claims**
 * (`cognito:groups`, `custom:tenant_id`) — the same claims the backend reads in
 * `rempart.common.tenant.resolve_principal`. A judge cannot pick a role by hand
 * once Cognito is configured.
 *
 * Demo mode: when `VITE_COGNITO_CLIENT_ID` is unset the portal falls back to the
 * persona picker and says so out loud. Judges must be able to get in without an
 * AWS account.
 */

import type { Role, UserSession } from '../types';
import { createCodeChallenge, createState, createCodeVerifier } from './pkce';

export const ROLES: Role[] = [
  'platform_admin',
  'analyst',
  'account_manager',
  'client_security',
  'client_dev',
  'executive',
  'demo'
];

export interface CognitoConfig {
  domain: string;
  clientId: string;
  redirectUri: string;
}

const PENDING_KEY = 'rempart_oidc_pending';

export function cognitoConfig(): CognitoConfig | null {
  const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined;
  const domain = import.meta.env.VITE_COGNITO_DOMAIN as string | undefined;
  if (!clientId || !domain) return null;
  const redirectUri =
    (import.meta.env.VITE_COGNITO_REDIRECT_URI as string | undefined) ||
    (typeof window !== 'undefined' ? window.location.origin + window.location.pathname : '/');
  return { domain: domain.replace(/\/$/, ''), clientId, redirectUri };
}

export function isCognitoEnabled(): boolean {
  return cognitoConfig() !== null;
}

/** First Cognito group that maps to a known Rempart role. */
export function roleFromGroups(groups: unknown): Role | null {
  if (!Array.isArray(groups)) return null;
  for (const group of groups) {
    if (typeof group === 'string' && ROLES.includes(group as Role)) return group as Role;
  }
  return null;
}

interface TokenPayload {
  sub?: string;
  'cognito:groups'?: unknown;
  'custom:tenant_id'?: string;
  username?: string;
  exp?: number;
}

/**
 * Decode a JWT payload WITHOUT verifying the signature.
 *
 * Deliberate: the browser is not the trust boundary — the API verifies the
 * token against the user pool on every call and returns 401 otherwise. We only
 * read claims to render the right persona. Documented so nobody mistakes this
 * for authentication.
 */
export function decodeTokenPayload(token: string): TokenPayload | null {
  const part = token.split('.')[1];
  if (!part) return null;
  try {
    const padded = part.replace(/-/g, '+').replace(/_/g, '/');
    const json = atob(padded + '='.repeat((4 - (padded.length % 4)) % 4));
    return JSON.parse(json) as TokenPayload;
  } catch {
    return null;
  }
}

/** Build the UserSession the rest of the portal consumes, from id-token claims. */
export function sessionFromIdToken(idToken: string, accessToken?: string): UserSession | null {
  const payload = decodeTokenPayload(idToken);
  if (!payload) return null;
  const role = roleFromGroups(payload['cognito:groups']) ?? 'demo';
  return {
    role,
    tenant_id: payload['custom:tenant_id'],
    token: accessToken || idToken,
    username: payload.username || payload.sub || 'authenticated-user'
  };
}

interface PendingFlow {
  verifier: string;
  state: string;
}

/** Redirect the browser to Cognito /oauth2/authorize (PKCE, no secret). */
export async function startSignIn(): Promise<void> {
  const config = cognitoConfig();
  if (!config) return;
  const verifier = createCodeVerifier();
  const state = createState();
  sessionStorage.setItem(PENDING_KEY, JSON.stringify({ verifier, state } satisfies PendingFlow));

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    scope: 'openid email profile',
    state,
    code_challenge: await createCodeChallenge(verifier),
    code_challenge_method: 'S256'
  });
  window.location.assign(`${config.domain}/oauth2/authorize?${params.toString()}`);
}

/** True when the current URL carries an authorization response to exchange. */
export function hasAuthorizationCode(): boolean {
  if (typeof window === 'undefined') return false;
  const params = new URLSearchParams(window.location.search);
  return Boolean(params.get('code'));
}

/** Exchange ?code=… for tokens. Returns null when state mismatches or on error. */
export async function completeSignIn(): Promise<UserSession | null> {
  const config = cognitoConfig();
  if (!config || typeof window === 'undefined') return null;

  const params = new URLSearchParams(window.location.search);
  const code = params.get('code');
  const state = params.get('state');
  const raw = sessionStorage.getItem(PENDING_KEY);
  if (!code || !raw) return null;

  let pending: PendingFlow;
  try {
    pending = JSON.parse(raw) as PendingFlow;
  } catch {
    return null;
  }
  sessionStorage.removeItem(PENDING_KEY);
  if (state !== pending.state) return null; // forged or stale response

  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: config.clientId,
    code,
    redirect_uri: config.redirectUri,
    code_verifier: pending.verifier
  });
  const res = await fetch(`${config.domain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString()
  });
  if (!res.ok) return null;

  const tokens = (await res.json()) as { id_token?: string; access_token?: string };
  if (!tokens.id_token) return null;
  // Strip ?code=&state= so a reload does not replay an expired code.
  window.history.replaceState({}, '', window.location.pathname);
  return sessionFromIdToken(tokens.id_token, tokens.access_token);
}

export async function signOut(): Promise<void> {
  const config = cognitoConfig();
  if (!config) return;
  const params = new URLSearchParams({
    client_id: config.clientId,
    logout_uri: config.redirectUri
  });
  window.location.assign(`${config.domain}/logout?${params.toString()}`);
}

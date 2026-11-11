/**
 * PKCE (RFC 7636) helpers for the Cognito authorization-code flow.
 *
 * Implemented with the Web Crypto API only: no `aws-amplify`, no
 * `oidc-client-ts`. Keeping the bundle small matters because CI must build
 * the portal inside a 5-minute budget.
 */

const CHARSET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';

/** Cryptographically random code verifier, 43-128 chars per the RFC. */
export function createCodeVerifier(length = 64): string {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => CHARSET[byte % CHARSET.length]).join('');
}

/** Base64url of a byte array, without padding (RFC 7636 Appendix A). */
export function base64UrlEncode(bytes: Uint8Array): string {
  let binary = '';
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** S256 code challenge: BASE64URL(SHA256(verifier)). */
export async function createCodeChallenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return base64UrlEncode(new Uint8Array(digest));
}

/** Opaque `state` value, used to reject a forged authorization response. */
export function createState(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

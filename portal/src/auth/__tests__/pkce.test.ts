import { describe, expect, it } from 'vitest';
import { base64UrlEncode, createCodeChallenge, createCodeVerifier, createState } from '../pkce';

describe('pkce', () => {
  it('produces a verifier of the requested length from the RFC charset', () => {
    const verifier = createCodeVerifier(64);
    expect(verifier).toHaveLength(64);
    expect(verifier).toMatch(/^[A-Za-z0-9\-._~]+$/);
  });

  it('produces a different verifier on each call', () => {
    expect(createCodeVerifier()).not.toBe(createCodeVerifier());
  });

  it('keeps the verifier inside the RFC 7636 bounds (43-128)', () => {
    expect(createCodeVerifier(43)).toHaveLength(43);
    expect(createCodeVerifier(128)).toHaveLength(128);
  });

  it('encodes base64url without padding', () => {
    const encoded = base64UrlEncode(new Uint8Array([255, 254, 253]));
    expect(encoded).not.toContain('+');
    expect(encoded).not.toContain('/');
    expect(encoded).not.toContain('=');
  });

  it('derives an S256 challenge that differs from the verifier', async () => {
    const verifier = createCodeVerifier();
    const challenge = await createCodeChallenge(verifier);
    expect(challenge).not.toBe(verifier);
    expect(challenge).toMatch(/^[A-Za-z0-9\-_]+$/);
    // Known-answer test: SHA-256 of "abc" in base64url.
    expect(await createCodeChallenge('abc')).toBe(
      'ungWv48Bz-pBQUDeXa4iI7ADYaOWF3qctBD_YfIAFa0'
    );
  });

  it('is deterministic for the same verifier', async () => {
    const first = await createCodeChallenge('fixed-verifier');
    const second = await createCodeChallenge('fixed-verifier');
    expect(first).toBe(second);
  });

  it('produces a 22-character state value', () => {
    expect(createState()).toHaveLength(22);
  });
});

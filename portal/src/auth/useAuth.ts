import { useCallback, useEffect, useState } from 'react';
import { clearSession, getSession, saveSession } from '../api/client';
import type { UserSession } from '../types';
import {
  completeSignIn,
  hasAuthorizationCode,
  isCognitoEnabled,
  signOut,
  startSignIn
} from './cognito';

export interface AuthState {
  /** True when a real Cognito user pool is configured (no persona picker). */
  cognito: boolean;
  session: UserSession;
  /** True while the authorization code is being exchanged for tokens. */
  pending: boolean;
  signIn: () => Promise<void>;
  logout: () => Promise<void>;
  /** Persona picker, demo mode only. Throws if Cognito is configured. */
  useDemoPersona: (session: UserSession) => void;
}

/**
 * Single authentication entry point for the portal.
 *
 * With Cognito configured: the session comes from id-token claims and the
 * persona picker is refused. Without it: demo mode, and the UI must say so.
 */
export function useAuth(): AuthState {
  const [session, setSession] = useState<UserSession>(getSession());
  const [pending, setPending] = useState<boolean>(hasAuthorizationCode());
  const cognito = isCognitoEnabled();

  useEffect(() => {
    if (!hasAuthorizationCode()) return;
    let cancelled = false;
    completeSignIn()
      .then((next) => {
        if (cancelled) return;
        if (next) {
          saveSession(next);
          setSession(next);
        }
      })
      .finally(() => {
        if (!cancelled) setPending(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async () => {
    setPending(true);
    await startSignIn();
  }, []);

  const logout = useCallback(async () => {
    clearSession();
    setSession({ role: 'demo', tenant_id: 'demo-tenant-shoplite' });
    if (isCognitoEnabled()) await signOut();
  }, []);

  const useDemoPersona = useCallback(
    (next: UserSession) => {
      if (isCognitoEnabled()) {
        throw new Error('Persona selection is disabled when Cognito is configured');
      }
      saveSession(next);
      setSession(next);
    },
    []
  );

  return { cognito, session, pending, signIn, logout, useDemoPersona };
}

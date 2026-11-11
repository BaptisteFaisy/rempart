import { useCallback, useState } from 'react';
import { UserSession } from '../types';
import { getSession, saveSession, clearSession } from '../api/client';

export function useSession() {
  const [session, setSession] = useState<UserSession>(getSession());

  const update = useCallback((next: UserSession) => {
    saveSession(next);
    setSession(next);
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setSession({ role: 'demo', tenant_id: 'demo-tenant-shoplite' });
  }, []);

  return { session, update, logout };
}

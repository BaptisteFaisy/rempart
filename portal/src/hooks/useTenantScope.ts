import { useEffect, useState } from 'react';
import { Tenant } from '../types';
import { portalApi } from '../api/service';
import { useSession } from './useSession';

export interface TenantScope {
  tenants: Tenant[];
  tenantId: string;
  setTenantId: (tenantId: string) => void;
  loading: boolean;
}

export interface TenantScopeOptions {
  /** Allow the "All tenants" (fleet-wide) choice. */
  allowAll?: boolean;
  /** Pre-selected tenant, e.g. from a `?tenant=` link. */
  initial?: string | null;
}

/**
 * Tenant selector shared by every tenant-scoped page (audit, policy, evidence,
 * industrialization, budget, reports).
 *
 * Starts on the requested tenant, else the session tenant; when that id is
 * unknown to the API (a legacy demo default), it falls back to the first
 * visible tenant so the page shows data instead of an empty screen.
 */
export function useTenantScope(options: TenantScopeOptions = {}): TenantScope {
  const { allowAll = false, initial = null } = options;
  const { session } = useSession();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantId, setTenantId] = useState<string>(
    initial || (allowAll ? '' : session.tenant_id ?? '')
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    portalApi
      .getTenants()
      .then(setTenants)
      .catch(() => setTenants([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (loading || tenants.length === 0 || allowAll) return;
    const known = tenants.some((t) => t.tenant_id === tenantId);
    if (!known) setTenantId(tenants[0].tenant_id);
  }, [loading, tenants, tenantId, allowAll]);

  return { tenants, tenantId, setTenantId, loading };
}

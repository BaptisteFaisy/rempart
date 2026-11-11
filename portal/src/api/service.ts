import { apiRequest, showApiError } from './client';
import {
  DEMO_COLLECTIONS,
  DEMO_ITEM_COUNT,
  DEMO_TENANTS,
  demoApplication,
  demoApplications,
  demoBudget,
  demoFinding,
  demoFindings,
  demoReports,
  demoRun,
  demoRuns,
  demoTenant,
  deriveKpis
} from './mockData';
import {
  Application,
  BudgetState,
  Decision,
  Finding,
  Kpis,
  Report,
  Run,
  Tenant
} from '../types';

/**
 * Two explicit modes — never a silent fallback.
 *
 * - API mode (default): every call goes to VITE_API_URL. A failure throws
 *   `ApiError` and is surfaced by the banner in `client.ts`; no invented rows.
 * - Offline demo mode (`VITE_USE_MOCKS=1`): calls are answered from the frozen
 *   dataset `demo/seed/demo-dataset.json` — the very same file
 *   `scripts/serve_local.py` loads — and a banner says so.
 */
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === '1';

export const isOfflineDemoMode = (): boolean => USE_MOCKS;

export interface PortalApi {
  getTenants(): Promise<Tenant[]>;
  getTenant(tenantId: string): Promise<Tenant | null>;
  getApplications(tenantId?: string): Promise<Application[]>;
  getApplication(appId: string): Promise<Application | null>;
  getRuns(appId?: string): Promise<Run[]>;
  getRun(runId: string): Promise<Run | null>;
  getFindings(params?: FindingQuery): Promise<Finding[]>;
  getFinding(findingId: string): Promise<Finding | null>;
  postDecision(
    findingId: string,
    action: DecisionAction,
    justification: string
  ): Promise<Decision>;
  getReports(tenantId?: string): Promise<Report[]>;
  getBudget(tenantId: string): Promise<BudgetState>;
  updateBudget(tenantId: string, update: Partial<BudgetState>): Promise<BudgetState>;
  getFleetKpis(): Promise<Kpis>;
  getTenantKpis(tenantId: string): Promise<Kpis>;
}

type DecisionAction = 'confirmed' | 'false_positive' | 'risk_accepted' | 'retest';

interface FindingQuery {
  tenant_id?: string;
  app_id?: string;
  status?: string;
  priority?: string;
  [key: string]: string | undefined;
}

async function unwrap<T>(promise: Promise<{ [key: string]: T[] }>, key: string): Promise<T[]> {
  const payload = await promise;
  return payload[key] ?? [];
}

const liveApi: PortalApi = {
  async getTenants() {
    return unwrap(apiRequest<{ tenants: Tenant[] }>('/v1/tenants'), 'tenants');
  },

  async getTenant(tenantId) {
    return apiRequest<Tenant>(`/v1/tenants/${tenantId}`);
  },

  async getApplications(tenantId) {
    const endpoint = tenantId ? `/v1/tenants/${tenantId}/applications` : '/v1/applications';
    return unwrap(apiRequest<{ applications: Application[] }>(endpoint), 'applications');
  },

  async getApplication(appId) {
    return apiRequest<Application>(`/v1/applications/${appId}`);
  },

  async getRuns(appId) {
    if (appId) {
      return unwrap(apiRequest<{ runs: Run[] }>(`/v1/applications/${appId}/runs`), 'runs');
    }
    return unwrap(apiRequest<{ runs: Run[] }>('/v1/runs'), 'runs');
  },

  async getRun(runId) {
    return apiRequest<Run>(`/v1/runs/${runId}`);
  },

  async getFindings(params) {
    return unwrap(apiRequest<{ findings: Finding[] }>('/v1/findings', { params }), 'findings');
  },

  async getFinding(findingId) {
    return apiRequest<Finding>(`/v1/findings/${findingId}`);
  },

  async postDecision(findingId, action, justification) {
    const payload = await apiRequest<{ decision: Decision }>(
      `/v1/findings/${findingId}/decision`,
      { method: 'POST', body: { action, justification } }
    );
    return payload.decision;
  },

  async getReports(tenantId) {
    const endpoint = tenantId ? `/v1/tenants/${tenantId}/reports` : '/v1/reports';
    return unwrap(apiRequest<{ reports: Report[] }>(endpoint), 'reports');
  },

  async getBudget(tenantId) {
    return apiRequest<BudgetState>(`/v1/tenants/${tenantId}/budget`);
  },

  async updateBudget(tenantId, update) {
    return apiRequest<BudgetState>(`/v1/tenants/${tenantId}/budget`, {
      method: 'PUT',
      body: update
    });
  },

  async getFleetKpis() {
    return apiRequest<Kpis>('/v1/fleet/kpis');
  },

  async getTenantKpis(tenantId) {
    return apiRequest<Kpis>(`/v1/tenants/${tenantId}/kpis`);
  }
};

/** Offline answers, all read from the frozen seed dataset. */
const offlineApi: PortalApi = {
  async getTenants() {
    return DEMO_TENANTS;
  },

  async getTenant(tenantId) {
    return demoTenant(tenantId);
  },

  async getApplications(tenantId) {
    return demoApplications(tenantId);
  },

  async getApplication(appId) {
    return demoApplication(appId);
  },

  async getRuns(appId) {
    return demoRuns(appId);
  },

  async getRun(runId) {
    return demoRun(runId);
  },

  async getFindings(params) {
    return demoFindings(params);
  },

  async getFinding(findingId) {
    return demoFinding(findingId);
  },

  async postDecision(findingId, action, justification) {
    return {
      decision_id: `dec-offline-${findingId}`,
      finding_id: findingId,
      author_type: 'human',
      author: 'offline-demo',
      action,
      justification,
      created_at: new Date().toISOString()
    };
  },

  async getReports(tenantId) {
    return demoReports(tenantId);
  },

  async getBudget(tenantId) {
    return demoBudget(tenantId);
  },

  async updateBudget(tenantId, update) {
    return { ...demoBudget(tenantId), ...update };
  },

  async getFleetKpis() {
    return deriveKpis();
  },

  async getTenantKpis(tenantId) {
    return deriveKpis(tenantId);
  }
};

const OFFLINE_BANNER_ID = 'rempart-offline-demo-banner';

/**
 * Tell the judge, loudly, that nothing on screen came from a live backend.
 * Rendered from the API layer because the offline switch lives here; pages keep
 * rendering the same components in both modes.
 */
export function installOfflineDemoBanner(): void {
  if (!USE_MOCKS || typeof document === 'undefined') return;
  if (document.getElementById(OFFLINE_BANNER_ID)) return;
  const banner = document.createElement('div');
  banner.id = OFFLINE_BANNER_ID;
  banner.setAttribute('data-testid', 'offline-demo-banner');
  banner.setAttribute('role', 'status');
  banner.style.cssText =
    'position:fixed;bottom:0;left:0;right:0;z-index:1000;padding:8px 16px;' +
    'background:#78350f;color:#fde68a;font:13px/1.4 system-ui,sans-serif;text-align:center';
  banner.textContent =
    `OFFLINE DEMO MODE (VITE_USE_MOCKS=1) — ${DEMO_ITEM_COUNT} frozen items from ` +
    `demo/seed/demo-dataset.json (${DEMO_COLLECTIONS.join(', ')}). No API call, no AWS.`;
  document.body.appendChild(banner);
}

installOfflineDemoBanner();

/**
 * The portal's single data entry point. Errors in API mode are reported and
 * rethrown (never replaced by placeholder data); offline mode answers from the
 * frozen dataset only.
 */
export const portalApi: PortalApi = USE_MOCKS ? offlineApi : liveApi;

/** Report a failure from a page that catches it, so nothing fails silently. */
export function reportApiFailure(context: string, error: unknown): void {
  const message = error instanceof Error ? error.message : String(error);
  showApiError(`${context}: ${message}`);
}

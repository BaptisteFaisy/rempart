/**
 * Live API implementation: one method per backend route.
 *
 * Every call goes to `VITE_API_URL` through `apiRequest`; a failure throws
 * `ApiError` and is shown by the banner in `client.ts` — the portal never
 * replaces a real error with placeholder rows.
 */
import { apiRequest } from './client';
import { unwrapPayload } from './fields';
import {
  Application,
  AuditPage,
  AuditQuery,
  BudgetForecast,
  BudgetPayload,
  Decision,
  EffectivePolicy,
  EvidencePack,
  Finding,
  Industrialization,
  Kpis,
  OnboardingStatus,
  RemediationResult,
  Report,
  Run,
  Tenant,
  TenantPolicy
} from '../types';
import { PortalApi, VerificationMethod } from './contracts';

async function unwrap<T>(promise: Promise<{ [key: string]: T[] }>, key: string): Promise<T[]> {
  const payload = await promise;
  return payload[key] ?? [];
}

export const liveApi: PortalApi = {
  async getTenants() {
    return unwrap(apiRequest<{ tenants: Tenant[] }>('/v1/tenants'), 'tenants');
  },

  async getTenant(tenantId) {
    return apiRequest<Tenant>(`/v1/tenants/${tenantId}`);
  },

  async getApplications(tenantId) {
    return unwrap(
      apiRequest<{ applications: Application[] }>(`/v1/tenants/${tenantId}/applications`),
      'applications'
    );
  },

  async getApplication(appId) {
    return apiRequest<Application>(`/v1/applications/${appId}`);
  },

  async getOnboarding(appId) {
    return apiRequest<OnboardingStatus>(`/v1/applications/${appId}/onboarding`);
  },

  async postOnboarding(appId, method: VerificationMethod) {
    return apiRequest<OnboardingStatus>(`/v1/applications/${appId}/onboarding`, {
      method: 'POST',
      body: { verification_method: method }
    });
  },

  async getRuns(appId) {
    return unwrap(apiRequest<{ runs: Run[] }>(`/v1/applications/${appId}/runs`), 'runs');
  },

  async getRun(runId) {
    return apiRequest<Run>(`/v1/runs/${runId}`);
  },

  async postRun(appId) {
    return apiRequest<Run>(`/v1/applications/${appId}/runs`, {
      method: 'POST',
      body: { trigger: 'manual', scope_decision: 'minimal' }
    });
  },

  async stopRun(runId) {
    return apiRequest<Run>(`/v1/runs/${runId}/stop`, { method: 'POST' });
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

  async postRemediation(findingId) {
    return apiRequest<RemediationResult>(`/v1/findings/${findingId}/remediation`, {
      method: 'POST'
    });
  },

  async getReports(tenantId) {
    const endpoint = tenantId ? `/v1/tenants/${tenantId}/reports` : '/v1/reports';
    return unwrap(apiRequest<{ reports: Report[] }>(endpoint), 'reports');
  },

  async getReport(reportId) {
    return apiRequest<Report>(`/v1/reports/${reportId}`);
  },

  async postReport(tenantId, period) {
    return apiRequest<Report>(`/v1/tenants/${tenantId}/reports`, {
      method: 'POST',
      body: period ? { period } : {}
    });
  },

  async getEvidence(tenantId, period) {
    const payload = await apiRequest<unknown>(
      `/v1/tenants/${tenantId}/evidence`,
      period ? { params: { period } } : undefined
    );
    return unwrapPayload<EvidencePack>(payload, ['evidence', 'pack', 'dossier']);
  },

  async postEvidence(tenantId, period) {
    const payload = await apiRequest<unknown>(`/v1/tenants/${tenantId}/evidence`, {
      method: 'POST',
      body: period ? { period } : {}
    });
    return unwrapPayload<EvidencePack>(payload, ['evidence', 'pack', 'dossier']);
  },

  async getBudget(tenantId) {
    return apiRequest<BudgetPayload>(`/v1/tenants/${tenantId}/budget`);
  },

  async updateBudget(tenantId, update) {
    return apiRequest<BudgetPayload>(`/v1/tenants/${tenantId}/budget`, {
      method: 'PUT',
      body: update
    });
  },

  async getForecast(tenantId, month) {
    const payload = await apiRequest<unknown>(
      `/v1/tenants/${tenantId}/forecast`,
      month ? { params: { month } } : undefined
    );
    return unwrapPayload<BudgetForecast>(payload, ['forecast']);
  },

  async getFleetKpis() {
    return apiRequest<Kpis>('/v1/fleet/kpis');
  },

  async getTenantKpis(tenantId) {
    return apiRequest<Kpis>(`/v1/tenants/${tenantId}/kpis`);
  },

  async getAudit(query?: AuditQuery) {
    const params = {
      action: query?.action,
      actor: query?.actor,
      object_type: query?.object_type,
      object_id: query?.object_id,
      since: query?.since,
      until: query?.until,
      limit: query?.limit,
      offset: query?.offset
    };
    const endpoint = query?.tenant_id ? `/v1/tenants/${query.tenant_id}/audit` : '/v1/audit';
    return apiRequest<AuditPage>(endpoint, { params });
  },

  async getPolicy(tenantId) {
    return apiRequest<TenantPolicy>(`/v1/tenants/${tenantId}/policy`);
  },

  async updatePolicy(tenantId, policy) {
    return apiRequest<TenantPolicy>(`/v1/tenants/${tenantId}/policy`, {
      method: 'PUT',
      body: { policy }
    });
  },

  async getPolicyDefaults() {
    return apiRequest<EffectivePolicy>('/v1/settings/defaults');
  },

  async getIndustrialization(tenantId, period) {
    const payload = await apiRequest<unknown>(
      `/v1/tenants/${tenantId}/industrialization`,
      period ? { params: { period } } : undefined
    );
    return unwrapPayload<Industrialization>(payload, ['industrialization', 'metrics']);
  }
};

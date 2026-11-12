/**
 * Offline demo implementation: every answer comes from the frozen dataset
 * `demo/seed/demo-dataset.json` — the very same file `scripts/serve_local.py`
 * serves. No API call, no AWS, no invented numbers.
 *
 * When the frozen dataset does not carry a collection (the governance
 * collections are being added to it), the readers return `null` and the pages
 * say "not available in the frozen dataset".
 */
import {
  DEMO_TENANTS,
  deriveKpis,
  demoApplication,
  demoApplications,
  demoBudget,
  demoFinding,
  demoFindings,
  demoOnboarding,
  demoReport,
  demoReports,
  demoRun,
  demoRuns,
  demoTenant
} from './mockData';
import {
  demoAudit,
  demoEvidence,
  demoForecast,
  demoIndustrialization,
  demoPolicy,
  demoPolicyDefaults
} from './mockGovernance';
import {
  AuditQuery,
  BudgetPayload,
  Decision,
  EffectivePolicy,
  Industrialization,
  OnboardingStatus,
  RemediationResult,
  Report,
  Run,
  TenantPolicy,
  AuditPage
} from '../types';
import { PortalApi, VerificationMethod } from './contracts';

const now = (): string => new Date().toISOString();

export const offlineApi: PortalApi = {
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

  async getOnboarding(appId) {
    return demoOnboarding(appId);
  },

  async postOnboarding(appId, method: VerificationMethod) {
    const app = demoApplication(appId);
    return {
      app_id: appId,
      status: 'completed',
      onboarded: true,
      agent_space_id: app?.agent_space_id ?? null,
      domains: app?.domains ?? [],
      verification_method: method,
      verification_instructions: []
    } satisfies OnboardingStatus;
  },

  async getRuns(appId) {
    return demoRuns(appId);
  },

  async getRun(runId) {
    return demoRun(runId);
  },

  async postRun(appId) {
    const app = demoApplication(appId);
    return {
      run_id: `run-offline-${appId}`,
      config_id: 'offline',
      app_id: appId,
      tenant_id: app?.tenant_id ?? '',
      trigger: 'manual',
      scope_decision: 'minimal',
      status: 'running',
      started_at: now(),
      ended_at: null,
      duration_s: null,
      task_hours: null,
      cost_usd: null
    } satisfies Run;
  },

  async stopRun(runId) {
    const run = demoRun(runId);
    return {
      run_id: runId,
      config_id: run?.config_id ?? 'offline',
      app_id: run?.app_id ?? '',
      tenant_id: run?.tenant_id ?? '',
      trigger: run?.trigger ?? 'manual',
      status: 'stopped',
      started_at: run?.started_at ?? now(),
      ended_at: now(),
      duration_s: null,
      task_hours: null,
      cost_usd: null
    } satisfies Run;
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
      created_at: now()
    } satisfies Decision;
  },

  async postRemediation(findingId) {
    const finding = demoFinding(findingId);
    return {
      finding: finding ? { ...finding, status: 'in_remediation' } : undefined,
      remediation: { offline: true, note: 'frozen demo dataset — no Security Agent call' }
    } satisfies RemediationResult;
  },

  async getReports(tenantId) {
    return demoReports(tenantId);
  },

  async getReport(reportId) {
    return demoReport(reportId);
  },

  async postReport(tenantId, period) {
    const month = period ?? '2026-10';
    const frozen = demoReports(tenantId).find((r) => r.period === month);
    return {
      report_id: frozen?.report_id ?? `rep-offline-${tenantId}-${month}`,
      tenant_id: tenantId,
      period: month,
      s3_key: frozen?.s3_key ?? `reports/${tenantId}/${month}/demo.pdf`,
      kpis: frozen?.kpis ?? {},
      created_at: now()
    } satisfies Report;
  },

  async getEvidence(tenantId, period) {
    return demoEvidence(tenantId, period);
  },

  async postEvidence(tenantId, period) {
    return demoEvidence(tenantId, period);
  },

  async getBudget(tenantId) {
    return demoBudget(tenantId) as BudgetPayload;
  },

  async updateBudget(tenantId, update) {
    return { ...demoBudget(tenantId), ...update } as BudgetPayload;
  },

  async getForecast(tenantId) {
    return demoForecast(tenantId);
  },

  async getFleetKpis() {
    return deriveKpis();
  },

  async getTenantKpis(tenantId) {
    return deriveKpis(tenantId);
  },

  async getAudit(query?: AuditQuery) {
    return demoAudit(query) as AuditPage | null;
  },

  async getPolicy(tenantId) {
    return demoPolicy(tenantId);
  },

  async updatePolicy(tenantId, policy) {
    const current = demoPolicy(tenantId);
    return {
      tenant_id: tenantId,
      policy: { ...(current?.policy ?? {}), ...policy },
      effective: { ...(current?.effective ?? {}), ...policy } as EffectivePolicy
    } satisfies TenantPolicy;
  },

  async getPolicyDefaults() {
    return demoPolicyDefaults();
  },

  async getIndustrialization(tenantId) {
    return demoIndustrialization(tenantId) as Industrialization | null;
  }
};

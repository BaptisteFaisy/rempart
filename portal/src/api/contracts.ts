import {
  Application,
  AuditPage,
  AuditQuery,
  BudgetForecast,
  BudgetPayload,
  BudgetUpdate,
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

export type DecisionAction = 'confirmed' | 'false_positive' | 'risk_accepted' | 'retest';

export type VerificationMethod = 'DNS_TXT' | 'HTTP_ROUTE' | 'PRIVATE_VPC';

export interface FindingQuery {
  tenant_id?: string;
  app_id?: string;
  status?: string;
  priority?: string;
  [key: string]: string | undefined;
}

/**
 * The portal's whole data surface: one method per backend route the UI needs.
 *
 * `null` means "the frozen dataset has no entry for this" (offline demo mode
 * only) — pages then say so instead of rendering an empty screen. In API mode
 * a failure throws `ApiError` and is surfaced by the banner in `client.ts`.
 */
export interface PortalApi {
  /* tenants */
  getTenants(): Promise<Tenant[]>;
  getTenant(tenantId: string): Promise<Tenant | null>;

  /* applications + onboarding */
  getApplications(tenantId: string): Promise<Application[]>;
  getApplication(appId: string): Promise<Application | null>;
  getOnboarding(appId: string): Promise<OnboardingStatus | null>;
  postOnboarding(appId: string, method: VerificationMethod): Promise<OnboardingStatus>;

  /* runs */
  getRuns(appId: string): Promise<Run[]>;
  getRun(runId: string): Promise<Run | null>;
  postRun(appId: string): Promise<Run>;
  stopRun(runId: string): Promise<Run>;

  /* findings */
  getFindings(params?: FindingQuery): Promise<Finding[]>;
  getFinding(findingId: string): Promise<Finding | null>;
  postDecision(
    findingId: string,
    action: DecisionAction,
    justification: string
  ): Promise<Decision>;
  postRemediation(findingId: string): Promise<RemediationResult>;

  /* reports + evidence dossier */
  getReports(tenantId?: string): Promise<Report[]>;
  getReport(reportId: string): Promise<Report | null>;
  postReport(tenantId: string, period?: string): Promise<Report>;
  getEvidence(tenantId: string, period?: string): Promise<EvidencePack | null>;
  postEvidence(tenantId: string, period?: string): Promise<EvidencePack | null>;

  /* budget, forecast, KPIs */
  getBudget(tenantId: string): Promise<BudgetPayload>;
  updateBudget(tenantId: string, update: BudgetUpdate): Promise<BudgetPayload>;
  getForecast(tenantId: string, month?: string): Promise<BudgetForecast | null>;
  getFleetKpis(): Promise<Kpis>;
  getTenantKpis(tenantId: string): Promise<Kpis>;

  /* audit journal + correction policy */
  getAudit(query?: AuditQuery): Promise<AuditPage | null>;
  getPolicy(tenantId: string): Promise<TenantPolicy | null>;
  updatePolicy(tenantId: string, policy: Partial<EffectivePolicy>): Promise<TenantPolicy | null>;
  getPolicyDefaults(): Promise<EffectivePolicy | null>;

  /* industrialization metrics */
  getIndustrialization(tenantId: string, period?: string): Promise<Industrialization | null>;
}

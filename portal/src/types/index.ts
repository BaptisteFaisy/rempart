export type Role =
  | 'platform_admin'
  | 'analyst'
  | 'account_manager'
  | 'client_security'
  | 'client_dev'
  | 'executive'
  | 'demo';

export type Plan = 'essentiel' | 'continu' | 'critique';
export type MandateStatus = 'none' | 'pending' | 'valid' | 'expired';
export type Criticality = 'low' | 'medium' | 'high';
export type Priority = 'P1' | 'P2' | 'P3' | 'P4';
export type Severity = 'Critical' | 'High' | 'Medium' | 'Low' | 'Informational';
export type Confidence = 'High' | 'Medium' | 'Low';
export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'stopped' | 'blocked';
export type FindingStatus =
  | 'new'
  | 'pending_validation'
  | 'confirmed'
  | 'false_positive'
  | 'risk_accepted'
  | 'in_remediation'
  | 'to_retest'
  | 'closed'
  | 'reopened';

export interface UserSession {
  role: Role;
  tenant_id?: string;
  token?: string;
  username?: string;
}

export interface Contact {
  name: string;
  email: string;
  role?: string;
}

export interface Tenant {
  tenant_id: string;
  name: string;
  aws_account_id?: string;
  region?: string;
  role_arn?: string;
  external_id?: string;
  plan: Plan;
  contacts: Contact[];
  monthly_budget_hours: number;
  mandate_status: MandateStatus;
  created_at: string;
  policy?: Record<string, unknown>;
  free_tier_confirmed?: boolean;
}

export interface TestWindow {
  days?: string[];
  start?: string;
  end?: string;
  environment?: string;
}

export interface Application {
  app_id: string;
  tenant_id: string;
  name: string;
  criticality: Criticality;
  internet_exposed: boolean;
  data_types: string[];
  environment: 'staging' | 'production';
  agent_space_id?: string | null;
  domains: string[];
  repositories: string[];
  team: string;
  ticket_channel: string;
  context?: Record<string, unknown>;
  created_at: string;
  test_windows?: TestWindow[];
}

export interface TestConfig {
  config_id: string;
  app_id: string;
  sa_pentest_id?: string;
  kind: 'delivery' | 'full' | 'on_demand';
  scope?: Record<string, unknown>;
  risk_types: string[];
  blocking_threshold: string;
  schedule?: string | null;
}

export interface Run {
  run_id: string;
  config_id: string;
  app_id: string;
  tenant_id: string;
  trigger: 'cicd' | 'schedule' | 'manual' | 'retest';
  commit_from?: string;
  commit_to?: string;
  scope_decision?: string;
  status: RunStatus;
  started_at: string;
  ended_at?: string | null;
  duration_s?: number | null;
  task_hours?: number | null;
  cost_usd?: number | null;
}

export interface Finding {
  finding_id: string;
  app_id: string;
  tenant_id: string;
  run_id: string;
  fingerprint: string;
  title: string;
  risk_type: string;
  severity: Severity;
  confidence: Confidence;
  priority: Priority;
  status: FindingStatus;
  due_at?: string | null;
  ticket_url?: string | null;
  remediation_pr_url?: string | null;
  evidence?: Record<string, unknown>;
  cvss?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  closed_at?: string | null;
  closed_by_run_id?: string | null;
  /** EF-COR-07: risk acceptance is timestamped and attributed. */
  risk_review_at?: string | null;
  risk_review_by?: string | null;
}

export interface Decision {
  decision_id: string;
  finding_id: string;
  author_type: 'agent' | 'human';
  author: string;
  action: 'confirmed' | 'false_positive' | 'risk_accepted' | 'retest';
  justification: string;
  created_at: string;
}

export interface Report {
  report_id: string;
  tenant_id: string;
  period: string;
  s3_key: string;
  kpis: Record<string, unknown>;
  created_at: string;
}

export interface BudgetState {
  tenant_id: string;
  month: string;
  hours_used: number;
  thresholds_hit: number[];
  auto_stop: boolean;
}

/** Budget payload as returned by GET/PUT /v1/tenants/{id}/budget. */
export interface BudgetPayload extends BudgetState {
  monthly_budget_hours?: number;
  budget_pct?: number;
  allowed?: boolean;
  /** Coupe-circuit global : vrai quand aucun test ne peut démarrer. */
  kill_switch?: boolean;
}

export interface Kpis {
  delivery_to_result_hours: number;
  critical_blocked_before_prod: number;
  mean_time_to_fix_days_by_priority: Record<Priority, number | null>;
  sla_compliance: number;
  coverage: number;
  reopen_rate: number;
  findings_open_by_priority: Record<Priority, number>;
  findings_closed: number;
  tests_total: number;
  tests_blocked: number;
  task_hours_used: number;
  cost_usd: number;
}

/* ------------------------------------------------------------------ */
/* Audit journal (EF-ADM-02) — read only, never modifiable            */
/* ------------------------------------------------------------------ */

export interface AuditEvent {
  audit_id: string;
  actor: string;
  action: string;
  object_type: string;
  object_id: string;
  result: string;
  created_at: string;
  tenant_id?: string;
}

export interface AuditPage {
  events: AuditEvent[];
  count: number;
  total: number;
  limit: number;
  offset: number;
  next_offset?: number | null;
  scan_truncated?: boolean;
}

export interface AuditQuery {
  tenant_id?: string;
  action?: string;
  actor?: string;
  object_type?: string;
  object_id?: string;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

/* ------------------------------------------------------------------ */
/* Correction policy per contract (EF-ADM-01)                         */
/* ------------------------------------------------------------------ */

export type DueDays = Partial<Record<Priority, number | null>>;
export type MatrixOverrides = Partial<Record<Severity, Priority>>;

export interface EffectivePolicy {
  due_days: DueDays;
  matrix_overrides: MatrixOverrides;
  blocking_threshold: Severity;
  hourly_rate: number;
}

export interface TenantPolicy {
  tenant_id: string;
  policy: Partial<EffectivePolicy>;
  effective: EffectivePolicy;
}

/* ------------------------------------------------------------------ */
/* Onboarding (AWS Security Agent)                                     */
/* ------------------------------------------------------------------ */

export interface VerificationInstruction {
  method?: string;
  domain?: string;
  action?: string;
  requires_dns_access?: boolean;
  details?: Record<string, unknown>;
}

export interface OnboardingStatus {
  app_id?: string;
  onboarded?: boolean;
  agent_space_id?: string | null;
  domains?: string[];
  configs?: TestConfig[];
  status?: string;
  config_id?: string;
  sa_pentest_id?: string;
  verification_method?: string;
  verification_instructions?: VerificationInstruction[];
}

/* ------------------------------------------------------------------ */
/* Evidence dossier (EF-RAP-04)                                        */
/* ------------------------------------------------------------------ */

export interface EvidenceIdentity {
  product?: string;
  evidence_version?: string;
  tenant_id?: string;
  tenant_name?: string;
  period?: string;
  generated_at?: string;
  mandate_status?: string;
  plan?: string;
}

export interface EvidenceScopeEntry {
  app_id?: string;
  name?: string;
  environment?: string;
  criticality?: string;
  internet_exposed?: boolean;
  data_types?: string[];
  domains?: string[];
  repositories?: string[];
  agent_space_id?: string | null;
}

export interface EvidenceTest {
  run_id?: string;
  app_id?: string;
  trigger?: string;
  status?: string;
  started_at?: string;
  ended_at?: string | null;
  task_hours?: number | null;
  cost_usd?: number | null;
}

export interface EvidenceDecision {
  decision_id?: string;
  author_type?: 'agent' | 'human';
  author?: string;
  action?: string;
  justification?: string;
  created_at?: string;
}

export interface EvidenceChain {
  finding?: Record<string, unknown>;
  decisions?: EvidenceDecision[];
}

export interface EvidenceClosureProof {
  finding_id?: string;
  title?: string;
  priority?: string;
  closed_at?: string | null;
  proven_by_run_id?: string | null;
}

export interface EvidenceException {
  finding_id?: string;
  title?: string;
  severity?: string;
  priority?: string;
  decided_by?: string[];
  decided_at?: string[];
}

export interface EvidenceIntegrity {
  algorithm?: string;
  digest?: string;
  canonical_form?: string;
  recompute?: string;
}

export interface EvidencePack {
  identity?: EvidenceIdentity;
  scope?: EvidenceScopeEntry[];
  mandate_and_controls?: Record<string, unknown>;
  tests?: EvidenceTest[];
  tests_summary?: Record<string, unknown>;
  closed_findings?: Record<string, unknown>[];
  closure_proofs?: EvidenceClosureProof[];
  decision_chains?: EvidenceChain[];
  exceptions?: {
    false_positives?: EvidenceException[];
    risk_accepted?: EvidenceException[];
  };
  ai_guardrails?: Record<string, unknown>;
  audit_events?: AuditEvent[];
  kpis?: Record<string, unknown>;
  integrity?: EvidenceIntegrity;
}

/* ------------------------------------------------------------------ */
/* Industrialization metrics (#68, #26, #47, #34)                      */
/* ------------------------------------------------------------------ */

export interface IndustrializationIntervention {
  findings_total?: number;
  findings_with_human_decision?: number;
  human_intervention_rate?: number | null;
  findings_with_agent_proposal?: number;
  findings_reviewed_by_human?: number;
  findings_diverged?: number;
  agent_human_divergence_rate?: number | null;
  divergence_rate_among_reviewed?: number | null;
  agent_agreement_rate_on_reviewed?: number | null;
  human_decisions?: number;
  agent_decisions?: number;
  formulas?: Record<string, string>;
}

export interface IndustrializationFatigue {
  window_start?: string;
  window_end?: string;
  window_days?: number;
  human_validations?: number;
  active_days?: number;
  validations_per_active_day?: number;
  validations_per_calendar_day?: number;
  comparable_validations?: number;
  unchanged_validations?: number;
  diverged_validations?: number;
  no_change_validation_ratio?: number | null;
  fatigue_score?: number;
  alert_triggered?: boolean;
  alert_reasons?: string[];
  thresholds?: Record<string, number>;
}

export interface IndustrializationMinutesSaved {
  findings_total?: number;
  findings_triaged?: number;
  findings_not_triaged?: number;
  findings_automatically_triaged?: number;
  findings_reviewed_by_human?: number;
  manual_minutes_if_all_human?: number;
  estimated_minutes_spent?: number;
  minutes_saved?: number;
  hours_saved?: number;
  assumptions?: Record<string, unknown>;
}

export interface IndustrializationCorpus {
  size?: number;
  by_status?: Record<string, number>;
  by_final_verdict?: Record<string, number>;
  by_risk_type?: Record<string, number>;
  by_severity?: Record<string, number>;
  by_agent_human_relation?: Record<string, number>;
  observed_risk_types?: string[];
  configured_risk_types?: string[];
  covered_risk_types?: string[];
  gaps?: string[];
  coverage_ratio?: number;
}

export interface Industrialization {
  tenant_id?: string;
  period?: string;
  human_intervention?: IndustrializationIntervention;
  alert_fatigue?: IndustrializationFatigue;
  minutes_saved?: IndustrializationMinutesSaved;
  corpus?: IndustrializationCorpus;
  [key: string]: unknown;
}

/* ------------------------------------------------------------------ */
/* Budget forecast (EF-BUD-04)                                         */
/* ------------------------------------------------------------------ */

export interface BudgetForecast {
  tenant_id?: string;
  month?: string;
  period?: string;
  hours_used?: number;
  monthly_budget_hours?: number;
  budget_pct?: number;
  projected_month_end_hours?: number;
  projected_hours?: number;
  projected_exhaustion_date?: string | null;
  exhaustion_date?: string | null;
  daily_burn_hours?: number;
  hours_per_day?: number;
  projected_cost_usd?: number;
  estimated_cost_usd?: number;
  thresholds?: number[] | Record<string, number>;
  auto_stop?: boolean;
  [key: string]: unknown;
}

/** Body accepted by PUT /v1/tenants/{id}/budget. */
export interface BudgetUpdate extends Partial<BudgetState> {
  monthly_budget_hours?: number;
  month?: string;
}

/** Result of POST /v1/findings/{id}/remediation. */
export interface RemediationResult {
  finding?: Finding;
  remediation?: Record<string, unknown>;
}

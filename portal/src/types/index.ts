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

import { Tenant, Application, Run, Finding, Decision, Report, BudgetState, Kpis } from '../types';

export const MOCK_TENANTS: Tenant[] = [
  {
    tenant_id: 'tenant-acme',
    name: 'Acme Retail Corp',
    aws_account_id: '123456789012',
    region: 'eu-west-3',
    role_arn: 'arn:aws:iam::123456789012:role/RempartScanner',
    plan: 'critique',
    monthly_budget_hours: 120,
    mandate_status: 'valid',
    created_at: '2026-09-01T08:00:00Z',
    contacts: [
      { name: 'Alice SecOps', email: 'alice@acme.com', role: 'CISO' },
      { name: 'Bob Lead', email: 'bob@acme.com', role: 'DevSecOps Lead' }
    ]
  },
  {
    tenant_id: 'tenant-bookworm',
    name: 'BookWorm SaaS',
    aws_account_id: '987654321098',
    region: 'eu-west-1',
    role_arn: 'arn:aws:iam::987654321098:role/RempartAuditor',
    plan: 'continu',
    monthly_budget_hours: 60,
    mandate_status: 'valid',
    created_at: '2026-10-01T09:00:00Z',
    contacts: [{ name: 'Charlie Admin', email: 'charlie@bookworm.io', role: 'VP Eng' }]
  },
  {
    tenant_id: 'demo-tenant-shoplite',
    name: 'ShopLite (Judge Demo)',
    aws_account_id: '111222333444',
    region: 'eu-west-3',
    role_arn: 'arn:aws:iam::111222333444:role/RempartDemoRole',
    plan: 'critique',
    monthly_budget_hours: 80,
    mandate_status: 'valid',
    created_at: '2026-11-01T12:00:00Z',
    contacts: [{ name: 'Demo Judge', email: 'judge@aws-msp-hackathon.internal', role: 'Judge' }]
  }
];

export const MOCK_APPLICATIONS: Application[] = [
  {
    app_id: 'app-shoplite-core',
    tenant_id: 'demo-tenant-shoplite',
    name: 'ShopLite Checkout & Orders API',
    criticality: 'high',
    internet_exposed: true,
    data_types: ['personal', 'payment'],
    environment: 'production',
    agent_space_id: 'space-shoplite-prod',
    domains: ['api.shoplite.rempart.internal', 'checkout.shoplite.com'],
    repositories: ['rempart/demo/app-a'],
    team: 'Checkout Guild',
    ticket_channel: 'github-issues',
    created_at: '2026-11-02T10:00:00Z'
  },
  {
    app_id: 'app-bookworm-search',
    tenant_id: 'tenant-bookworm',
    name: 'BookWorm Search & Catalog',
    criticality: 'medium',
    internet_exposed: true,
    data_types: ['personal'],
    environment: 'production',
    agent_space_id: 'space-bookworm-prod',
    domains: ['search.bookworm.io'],
    repositories: ['rempart/demo/app-b'],
    team: 'Catalog Team',
    ticket_channel: 'jira',
    created_at: '2026-10-05T11:00:00Z'
  }
];

export const MOCK_RUNS: Run[] = [
  {
    run_id: 'run-2026-11-10-001',
    config_id: 'cfg-shoplite-delivery',
    app_id: 'app-shoplite-core',
    tenant_id: 'demo-tenant-shoplite',
    trigger: 'cicd',
    commit_from: 'a1b2c3d',
    commit_to: 'e4f5a6b',
    scope_decision: 'incremental: order routes modified in PR #42',
    status: 'completed',
    started_at: '2026-11-10T14:02:00Z',
    ended_at: '2026-11-10T14:18:30Z',
    duration_s: 990,
    task_hours: 0.275,
    cost_usd: 13.75
  },
  {
    run_id: 'run-2026-11-11-002',
    config_id: 'cfg-shoplite-full',
    app_id: 'app-shoplite-core',
    tenant_id: 'demo-tenant-shoplite',
    trigger: 'schedule',
    scope_decision: 'full pentest scheduled bi-weekly',
    status: 'running',
    started_at: '2026-11-11T08:00:00Z',
    ended_at: null,
    duration_s: 1800,
    task_hours: 0.5,
    cost_usd: 25.0
  }
];

export const MOCK_FINDINGS: Finding[] = [
  {
    finding_id: 'find-idor-shoplite-01',
    app_id: 'app-shoplite-core',
    tenant_id: 'demo-tenant-shoplite',
    run_id: 'run-2026-11-10-001',
    fingerprint: '3b8f8a1290bcde41',
    title: 'IDOR in Order Details Route (/orders/<id>)',
    risk_type: 'Broken Object Level Authorization (BOLA/IDOR)',
    severity: 'Critical',
    confidence: 'High',
    priority: 'P1',
    status: 'pending_validation',
    due_at: '2026-11-17T14:02:00Z',
    ticket_url: 'https://github.com/rempart/demo/issues/42',
    remediation_pr_url: 'https://github.com/rempart/demo/pull/43',
    evidence: {
      endpoint: '/orders/999',
      method: 'GET',
      payload: 'X-User-Id: attacker-42',
      vulnerable_code: 'models.py line 82: order = query_order(id)'
    },
    cvss: { score: 9.1, vector: 'CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N' },
    created_at: '2026-11-10T14:15:00Z',
    updated_at: '2026-11-10T14:16:00Z'
  },
  {
    finding_id: 'find-sqli-bookworm-02',
    app_id: 'app-bookworm-search',
    tenant_id: 'tenant-bookworm',
    run_id: 'run-2026-11-10-001',
    fingerprint: '98a4e101cf45aa23',
    title: 'SQL Injection in Book Catalog Search Parameter (q)',
    risk_type: 'SQL Injection (CWE-89)',
    severity: 'High',
    confidence: 'High',
    priority: 'P2',
    status: 'in_remediation',
    due_at: '2026-12-10T10:00:00Z',
    ticket_url: 'https://github.com/rempart/demo/issues/38',
    remediation_pr_url: 'https://github.com/rempart/demo/pull/39',
    evidence: { endpoint: '/search?q=test%27+OR+1=1--', method: 'GET' },
    cvss: { score: 8.6, vector: 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N' },
    created_at: '2026-11-08T10:00:00Z',
    updated_at: '2026-11-09T11:00:00Z'
  },
  {
    finding_id: 'find-sec-headers-03',
    app_id: 'app-shoplite-core',
    tenant_id: 'demo-tenant-shoplite',
    run_id: 'run-2026-11-10-001',
    fingerprint: '11fa78e90bc91234',
    title: 'Missing Strict-Transport-Security Header',
    risk_type: 'Security Misconfiguration',
    severity: 'Low',
    confidence: 'High',
    priority: 'P4',
    status: 'confirmed',
    due_at: null,
    ticket_url: null,
    remediation_pr_url: null,
    evidence: { missing: 'Strict-Transport-Security' },
    cvss: { score: 3.1, vector: 'CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:N/I:L/A:N' },
    created_at: '2026-11-05T09:00:00Z',
    updated_at: '2026-11-05T09:00:00Z'
  }
];

export const MOCK_DECISIONS: Decision[] = [
  {
    decision_id: 'dec-001',
    finding_id: 'find-idor-shoplite-01',
    author_type: 'agent',
    author: 'StrandsTriageAgent',
    action: 'confirmed',
    justification: 'IDOR verified on /orders/<id> accessing orders of other tenants.',
    created_at: '2026-11-10T14:16:00Z'
  }
];

export const MOCK_REPORTS: Report[] = [
  {
    report_id: 'rep-2026-10-shoplite',
    tenant_id: 'demo-tenant-shoplite',
    period: '2026-10',
    s3_key: 'reports/demo-tenant-shoplite/2026-10.pdf',
    kpis: {
      delivery_to_result_hours: 0.28,
      critical_blocked_before_prod: 1.0,
      sla_compliance: 0.98,
      coverage: 0.92,
      tests_total: 18,
      task_hours_used: 42.5
    },
    created_at: '2026-11-01T00:05:00Z'
  },
  {
    report_id: 'rep-2026-09-shoplite',
    tenant_id: 'demo-tenant-shoplite',
    period: '2026-09',
    s3_key: 'reports/demo-tenant-shoplite/2026-09.pdf',
    kpis: {
      delivery_to_result_hours: 0.32,
      critical_blocked_before_prod: 1.0,
      sla_compliance: 0.95,
      coverage: 0.88,
      tests_total: 14,
      task_hours_used: 36.0
    },
    created_at: '2026-10-01T00:05:00Z'
  }
];

export const MOCK_BUDGET: BudgetState = {
  tenant_id: 'demo-tenant-shoplite',
  month: '2026-11',
  hours_used: 48.5,
  thresholds_hit: [50],
  auto_stop: true
};

export const MOCK_KPIS: Kpis = {
  delivery_to_result_hours: 0.28,
  critical_blocked_before_prod: 1.0,
  mean_time_to_fix_days_by_priority: {
    P1: 4.2,
    P2: 18.5,
    P3: 45.0,
    P4: null
  },
  sla_compliance: 0.96,
  coverage: 0.94,
  reopen_rate: 0.04,
  findings_open_by_priority: {
    P1: 2,
    P2: 4,
    P3: 7,
    P4: 12
  },
  findings_closed: 48,
  tests_total: 62,
  tests_blocked: 3,
  task_hours_used: 124.5,
  cost_usd: 6225.0
};

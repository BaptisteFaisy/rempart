/**
 * Offline demo data — a single source of truth.
 *
 * Nothing here is hand-written fixture data: every value is read from the
 * frozen dataset `demo/seed/demo-dataset.json`, produced by
 * `scripts/seed_demo.py` and served verbatim by `scripts/serve_local.py`.
 * The portal therefore shows exactly the same rows whether it talks to the
 * local demo API or runs fully offline (`VITE_USE_MOCKS=1`).
 *
 * Numbers (KPIs) are derived deterministically in `deriveKpis()` from the same
 * dataset — never invented, never model-generated (ENF-IA-01).
 */
import seed from '../../../demo/seed/demo-dataset.json';
import {
  Application,
  BudgetState,
  Decision,
  Finding,
  Kpis,
  Priority,
  Report,
  Run,
  Tenant
} from '../types';

type SeedItems = Record<string, unknown>[];

const SEED = seed as unknown as Record<string, SeedItems>;

function collection<T>(key: string): T[] {
  return (SEED[key] ?? []) as unknown as T[];
}

export const DEMO_COLLECTIONS: readonly string[] = Object.keys(SEED);

export const DEMO_TENANTS: Tenant[] = collection<Tenant>('tenants');
export const DEMO_APPLICATIONS: Application[] = collection<Application>('applications');
export const DEMO_RUNS: Run[] = collection<Run>('runs');
export const DEMO_FINDINGS: Finding[] = collection<Finding>('findings');
export const DEMO_DECISIONS: Decision[] = collection<Decision>('decisions');
export const DEMO_REPORTS: Report[] = collection<Report>('reports');
export const DEMO_BUDGETS: BudgetState[] = collection<BudgetState>('budget');

/** Total number of items in the frozen dataset (used by the offline banner). */
export const DEMO_ITEM_COUNT: number = DEMO_COLLECTIONS.reduce(
  (total, key) => total + (SEED[key] ?? []).length,
  0
);

export const PRIORITIES: Priority[] = ['P1', 'P2', 'P3', 'P4'];

/** Statuses that keep a finding "open" (mirrors the backend lifecycle). */
const OPEN_STATUSES = new Set([
  'new',
  'pending_validation',
  'confirmed',
  'in_remediation',
  'to_retest',
  'reopened'
]);

function findingsFor(tenantId?: string): Finding[] {
  return tenantId
    ? DEMO_FINDINGS.filter((f) => f.tenant_id === tenantId)
    : DEMO_FINDINGS;
}

function runsFor(tenantId?: string): Run[] {
  return tenantId ? DEMO_RUNS.filter((r) => r.tenant_id === tenantId) : DEMO_RUNS;
}

function openByPriority(findings: Finding[]): Record<Priority, number> {
  const counts = { P1: 0, P2: 0, P3: 0, P4: 0 } as Record<Priority, number>;
  findings.forEach((f) => {
    if (OPEN_STATUSES.has(f.status)) counts[f.priority] += 1;
  });
  return counts;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

/** Hours between a run start and its result, for completed runs only. */
function deliveryToResultHours(runs: Run[]): number {
  const hours = runs
    .filter((r) => r.status === 'completed' && r.started_at && r.ended_at)
    .map((r) => (new Date(r.ended_at!).getTime() - new Date(r.started_at).getTime()) / 3_600_000);
  return Number(median(hours).toFixed(2));
}

/** Frozen KPI block already stored in the monthly report of the dataset. */
function reportKpis(tenantId?: string): Record<string, unknown> {
  const report = tenantId
    ? DEMO_REPORTS.find((r) => r.tenant_id === tenantId)
    : DEMO_REPORTS[DEMO_REPORTS.length - 1];
  return (report?.kpis ?? {}) as Record<string, unknown>;
}

function numberOr(value: unknown, fallback: number): number {
  return typeof value === 'number' ? value : fallback;
}

function ratio(part: number, total: number): number {
  return total === 0 ? 0 : Number((part / total).toFixed(2));
}

/**
 * Derive every KPI from the frozen dataset: counters come from the findings
 * and runs themselves, ratios and delays come from the stored monthly report.
 */
export function deriveKpis(tenantId?: string): Kpis {
  const findings = findingsFor(tenantId);
  const runs = runsFor(tenantId);
  const frozen = reportKpis(tenantId);
  const closed = findings.filter((f) => f.status === 'closed').length;
  const reopened = findings.filter((f) => f.status === 'reopened').length;
  const mttr = (frozen.mean_time_to_fix_days_by_priority ?? {}) as Record<string, number | null>;

  return {
    delivery_to_result_hours: numberOr(frozen.delivery_to_result_hours, deliveryToResultHours(runs)),
    critical_blocked_before_prod: numberOr(frozen.critical_blocked_before_prod, 0),
    mean_time_to_fix_days_by_priority: {
      P1: mttr.P1 ?? null,
      P2: mttr.P2 ?? null,
      P3: mttr.P3 ?? null,
      P4: mttr.P4 ?? null
    },
    sla_compliance: numberOr(frozen.sla_compliance, 0),
    coverage: numberOr(frozen.coverage, 0),
    reopen_rate: numberOr(frozen.reopen_rate, ratio(reopened, findings.length)),
    findings_open_by_priority: openByPriority(findings),
    findings_closed: closed,
    tests_total: runs.length,
    tests_blocked: runs.filter((r) => r.status === 'blocked').length,
    task_hours_used: numberOr(
      frozen.task_hours_used,
      runs.reduce((total, r) => total + (r.task_hours ?? 0), 0)
    ),
    cost_usd: numberOr(
      frozen.cost_usd,
      runs.reduce((total, r) => total + (r.cost_usd ?? 0), 0)
    )
  };
}

export function demoTenant(tenantId: string): Tenant | null {
  return DEMO_TENANTS.find((t) => t.tenant_id === tenantId) ?? null;
}

export function demoApplication(appId: string): Application | null {
  return DEMO_APPLICATIONS.find((a) => a.app_id === appId) ?? null;
}

export function demoRun(runId: string): Run | null {
  return DEMO_RUNS.find((r) => r.run_id === runId) ?? null;
}

export function demoFinding(findingId: string): Finding | null {
  return DEMO_FINDINGS.find((f) => f.finding_id === findingId) ?? null;
}

export function demoFindings(params?: {
  tenant_id?: string;
  app_id?: string;
  status?: string;
  priority?: string;
}): Finding[] {
  return DEMO_FINDINGS.filter(
    (f) =>
      (!params?.tenant_id || f.tenant_id === params.tenant_id) &&
      (!params?.app_id || f.app_id === params.app_id) &&
      (!params?.status || f.status === params.status) &&
      (!params?.priority || f.priority === params.priority)
  );
}

export function demoApplications(tenantId?: string): Application[] {
  return tenantId
    ? DEMO_APPLICATIONS.filter((a) => a.tenant_id === tenantId)
    : DEMO_APPLICATIONS;
}

export function demoRuns(appId?: string): Run[] {
  return appId ? DEMO_RUNS.filter((r) => r.app_id === appId) : DEMO_RUNS;
}

export function demoReports(tenantId?: string): Report[] {
  return tenantId ? DEMO_REPORTS.filter((r) => r.tenant_id === tenantId) : DEMO_REPORTS;
}

export function demoDecisions(findingId?: string): Decision[] {
  return findingId
    ? DEMO_DECISIONS.filter((d) => d.finding_id === findingId)
    : DEMO_DECISIONS;
}

export function demoBudget(tenantId: string): BudgetState {
  const state = DEMO_BUDGETS.find((b) => b.tenant_id === tenantId);
  return state ?? {
    tenant_id: tenantId,
    month: '2026-10',
    hours_used: 0,
    thresholds_hit: [],
    auto_stop: false
  };
}

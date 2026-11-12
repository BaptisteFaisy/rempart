/**
 * Offline readers for the governance datasets of the frozen demo.
 *
 * The frozen dataset (`demo/seed/demo-dataset.json`) is being extended with
 * the `audit`, `policy`, `evidence`, `industrialization` and `forecast`
 * collections. Every reader below returns `null` when its collection is
 * missing: the page then says "not available in the frozen dataset" instead
 * of showing an empty table that looks like a bug.
 */
import {
  AuditEvent,
  AuditPage,
  AuditQuery,
  BudgetForecast,
  EffectivePolicy,
  EvidencePack,
  Industrialization,
  TenantPolicy
} from '../types';
import { seedCollection, seedHas } from './mockData';
import { unwrapPayload } from './fields';

type Row = Record<string, unknown>;

function rows(key: string): Row[] {
  return seedCollection<Row>(key);
}

function rowFor(key: string, tenantId: string): Row | undefined {
  return rows(key).find((row) => row.tenant_id === tenantId);
}

function asRecord(value: unknown): Row {
  return typeof value === 'object' && value !== null ? (value as Row) : {};
}

/* ------------------------------------------------------------------ */
/* Audit journal                                                       */
/* ------------------------------------------------------------------ */

export function demoAudit(query?: AuditQuery): AuditPage | null {
  if (!seedHas('audit')) return null;
  let events = seedCollection<AuditEvent>('audit');
  if (query?.tenant_id) {
    events = events.filter((e) => !e.tenant_id || e.tenant_id === query.tenant_id);
  }
  if (query?.action) events = events.filter((e) => e.action === query.action);
  if (query?.actor) events = events.filter((e) => e.actor === query.actor);
  if (query?.object_type) events = events.filter((e) => e.object_type === query.object_type);
  if (query?.object_id) events = events.filter((e) => e.object_id === query.object_id);
  if (query?.since) events = events.filter((e) => e.created_at >= String(query.since));
  if (query?.until) events = events.filter((e) => e.created_at <= String(query.until));
  const offset = query?.offset ?? 0;
  const limit = query?.limit ?? events.length;
  const page = events.slice(offset, offset + limit);
  return {
    events: page,
    count: page.length,
    total: events.length,
    limit,
    offset,
    next_offset: offset + limit < events.length ? offset + limit : null,
    scan_truncated: false
  };
}

/* ------------------------------------------------------------------ */
/* Correction policy                                                   */
/* ------------------------------------------------------------------ */

const POLICY_FIELDS = ['due_days', 'matrix_overrides', 'blocking_threshold', 'hourly_rate'];

function policyValues(source: Row): Partial<EffectivePolicy> {
  const holder = asRecord(source.policy ?? source.effective ?? source);
  const values: Partial<EffectivePolicy> = {};
  for (const field of POLICY_FIELDS) {
    if (holder[field] !== undefined) {
      (values as Row)[field] = holder[field];
    }
  }
  return values;
}

export function demoPolicy(tenantId: string): TenantPolicy | null {
  if (!seedHas('policy')) return null;
  const row = rowFor('policy', tenantId);
  if (!row) return null;
  const policy = policyValues(row);
  const effective = {
    ...policy,
    ...policyValues(asRecord(row.effective))
  } as EffectivePolicy;
  return { tenant_id: tenantId, policy, effective };
}

export function demoPolicyDefaults(): EffectivePolicy | null {
  if (seedHas('policy_defaults')) {
    const row = rows('policy_defaults')[0];
    if (row) return policyValues(row) as EffectivePolicy;
  }
  if (!seedHas('policy')) return null;
  const shared = rows('policy').find(
    (row) => row.tenant_id === undefined || row.tenant_id === null || row.tenant_id === 'default'
  );
  return shared ? (policyValues(shared) as EffectivePolicy) : null;
}

/* ------------------------------------------------------------------ */
/* Evidence dossier                                                    */
/* ------------------------------------------------------------------ */

export function demoEvidence(tenantId: string, period?: string): EvidencePack | null {
  if (!seedHas('evidence')) return null;
  const candidates = rows('evidence');
  const row =
    candidates.find((r) => r.tenant_id === tenantId && (!period || r.period === period)) ??
    candidates.find((r) => r.tenant_id === tenantId);
  if (!row) return null;
  return unwrapPayload<EvidencePack>(row, ['pack', 'evidence', 'dossier']);
}

/* ------------------------------------------------------------------ */
/* Industrialization metrics                                           */
/* ------------------------------------------------------------------ */

export function demoIndustrialization(tenantId: string): Industrialization | null {
  if (!seedHas('industrialization')) return null;
  const row = rowFor('industrialization', tenantId);
  if (!row) return null;
  return unwrapPayload<Industrialization>(row, ['metrics', 'industrialization']);
}

/* ------------------------------------------------------------------ */
/* Budget forecast                                                     */
/* ------------------------------------------------------------------ */

export function demoForecast(tenantId: string): BudgetForecast | null {
  if (!seedHas('forecast')) return null;
  const row = rowFor('forecast', tenantId);
  if (!row) return null;
  return unwrapPayload<BudgetForecast>(row, ['forecast']);
}

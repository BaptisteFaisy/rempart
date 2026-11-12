import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { portalApi } from '../api/service';
import { AuditEvent } from '../types';
import { useTenantScope } from '../hooks/useTenantScope';
import { useAsyncData } from '../hooks/useAsyncData';
import { TenantPicker } from '../components/TenantPicker';
import { DataTable, Column } from '../components/DataTable';
import { Card } from '../components/Card';
import { DataUnavailable } from '../components/DataUnavailable';
import { KpiCard } from '../components/KpiCard';

interface Filters {
  action: string;
  actor: string;
  objectType: string;
}

const EMPTY_FILTERS: Filters = { action: '', actor: '', objectType: '' };

export function AuditPage() {
  const [searchParams] = useSearchParams();
  const { tenants, tenantId, setTenantId } = useTenantScope({
    allowAll: true,
    initial: searchParams.get('tenant')
  });
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);

  const { data, loading, error } = useAsyncData(
    () =>
      portalApi.getAudit({
        tenant_id: tenantId || undefined,
        action: filters.action || undefined,
        actor: filters.actor || undefined,
        object_type: filters.objectType || undefined
      }),
    [tenantId, filters.action, filters.actor, filters.objectType]
  );

  return (
    <div className="container">
      <h1 style={{ marginBottom: 8 }}>Audit Journal</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: 16 }}>
        Every action taken on the platform, with its actor and its target.{' '}
        <strong data-testid="audit-readonly-note">
          This journal is not modifiable: entries are written by the platform and never edited
          nor deleted (ENF-SEC-06).
        </strong>
      </p>

      <TenantPicker tenants={tenants} value={tenantId} onChange={setTenantId} allowAll />
      <AuditFilters
        draft={draft}
        onDraft={setDraft}
        onApply={() => setFilters(draft)}
        onReset={() => {
          setDraft(EMPTY_FILTERS);
          setFilters(EMPTY_FILTERS);
        }}
      />
      {error ? <div className="card">{error}</div> : null}

      {loading ? (
        <div style={{ marginTop: 16 }}>Loading audit journal...</div>
      ) : data === null ? (
        <div style={{ marginTop: 16 }}>
          <DataUnavailable feature="Audit journal" datasetKey="audit" />
        </div>
      ) : (
        <AuditResults page={data} />
      )}
    </div>
  );
}

interface AuditFiltersProps {
  draft: Filters;
  onDraft: (filters: Filters) => void;
  onApply: () => void;
  onReset: () => void;
}

function AuditFilters({ draft, onDraft, onApply, onReset }: AuditFiltersProps) {
  const fields: { id: string; label: string; key: keyof Filters }[] = [
    { id: 'audit-filter-action', label: 'Action', key: 'action' },
    { id: 'audit-filter-actor', label: 'Actor', key: 'actor' },
    { id: 'audit-filter-object', label: 'Object type', key: 'objectType' }
  ];
  return (
    <Card title="Filters">
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        {fields.map((field) => (
          <div key={field.id} className="form-group" style={{ marginBottom: 0, minWidth: 180 }}>
            <label htmlFor={field.id}>{field.label}</label>
            <input
              id={field.id}
              className="form-control"
              value={draft[field.key]}
              onChange={(e) => onDraft({ ...draft, [field.key]: e.target.value })}
              placeholder={`${field.label} (exact match)`}
            />
          </div>
        ))}
        <button className="btn btn-primary" onClick={onApply}>
          Apply filters
        </button>
        <button className="btn btn-secondary" onClick={onReset}>
          Reset
        </button>
      </div>
    </Card>
  );
}

interface JournalPage {
  events: AuditEvent[];
  count: number;
  total: number;
  scan_truncated?: boolean;
}

function AuditResults({ page }: { page: JournalPage }) {
  return (
    <div style={{ marginTop: 16 }}>
      <div className="grid-cols-4">
        <KpiCard label="Matching events" value={page.total} sub="Journal entries" />
        <KpiCard label="Shown" value={page.count} sub="Current page" />
        <KpiCard
          label="Truncated scan"
          value={page.scan_truncated ? 'YES' : 'NO'}
          sub="Journal larger than the scan window"
          tone={page.scan_truncated ? 'warn' : 'default'}
        />
        <KpiCard label="Writable" value="NO" sub="Read-only journal" tone="good" />
      </div>
      <Card title={`Journal entries (${page.count})`} style={{ marginTop: 16 }}>
        <DataTable columns={COLUMNS} data={page.events} keyField="audit_id" />
      </Card>
    </div>
  );
}

const COLUMNS: Column<AuditEvent>[] = [
  { key: 'created_at', header: 'When' },
  { key: 'actor', header: 'Actor' },
  { key: 'action', header: 'Action' },
  { key: 'object_type', header: 'Object type' },
  { key: 'object_id', header: 'Object' },
  { key: 'result', header: 'Result' }
];

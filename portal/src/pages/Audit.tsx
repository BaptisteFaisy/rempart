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

  const columns: Column<AuditEvent>[] = [
    { key: 'created_at', header: 'When' },
    { key: 'actor', header: 'Actor' },
    { key: 'action', header: 'Action' },
    { key: 'object_type', header: 'Object type' },
    { key: 'object_id', header: 'Object' },
    { key: 'result', header: 'Result' }
  ];

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

      <Card title="Filters">
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <FilterField
            id="audit-filter-action"
            label="Action"
            value={draft.action}
            onChange={(v) => setDraft({ ...draft, action: v })}
          />
          <FilterField
            id="audit-filter-actor"
            label="Actor"
            value={draft.actor}
            onChange={(v) => setDraft({ ...draft, actor: v })}
          />
          <FilterField
            id="audit-filter-object"
            label="Object type"
            value={draft.objectType}
            onChange={(v) => setDraft({ ...draft, objectType: v })}
          />
          <button className="btn btn-primary" onClick={() => setFilters(draft)}>
            Apply filters
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => {
              setDraft(EMPTY_FILTERS);
              setFilters(EMPTY_FILTERS);
            }}
          >
            Reset
          </button>
        </div>
      </Card>

      {error ? <div className="card" style={{ marginTop: 16 }}>{error}</div> : null}

      {loading ? (
        <div style={{ marginTop: 16 }}>Loading audit journal...</div>
      ) : data === null ? (
        <div style={{ marginTop: 16 }}>
          <DataUnavailable feature="Audit journal" datasetKey="audit" />
        </div>
      ) : (
        <AuditResults page={data} columns={columns} />
      )}
    </div>
  );
}

function FilterField(props: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="form-group" style={{ marginBottom: 0, minWidth: 180 }}>
      <label htmlFor={props.id}>{props.label}</label>
      <input
        id={props.id}
        className="form-control"
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        placeholder={`${props.label} (exact match)`}
      />
    </div>
  );
}

function AuditResults(props: {
  page: { events: AuditEvent[]; count: number; total: number; scan_truncated?: boolean };
  columns: Column<AuditEvent>[];
}) {
  const { page, columns } = props;
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
        <DataTable columns={columns} data={page.events} keyField="audit_id" />
      </Card>
    </div>
  );
}

import { useState } from 'react';
import { portalApi } from '../api/service';
import { EvidenceChain, EvidenceClosureProof, EvidenceException, EvidencePack } from '../types';
import { useTenantScope } from '../hooks/useTenantScope';
import { useAsyncData } from '../hooks/useAsyncData';
import { useApiAction } from '../hooks/useApiAction';
import { TenantPicker } from '../components/TenantPicker';
import { Card } from '../components/Card';
import { DetailList } from '../components/DetailList';
import { DataUnavailable } from '../components/DataUnavailable';
import { KpiCard } from '../components/KpiCard';
import { ActionNotice } from '../components/ActionNotice';
import { DataTable, Column } from '../components/DataTable';

const text = (value: unknown): string =>
  value === null || value === undefined ? '—' : String(value);

export function EvidencePage() {
  const { tenants, tenantId, setTenantId } = useTenantScope();
  const action = useApiAction();
  const [period, setPeriod] = useState('');

  const { data: pack, loading, error, setData } = useAsyncData(
    () => portalApi.getEvidence(tenantId, period || undefined),
    [tenantId, period]
  );

  const generate = async () => {
    const generated = await action.run(
      () => portalApi.postEvidence(tenantId, period || undefined),
      'Evidence dossier generated (POST /v1/tenants/{id}/evidence).'
    );
    if (generated) setData(generated);
  };

  return (
    <div className="container">
      <h1 style={{ marginBottom: 8 }}>Evidence Dossier</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: 20 }}>
        Exportable proof pack for auditors (EF-RAP-04, ISO 27001 / SOC 2): scope, tests, decision
        chain of every finding, closure proofs, exceptions and the frozen audit journal — sealed
        with a SHA-256 fingerprint any third party can recompute.
      </p>

      <TenantPicker tenants={tenants} value={tenantId} onChange={setTenantId} />
      <PeriodPicker period={period} onChange={setPeriod} onGenerate={generate} busy={action.busy} />
      <ActionNotice message={action.message} error={action.error} />
      {error ? <div className="card">{error}</div> : null}

      {loading ? (
        <div>Loading evidence dossier...</div>
      ) : pack === null ? (
        <DataUnavailable feature="Evidence dossier" datasetKey="evidence" />
      ) : (
        <EvidenceBody pack={pack} />
      )}
    </div>
  );
}

function PeriodPicker(props: {
  period: string;
  busy: boolean;
  onChange: (period: string) => void;
  onGenerate: () => void;
}) {
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginBottom: 16 }}>
      <div className="form-group" style={{ marginBottom: 0 }}>
        <label htmlFor="evidence-period">Period (YYYY-MM, empty = latest)</label>
        <input
          id="evidence-period"
          className="form-control"
          placeholder="2026-10"
          value={props.period}
          onChange={(e) => props.onChange(e.target.value)}
        />
      </div>
      <button
        className="btn btn-primary"
        onClick={props.onGenerate}
        disabled={props.busy}
        data-testid="evidence-generate"
      >
        {props.busy ? 'Generating...' : 'Generate dossier'}
      </button>
    </div>
  );
}

function EvidenceBody({ pack }: { pack: EvidencePack }) {
  const identity = pack.identity ?? {};
  const chains = pack.decision_chains ?? [];
  const proofs = pack.closure_proofs ?? [];
  const exceptions = pack.exceptions ?? {};
  const falsePositives = exceptions.false_positives ?? [];
  const riskAccepted = exceptions.risk_accepted ?? [];

  return (
    <>
      <IntegrityCard pack={pack} />
      <div className="grid-cols-4" style={{ marginTop: 16 }}>
        <KpiCard label="Applications in scope" value={(pack.scope ?? []).length} sub="Tested surface" />
        <KpiCard label="Tests on the period" value={(pack.tests ?? []).length} sub="Runs performed" />
        <KpiCard label="Decision chains" value={chains.length} sub="Findings with a traced verdict" />
        <KpiCard
          label="Audit events"
          value={(pack.audit_events ?? []).length}
          sub="Frozen journal of the period"
        />
      </div>

      <Card title="Summary" style={{ marginTop: 16 }}>
        <DetailList
          items={[
            { label: 'Product', value: text(identity.product) },
            { label: 'Dossier version', value: text(identity.evidence_version) },
            { label: 'Client', value: text(identity.tenant_name) },
            { label: 'Period', value: text(identity.period) },
            { label: 'Generated at', value: text(identity.generated_at) },
            { label: 'Mandate status', value: text(identity.mandate_status) },
            { label: 'Plan', value: text(identity.plan) }
          ]}
        />
      </Card>

      <Card title={`Decision chain per finding (${chains.length})`} style={{ marginTop: 16 }}>
        <DataTable
          columns={CHAIN_COLUMNS}
          data={chains}
          rowKey={(row, index) => String(row.finding?.finding_id ?? index)}
        />
      </Card>

      <Card title={`Closure proofs (${proofs.length})`} style={{ marginTop: 16 }}>
        <DataTable columns={PROOF_COLUMNS} data={proofs} keyField="finding_id" />
      </Card>

      <Card title={`Exceptions — false positives (${falsePositives.length})`} style={{ marginTop: 16 }}>
        <DataTable columns={EXCEPTION_COLUMNS} data={falsePositives} keyField="finding_id" />
      </Card>

      <Card title={`Exceptions — accepted risks (${riskAccepted.length})`} style={{ marginTop: 16 }}>
        <DataTable columns={EXCEPTION_COLUMNS} data={riskAccepted} keyField="finding_id" />
      </Card>
    </>
  );
}

function IntegrityCard({ pack }: { pack: EvidencePack }) {
  const integrity = pack.integrity;
  return (
    <Card title="Integrity seal (SHA-256)">
      {integrity?.digest ? (
        <DetailList
          items={[
            {
              label: 'Fingerprint',
              value: <code data-testid="evidence-digest">{integrity.digest}</code>
            },
            { label: 'Algorithm', value: text(integrity.algorithm) },
            { label: 'Canonical form', value: text(integrity.canonical_form) },
            { label: 'Recompute', value: text(integrity.recompute) }
          ]}
        />
      ) : (
        <DataUnavailable feature="Integrity fingerprint" />
      )}
    </Card>
  );
}

const CHAIN_COLUMNS: Column<EvidenceChain>[] = [
  {
    key: 'finding',
    header: 'Finding',
    render: (row) => `${text(row.finding?.finding_id)} — ${text(row.finding?.title)}`
  },
  { key: 'priority', header: 'Priority', render: (row) => text(row.finding?.priority) },
  { key: 'status', header: 'Status', render: (row) => text(row.finding?.status) },
  {
    key: 'decisions',
    header: 'Decision chain (agent → human)',
    render: (row) =>
      (row.decisions ?? [])
        .map((d) => `${d.author_type ?? '?'}:${d.action ?? '?'}`)
        .join(' → ') || '—'
  }
];

const PROOF_COLUMNS: Column<EvidenceClosureProof>[] = [
  { key: 'finding_id', header: 'Finding' },
  { key: 'title', header: 'Title' },
  { key: 'priority', header: 'Priority' },
  { key: 'closed_at', header: 'Closed at' },
  { key: 'proven_by_run_id', header: 'Proven by retest run' }
];

const EXCEPTION_COLUMNS: Column<EvidenceException>[] = [
  { key: 'finding_id', header: 'Finding' },
  { key: 'title', header: 'Title' },
  { key: 'severity', header: 'Severity' },
  { key: 'priority', header: 'Priority' },
  { key: 'decided_by', header: 'Decided by', render: (row) => (row.decided_by ?? []).join(', ') },
  { key: 'decided_at', header: 'Decided at', render: (row) => (row.decided_at ?? []).join(', ') }
];

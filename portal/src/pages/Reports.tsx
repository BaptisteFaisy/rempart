import { CSSProperties, useState } from 'react';
import { Report } from '../types';
import { portalApi } from '../api/service';
import { downloadJson } from '../api/download';
import { useTenantScope } from '../hooks/useTenantScope';
import { useAsyncData } from '../hooks/useAsyncData';
import { useApiAction } from '../hooks/useApiAction';
import { DataTable, Column } from '../components/DataTable';
import { Card } from '../components/Card';
import { ActionNotice } from '../components/ActionNotice';
import { TenantPicker } from '../components/TenantPicker';

export function Reports() {
  const { tenants, tenantId, setTenantId } = useTenantScope({ allowAll: true });
  const action = useApiAction();
  const [selected, setSelected] = useState<Report | null>(null);

  const { data: reports, loading, error } = useAsyncData(
    () => portalApi.getReports(tenantId || undefined),
    [tenantId]
  );

  const inspect = async (reportId: string) => {
    const report = await action.run(
      () => portalApi.getReport(reportId),
      'Report loaded (GET /v1/reports/{id}).'
    );
    if (report) setSelected(report);
  };

  const downloadEvidence = async () => {
    if (!tenantId) return;
    const pack = await action.run(async () => {
      const dossier = await portalApi.getEvidence(tenantId);
      if (!dossier) throw new Error('Evidence dossier not available for this client');
      return dossier;
    }, 'Evidence dossier downloaded (GET /v1/tenants/{id}/evidence).');
    if (pack) downloadJson(`evidence-${tenantId}.json`, pack);
  };

  const columns: Column<Report>[] = [
    { key: 'period', header: 'Period (Month)' },
    { key: 'tenant_id', header: 'Tenant' },
    { key: 'created_at', header: 'Generated At' },
    {
      key: 'actions',
      header: 'Actions',
      render: (report) => (
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn btn-secondary"
            onClick={() => inspect(report.report_id)}
            data-testid="report-inspect"
          >
            Inspect Telemetry
          </button>
          <a
            className="btn btn-primary"
            href={`#download-${report.report_id}`}
            onClick={(e) => {
              e.preventDefault();
              alert(`Simulated download from S3: s3://${report.s3_key}`);
            }}
          >
            Download PDF
          </a>
        </div>
      )
    }
  ];

  return (
    <div className="container">
      <h1 style={{ marginBottom: 8 }}>Monthly Executive Reports</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: 20 }}>
        Deterministic frozen metrics and executive summaries generated on the 1st of each month,
        plus the exportable evidence dossier (EF-RAP-04).
      </p>

      <TenantPicker tenants={tenants} value={tenantId} onChange={setTenantId} allowAll />
      <ActionNotice message={action.message} error={action.error} />

      <Card title="Evidence dossier" style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            className="btn btn-primary"
            onClick={downloadEvidence}
            disabled={action.busy || !tenantId}
            data-testid="evidence-download"
          >
            {action.busy ? 'Working...' : 'Download the evidence dossier (JSON)'}
          </button>
          <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Sealed with a SHA-256 fingerprint; select a client first.
          </span>
        </div>
      </Card>

      {error ? <div className="card" style={{ marginTop: 16 }}>{error}</div> : null}

      {loading ? (
        <div style={{ marginTop: 16 }}>Loading reports...</div>
      ) : (
        <Card title={`Reports (${reports?.length ?? 0})`} style={{ marginTop: 16 }}>
          <DataTable columns={columns} data={reports ?? []} keyField="report_id" />
        </Card>
      )}

      {selected ? (
        <Card
          title={`Report Metrics — Period ${selected.period}`}
          style={{ marginTop: 24 }}
          actions={
            <button className="btn btn-secondary" onClick={() => setSelected(null)}>
              Close
            </button>
          }
        >
          <pre style={PRE_STYLE}>{JSON.stringify(selected.kpis, null, 2)}</pre>
        </Card>
      ) : null}
    </div>
  );
}

const PRE_STYLE: CSSProperties = {
  background: 'var(--bg-secondary)',
  padding: 12,
  borderRadius: 6,
  overflowX: 'auto',
  fontSize: '0.9rem'
};

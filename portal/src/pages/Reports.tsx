import { useEffect, useState } from 'react';
import { Report } from '../types';
import { portalApi } from '../api/service';
import { DataTable, Column } from '../components/DataTable';
import { useSession } from '../hooks/useSession';

export function Reports() {
  const { session } = useSession();
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedReport, setSelectedReport] = useState<Report | null>(null);

  useEffect(() => {
    portalApi
      .getReports(session.tenant_id)
      .then((res) => {
        setReports(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [session.tenant_id]);

  const columns: Column<Report>[] = [
    { key: 'period', header: 'Period (Month)' },
    { key: 'tenant_id', header: 'Tenant' },
    { key: 'created_at', header: 'Generated At' },
    {
      key: 'actions',
      header: 'Actions',
      render: (r) => (
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-secondary" onClick={() => setSelectedReport(r)}>
            Inspect Telemetry
          </button>
          <a
            className="btn btn-primary"
            href={`#download-${r.report_id}`}
            onClick={(e) => {
              e.preventDefault();
              alert(`Simulated download from S3: s3://${r.s3_key}`);
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
        Deterministic frozen metrics and GenAI executive summaries generated on the 1st of each month.
      </p>

      {loading ? (
        <div>Loading reports...</div>
      ) : (
        <div className="card">
          <DataTable
            columns={columns}
            data={reports}
            keyField="report_id"
          />
        </div>
      )}

      {selectedReport ? (
        <div className="card" style={{ marginTop: 24 }}>
          <div className="card-title">
            <span>Report Metrics &mdash; Period {selectedReport.period}</span>
            <button className="btn btn-secondary" onClick={() => setSelectedReport(null)}>
              Close
            </button>
          </div>
          <pre
            style={{
              background: 'var(--bg-secondary)',
              padding: 12,
              borderRadius: 6,
              overflowX: 'auto',
              fontSize: '0.9rem'
            }}
          >
            {JSON.stringify(selectedReport.kpis, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

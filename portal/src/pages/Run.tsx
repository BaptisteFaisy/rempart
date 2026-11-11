import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Run, Finding } from '../types';
import { portalApi } from '../api/service';
import { DataTable, Column } from '../components/DataTable';
import { PriorityBadge, FindingStatusBadge, RunStatusBadge } from '../components/Badges';

export function RunPage() {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<Run | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    if (!runId) return;
    portalApi.getRun(runId).then(async (r) => {
      setRun(r);
      if (r) {
        const allFindings = await portalApi.getFindings({ app_id: r.app_id });
        setFindings(allFindings.filter((f) => f.run_id === r.run_id));
      }
      setLoading(false);
    });
  }, [runId]);

  if (loading) return <div className="container">Loading run details...</div>;
  if (!run) return <div className="container">Run not found.</div>;

  const findingColumns: Column<Finding>[] = [
    {
      key: 'priority',
      header: 'Priority',
      render: (f) => <PriorityBadge priority={f.priority} />
    },
    { key: 'title', header: 'Title' },
    { key: 'risk_type', header: 'Risk Type' },
    { key: 'severity', header: 'Severity' },
    {
      key: 'status',
      header: 'Status',
      render: (f) => <FindingStatusBadge status={f.status} />
    }
  ];

  return (
    <div className="container">
      <div style={{ marginBottom: 16 }}>
        <Link to={`/applications/${run.app_id}`}>&larr; Back to Application</Link>
      </div>

      <h1 style={{ marginBottom: 20 }}>Run {run.run_id}</h1>

      <div className="card">
        <div className="card-title">
          Execution Telemetry <RunStatusBadge status={run.status} />
        </div>
        <div className="grid-cols-2">
          <div>
            <p><strong>Config ID:</strong> {run.config_id}</p>
            <p><strong>Trigger:</strong> {run.trigger}</p>
            <p><strong>Scope Decision:</strong> {run.scope_decision || 'default'}</p>
            <p><strong>Commits:</strong> {run.commit_from || '—'} &rarr; {run.commit_to || '—'}</p>
          </div>
          <div>
            <p><strong>Started At:</strong> {run.started_at}</p>
            <p><strong>Ended At:</strong> {run.ended_at || 'In progress'}</p>
            <p><strong>Duration:</strong> {run.duration_s ? `${Math.round(run.duration_s / 60)} min (${run.duration_s}s)` : '—'}</p>
            <p><strong>Task Hours:</strong> {run.task_hours ?? '—'} h</p>
            <p><strong>Estimated Cost:</strong> {run.cost_usd !== null && run.cost_usd !== undefined ? `$${run.cost_usd.toFixed(2)}` : '—'}</p>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">Detected Findings ({findings.length})</div>
        <DataTable
          columns={findingColumns}
          data={findings}
          keyField="finding_id"
          onRowClick={(f) => navigate(`/findings/${String(f.finding_id)}`)}
        />
      </div>
    </div>
  );
}

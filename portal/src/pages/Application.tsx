import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Application, Run } from '../types';
import { portalApi } from '../api/service';
import { DataTable, Column } from '../components/DataTable';
import { RunStatusBadge } from '../components/Badges';

export function ApplicationPage() {
  const { appId } = useParams<{ appId: string }>();
  const [app, setApp] = useState<Application | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    if (!appId) return;
    Promise.all([portalApi.getApplication(appId), portalApi.getRuns(appId)]).then(([a, r]) => {
      setApp(a);
      setRuns(r);
      setLoading(false);
    });
  }, [appId]);

  if (loading) return <div className="container">Loading application details...</div>;
  if (!app) return <div className="container">Application not found.</div>;

  const runColumns: Column<Run>[] = [
    { key: 'run_id', header: 'Run ID' },
    { key: 'trigger', header: 'Trigger' },
    {
      key: 'status',
      header: 'Status',
      render: (r) => <RunStatusBadge status={r.status} />
    },
    { key: 'started_at', header: 'Started At' },
    {
      key: 'task_hours',
      header: 'Task Hours',
      render: (r) => (r.task_hours !== undefined && r.task_hours !== null ? `${r.task_hours}h` : '—')
    },
    {
      key: 'cost_usd',
      header: 'Est. Cost',
      render: (r) => (r.cost_usd !== undefined && r.cost_usd !== null ? `$${r.cost_usd.toFixed(2)}` : '—')
    }
  ];

  return (
    <div className="container">
      <div style={{ marginBottom: 16 }}>
        <Link to={`/tenants/${app.tenant_id}`}>&larr; Back to Tenant</Link>
      </div>

      <h1 style={{ marginBottom: 20 }}>{app.name}</h1>

      <div className="grid-cols-2">
        <div className="card">
          <div className="card-title">Application Profile</div>
          <p><strong>App ID:</strong> {app.app_id}</p>
          <p><strong>Criticality:</strong> {app.criticality}</p>
          <p><strong>Internet Exposed:</strong> {app.internet_exposed ? 'Yes' : 'No'}</p>
          <p><strong>Data Types:</strong> {app.data_types.join(', ') || 'none'}</p>
          <p><strong>Environment:</strong> {app.environment}</p>
          <p><strong>Owner Team:</strong> {app.team}</p>
          <p><strong>Ticket Channel:</strong> {app.ticket_channel}</p>
        </div>

        <div className="card">
          <div className="card-title">Scope & Repositories</div>
          <p><strong>Agent Space ID:</strong> {app.agent_space_id || 'Pending provisioning'}</p>
          <p style={{ marginTop: 8 }}><strong>Target Domains:</strong></p>
          <ul style={{ marginLeft: 20, marginBottom: 10 }}>
            {app.domains.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
          <p><strong>Repositories:</strong></p>
          <ul style={{ marginLeft: 20 }}>
            {app.repositories.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      </div>

      <div className="card">
        <div className="card-title">Pentest Run History ({runs.length})</div>
        <DataTable
          columns={runColumns}
          data={runs}
          keyField="run_id"
          onRowClick={(r) => navigate(`/runs/${String(r.run_id)}`)}
        />
      </div>
    </div>
  );
}

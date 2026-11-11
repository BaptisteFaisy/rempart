import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Tenant, Application } from '../types';
import { portalApi } from '../api/service';
import { DataTable, Column } from '../components/DataTable';

export function TenantPage() {
  const { tenantId } = useParams<{ tenantId: string }>();
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [apps, setApps] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    if (!tenantId) return;
    Promise.all([portalApi.getTenant(tenantId), portalApi.getApplications(tenantId)]).then(
      ([t, a]) => {
        setTenant(t);
        setApps(a);
        setLoading(false);
      }
    );
  }, [tenantId]);

  if (loading) return <div className="container">Loading client details...</div>;
  if (!tenant) return <div className="container">Client not found.</div>;

  const appColumns: Column<Application>[] = [
    { key: 'app_id', header: 'App ID' },
    { key: 'name', header: 'Name' },
    { key: 'criticality', header: 'Criticality' },
    {
      key: 'internet_exposed',
      header: 'Exposed',
      render: (a) => (a.internet_exposed ? 'Yes' : 'Internal')
    },
    { key: 'environment', header: 'Environment' },
    { key: 'team', header: 'Owner Team' }
  ];

  return (
    <div className="container">
      <div style={{ marginBottom: 16 }}>
        <Link to="/fleet">&larr; Back to Fleet</Link>
      </div>

      <h1 style={{ marginBottom: 20 }}>{tenant.name}</h1>

      <div className="grid-cols-2">
        <div className="card">
          <div className="card-title">Client Profile</div>
          <p><strong>Tenant ID:</strong> {tenant.tenant_id}</p>
          <p><strong>AWS Account:</strong> {tenant.aws_account_id || '—'} ({tenant.region || 'eu-west-3'})</p>
          <p><strong>Plan:</strong> {tenant.plan}</p>
          <p><strong>Mandate Status:</strong> {tenant.mandate_status}</p>
          <p><strong>Monthly Budget:</strong> {tenant.monthly_budget_hours} task hours</p>
          <div style={{ marginTop: 12 }}>
            <Link to={`/budget?tenant=${tenant.tenant_id}`} className="btn btn-secondary">
              View Budget & Limits
            </Link>
          </div>
        </div>

        <div className="card">
          <div className="card-title">Security Contacts</div>
          {tenant.contacts.length === 0 ? (
            <p style={{ color: 'var(--text-muted)' }}>No contacts listed.</p>
          ) : (
            <ul style={{ listStyle: 'none' }}>
              {tenant.contacts.map((c, idx) => (
                <li key={idx} style={{ marginBottom: 8 }}>
                  <strong>{c.name}</strong> ({c.role || 'Contact'}) &mdash; {c.email}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-title">Applications ({apps.length})</div>
        <DataTable
          columns={appColumns}
          data={apps}
          keyField="app_id"
          onRowClick={(a) => navigate(`/applications/${String(a.app_id)}`)}
        />
      </div>
    </div>
  );
}

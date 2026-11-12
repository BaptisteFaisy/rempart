import { useNavigate, useParams, Link } from 'react-router-dom';
import { Application, Kpis, Tenant } from '../types';
import { portalApi } from '../api/service';
import { canWrite } from '../types/constants';
import { useSession } from '../hooks/useSession';
import { useAsyncData } from '../hooks/useAsyncData';
import { useApiAction } from '../hooks/useApiAction';
import { DataTable, Column } from '../components/DataTable';
import { Card } from '../components/Card';
import { DetailList } from '../components/DetailList';
import { KpiCard } from '../components/KpiCard';
import { ActionNotice } from '../components/ActionNotice';
import { MandateBadge } from '../components/Badges';

export function TenantPage() {
  const { tenantId } = useParams<{ tenantId: string }>();
  const navigate = useNavigate();
  const { session } = useSession();
  const action = useApiAction();
  const id = tenantId ?? '';

  const { data: tenant, loading, error } = useAsyncData(
    () => (id ? portalApi.getTenant(id) : Promise.resolve(null)),
    [id]
  );
  const { data: apps } = useAsyncData(
    () => (id ? portalApi.getApplications(id) : Promise.resolve([])),
    [id]
  );
  const { data: kpis } = useAsyncData(
    () => (id && session.role !== 'demo' ? portalApi.getTenantKpis(id) : Promise.resolve(null)),
    [id, session.role]
  );

  const generateReport = async () => {
    const report = await action.run(
      () => portalApi.postReport(id),
      'Monthly report generated (POST /v1/tenants/{id}/reports).'
    );
    if (report) navigate('/reports');
  };

  if (loading) return <div className="container">Loading client details...</div>;
  if (error) return <div className="container">{error}</div>;
  if (!tenant) return <div className="container">Client not found.</div>;

  return (
    <div className="container">
      <div style={{ marginBottom: 16 }}>
        <Link to="/fleet">&larr; Back to Fleet</Link>
      </div>

      <h1 style={{ marginBottom: 8 }}>{tenant.name}</h1>
      <div style={{ marginBottom: 16 }}>
        <MandateBadge status={tenant.mandate_status} />
      </div>

      <ActionNotice message={action.message} error={action.error} />

      <div className="grid-cols-2" style={{ marginTop: 16 }}>
        <Card title="Client Profile">
          <DetailList
            items={[
              { label: 'Tenant ID', value: tenant.tenant_id },
              {
                label: 'AWS account',
                value: `${tenant.aws_account_id || '—'} (${tenant.region || 'eu-west-3'})`
              },
              { label: 'Plan', value: tenant.plan },
              { label: 'Mandate status', value: tenant.mandate_status },
              { label: 'Monthly budget', value: `${tenant.monthly_budget_hours} task hours` },
              { label: 'Free tier confirmed', value: tenant.free_tier_confirmed ? 'yes' : 'no' },
              { label: 'Created at', value: tenant.created_at }
            ]}
          />
          <TenantLinks tenantId={tenant.tenant_id} />
        </Card>

        <Card title="Security Contacts">
          <Contacts contacts={tenant.contacts} />
        </Card>
      </div>

      <TenantKpis kpis={kpis} />

      <Card title="Reports & Evidence" style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button
            className="btn btn-primary"
            onClick={generateReport}
            disabled={action.busy || !canWrite(session.role)}
            data-testid="generate-report"
          >
            {action.busy ? 'Working...' : 'Generate the monthly report'}
          </button>
          <Link to="/reports" className="btn btn-secondary">
            Open reports & evidence downloads
          </Link>
        </div>
        {!canWrite(session.role) ? (
          <div style={{ marginTop: 8, color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Report generation needs a write-capable role.
          </div>
        ) : null}
      </Card>

      <Card title={`Applications (${apps?.length ?? 0})`} style={{ marginTop: 16 }}>
        <DataTable
          columns={APP_COLUMNS}
          data={apps ?? []}
          keyField="app_id"
          onRowClick={(app) => navigate(`/applications/${app.app_id}`)}
        />
      </Card>
    </div>
  );
}

function TenantLinks({ tenantId }: { tenantId: string }) {
  const links = [
    { to: `/budget?tenant=${tenantId}`, label: 'Budget & limits' },
    { to: `/audit?tenant=${tenantId}`, label: 'Audit journal' },
    { to: '/policy', label: 'Contract policy' },
    { to: '/evidence', label: 'Evidence dossier' },
    { to: '/industrialization', label: 'Industrialization' }
  ];
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
      {links.map((link) => (
        <Link key={link.to} to={link.to} className="btn btn-secondary">
          {link.label}
        </Link>
      ))}
    </div>
  );
}

function Contacts({ contacts }: { contacts: Tenant['contacts'] }) {
  if (contacts.length === 0) {
    return <p style={{ color: 'var(--text-muted)' }}>No contacts listed.</p>;
  }
  return (
    <ul style={{ listStyle: 'none' }}>
      {contacts.map((contact, index) => (
        <li key={index} style={{ marginBottom: 8 }}>
          <strong>{contact.name}</strong> ({contact.role || 'Contact'}) &mdash; {contact.email}
        </li>
      ))}
    </ul>
  );
}

function TenantKpis({ kpis }: { kpis: Kpis | null }) {
  if (!kpis) return null;
  return (
    <div className="grid-cols-4" style={{ marginTop: 16 }} data-testid="tenant-kpis">
      <KpiCard
        label="Delivery to result"
        value={`${kpis.delivery_to_result_hours.toFixed(2)} h`}
        sub="Median run → result"
      />
      <KpiCard label="SLA compliance" value={`${Math.round(kpis.sla_compliance * 100)}%`} sub="Remediation SLA" />
      <KpiCard label="Coverage" value={`${Math.round(kpis.coverage * 100)}%`} sub="Attack surface tested" />
      <KpiCard
        label="Task hours used"
        value={`${kpis.task_hours_used.toFixed(1)} h`}
        sub={`$${kpis.cost_usd.toFixed(0)} estimated cost`}
      />
    </div>
  );
}

const APP_COLUMNS: Column<Application>[] = [
  { key: 'app_id', header: 'App ID' },
  { key: 'name', header: 'Name' },
  { key: 'criticality', header: 'Criticality' },
  {
    key: 'internet_exposed',
    header: 'Exposed',
    render: (app) => (app.internet_exposed ? 'Yes' : 'Internal')
  },
  { key: 'environment', header: 'Environment' },
  { key: 'team', header: 'Owner Team' }
];

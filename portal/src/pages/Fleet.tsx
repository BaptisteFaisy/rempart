import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Tenant, Kpis } from '../types';
import { portalApi } from '../api/service';
import { KpiCard } from '../components/KpiCard';
import { DataTable, Column } from '../components/DataTable';
import { PriorityBadge } from '../components/Badges';

export function Fleet() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([portalApi.getTenants(), portalApi.getFleetKpis()]).then(([t, k]) => {
      setTenants(t);
      setKpis(k);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return <div className="container">Loading fleet telemetry...</div>;
  }

  const columns: Column<Tenant>[] = [
    { key: 'tenant_id', header: 'Tenant ID' },
    { key: 'name', header: 'Client Name' },
    { key: 'plan', header: 'Plan' },
    { key: 'mandate_status', header: 'Mandate' },
    { key: 'monthly_budget_hours', header: 'Budget (Hours)' },
    {
      key: 'actions',
      header: 'Actions',
      render: (t) => (
        <button
          className="btn btn-secondary"
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/tenants/${t.tenant_id}`);
          }}
        >
          View Client
        </button>
      )
    }
  ];

  return (
    <div className="container">
      <h1 style={{ marginBottom: 20 }}>MSP Fleet Overview</h1>

      {kpis ? (
        <div className="grid-cols-4">
          <KpiCard
            label="Delivery to Result"
            value={`${kpis.delivery_to_result_hours.toFixed(2)}h`}
            sub="Median duration"
            tone="good"
          />
          <KpiCard
            label="Critical Blocked"
            value={`${Math.round(kpis.critical_blocked_before_prod * 100)}%`}
            sub="Before production"
            tone="good"
          />
          <KpiCard
            label="SLA Compliance"
            value={`${Math.round(kpis.sla_compliance * 100)}%`}
            sub="Remediation SLA"
            tone="good"
          />
          <KpiCard
            label="Coverage"
            value={`${Math.round(kpis.coverage * 100)}%`}
            sub="Target attack surface"
            tone="good"
          />
        </div>
      ) : null}

      {kpis ? (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-title">Open Findings by Priority</div>
          <div style={{ display: 'flex', gap: 24, alignItems: 'center' }}>
            <div>
              <PriorityBadge priority="P1" />{' '}
              <strong style={{ marginLeft: 6 }}>{kpis.findings_open_by_priority.P1}</strong>
            </div>
            <div>
              <PriorityBadge priority="P2" />{' '}
              <strong style={{ marginLeft: 6 }}>{kpis.findings_open_by_priority.P2}</strong>
            </div>
            <div>
              <PriorityBadge priority="P3" />{' '}
              <strong style={{ marginLeft: 6 }}>{kpis.findings_open_by_priority.P3}</strong>
            </div>
            <div>
              <PriorityBadge priority="P4" />{' '}
              <strong style={{ marginLeft: 6 }}>{kpis.findings_open_by_priority.P4}</strong>
            </div>
          </div>
        </div>
      ) : null}

      <div className="card">
        <div className="card-title">Enrolled Clients ({tenants.length})</div>
        <DataTable
          columns={columns}
          data={tenants}
          keyField="tenant_id"
          onRowClick={(row) => navigate(`/tenants/${String(row.tenant_id)}`)}
        />
      </div>
    </div>
  );
}

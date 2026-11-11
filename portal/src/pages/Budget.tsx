import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { BudgetState, Tenant } from '../types';
import { portalApi } from '../api/service';
import { useSession } from '../hooks/useSession';
import { KpiCard } from '../components/KpiCard';

export function Budget() {
  const { session } = useSession();
  const [searchParams] = useSearchParams();
  const tenantId = searchParams.get('tenant') || session.tenant_id || 'demo-tenant-shoplite';

  const [budget, setBudget] = useState<BudgetState | null>(null);
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const isReadOnly = session.role === 'demo' || session.role === 'account_manager';

  useEffect(() => {
    Promise.all([portalApi.getBudget(tenantId), portalApi.getTenant(tenantId)]).then(
      ([b, t]) => {
        setBudget(b);
        setTenant(t);
        setLoading(false);
      }
    );
  }, [tenantId]);

  if (loading) return <div className="container">Loading budget state...</div>;
  if (!budget || !tenant) return <div className="container">Budget data not found.</div>;

  const allocated = tenant.monthly_budget_hours || 100;
  const used = budget.hours_used;
  const pct = Math.min(100, Math.round((used / allocated) * 100));

  const handleToggleAutoStop = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (isReadOnly) return;
    const nextVal = e.target.checked;
    setSaving(true);
    const updated = await portalApi.updateBudget(tenantId, { auto_stop: nextVal });
    setBudget(updated);
    setSaving(false);
  };

  return (
    <div className="container">
      <h1 style={{ marginBottom: 8 }}>Budget & Consumption Guardrails</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: 20 }}>
        Tracking task hours for client <strong>{tenant.name}</strong> ({tenantId}) &mdash; Month {budget.month}
      </p>

      <div className="grid-cols-4">
        <KpiCard label="Allocated Hours" value={`${allocated} h`} sub="Monthly contractual quota" />
        <KpiCard
          label="Hours Consumed"
          value={`${used.toFixed(1)} h`}
          sub={`${pct}% of monthly allocation`}
          tone={pct >= 100 ? 'bad' : pct >= 80 ? 'warn' : 'good'}
        />
        <KpiCard
          label="Est. Spend"
          value={`$${(used * 50).toFixed(0)}`}
          sub="@ $50/task-hour (AWS Bedrock / SA)"
        />
        <KpiCard
          label="Auto-Stop Guard"
          value={budget.auto_stop ? 'ACTIVE' : 'DISABLED'}
          sub="Halt tests at 100% budget"
          tone={budget.auto_stop ? 'good' : 'warn'}
        />
      </div>

      <div className="card">
        <div className="card-title">Consumption Gauge</div>
        <div
          style={{
            background: 'var(--bg-secondary)',
            height: 24,
            borderRadius: 12,
            overflow: 'hidden',
            margin: '12px 0',
            position: 'relative'
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${pct}%`,
              background: pct >= 100 ? 'var(--danger)' : pct >= 80 ? 'var(--warning)' : 'var(--accent)',
              transition: 'width 0.3s ease'
            }}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          <span>0%</span>
          <span>50% Threshold {budget.thresholds_hit.includes(50) ? '✅' : '⚪'}</span>
          <span>80% Threshold {budget.thresholds_hit.includes(80) ? '✅' : '⚪'}</span>
          <span>100% Threshold {budget.thresholds_hit.includes(100) ? '🛑' : '⚪'}</span>
        </div>
      </div>

      <div className="card">
        <div className="card-title">Budget Enforcement Policies</div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={budget.auto_stop}
            disabled={isReadOnly || saving}
            onChange={handleToggleAutoStop}
            style={{ width: 18, height: 18 }}
          />
          <div>
            <strong>Enforce Auto-Stop (Zero Over-Budget Guarantee)</strong>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              Automatically block new pentest runs and interrupt active jobs if consumption reaches 100%.
            </div>
          </div>
        </label>
        {isReadOnly ? (
          <div style={{ marginTop: 8, color: 'var(--warning)', fontSize: '0.85rem' }}>
            Policy modifications are locked in Judge Demo / Read-Only mode.
          </div>
        ) : null}
      </div>
    </div>
  );
}

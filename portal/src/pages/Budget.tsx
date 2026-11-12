import { useSearchParams } from 'react-router-dom';
import { BudgetForecast } from '../types';
import { portalApi } from '../api/service';
import { canWrite } from '../types/constants';
import {
  NOT_REPORTED,
  formatNumber,
  readArray,
  readBoolean,
  readNumber,
  readString
} from '../api/fields';
import { useSession } from '../hooks/useSession';
import { useTenantScope } from '../hooks/useTenantScope';
import { useAsyncData } from '../hooks/useAsyncData';
import { useApiAction } from '../hooks/useApiAction';
import { KpiCard } from '../components/KpiCard';
import { Card } from '../components/Card';
import { DetailList } from '../components/DetailList';
import { DataUnavailable } from '../components/DataUnavailable';
import { ActionNotice } from '../components/ActionNotice';
import { AutoStopToggle } from '../components/AutoStopToggle';
import { BudgetEditor } from '../components/BudgetEditor';
import { TenantPicker } from '../components/TenantPicker';

export function Budget() {
  const [searchParams] = useSearchParams();
  const { session } = useSession();
  const { tenants, tenantId, setTenantId } = useTenantScope({
    initial: searchParams.get('tenant')
  });
  const readOnly = !canWrite(session.role);
  const action = useApiAction();

  const { data: budget, loading, error, setData } = useAsyncData(
    () => portalApi.getBudget(tenantId),
    [tenantId]
  );
  const { data: forecast } = useAsyncData(() => portalApi.getForecast(tenantId), [tenantId]);
  const { data: tenant } = useAsyncData(() => portalApi.getTenant(tenantId), [tenantId]);

  const saveAllocation = async (hours: number) => {
    const updated = await action.run(
      () => portalApi.updateBudget(tenantId, { monthly_budget_hours: hours }),
      'Monthly allocation updated (PUT /v1/tenants/{id}/budget).'
    );
    if (updated) setData(updated);
  };

  const toggleAutoStop = async (next: boolean) => {
    const updated = await action.run(
      () => portalApi.updateBudget(tenantId, { auto_stop: next }),
      next ? 'Auto-stop enabled.' : 'Auto-stop disabled.'
    );
    if (updated) setData(updated);
  };

  if (loading) return <div className="container">Loading budget state...</div>;
  if (error) return <div className="container">{error}</div>;
  if (!budget) return <div className="container">Budget data not found.</div>;

  const allocated = budget.monthly_budget_hours ?? tenant?.monthly_budget_hours ?? null;
  const used = budget.hours_used;
  const pct =
    budget.budget_pct ?? (allocated ? Math.min(100, Math.round((used / allocated) * 100)) : 0);

  return (
    <div className="container">
      <h1 style={{ marginBottom: 8 }}>Budget & Consumption Guardrails</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: 20 }}>
        Task hours, forecast and guardrails for <strong>{tenant?.name ?? tenantId}</strong> (
        {tenantId}) — month {budget.month}
      </p>

      <TenantPicker tenants={tenants} value={tenantId} onChange={setTenantId} />
      <ActionNotice message={action.message} error={action.error} />

      <div className="grid-cols-4">
        <KpiCard
          label="Allocated Hours"
          value={allocated === null ? NOT_REPORTED : `${allocated} h`}
          sub="Monthly contractual quota"
        />
        <KpiCard
          label="Hours Consumed"
          value={formatNumber(used, ' h', 1)}
          sub={`${pct}% of the monthly allocation`}
          tone={pct >= 100 ? 'bad' : pct >= 80 ? 'warn' : 'good'}
        />
        <KpiCard
          label="Projected Month-End"
          value={formatNumber(projectedHours(forecast), ' h', 1)}
          sub="Forecast at the current burn rate"
          tone={
            allocated !== null && (projectedHours(forecast) ?? 0) > allocated ? 'bad' : 'default'
          }
        />
        <KpiCard
          label="Auto-Stop Guard"
          value={budget.auto_stop ? 'ACTIVE' : 'DISABLED'}
          sub="Halt tests at 100% of the budget"
          tone={budget.auto_stop ? 'good' : 'warn'}
        />
      </div>

      <GaugeCard pct={pct} thresholds={budget.thresholds_hit} />
      <ForecastCard forecast={forecast} allocated={allocated} allowed={budget.allowed} />

      <Card title="Budget Enforcement Policies" style={{ marginTop: 16 }}>
        <AutoStopToggle
          autoStop={budget.auto_stop}
          readOnly={readOnly}
          busy={action.busy}
          onToggle={toggleAutoStop}
        />
      </Card>

      <Card title="Edit the monthly allocation" style={{ marginTop: 16 }}>
        <BudgetEditor
          key={tenantId}
          allocated={allocated}
          readOnly={readOnly}
          busy={action.busy}
          onSave={saveAllocation}
        />
      </Card>
    </div>
  );
}

const PROJECTED_HOURS = [
  'projected_month_end_hours',
  'projected_hours',
  'month_end_projection',
  'projected_hours_used',
  'forecast_hours'
];

const PROJECTED_COST = [
  'projected_cost_usd',
  'projected_month_end_cost_usd',
  'projected_spend_usd',
  'estimated_cost_usd'
];

const EXHAUSTION_DATE = [
  'projected_exhaustion_date',
  'exhaustion_date',
  'projected_rupture_date',
  'budget_exhaustion_date',
  'projected_exhausted_at'
];

const DAILY_BURN = ['daily_burn_hours', 'burn_rate_hours_per_day', 'hours_per_day'];

function projectedHours(forecast: BudgetForecast | null): number | null {
  return forecast === null ? null : readNumber(forecast, PROJECTED_HOURS);
}

function GaugeCard({ pct, thresholds }: { pct: number; thresholds: number[] }) {
  return (
    <Card title="Consumption Gauge" style={{ marginTop: 16 }}>
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
            width: `${Math.max(0, Math.min(100, pct))}%`,
            background:
              pct >= 100 ? 'var(--danger)' : pct >= 80 ? 'var(--warning)' : 'var(--accent)',
            transition: 'width 0.3s ease'
          }}
        />
      </div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          color: 'var(--text-muted)',
          fontSize: '0.85rem'
        }}
      >
        <span>0%</span>
        <span>50% {thresholds.includes(50) ? '✅' : '⚪'}</span>
        <span>80% {thresholds.includes(80) ? '✅' : '⚪'}</span>
        <span>100% {thresholds.includes(100) ? '🛑' : '⚪'}</span>
      </div>
    </Card>
  );
}

function ForecastCard(props: {
  forecast: BudgetForecast | null;
  allocated: number | null;
  allowed?: boolean;
}) {
  const { forecast, allocated, allowed } = props;
  const thresholds = readArray<number>(forecast, ['thresholds']) ?? [];
  return (
    <Card title="Month-End Forecast (EF-BUD-04)" style={{ marginTop: 16 }}>
      {forecast === null ? (
        <DataUnavailable feature="Budget forecast" datasetKey="forecast" />
      ) : (
        <DetailList
          items={[
            { label: 'Month', value: readString(forecast, ['month', 'period']) ?? undefined },
            { label: 'Hours consumed', value: readNumber(forecast, ['hours_used']) ?? undefined },
            { label: 'Monthly allocation', value: allocated ?? undefined },
            { label: 'Projected month-end hours', value: projectedHours(forecast) ?? undefined },
            {
              label: 'Projected month-end cost',
              value: formatUsd(readNumber(forecast, PROJECTED_COST))
            },
            {
              label: 'Daily burn rate',
              value: formatNumber(readNumber(forecast, DAILY_BURN), ' h/day', 2)
            },
            {
              label: 'Projected exhaustion date',
              value: readString(forecast, EXHAUSTION_DATE) ?? 'not projected (allocation holds)'
            },
            {
              label: 'Tests still allowed',
              value: boolLabel(allowed === undefined ? readBoolean(forecast, ['allowed']) : allowed)
            },
            { label: 'Forecast thresholds', value: thresholds.length ? thresholds.join(', ') : undefined },
            { label: 'Auto-stop at 100%', value: boolLabel(readBoolean(forecast, ['auto_stop'])) }
          ]}
        />
      )}
    </Card>
  );
}

function formatUsd(value: number | null): string | undefined {
  return value === null ? undefined : `$${value.toFixed(0)}`;
}

function boolLabel(value: boolean | null): string | undefined {
  return value === null ? undefined : value ? 'yes' : 'no';
}

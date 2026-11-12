import { CSSProperties, useState } from 'react';
import { portalApi } from '../api/service';
import { EffectivePolicy, TenantPolicy } from '../types';
import { canWrite, canWritePolicy } from '../types/constants';
import { NOT_REPORTED } from '../api/fields';
import { useSession } from '../hooks/useSession';
import { useTenantScope } from '../hooks/useTenantScope';
import { useAsyncData } from '../hooks/useAsyncData';
import { useApiAction } from '../hooks/useApiAction';
import { TenantPicker } from '../components/TenantPicker';
import { Card } from '../components/Card';
import { DetailList } from '../components/DetailList';
import { DataUnavailable } from '../components/DataUnavailable';
import { KpiCard } from '../components/KpiCard';
import { ActionNotice } from '../components/ActionNotice';
import { AutoStopToggle } from '../components/AutoStopToggle';
import { DueDaysList, MatrixOverridesList } from '../components/PolicyMatrix';
import {
  PolicyDraft,
  PolicyEditor,
  draftFromPolicy,
  draftToPayload
} from '../components/PolicyEditor';

export function PolicyPage() {
  const { session } = useSession();
  const { tenants, tenantId, setTenantId } = useTenantScope();
  const action = useApiAction();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<PolicyDraft | null>(null);

  const { data: policy, loading, error, setData } = useAsyncData(
    () => portalApi.getPolicy(tenantId),
    [tenantId]
  );
  const { data: defaults } = useAsyncData(() => portalApi.getPolicyDefaults(), []);
  const { data: budget, setData: setBudget } = useAsyncData(
    () => portalApi.getBudget(tenantId),
    [tenantId]
  );

  const editable = canWritePolicy(session.role);

  const startEdit = () => {
    if (!policy) return;
    setDraft(draftFromPolicy(policy));
    setEditing(true);
    action.clear();
  };

  const save = async () => {
    if (!draft) return;
    const saved = await action.run(
      () => portalApi.updatePolicy(tenantId, draftToPayload(draft)),
      'Contract policy saved (PUT /v1/tenants/{id}/policy).'
    );
    if (saved) {
      setData(saved);
      setEditing(false);
    }
  };

  const toggleAutoStop = async (next: boolean) => {
    const updated = await action.run(
      () => portalApi.updateBudget(tenantId, { auto_stop: next }),
      next ? 'Auto-stop enabled.' : 'Auto-stop disabled.'
    );
    if (updated) setBudget(updated);
  };

  return (
    <div className="container">
      <h1 style={{ marginBottom: 8 }}>Contract Correction Policy</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: 20 }}>
        Per-contract policy (EF-ADM-01): priority matrix, remediation deadlines P1&ndash;P4,
        blocking threshold and hourly rate. Platform defaults apply where the contract is silent.
        Only <code>platform_admin</code> may write it.
      </p>

      <TenantPicker tenants={tenants} value={tenantId} onChange={setTenantId} />
      <ActionNotice message={action.message} error={action.error} />
      {error ? <div className="card">{error}</div> : null}

      {loading ? (
        <div>Loading contract policy...</div>
      ) : policy === null ? (
        <DataUnavailable feature="Contract policy" datasetKey="policy" />
      ) : (
        <>
          <PolicyReadView policy={policy} defaults={defaults} />
          <PolicyEditPanel
            editable={editable}
            editing={editing}
            draft={draft}
            busy={action.busy}
            onStart={startEdit}
            onChange={setDraft}
            onSave={save}
            onCancel={() => setEditing(false)}
          />
          <Card title="Budget guardrail attached to this contract" style={{ marginTop: 16 }}>
            {budget ? (
              <AutoStopToggle
                autoStop={budget.auto_stop}
                readOnly={!canWrite(session.role)}
                busy={action.busy}
                onToggle={toggleAutoStop}
              />
            ) : (
              <DataUnavailable feature="Auto-stop state" />
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function PolicyReadView({
  policy,
  defaults
}: {
  policy: TenantPolicy;
  defaults: EffectivePolicy | null;
}) {
  const effective = policy.effective ?? ({} as EffectivePolicy);
  const overrides = effective.matrix_overrides ?? {};
  return (
    <>
      <div className="grid-cols-4">
        <KpiCard
          label="Blocking threshold"
          value={effective.blocking_threshold ?? NOT_REPORTED}
          sub="Tests stop at this severity"
          tone="warn"
        />
        <KpiCard
          label="Hourly rate"
          value={effective.hourly_rate === undefined ? NOT_REPORTED : `$${effective.hourly_rate}`}
          sub="Contract price per task hour"
        />
        <KpiCard
          label="Matrix overrides"
          value={Object.keys(overrides).length}
          sub="Severities re-prioritised by contract"
        />
        <KpiCard label="Writer role" value="platform_admin" sub="Single role allowed to edit" />
      </div>

      <Card title="Remediation deadlines (P1–P4)" style={{ marginTop: 16 }}>
        <DueDaysList policy={effective} />
      </Card>

      <Card title="Priority matrix" style={{ marginTop: 16 }}>
        <MatrixOverridesList policy={effective} />
      </Card>

      <Card title="Stored contract policy (raw)" style={{ marginTop: 16 }}>
        <pre style={PRE_STYLE}>{JSON.stringify(policy.policy ?? {}, null, 2)}</pre>
      </Card>

      <Card title="Platform defaults" style={{ marginTop: 16 }}>
        {defaults ? (
          <>
            <DetailList
              items={[
                { label: 'Blocking threshold', value: defaults.blocking_threshold },
                {
                  label: 'Hourly rate',
                  value: defaults.hourly_rate === undefined ? undefined : `$${defaults.hourly_rate}`
                }
              ]}
            />
            <DueDaysList policy={defaults} />
          </>
        ) : (
          <DataUnavailable feature="Platform defaults" datasetKey="policy_defaults" />
        )}
      </Card>
    </>
  );
}

interface PolicyEditPanelProps {
  editable: boolean;
  editing: boolean;
  draft: PolicyDraft | null;
  busy: boolean;
  onStart: () => void;
  onChange: (draft: PolicyDraft) => void;
  onSave: () => void;
  onCancel: () => void;
}

function PolicyEditPanel(props: PolicyEditPanelProps) {
  if (props.editing && props.draft) {
    return (
      <Card title="Edit contract policy" style={{ marginTop: 16 }}>
        <PolicyEditor
          draft={props.draft}
          onChange={props.onChange}
          busy={props.busy}
          onSave={props.onSave}
          onCancel={props.onCancel}
        />
      </Card>
    );
  }
  return (
    <Card title="Write access" style={{ marginTop: 16 }}>
      {props.editable ? (
        <button className="btn btn-primary" onClick={props.onStart} data-testid="policy-edit">
          Edit contract policy
        </button>
      ) : (
        <span
          style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}
          data-testid="policy-readonly-note"
        >
          Your role has read access only — the contract policy is written by{' '}
          <code>platform_admin</code>.
        </span>
      )}
    </Card>
  );
}

const PRE_STYLE: CSSProperties = {
  background: 'var(--bg-secondary)',
  padding: 12,
  borderRadius: 6,
  overflowX: 'auto',
  fontSize: '0.85rem'
};

import { CSSProperties } from 'react';
import {
  DueDays,
  EffectivePolicy,
  MatrixOverrides,
  Priority,
  Severity,
  TenantPolicy
} from '../types';
import { PRIORITIES, SEVERITIES } from '../types/constants';

export interface PolicyDraft {
  dueDays: Record<Priority, string>;
  matrixOverrides: Record<Severity, string>;
  blockingThreshold: Severity | '';
  hourlyRate: string;
}

/** Seed the form from the policy the API returned (empty string = "no value"). */
export function draftFromPolicy(policy: TenantPolicy): PolicyDraft {
  const dueDays = {} as Record<Priority, string>;
  const matrixOverrides = {} as Record<Severity, string>;
  PRIORITIES.forEach((p) => {
    const days = policy.effective?.due_days?.[p];
    dueDays[p] = days === null || days === undefined ? '' : String(days);
  });
  SEVERITIES.forEach((s) => {
    matrixOverrides[s] = policy.effective?.matrix_overrides?.[s] ?? '';
  });
  return {
    dueDays,
    matrixOverrides,
    blockingThreshold: policy.effective?.blocking_threshold ?? '',
    hourlyRate:
      policy.effective?.hourly_rate === undefined ? '' : String(policy.effective.hourly_rate)
  };
}

/** Only the keys the contract accepts (backend POLICY_KEYS). */
export function draftToPayload(draft: PolicyDraft): Partial<EffectivePolicy> {
  const dueDays: DueDays = {};
  PRIORITIES.forEach((p) => {
    const raw = draft.dueDays[p].trim();
    dueDays[p] = raw === '' ? null : Number(raw);
  });
  const matrixOverrides: MatrixOverrides = {};
  SEVERITIES.forEach((s) => {
    if (draft.matrixOverrides[s]) matrixOverrides[s] = draft.matrixOverrides[s] as Priority;
  });
  const payload: Partial<EffectivePolicy> = { due_days: dueDays, matrix_overrides: matrixOverrides };
  if (draft.blockingThreshold) payload.blocking_threshold = draft.blockingThreshold;
  const rate = Number(draft.hourlyRate);
  if (draft.hourlyRate.trim() !== '' && Number.isFinite(rate)) payload.hourly_rate = rate;
  return payload;
}

const FIELD: CSSProperties = { marginBottom: 12, minWidth: 190 };

interface PolicyEditorProps {
  draft: PolicyDraft;
  onChange: (draft: PolicyDraft) => void;
  busy: boolean;
  onSave: () => void;
  onCancel: () => void;
}

/** Contract policy form — shown to the roles allowed to write a policy. */
export function PolicyEditor({ draft, onChange, busy, onSave, onCancel }: PolicyEditorProps) {
  return (
    <div data-testid="policy-editor">
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <DueDaysFields draft={draft} onChange={onChange} />
        <MatrixFields draft={draft} onChange={onChange} />
        <div style={FIELD}>
          <label htmlFor="policy-threshold">Blocking threshold</label>
          <select
            id="policy-threshold"
            className="form-control"
            value={draft.blockingThreshold}
            onChange={(e) => onChange({ ...draft, blockingThreshold: e.target.value as Severity })}
          >
            <option value="">(platform default)</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <label htmlFor="policy-rate" style={{ marginTop: 12 }}>
            Hourly rate (USD / task hour)
          </label>
          <input
            id="policy-rate"
            className="form-control"
            type="number"
            min={0}
            step="0.01"
            value={draft.hourlyRate}
            onChange={(e) => onChange({ ...draft, hourlyRate: e.target.value })}
          />
        </div>
      </div>
      <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
        <button className="btn btn-primary" onClick={onSave} disabled={busy} data-testid="policy-save">
          {busy ? 'Saving...' : 'Save contract policy'}
        </button>
        <button className="btn btn-secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function DueDaysFields({ draft, onChange }: Pick<PolicyEditorProps, 'draft' | 'onChange'>) {
  return (
    <div style={FIELD}>
      <label>Remediation deadlines (days, empty = none)</label>
      {PRIORITIES.map((p) => (
        <div key={p} style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 6 }}>
          <span style={{ minWidth: 28 }}>{p}</span>
          <input
            className="form-control"
            type="number"
            min={1}
            aria-label={`Due days ${p}`}
            value={draft.dueDays[p]}
            onChange={(e) => onChange({ ...draft, dueDays: { ...draft.dueDays, [p]: e.target.value } })}
          />
        </div>
      ))}
    </div>
  );
}

function MatrixFields({ draft, onChange }: Pick<PolicyEditorProps, 'draft' | 'onChange'>) {
  return (
    <div style={FIELD}>
      <label>Priority matrix overrides</label>
      {SEVERITIES.map((s) => (
        <div key={s} style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 6 }}>
          <span style={{ minWidth: 110 }}>{s}</span>
          <select
            className="form-control"
            aria-label={`Override for ${s}`}
            value={draft.matrixOverrides[s]}
            onChange={(e) =>
              onChange({ ...draft, matrixOverrides: { ...draft.matrixOverrides, [s]: e.target.value } })
            }
          >
            <option value="">(no override)</option>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
      ))}
    </div>
  );
}

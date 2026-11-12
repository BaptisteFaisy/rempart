import { useState } from 'react';

interface BudgetEditorProps {
  allocated: number | null;
  readOnly: boolean;
  busy: boolean;
  onSave: (monthlyBudgetHours: number) => void;
}

/** Edition of the monthly allocation (PUT /v1/tenants/{id}/budget). */
export function BudgetEditor({ allocated, readOnly, busy, onSave }: BudgetEditorProps) {
  const [hours, setHours] = useState(allocated === null ? '' : String(allocated));
  const parsed = Number(hours);
  const valid = hours.trim() !== '' && Number.isFinite(parsed) && parsed >= 0;

  if (readOnly) {
    return (
      <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
        Your role has read access only — the monthly allocation is written by the platform or the
        client roles.
      </span>
    );
  }

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
      <div className="form-group" style={{ marginBottom: 0 }}>
        <label htmlFor="budget-hours">Monthly allocation (task hours)</label>
        <input
          id="budget-hours"
          className="form-control"
          type="number"
          min={0}
          step="0.5"
          value={hours}
          onChange={(e) => setHours(e.target.value)}
          data-testid="budget-hours-input"
        />
      </div>
      <button
        className="btn btn-primary"
        disabled={busy || !valid}
        onClick={() => onSave(parsed)}
        data-testid="budget-save"
      >
        {busy ? 'Saving...' : 'Save allocation'}
      </button>
    </div>
  );
}

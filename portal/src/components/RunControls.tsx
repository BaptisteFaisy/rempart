import { Run } from '../types';

interface RunControlsProps {
  runs: Run[];
  readOnly: boolean;
  busy: boolean;
  onStart: () => void;
  onStop: (runId: string) => void;
}

const ACTIVE: Run['status'][] = ['queued', 'running'];

/** On-demand test launcher and stop button for the active run. */
export function RunControls({ runs, readOnly, busy, onStart, onStop }: RunControlsProps) {
  const active = runs.find((run) => ACTIVE.includes(run.status));
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
      <button
        className="btn btn-primary"
        onClick={onStart}
        disabled={busy || readOnly}
        data-testid="run-start"
      >
        {busy ? 'Working...' : 'Run an on-demand test'}
      </button>
      {active ? (
        <button
          className="btn btn-danger"
          onClick={() => onStop(active.run_id)}
          disabled={busy || readOnly}
          data-testid="run-stop"
        >
          Stop test {active.run_id}
        </button>
      ) : (
        <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }} data-testid="run-no-active">
          No queued or running test to stop.
        </span>
      )}
      {readOnly ? (
        <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          (write actions disabled for this role)
        </span>
      ) : null}
    </div>
  );
}

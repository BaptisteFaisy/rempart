interface AutoStopToggleProps {
  autoStop: boolean;
  readOnly: boolean;
  busy?: boolean;
  onToggle: (next: boolean) => void;
}

/**
 * The zero-over-budget guard: when enabled the platform blocks new tests and
 * interrupts active jobs once the monthly allocation is consumed. One shared
 * component so the Budget page and the Policy page show the same control.
 */
export function AutoStopToggle({ autoStop, readOnly, busy = false, onToggle }: AutoStopToggleProps) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }}>
      <input
        type="checkbox"
        checked={autoStop}
        disabled={readOnly || busy}
        onChange={(e) => onToggle(e.target.checked)}
        style={{ width: 18, height: 18 }}
        data-testid="auto-stop-toggle"
      />
      <div>
        <strong>Enforce Auto-Stop (Zero Over-Budget Guarantee)</strong>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          Automatically block new pentest runs and interrupt active jobs if consumption reaches
          100% of the monthly allocation.
        </div>
      </div>
    </label>
  );
}

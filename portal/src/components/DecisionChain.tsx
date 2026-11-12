import { EvidenceDecision } from '../types';

/**
 * Chronological decision chain of a finding: who decided what, agent or human.
 * Read from the evidence dossier (the API exposes no separate decisions route).
 */
export function DecisionChain({ decisions }: { decisions: EvidenceDecision[] }) {
  if (decisions.length === 0) {
    return (
      <div className="table-empty" data-testid="decision-chain-empty">
        No decision recorded for this finding.
      </div>
    );
  }
  return (
    <ol style={{ marginLeft: 20 }} data-testid="decision-chain">
      {decisions.map((decision, index) => (
        <li key={decision.decision_id ?? index} style={{ marginBottom: 10 }}>
          <span
            className={`badge ${decision.author_type === 'human' ? 'status-info' : 'status-muted'}`}
          >
            {decision.author_type ?? 'unknown'}
          </span>{' '}
          <strong>{decision.action ?? '—'}</strong> — {decision.author ?? '—'} ·{' '}
          {decision.created_at ?? '—'}
          <div style={{ color: 'var(--text-muted)', fontSize: '0.88rem' }}>
            {decision.justification || 'no justification recorded'}
          </div>
        </li>
      ))}
    </ol>
  );
}

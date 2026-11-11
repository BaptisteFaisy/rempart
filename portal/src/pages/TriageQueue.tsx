import { useEffect, useState } from 'react';
import { Finding } from '../types';
import { portalApi } from '../api/service';
import { PriorityBadge, FindingStatusBadge } from '../components/Badges';
import { useSession } from '../hooks/useSession';

export function TriageQueue() {
  const { session } = useSession();
  const [queue, setQueue] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);
  const [justification, setJustification] = useState<Record<string, string>>({});
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const isReadOnly = session.role === 'demo' || session.role === 'account_manager';

  const loadQueue = () => {
    setLoading(true);
    portalApi
      .getFindings({ status: 'pending_validation' })
      .then((res) => {
        setQueue(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    loadQueue();
  }, []);

  const handleDecision = async (
    finding: Finding,
    action: 'confirmed' | 'false_positive'
  ) => {
    const reason =
      justification[finding.finding_id] ||
      (action === 'confirmed'
        ? `Confirmed ${finding.priority} impact by ${session.role}`
        : `Marked false positive by ${session.role}`);

    try {
      await portalApi.postDecision(finding.finding_id, action, reason);
      setStatusMessage(
        `Finding ${finding.finding_id} successfully updated to ${action}.`
      );
      setQueue((prev) => prev.filter((f) => f.finding_id !== finding.finding_id));
    } catch {
      setStatusMessage(`Failed to update finding ${finding.finding_id}`);
    }
  };

  return (
    <div className="container">
      <h1 style={{ marginBottom: 8 }}>Analyst Triage Queue</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: 20 }}>
        Review findings flagged with <code>pending_validation</code> by the automated Strands triage agent.
      </p>

      {statusMessage ? (
        <div className="card" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--accent)' }}>
          {statusMessage}
        </div>
      ) : null}

      {loading ? (
        <div>Loading queue...</div>
      ) : queue.length === 0 ? (
        <div className="table-empty">No findings awaiting validation. Great job!</div>
      ) : (
        queue.map((f) => (
          <div key={f.finding_id} className="card" data-testid="triage-card">
            <div className="card-title">
              <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <PriorityBadge priority={f.priority} />
                <FindingStatusBadge status={f.status} />
                <span>{f.title}</span>
              </div>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                {f.finding_id}
              </span>
            </div>

            <p style={{ marginBottom: 12 }}>
              <strong>Risk Type:</strong> {f.risk_type} &bull; <strong>Severity:</strong>{' '}
              {f.severity} &bull; <strong>Confidence:</strong> {f.confidence}
            </p>

            {f.evidence ? (
              <pre
                style={{
                  background: 'var(--bg-secondary)',
                  padding: 10,
                  borderRadius: 6,
                  marginBottom: 12,
                  fontSize: '0.85rem',
                  overflowX: 'auto'
                }}
              >
                {JSON.stringify(f.evidence, null, 2)}
              </pre>
            ) : null}

            <div className="form-group" style={{ marginBottom: 12 }}>
              <label htmlFor={`justification-${f.finding_id}`}>Analyst Justification</label>
              <input
                id={`justification-${f.finding_id}`}
                className="form-control"
                placeholder="Enter justification rationale..."
                value={justification[f.finding_id] || ''}
                disabled={isReadOnly}
                onChange={(e) =>
                  setJustification({ ...justification, [f.finding_id]: e.target.value })
                }
              />
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <button
                className="btn btn-danger"
                disabled={isReadOnly}
                onClick={() => handleDecision(f, 'confirmed')}
                data-testid="btn-confirm"
              >
                Confirm {f.priority}
              </button>
              <button
                className="btn btn-secondary"
                disabled={isReadOnly}
                onClick={() => handleDecision(f, 'false_positive')}
                data-testid="btn-reject"
              >
                Reject / False Positive
              </button>
              {isReadOnly ? (
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', alignSelf: 'center' }}>
                  (Actions disabled in read-only mode)
                </span>
              ) : null}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

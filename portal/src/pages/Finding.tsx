import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Finding } from '../types';
import { portalApi } from '../api/service';
import { PriorityBadge, FindingStatusBadge } from '../components/Badges';

export function FindingPage() {
  const { findingId } = useParams<{ findingId: string }>();
  const [finding, setFinding] = useState<Finding | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!findingId) return;
    portalApi.getFinding(findingId).then((f) => {
      setFinding(f);
      setLoading(false);
    });
  }, [findingId]);

  if (loading) return <div className="container">Loading finding details...</div>;
  if (!finding) return <div className="container">Finding not found.</div>;

  return (
    <div className="container">
      <div style={{ marginBottom: 16 }}>
        <Link to={`/runs/${finding.run_id}`}>&larr; Back to Run {finding.run_id}</Link>
      </div>

      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
        <PriorityBadge priority={finding.priority} />
        <FindingStatusBadge status={finding.status} />
        <span style={{ color: 'var(--text-muted)' }}>Fingerprint: {finding.fingerprint}</span>
      </div>

      <h1 style={{ marginBottom: 20 }}>{finding.title}</h1>

      <div className="grid-cols-2">
        <div className="card">
          <div className="card-title">Attributes</div>
          <p><strong>Risk Type:</strong> {finding.risk_type}</p>
          <p><strong>Severity:</strong> {finding.severity}</p>
          <p><strong>Confidence:</strong> {finding.confidence}</p>
          <p><strong>Priority:</strong> {finding.priority}</p>
          <p><strong>Status:</strong> {finding.status}</p>
          <p><strong>Due Date (SLA):</strong> {finding.due_at || 'None (P4)'}</p>
          <p><strong>Created At:</strong> {finding.created_at}</p>
        </div>

        <div className="card">
          <div className="card-title">Remediation Tracking</div>
          <p>
            <strong>Ticket URL:</strong>{' '}
            {finding.ticket_url ? (
              <a href={finding.ticket_url} target="_blank" rel="noreferrer">
                {finding.ticket_url}
              </a>
            ) : (
              'None'
            )}
          </p>
          <p style={{ marginTop: 8 }}>
            <strong>Remediation PR:</strong>{' '}
            {finding.remediation_pr_url ? (
              <a href={finding.remediation_pr_url} target="_blank" rel="noreferrer">
                {finding.remediation_pr_url}
              </a>
            ) : (
              'None'
            )}
          </p>
          {finding.cvss ? (
            <div style={{ marginTop: 16 }}>
              <strong>CVSS Vector:</strong>
              <pre
                style={{
                  background: 'var(--bg-secondary)',
                  padding: 8,
                  borderRadius: 4,
                  marginTop: 4,
                  fontSize: '0.85rem'
                }}
              >
                {JSON.stringify(finding.cvss, null, 2)}
              </pre>
            </div>
          ) : null}
        </div>
      </div>

      {finding.evidence ? (
        <div className="card">
          <div className="card-title">Evidence & Reproduction</div>
          <pre
            style={{
              background: 'var(--bg-secondary)',
              padding: 12,
              borderRadius: 6,
              overflowX: 'auto',
              fontSize: '0.85rem'
            }}
          >
            {JSON.stringify(finding.evidence, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

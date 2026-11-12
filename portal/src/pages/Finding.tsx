import { CSSProperties } from 'react';
import { useParams, Link } from 'react-router-dom';
import { portalApi } from '../api/service';
import { canWrite } from '../types/constants';
import { useSession } from '../hooks/useSession';
import { useAsyncData } from '../hooks/useAsyncData';
import { useApiAction } from '../hooks/useApiAction';
import { PriorityBadge, FindingStatusBadge } from '../components/Badges';
import { Card } from '../components/Card';
import { DetailList } from '../components/DetailList';
import { ActionNotice } from '../components/ActionNotice';
import { DataUnavailable } from '../components/DataUnavailable';
import { DecisionChain } from '../components/DecisionChain';

const PRE_STYLE: CSSProperties = {
  background: 'var(--bg-secondary)',
  padding: 12,
  borderRadius: 6,
  overflowX: 'auto',
  fontSize: '0.85rem'
};

export function FindingPage() {
  const { findingId } = useParams<{ findingId: string }>();
  const { session } = useSession();
  const action = useApiAction();
  const readOnly = !canWrite(session.role);

  const { data: finding, loading, error, setData } = useAsyncData(
    () => (findingId ? portalApi.getFinding(findingId) : Promise.resolve(null)),
    [findingId]
  );

  const { data: dossier } = useAsyncData(
    () => (finding ? portalApi.getEvidence(finding.tenant_id) : Promise.resolve(null)),
    [finding?.tenant_id]
  );

  const requestRemediation = async () => {
    if (!findingId) return;
    const result = await action.run(
      () => portalApi.postRemediation(findingId),
      'Remediation requested (POST /v1/findings/{id}/remediation).'
    );
    if (result?.finding) setData(result.finding);
  };

  if (loading) return <div className="container">Loading finding details...</div>;
  if (error) return <div className="container">{error}</div>;
  if (!finding) return <div className="container">Finding not found.</div>;

  const chain =
    dossier?.decision_chains?.find((entry) => entry.finding?.finding_id === finding.finding_id)
      ?.decisions ?? [];

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

      <ActionNotice message={action.message} error={action.error} />

      <div className="grid-cols-2" style={{ marginTop: 16 }}>
        <Card title="Attributes">
          <DetailList
            items={[
              { label: 'Risk type', value: finding.risk_type },
              { label: 'Severity', value: finding.severity },
              { label: 'Confidence', value: finding.confidence },
              { label: 'Priority', value: finding.priority },
              { label: 'Status', value: finding.status.replace(/_/g, ' ') },
              { label: 'Due date (SLA)', value: finding.due_at || 'None (P4)' },
              { label: 'Created at', value: finding.created_at },
              { label: 'Updated at', value: finding.updated_at }
            ]}
          />
        </Card>

        <Card title="Risk acceptance (EF-COR-07)">
          <DetailList
            items={[
              {
                label: 'Acceptance status',
                value: finding.status === 'risk_accepted' ? 'Risk accepted' : 'Not accepted'
              },
              { label: 'Reviewed at', value: finding.risk_review_at || 'No review recorded' },
              { label: 'Reviewed by', value: finding.risk_review_by || '—' }
            ]}
          />
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: 8 }}>
            Only the security lead of the owning client (<code>client_security</code>) may accept a
            risk, and only with a traced justification.
          </p>
        </Card>
      </div>

      <Card title="Remediation Tracking" style={{ marginTop: 16 }}>
        <DetailList
          items={[
            {
              label: 'Ticket',
              value: finding.ticket_url ? (
                <a href={finding.ticket_url} target="_blank" rel="noreferrer">
                  {finding.ticket_url}
                </a>
              ) : (
                'None'
              )
            },
            {
              label: 'Remediation pull request',
              value: finding.remediation_pr_url ? (
                <a href={finding.remediation_pr_url} target="_blank" rel="noreferrer">
                  {finding.remediation_pr_url}
                </a>
              ) : (
                'None'
              )
            }
          ]}
        />
        <div style={{ marginTop: 12 }}>
          <button
            className="btn btn-primary"
            onClick={requestRemediation}
            disabled={readOnly || action.busy}
            data-testid="finding-remediation"
          >
            {action.busy ? 'Working...' : 'Request a remediation pull request'}
          </button>
          {readOnly ? (
            <span style={{ marginLeft: 12, color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              (write actions disabled for this role)
            </span>
          ) : null}
        </div>
        {finding.cvss ? <pre style={{ ...PRE_STYLE, marginTop: 12 }}>{JSON.stringify(finding.cvss, null, 2)}</pre> : null}
      </Card>

      <Card title="Decision chain (agent vs human)" style={{ marginTop: 16 }}>
        {dossier === null ? (
          <DataUnavailable feature="Decision chain" datasetKey="evidence" />
        ) : (
          <DecisionChain decisions={chain} />
        )}
      </Card>

      {finding.evidence ? (
        <Card title="Evidence & Reproduction" style={{ marginTop: 16 }}>
          <pre style={PRE_STYLE}>{JSON.stringify(finding.evidence, null, 2)}</pre>
        </Card>
      ) : null}
    </div>
  );
}

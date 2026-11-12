import { useState } from 'react';
import { OnboardingStatus, TestConfig, VerificationInstruction } from '../types';
import { VerificationMethod } from '../api/contracts';
import { DataUnavailable } from './DataUnavailable';
import { DetailList } from './DetailList';
import { DataTable, Column } from './DataTable';

const METHODS: VerificationMethod[] = ['DNS_TXT', 'HTTP_ROUTE', 'PRIVATE_VPC'];

interface OnboardingPanelProps {
  status: OnboardingStatus | null;
  readOnly: boolean;
  busy: boolean;
  onStart: (method: VerificationMethod) => void;
}

/**
 * Onboarding progress of an application: agent space, target domains, test
 * configurations, and the domain-ownership instructions the API returns
 * (DNS TXT record or HTTP route token).
 */
export function OnboardingPanel({ status, readOnly, busy, onStart }: OnboardingPanelProps) {
  const [method, setMethod] = useState<VerificationMethod>('DNS_TXT');

  if (status === null) return <DataUnavailable feature="Onboarding state" />;

  return (
    <div data-testid="onboarding-panel">
      <DetailList
        items={[
          { label: 'Onboarded', value: status.onboarded ? 'Yes' : 'No' },
          { label: 'Agent space', value: status.agent_space_id || 'Not provisioned yet' },
          { label: 'Target domains', value: (status.domains ?? []).join(', ') || undefined },
          { label: 'Test configurations', value: (status.configs ?? []).length },
          { label: 'Verification method', value: status.verification_method }
        ]}
      />

      <VerificationInstructions instructions={status.verification_instructions} />

      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginTop: 12 }}>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label htmlFor="onboarding-method">Domain verification method</label>
          <select
            id="onboarding-method"
            className="form-control"
            value={method}
            onChange={(e) => setMethod(e.target.value as VerificationMethod)}
          >
            {METHODS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <button
          className="btn btn-secondary"
          onClick={() => onStart(method)}
          disabled={busy || readOnly}
          data-testid="onboarding-start"
        >
          {busy ? 'Working...' : 'Run onboarding'}
        </button>
      </div>

      <ConfigTable configs={status.configs ?? []} />
    </div>
  );
}

function VerificationInstructions({
  instructions
}: {
  instructions?: VerificationInstruction[];
}) {
  if (!instructions || instructions.length === 0) return null;
  return (
    <div style={{ marginTop: 12 }} data-testid="verification-instructions">
      <strong>Domain verification instructions</strong>
      <ul style={{ marginLeft: 20, marginTop: 6 }}>
        {instructions.map((instruction, index) => (
          <li key={`${instruction.domain ?? 'domain'}-${index}`}>
            <code>{instruction.method}</code> — {instruction.domain}
            {instruction.requires_dns_access === false ? ' (no DNS access needed)' : ''}
            <div style={{ color: 'var(--text-muted)', fontSize: '0.88rem' }}>
              {instruction.action}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

const CONFIG_COLUMNS: Column<TestConfig>[] = [
  { key: 'config_id', header: 'Config' },
  { key: 'kind', header: 'Kind' },
  {
    key: 'risk_types',
    header: 'Risk types',
    render: (c) => (c.risk_types ?? []).join(', ') || '—'
  },
  { key: 'blocking_threshold', header: 'Blocking threshold' },
  { key: 'schedule', header: 'Schedule (cron)', render: (c) => c.schedule || 'on demand' }
];

function ConfigTable({ configs }: { configs: TestConfig[] }) {
  if (configs.length === 0) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <DataTable columns={CONFIG_COLUMNS} data={configs} keyField="config_id" />
    </div>
  );
}

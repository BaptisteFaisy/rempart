import { Application, Run, TestWindow } from '../types';
import { AWS_CONCURRENT_TEST_QUOTA } from '../types/constants';
import { readNumber } from '../api/fields';
import { DetailList } from './DetailList';

const ACTIVE_STATUSES: Run['status'][] = ['queued', 'running'];

/** Quota of simultaneous tests: reported by the app context when the API has it. */
function quotaLabel(app: Application): string {
  const value = readNumber(app.context, [
    'concurrency_quota',
    'concurrent_test_quota',
    'max_concurrent_tests'
  ]);
  if (value !== null) return `${value} simultaneous tests`;
  return `not exposed by the API (AWS account limit: ${AWS_CONCURRENT_TEST_QUOTA})`;
}

function windowLabel(window: TestWindow): string {
  const days = window.days && window.days.length > 0 ? window.days.join(', ') : 'every day';
  const environment = window.environment ? ` · ${window.environment}` : '';
  return `${days} · ${window.start ?? '?'}–${window.end ?? '?'} UTC${environment}`;
}

interface ApplicationScopeProps {
  app: Application;
  runs: Run[];
}

/** Agent space, domains, repositories, agreed test windows and quota usage. */
export function ApplicationScope({ app, runs }: ApplicationScopeProps) {
  const windows = app.test_windows ?? [];
  const active = runs.filter((run) => ACTIVE_STATUSES.includes(run.status)).length;

  return (
    <div data-testid="application-scope">
      <DetailList
        items={[
          { label: 'Agent space', value: app.agent_space_id || 'Not provisioned yet' },
          { label: 'Target domains', value: (app.domains ?? []).join(', ') },
          { label: 'Repositories', value: (app.repositories ?? []).join(', ') },
          { label: 'Concurrency quota', value: quotaLabel(app) },
          { label: 'Quota slots in use', value: `${active} test(s) queued or running` },
          {
            label: 'Agreed test windows',
            value: windows.length > 0 ? undefined : 'None — a production test needs an agreed window'
          }
        ]}
      />
      {windows.length > 0 ? (
        <ul style={{ marginLeft: 20, marginTop: 8 }} data-testid="test-windows">
          {windows.map((window, index) => (
            <li key={index}>{windowLabel(window)}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

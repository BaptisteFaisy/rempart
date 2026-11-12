import { useNavigate, useParams, Link } from 'react-router-dom';
import { Application, OnboardingStatus, Run, Tenant } from '../types';
import { portalApi } from '../api/service';
import { canWrite } from '../types/constants';
import { VerificationMethod } from '../api/contracts';
import { useSession } from '../hooks/useSession';
import { useAsyncData } from '../hooks/useAsyncData';
import { useApiAction } from '../hooks/useApiAction';
import { DataTable, Column } from '../components/DataTable';
import { RunStatusBadge, MandateBadge } from '../components/Badges';
import { Card } from '../components/Card';
import { DetailList } from '../components/DetailList';
import { ActionNotice } from '../components/ActionNotice';
import { RunControls } from '../components/RunControls';
import { OnboardingPanel } from '../components/OnboardingPanel';
import { ApplicationScope } from '../components/ApplicationScope';

interface ApplicationData {
  app: Application;
  tenant: Tenant | null;
  runs: Run[];
  onboarding: OnboardingStatus | null;
}

async function loadApplication(appId: string): Promise<ApplicationData | null> {
  const [app, runs, onboarding] = await Promise.all([
    portalApi.getApplication(appId),
    portalApi.getRuns(appId),
    portalApi.getOnboarding(appId)
  ]);
  if (!app) return null;
  const tenant = await portalApi.getTenant(app.tenant_id).catch(() => null);
  return { app, tenant, runs, onboarding };
}

export function ApplicationPage() {
  const { appId } = useParams<{ appId: string }>();
  const navigate = useNavigate();
  const { session } = useSession();
  const action = useApiAction();
  const readOnly = !canWrite(session.role);

  const { data, loading, error, setData } = useAsyncData(
    () => (appId ? loadApplication(appId) : Promise.resolve(null)),
    [appId]
  );

  const patchRuns = (run: Run) =>
    setData((prev) =>
      prev
        ? {
            ...prev,
            runs: [run, ...prev.runs.filter((r) => r.run_id !== run.run_id)]
          }
        : prev
    );

  const startRun = async () => {
    if (!appId) return;
    const run = await action.run(
      () => portalApi.postRun(appId),
      'On-demand test started (POST /v1/applications/{id}/runs).'
    );
    if (run) patchRuns(run);
  };

  const stopRun = async (runId: string) => {
    const run = await action.run(() => portalApi.stopRun(runId), `Test ${runId} stopped.`);
    if (run) patchRuns(run);
  };

  const startOnboarding = async (method: VerificationMethod) => {
    if (!appId) return;
    const status = await action.run(
      () => portalApi.postOnboarding(appId, method),
      `Onboarding run with ${method} (POST /v1/applications/{id}/onboarding).`
    );
    if (status) setData((prev) => (prev ? { ...prev, onboarding: status } : prev));
  };

  if (loading) return <div className="container">Loading application details...</div>;
  if (error) return <div className="container">{error}</div>;
  if (!data) return <div className="container">Application not found.</div>;

  return (
    <ApplicationDetailView
      view={data}
      readOnly={readOnly}
      busy={action.busy}
      message={action.message}
      actionError={action.error}
      onStartRun={startRun}
      onStopRun={stopRun}
      onStartOnboarding={startOnboarding}
      onOpenRun={(runId) => navigate(`/runs/${runId}`)}
    />
  );
}

interface ViewProps {
  view: ApplicationData;
  readOnly: boolean;
  busy: boolean;
  message: string | null;
  actionError: string | null;
  onStartRun: () => void;
  onStopRun: (runId: string) => void;
  onStartOnboarding: (method: VerificationMethod) => void;
  onOpenRun: (runId: string) => void;
}

function ApplicationDetailView(props: ViewProps) {
  const { app, tenant, runs, onboarding } = props.view;
  return (
    <div className="container">
      <div style={{ marginBottom: 16 }}>
        <Link to={`/tenants/${app.tenant_id}`}>&larr; Back to Tenant</Link>
      </div>

      <h1 style={{ marginBottom: 8 }}>{app.name}</h1>
      <div style={{ marginBottom: 16 }} data-testid="mandate-status">
        {tenant ? <MandateBadge status={tenant.mandate_status} /> : null}
        <span style={{ color: 'var(--text-muted)', marginLeft: 12, fontSize: '0.9rem' }}>
          Test mandate of {tenant?.name ?? app.tenant_id} — a run is refused without a valid mandate.
        </span>
      </div>

      <ActionNotice message={props.message} error={props.actionError} />

      <div className="grid-cols-2" style={{ marginTop: 16 }}>
        <Card title="Application Profile">
          <DetailList
            items={[
              { label: 'App ID', value: app.app_id },
              { label: 'Criticality', value: app.criticality },
              { label: 'Internet exposed', value: app.internet_exposed ? 'Yes' : 'No' },
              { label: 'Data types', value: (app.data_types ?? []).join(', ') || 'none' },
              { label: 'Environment', value: app.environment },
              { label: 'Owner team', value: app.team },
              { label: 'Ticket channel', value: app.ticket_channel }
            ]}
          />
        </Card>

        <Card title="Scope, Windows & Quota">
          <ApplicationScope app={app} runs={runs} />
        </Card>
      </div>

      <Card title="Onboarding (AWS Security Agent)" style={{ marginTop: 16 }}>
        <OnboardingPanel
          status={onboarding}
          readOnly={props.readOnly}
          busy={props.busy}
          onStart={props.onStartOnboarding}
        />
      </Card>

      <Card title="Test Control" style={{ marginTop: 16 }}>
        <RunControls
          runs={runs}
          readOnly={props.readOnly}
          busy={props.busy}
          onStart={props.onStartRun}
          onStop={props.onStopRun}
        />
      </Card>

      <Card title={`Pentest Run History (${runs.length})`} style={{ marginTop: 16 }}>
        <DataTable
          columns={RUN_COLUMNS}
          data={runs}
          keyField="run_id"
          onRowClick={(run) => props.onOpenRun(run.run_id)}
        />
      </Card>
    </div>
  );
}

const RUN_COLUMNS: Column<Run>[] = [
  { key: 'run_id', header: 'Run ID' },
  { key: 'trigger', header: 'Trigger' },
  { key: 'status', header: 'Status', render: (r) => <RunStatusBadge status={r.status} /> },
  { key: 'started_at', header: 'Started At' },
  {
    key: 'task_hours',
    header: 'Task Hours',
    render: (r) => (r.task_hours === undefined || r.task_hours === null ? '—' : `${r.task_hours}h`)
  },
  {
    key: 'cost_usd',
    header: 'Est. Cost',
    render: (r) => (r.cost_usd === undefined || r.cost_usd === null ? '—' : `$${r.cost_usd.toFixed(2)}`)
  }
];

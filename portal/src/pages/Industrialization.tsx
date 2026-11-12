import { portalApi } from '../api/service';
import { Industrialization } from '../types';
import {
  NOT_REPORTED,
  formatNumber,
  formatPercent,
  readArray,
  readBoolean,
  readNumber,
  readRecord,
  readString
} from '../api/fields';
import { useTenantScope } from '../hooks/useTenantScope';
import { useAsyncData } from '../hooks/useAsyncData';
import { TenantPicker } from '../components/TenantPicker';
import { Card } from '../components/Card';
import { DetailList, DetailItem } from '../components/DetailList';
import { DataUnavailable } from '../components/DataUnavailable';
import { KpiCard } from '../components/KpiCard';

/** A block may come back flat or grouped; both are read, nothing is invented. */
function block(source: unknown, names: string[]): unknown {
  return readRecord(source, names) ?? source;
}

export function IndustrializationPage() {
  const { tenants, tenantId, setTenantId } = useTenantScope();
  const { data, loading, error } = useAsyncData(
    () => portalApi.getIndustrialization(tenantId),
    [tenantId]
  );

  return (
    <div className="container">
      <h1 style={{ marginBottom: 8 }}>Industrialization</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: 20 }}>
        How much of the triage loop really runs without a human: intervention rate, agent/human
        divergence, alert fatigue, analyst minutes saved and training-corpus coverage. Every number
        is computed by deterministic code (ENF-IA-01); documented hypotheses are labelled as such.
      </p>

      <TenantPicker tenants={tenants} value={tenantId} onChange={setTenantId} />
      {error ? <div className="card">{error}</div> : null}

      {loading ? (
        <div>Loading industrialization metrics...</div>
      ) : data === null ? (
        <DataUnavailable feature="Industrialization metrics" datasetKey="industrialization" />
      ) : (
        <IndustrializationBody data={data} />
      )}
    </div>
  );
}

function IndustrializationBody({ data }: { data: Industrialization }) {
  const intervention = block(data, ['human_intervention', 'intervention']);
  const fatigue = block(data, ['alert_fatigue', 'fatigue']);
  const minutes = block(data, ['minutes_saved', 'analyst_minutes_saved', 'time_saved']);
  const corpus = block(data, ['corpus', 'training_corpus']);

  const interventionRate = readNumber(intervention, ['human_intervention_rate']);
  const divergence = readNumber(intervention, ['agent_human_divergence_rate']);
  const fatigueScore = readNumber(fatigue, ['fatigue_score']);
  const saved = readNumber(minutes, ['minutes_saved']);
  const coverage = readNumber(corpus, ['coverage_ratio']);
  const alertTriggered = readBoolean(fatigue, ['alert_triggered']);

  return (
    <>
      <div className="grid-cols-4">
        <KpiCard
          label="Human intervention rate"
          value={formatPercent(interventionRate)}
          sub="Findings that needed a human"
          tone={interventionRate !== null && interventionRate < 0.3 ? 'good' : 'warn'}
        />
        <KpiCard
          label="Agent/human divergence"
          value={formatPercent(divergence)}
          sub="Human corrected the agent"
          tone={divergence !== null && divergence < 0.2 ? 'good' : 'warn'}
        />
        <KpiCard
          label="Analyst minutes saved"
          value={formatNumber(saved, ' min', 0)}
          sub="Estimate (documented hypothesis)"
        />
        <KpiCard
          label="Alert fatigue"
          value={fatigueScore === null ? NOT_REPORTED : fatigueScore.toFixed(2)}
          sub={alertTriggered === null ? NOT_REPORTED : alertTriggered ? 'ALERT TRIGGERED' : 'No alert'}
          tone={alertTriggered ? 'bad' : 'good'}
        />
      </div>

      <InterventionCard source={intervention} />
      <FatigueCard source={fatigue} />
      <MinutesCard source={minutes} />
      <CorpusCard source={corpus} coverage={coverage} />
    </>
  );
}

function InterventionCard({ source }: { source: unknown }) {
  const items: DetailItem[] = [
    { label: 'Findings total', value: readNumber(source, ['findings_total']) ?? undefined },
    {
      label: 'Findings with a human decision',
      value: readNumber(source, ['findings_with_human_decision']) ?? undefined
    },
    {
      label: 'Findings with an agent proposal',
      value: readNumber(source, ['findings_with_agent_proposal']) ?? undefined
    },
    {
      label: 'Findings reviewed by a human',
      value: readNumber(source, ['findings_reviewed_by_human']) ?? undefined
    },
    { label: 'Findings diverged', value: readNumber(source, ['findings_diverged']) ?? undefined },
    {
      label: 'Divergence among reviewed',
      value: formatPercent(readNumber(source, ['divergence_rate_among_reviewed']))
    },
    {
      label: 'Agent agreement on reviewed',
      value: formatPercent(readNumber(source, ['agent_agreement_rate_on_reviewed']))
    },
    { label: 'Human decisions', value: readNumber(source, ['human_decisions']) ?? undefined },
    { label: 'Agent decisions', value: readNumber(source, ['agent_decisions']) ?? undefined }
  ];
  const formulas = readRecord(source, ['formulas']);
  return (
    <Card title="Human intervention rate (#68)" style={{ marginTop: 16 }}>
      <DetailList items={items} />
      {formulas ? (
        <pre style={PRE}>{JSON.stringify(formulas, null, 2)}</pre>
      ) : (
        <DataUnavailable feature="Formulas" />
      )}
    </Card>
  );
}

function FatigueCard({ source }: { source: unknown }) {
  const reasons = readArray<string>(source, ['alert_reasons']) ?? [];
  const thresholds = readRecord(source, ['thresholds']);
  return (
    <Card title="Alert fatigue (#26)" style={{ marginTop: 16 }}>
      <DetailList
        items={[
          { label: 'Window', value: windowLabel(source) },
          { label: 'Human validations', value: readNumber(source, ['human_validations']) ?? undefined },
          { label: 'Active days', value: readNumber(source, ['active_days']) ?? undefined },
          {
            label: 'Validations per active day',
            value: readNumber(source, ['validations_per_active_day']) ?? undefined
          },
          {
            label: 'Rubber-stamp ratio (no change)',
            value: formatPercent(readNumber(source, ['no_change_validation_ratio']))
          },
          { label: 'Fatigue score', value: readNumber(source, ['fatigue_score']) ?? undefined },
          {
            label: 'Alert triggered',
            value: readBoolean(source, ['alert_triggered']) === true ? 'YES' : 'NO'
          },
          { label: 'Thresholds', value: thresholds ? JSON.stringify(thresholds) : undefined }
        ]}
      />
      {reasons.length > 0 ? (
        <ul style={{ marginLeft: 20 }} data-testid="fatigue-reasons">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}

function windowLabel(source: unknown): string | undefined {
  const start = readString(source, ['window_start']);
  const end = readString(source, ['window_end']);
  const days = readNumber(source, ['window_days']);
  if (!start && !end && days === null) return undefined;
  return `${start ?? '?'} → ${end ?? '?'}${days === null ? '' : ` (${days} days)`}`;
}

function MinutesCard({ source }: { source: unknown }) {
  const assumptions = readRecord(source, ['assumptions']);
  return (
    <Card title="Analyst minutes saved (#47)" style={{ marginTop: 16 }}>
      <DetailList
        items={[
          { label: 'Findings triaged', value: readNumber(source, ['findings_triaged']) ?? undefined },
          {
            label: 'Triaged automatically (no human)',
            value: readNumber(source, ['findings_automatically_triaged']) ?? undefined
          },
          {
            label: 'Manual minutes if all human',
            value: readNumber(source, ['manual_minutes_if_all_human']) ?? undefined
          },
          {
            label: 'Estimated minutes spent',
            value: readNumber(source, ['estimated_minutes_spent']) ?? undefined
          },
          { label: 'Minutes saved', value: readNumber(source, ['minutes_saved']) ?? undefined },
          { label: 'Hours saved', value: readNumber(source, ['hours_saved']) ?? undefined }
        ]}
      />
      {assumptions ? (
        <pre style={PRE}>{JSON.stringify(assumptions, null, 2)}</pre>
      ) : (
        <DataUnavailable feature="Assumptions" />
      )}
    </Card>
  );
}

function CorpusCard({ source, coverage }: { source: unknown; coverage: number | null }) {
  const covered = readArray<string>(source, ['covered_risk_types']) ?? [];
  const gaps = readArray<string>(source, ['gaps']) ?? [];
  return (
    <Card title="Training corpus coverage (#34)" style={{ marginTop: 16 }}>
      <DetailList
        items={[
          { label: 'Corpus size', value: readNumber(source, ['size']) ?? undefined },
          { label: 'Coverage ratio', value: formatPercent(coverage) },
          { label: 'Covered risk types', value: covered.join(', ') || undefined },
          { label: 'Gaps (never judged by a human)', value: gaps.join(', ') || 'none' },
          {
            label: 'Configured risk types',
            value: (readArray<string>(source, ['configured_risk_types']) ?? []).join(', ') || undefined
          },
          {
            label: 'Observed risk types',
            value: (readArray<string>(source, ['observed_risk_types']) ?? []).join(', ') || undefined
          }
        ]}
      />
    </Card>
  );
}

const PRE = {
  background: 'var(--bg-secondary)',
  padding: 10,
  borderRadius: 6,
  overflowX: 'auto',
  fontSize: '0.82rem',
  marginTop: 8
} as const;

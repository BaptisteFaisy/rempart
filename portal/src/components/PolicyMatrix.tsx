import { EffectivePolicy, Priority, Severity } from '../types';
import { PRIORITIES, SEVERITIES } from '../types/constants';
import { DetailList, DetailItem } from './DetailList';

/** Severity → priority overrides written in the contract (empty = platform matrix). */
export function MatrixOverridesList({ policy }: { policy: EffectivePolicy }) {
  const overrides = policy?.matrix_overrides ?? {};
  const items: DetailItem[] = SEVERITIES.map((severity: Severity) => ({
    label: severity,
    value: overrides[severity] ?? 'platform deterministic matrix'
  }));
  return <DetailList items={items} />;
}

/** Contractual remediation deadlines, per priority. */
export function DueDaysList({ policy }: { policy: EffectivePolicy }) {
  const dueDays = policy?.due_days ?? {};
  const items: DetailItem[] = PRIORITIES.map((priority: Priority) => {
    const days = dueDays[priority];
    return {
      label: `${priority} deadline`,
      value: days === null || days === undefined ? 'no deadline' : `${days} days`
    };
  });
  return <DetailList items={items} />;
}

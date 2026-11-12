import { Priority, FindingStatus, RunStatus, MandateStatus } from '../types';

export const PRIORITY_CLASS: Record<Priority, string> = {
  P1: 'badge-p1',
  P2: 'badge-p2',
  P3: 'badge-p3',
  P4: 'badge-p4'
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  return (
    <span className={`badge ${PRIORITY_CLASS[priority]}`} data-testid="priority-badge">
      {priority}
    </span>
  );
}

export const FINDING_STATUS_CLASS: Record<FindingStatus, string> = {
  new: 'status-info',
  pending_validation: 'status-warning',
  confirmed: 'status-danger',
  false_positive: 'status-muted',
  risk_accepted: 'status-muted',
  in_remediation: 'status-info',
  to_retest: 'status-warning',
  closed: 'status-success',
  reopened: 'status-danger'
};

export function FindingStatusBadge({ status }: { status: FindingStatus }) {
  const cls = FINDING_STATUS_CLASS[status] ?? 'status-muted';
  return (
    <span className={`badge ${cls}`} data-testid="finding-status-badge">
      {status.replace(/_/g, ' ')}
    </span>
  );
}

export const RUN_STATUS_CLASS: Record<RunStatus, string> = {
  queued: 'status-info',
  running: 'status-warning',
  completed: 'status-success',
  failed: 'status-danger',
  stopped: 'status-muted',
  blocked: 'status-danger'
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const cls = RUN_STATUS_CLASS[status] ?? 'status-muted';
  return (
    <span className={`badge ${cls}`} data-testid="run-status-badge">
      {status}
    </span>
  );
}

export const MANDATE_STATUS_CLASS: Record<MandateStatus, string> = {
  none: 'status-danger',
  pending: 'status-warning',
  valid: 'status-success',
  expired: 'status-danger'
};

/** Test mandate (authorisation to scan) — a run is refused without a valid one. */
export function MandateBadge({ status }: { status: MandateStatus }) {
  const cls = MANDATE_STATUS_CLASS[status] ?? 'status-muted';
  return (
    <span className={`badge ${cls}`} data-testid="mandate-badge">
      mandate: {status}
    </span>
  );
}

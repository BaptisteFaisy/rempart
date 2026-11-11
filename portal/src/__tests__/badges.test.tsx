import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { PriorityBadge, FindingStatusBadge, RunStatusBadge, PRIORITY_CLASS } from '../components/Badges';
import { Priority, FindingStatus, RunStatus } from '../types';

describe('Badges components', () => {
  it('renders PriorityBadge with corresponding styling class', () => {
    const priorities: Priority[] = ['P1', 'P2', 'P3', 'P4'];
    priorities.forEach((p) => {
      const { getByText, unmount } = render(<PriorityBadge priority={p} />);
      const badge = getByText(p);
      expect(badge.className).toContain(PRIORITY_CLASS[p]);
      unmount();
    });
  });

  it('renders FindingStatusBadge formatted as words', () => {
    const statuses: FindingStatus[] = ['pending_validation', 'confirmed', 'false_positive', 'closed'];
    statuses.forEach((s) => {
      const label = s.replace(/_/g, ' ');
      const { getByText, unmount } = render(<FindingStatusBadge status={s} />);
      expect(getByText(label)).toBeDefined();
      unmount();
    });
  });

  it('renders RunStatusBadge with correct label', () => {
    const runs: RunStatus[] = ['running', 'completed', 'failed', 'blocked'];
    runs.forEach((r) => {
      const { getByText, unmount } = render(<RunStatusBadge status={r} />);
      expect(getByText(r)).toBeDefined();
      unmount();
    });
  });
});

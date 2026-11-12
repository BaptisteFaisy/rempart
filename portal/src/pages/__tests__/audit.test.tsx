import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuditPage } from '../Audit';
import { portalApi } from '../../api/service';
import { AuditEvent, Tenant } from '../../types';

const TENANTS: Tenant[] = [
  {
    tenant_id: 'demo-a',
    name: 'Northwind Retail',
    plan: 'continu',
    contacts: [],
    monthly_budget_hours: 40,
    mandate_status: 'valid',
    created_at: '2026-10-05T08:00:00Z'
  }
];

const EVENTS: AuditEvent[] = [
  {
    audit_id: 'aud-1',
    actor: 'analyst@rempart',
    action: 'finding.decision',
    object_type: 'finding',
    object_id: 'f-app-shop-0',
    result: 'ok',
    created_at: '2026-10-06T10:00:00Z'
  },
  {
    audit_id: 'aud-2',
    actor: 'platform@rempart',
    action: 'run.start',
    object_type: 'run',
    object_id: 'run-app-shop-1',
    result: 'ok',
    created_at: '2026-10-07T02:00:00Z'
  }
];

const page = (events: AuditEvent[]) => ({
  events,
  count: events.length,
  total: events.length,
  limit: 50,
  offset: 0,
  next_offset: null,
  scan_truncated: false
});

function renderPage() {
  return render(
    <MemoryRouter>
      <AuditPage />
    </MemoryRouter>
  );
}

describe('Audit page', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(
      'rempart_session',
      JSON.stringify({ role: 'analyst', tenant_id: 'demo-a' })
    );
    vi.spyOn(portalApi, 'getTenants').mockResolvedValue(TENANTS);
  });

  afterEach(() => vi.restoreAllMocks());

  it('renders the journal and states that it is not modifiable', async () => {
    vi.spyOn(portalApi, 'getAudit').mockResolvedValue(page(EVENTS));
    renderPage();

    expect(screen.getByTestId('audit-readonly-note').textContent).toContain('not modifiable');
    await waitFor(() => expect(screen.getByText('finding.decision')).toBeDefined());
    expect(screen.getByText('analyst@rempart')).toBeDefined();
    expect(screen.getByText('run-app-shop-1')).toBeDefined();
  });

  it('sends the filters to the API when Apply filters is clicked', async () => {
    const spy = vi.spyOn(portalApi, 'getAudit').mockResolvedValue(page(EVENTS));
    renderPage();

    fireEvent.change(screen.getByLabelText('Action'), { target: { value: 'run.start' } });
    fireEvent.change(screen.getByLabelText('Actor'), { target: { value: 'platform@rempart' } });
    fireEvent.change(screen.getByLabelText('Object type'), { target: { value: 'run' } });
    fireEvent.click(screen.getByText('Apply filters'));

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith(
        expect.objectContaining({
          action: 'run.start',
          actor: 'platform@rempart',
          object_type: 'run'
        })
      )
    );
  });

  it('shows a clean message when the frozen dataset has no audit collection', async () => {
    vi.spyOn(portalApi, 'getAudit').mockResolvedValue(null);
    renderPage();

    await waitFor(() => expect(screen.getByTestId('data-unavailable')).toBeDefined());
    expect(screen.getByTestId('data-unavailable').textContent).toContain('frozen dataset');
  });
});

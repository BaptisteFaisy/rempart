import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PolicyPage } from '../Policy';
import { portalApi } from '../../api/service';
import { BudgetPayload, EffectivePolicy, Tenant, TenantPolicy } from '../../types';

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

const POLICY: TenantPolicy = {
  tenant_id: 'demo-a',
  policy: { hourly_rate: 55, matrix_overrides: { High: 'P1' } },
  effective: {
    due_days: { P1: 7, P2: 30, P3: 90, P4: null },
    matrix_overrides: { High: 'P1' },
    blocking_threshold: 'High',
    hourly_rate: 55
  } as EffectivePolicy
};

const BUDGET: BudgetPayload = {
  tenant_id: 'demo-a',
  month: '2026-10',
  hours_used: 5.4,
  thresholds_hit: [],
  auto_stop: true,
  monthly_budget_hours: 40,
  budget_pct: 13.5,
  allowed: true
};

const DEFAULTS: EffectivePolicy = {
  due_days: { P1: 7, P2: 30, P3: 90, P4: null },
  matrix_overrides: {},
  blocking_threshold: 'High',
  hourly_rate: 50
};

function renderPage() {
  return render(
    <MemoryRouter>
      <PolicyPage />
    </MemoryRouter>
  );
}

function mockReads(policy: TenantPolicy | null) {
  vi.spyOn(portalApi, 'getTenants').mockResolvedValue(TENANTS);
  vi.spyOn(portalApi, 'getPolicy').mockResolvedValue(policy);
  vi.spyOn(portalApi, 'getPolicyDefaults').mockResolvedValue(DEFAULTS);
  vi.spyOn(portalApi, 'getBudget').mockResolvedValue(BUDGET);
  vi.spyOn(portalApi, 'updateBudget').mockResolvedValue({ ...BUDGET, auto_stop: false });
}

function setRole(role: string) {
  localStorage.clear();
  localStorage.setItem('rempart_session', JSON.stringify({ role, tenant_id: 'demo-a' }));
}

describe('Policy page', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows the contract policy: deadlines, matrix, threshold and hourly rate', async () => {
    setRole('analyst');
    mockReads(POLICY);
    renderPage();

    await waitFor(() => expect(screen.getByTestId('policy-read-only')).toBeDefined());
    expect(screen.getAllByText('7 days').length).toBeGreaterThan(0);
    expect(screen.getAllByText('no deadline').length).toBeGreaterThan(0);
    expect(screen.getAllByText('High').length).toBeGreaterThan(0);
    expect(screen.getAllByText('$55').length).toBeGreaterThan(0);
    expect(screen.getByTestId('auto-stop-toggle')).toBeDefined();
  });

  it('lets platform_admin edit and PUT the policy', async () => {
    setRole('platform_admin');
    mockReads(POLICY);
    const save = vi
      .spyOn(portalApi, 'updatePolicy')
      .mockResolvedValue({ ...POLICY, policy: { hourly_rate: 60 } });
    renderPage();

    fireEvent.click(await screen.findByTestId('policy-edit'));
    const rate = await screen.findByLabelText(/Hourly rate/);
    fireEvent.change(rate, { target: { value: '60' } });
    fireEvent.click(screen.getByTestId('policy-save'));

    await waitFor(() => expect(save).toHaveBeenCalled());
    const payload = save.mock.calls[0][1] as EffectivePolicy;
    expect(payload.hourly_rate).toBe(60);
    expect(payload.due_days?.P1).toBe(7);
    expect(payload.matrix_overrides?.High).toBe('P1');
    expect(payload.blocking_threshold).toBe('High');
  });

  it('toggles the auto-stop guard through the budget route', async () => {
    setRole('platform_admin');
    mockReads(POLICY);
    vi.spyOn(portalApi, 'updatePolicy').mockResolvedValue(POLICY);
    renderPage();

    const toggle = await screen.findByTestId('auto-stop-toggle');
    fireEvent.click(toggle);

    await waitFor(() =>
      expect(portalApi.updateBudget).toHaveBeenCalledWith('demo-a', { auto_stop: false })
    );
  });

  it('shows a clean message when the frozen dataset has no policy collection', async () => {
    setRole('analyst');
    mockReads(null);
    renderPage();

    await waitFor(() => expect(screen.getByTestId('data-unavailable')).toBeDefined());
    expect(screen.getByTestId('data-unavailable').textContent).toContain('policy');
  });
});

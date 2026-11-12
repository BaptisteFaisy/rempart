import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Budget } from '../Budget';
import { portalApi } from '../../api/service';
import { BudgetForecast, BudgetPayload, Tenant } from '../../types';

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

const BUDGET: BudgetPayload = {
  tenant_id: 'demo-a',
  month: '2026-11',
  hours_used: 20,
  thresholds_hit: [50],
  auto_stop: true,
  monthly_budget_hours: 40,
  budget_pct: 50,
  allowed: true
};

const FORECAST: BudgetForecast = {
  tenant_id: 'demo-a',
  month: '2026-11',
  hours_used: 20,
  monthly_budget_hours: 40,
  projected_month_end_hours: 52,
  projected_cost_usd: 2600,
  daily_burn_hours: 1.7,
  projected_exhaustion_date: '2026-11-24',
  thresholds: [50, 80, 100],
  auto_stop: true
};

function renderPage() {
  return render(
    <MemoryRouter>
      <Budget />
    </MemoryRouter>
  );
}

describe('Budget page enrichment', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(
      'rempart_session',
      JSON.stringify({ role: 'platform_admin', tenant_id: 'demo-a' })
    );
    vi.spyOn(portalApi, 'getTenants').mockResolvedValue(TENANTS);
    vi.spyOn(portalApi, 'getTenant').mockResolvedValue(TENANTS[0]);
    vi.spyOn(portalApi, 'getBudget').mockResolvedValue(BUDGET);
  });

  afterEach(() => vi.restoreAllMocks());

  it('shows the month-end forecast, the projected exhaustion date and the thresholds', async () => {
    vi.spyOn(portalApi, 'getForecast').mockResolvedValue(FORECAST);
    renderPage();

    await waitFor(() => expect(screen.getByText('52.0 h')).toBeDefined());
    expect(screen.getByText('2026-11-24')).toBeDefined();
    expect(screen.getByText('$2600')).toBeDefined();
    expect(screen.getByText('50, 80, 100')).toBeDefined();
    expect(screen.getByTestId('auto-stop-toggle')).toBeDefined();
  });

  it('edits the monthly allocation through PUT /v1/tenants/{id}/budget', async () => {
    vi.spyOn(portalApi, 'getForecast').mockResolvedValue(FORECAST);
    const update = vi.spyOn(portalApi, 'updateBudget').mockResolvedValue({
      ...BUDGET,
      monthly_budget_hours: 60
    });
    renderPage();

    fireEvent.change(await screen.findByTestId('budget-hours-input'), {
      target: { value: '60' }
    });
    fireEvent.click(screen.getByTestId('budget-save'));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith('demo-a', { monthly_budget_hours: 60 })
    );
  });

  it('shows a banner when the global kill-switch is active', async () => {
    vi.spyOn(portalApi, 'getForecast').mockResolvedValue(FORECAST);
    vi.spyOn(portalApi, 'getBudget').mockResolvedValue({ ...BUDGET, kill_switch: true });
    renderPage();

    const banner = await screen.findByTestId('kill-switch-banner');
    expect(banner.textContent).toContain('aucun test ne sera lancé');
  });

  it('shows a clean message when the frozen dataset has no forecast collection', async () => {
    vi.spyOn(portalApi, 'getForecast').mockResolvedValue(null);
    renderPage();

    await waitFor(() => expect(screen.getByTestId('data-unavailable')).toBeDefined());
    expect(screen.getByTestId('data-unavailable').textContent).toContain('forecast');
  });
});

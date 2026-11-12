import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ApplicationPage } from '../Application';
import { portalApi } from '../../api/service';
import { Application, OnboardingStatus, Run, Tenant } from '../../types';

const TENANT: Tenant = {
  tenant_id: 'demo-a',
  name: 'Northwind Retail',
  plan: 'continu',
  contacts: [],
  monthly_budget_hours: 40,
  mandate_status: 'valid',
  created_at: '2026-10-05T08:00:00Z'
};

const APP: Application = {
  app_id: 'app-shop',
  tenant_id: 'demo-a',
  name: 'ShopLite',
  criticality: 'high',
  internet_exposed: true,
  data_types: ['personal', 'payment'],
  environment: 'production',
  agent_space_id: 'space-app-shop',
  domains: ['shop.demo.example'],
  repositories: ['demo/shoplite'],
  team: 'Core',
  ticket_channel: 'github',
  context: { concurrency_quota: 3 },
  created_at: '2026-10-05T08:00:00Z',
  test_windows: [
    { days: ['mon', 'tue'], start: '22:00', end: '06:00', environment: 'production' }
  ]
};

const RUNNING: Run = {
  run_id: 'run-app-shop-9',
  config_id: 'cfg-app-shop-delivery',
  app_id: 'app-shop',
  tenant_id: 'demo-a',
  trigger: 'manual',
  status: 'running',
  started_at: '2026-11-10T02:00:00Z',
  ended_at: null
};

const ONBOARDING: OnboardingStatus = {
  app_id: 'app-shop',
  onboarded: true,
  agent_space_id: 'space-app-shop',
  domains: ['shop.demo.example'],
  configs: [
    {
      config_id: 'cfg-app-shop-delivery',
      app_id: 'app-shop',
      kind: 'delivery',
      risk_types: ['IDOR', 'SQLI'],
      blocking_threshold: 'High',
      schedule: '0 2 * * *'
    }
  ]
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/applications/app-shop']}>
      <Routes>
        <Route path="/applications/:appId" element={<ApplicationPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('Application page enrichment', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(
      'rempart_session',
      JSON.stringify({ role: 'platform_admin', tenant_id: 'demo-a' })
    );
    vi.spyOn(portalApi, 'getApplication').mockResolvedValue(APP);
    vi.spyOn(portalApi, 'getTenant').mockResolvedValue(TENANT);
    vi.spyOn(portalApi, 'getOnboarding').mockResolvedValue(ONBOARDING);
    vi.spyOn(portalApi, 'getRuns').mockResolvedValue([RUNNING]);
  });

  afterEach(() => vi.restoreAllMocks());

  it('shows the mandate, the test windows, the agent space and the concurrency quota', async () => {
    renderPage();

    await waitFor(() => expect(screen.getByTestId('mandate-badge')).toBeDefined());
    expect(screen.getByTestId('mandate-badge').textContent).toContain('valid');
    expect(screen.getByTestId('test-windows').textContent).toContain('mon, tue');
    expect(screen.getByTestId('test-windows').textContent).toContain('22:00–06:00 UTC');
    expect(screen.getByTestId('application-scope').textContent).toContain('space-app-shop');
    expect(screen.getByTestId('application-scope').textContent).toContain('3 simultaneous tests');
  });

  it('starts an on-demand test and stops the active run', async () => {
    const start = vi.spyOn(portalApi, 'postRun').mockResolvedValue(RUNNING);
    const stop = vi
      .spyOn(portalApi, 'stopRun')
      .mockResolvedValue({ ...RUNNING, status: 'stopped', ended_at: '2026-11-10T03:00:00Z' });
    renderPage();

    fireEvent.click(await screen.findByTestId('run-start'));
    await waitFor(() => expect(start).toHaveBeenCalledWith('app-shop'));

    fireEvent.click(await screen.findByTestId('run-stop'));
    await waitFor(() => expect(stop).toHaveBeenCalledWith('run-app-shop-9'));
  });

  it('shows the onboarding state and the domain verification instructions returned by the API', async () => {
    vi.spyOn(portalApi, 'postOnboarding').mockResolvedValue({
      ...ONBOARDING,
      verification_method: 'HTTP_ROUTE',
      verification_instructions: [
        {
          method: 'HTTP_ROUTE',
          domain: 'shop.demo.example',
          action: 'Publish the token "abc123" on route /.awscontinuum',
          requires_dns_access: false
        }
      ]
    });
    renderPage();

    await waitFor(() => expect(screen.getByTestId('onboarding-panel')).toBeDefined());
    expect(screen.getByTestId('onboarding-panel').textContent).toContain('cfg-app-shop-delivery');

    fireEvent.select(screen.getByLabelText('Domain verification method'), {
      target: { value: 'HTTP_ROUTE' }
    });
    fireEvent.click(screen.getByTestId('onboarding-start'));

    await waitFor(() => expect(screen.getByTestId('verification-instructions')).toBeDefined());
    expect(screen.getByTestId('verification-instructions').textContent).toContain('abc123');
    expect(screen.getByTestId('verification-instructions').textContent).toContain(
      'no DNS access needed'
    );
  });
});

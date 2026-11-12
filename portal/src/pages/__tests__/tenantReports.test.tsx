import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { TenantPage } from '../Tenant';
import { Reports } from '../Reports';
import { portalApi } from '../../api/service';
import { downloadJson } from '../../api/download';
import { Application, EvidencePack, Kpis, Report, Tenant } from '../../types';

vi.mock('../../api/download', () => ({ downloadJson: vi.fn() }));

const TENANT: Tenant = {
  tenant_id: 'demo-a',
  name: 'Northwind Retail',
  plan: 'continu',
  contacts: [{ name: 'Ops', email: 'ops@demo-a.example' }],
  monthly_budget_hours: 40,
  mandate_status: 'valid',
  created_at: '2026-10-05T08:00:00Z',
  free_tier_confirmed: false
};

const APPS: Application[] = [
  {
    app_id: 'app-shop',
    tenant_id: 'demo-a',
    name: 'ShopLite',
    criticality: 'high',
    internet_exposed: true,
    data_types: ['personal'],
    environment: 'staging',
    agent_space_id: 'space-app-shop',
    domains: ['shop.demo.example'],
    repositories: ['demo/shoplite'],
    team: 'Core',
    ticket_channel: 'github',
    created_at: '2026-10-05T08:00:00Z'
  }
];

const KPIS: Kpis = {
  delivery_to_result_hours: 1.2,
  critical_blocked_before_prod: 1,
  mean_time_to_fix_days_by_priority: { P1: 3, P2: null, P3: null, P4: null },
  sla_compliance: 1,
  coverage: 0.9,
  reopen_rate: 0,
  findings_open_by_priority: { P1: 0, P2: 1, P3: 2, P4: 0 },
  findings_closed: 3,
  tests_total: 6,
  tests_blocked: 0,
  task_hours_used: 5.4,
  cost_usd: 270
};

const REPORTS: Report[] = [
  {
    report_id: 'rep-demo-a-2026-10',
    tenant_id: 'demo-a',
    period: '2026-10',
    s3_key: 'reports/demo-a/2026-10/demo.pdf',
    kpis: { coverage: 1 },
    created_at: '2026-11-03T06:00:00Z'
  }
];

const PACK: EvidencePack = {
  identity: { tenant_id: 'demo-a', period: '2026-10' },
  integrity: { algorithm: 'sha256', digest: 'deadbeef' }
};

function setRole(role: string) {
  localStorage.clear();
  localStorage.setItem('rempart_session', JSON.stringify({ role, tenant_id: 'demo-a' }));
}

describe('Tenant page enrichment', () => {
  beforeEach(() => {
    setRole('platform_admin');
    vi.spyOn(portalApi, 'getTenant').mockResolvedValue(TENANT);
    vi.spyOn(portalApi, 'getApplications').mockResolvedValue(APPS);
    vi.spyOn(portalApi, 'getTenantKpis').mockResolvedValue(KPIS);
    vi.spyOn(portalApi, 'getTenants').mockResolvedValue([TENANT]);
    vi.spyOn(portalApi, 'getReports').mockResolvedValue(REPORTS);
  });

  afterEach(() => vi.restoreAllMocks());

  it('generates the monthly report and links straight to the client audit journal', async () => {
    const generate = vi.spyOn(portalApi, 'postReport').mockResolvedValue(REPORTS[0]);
    render(
      <MemoryRouter initialEntries={['/tenants/demo-a']}>
        <Routes>
          <Route path="/tenants/:tenantId" element={<TenantPage />} />
          <Route path="/reports" element={<Reports />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByTestId('tenant-kpis')).toBeDefined());
    const auditLink = screen.getByText('Audit journal').closest('a');
    expect(auditLink?.getAttribute('href')).toBe('/audit?tenant=demo-a');

    fireEvent.click(screen.getByTestId('generate-report'));
    await waitFor(() => expect(generate).toHaveBeenCalledWith('demo-a'));
  });
});

describe('Reports page enrichment', () => {
  beforeEach(() => {
    setRole('analyst');
    vi.spyOn(portalApi, 'getTenants').mockResolvedValue([TENANT]);
    vi.spyOn(portalApi, 'getReports').mockResolvedValue(REPORTS);
  });

  afterEach(() => vi.restoreAllMocks());

  it('downloads the evidence dossier next to the monthly report', async () => {
    const evidence = vi.spyOn(portalApi, 'getEvidence').mockResolvedValue(PACK);
    const inspect = vi.spyOn(portalApi, 'getReport').mockResolvedValue(REPORTS[0]);
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>
    );

    fireEvent.change(await screen.findByTestId('tenant-picker'), {
      target: { value: 'demo-a' }
    });
    fireEvent.click(await screen.findByTestId('evidence-download'));
    await waitFor(() => expect(evidence).toHaveBeenCalledWith('demo-a'));
    await waitFor(() =>
      expect(downloadJson).toHaveBeenCalledWith('evidence-demo-a.json', PACK)
    );

    fireEvent.click(screen.getByTestId('report-inspect'));
    await waitFor(() => expect(inspect).toHaveBeenCalledWith('rep-demo-a-2026-10'));
  });
});

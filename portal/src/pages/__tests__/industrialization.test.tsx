import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { IndustrializationPage } from '../Industrialization';
import { portalApi } from '../../api/service';
import { Industrialization, Tenant } from '../../types';

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

/** Grouped shape: one block per metric family. */
const NESTED: Industrialization = {
  tenant_id: 'demo-a',
  human_intervention: {
    findings_total: 6,
    findings_with_human_decision: 2,
    human_intervention_rate: 0.3333,
    findings_reviewed_by_human: 2,
    findings_diverged: 1,
    agent_human_divergence_rate: 0.1667,
    divergence_rate_among_reviewed: 0.5,
    formulas: { human_intervention_rate: 'findings_with_human_decision / findings_total' }
  },
  alert_fatigue: {
    window_start: '2026-10-01T00:00:00Z',
    window_end: '2026-10-31T00:00:00Z',
    window_days: 30,
    human_validations: 4,
    active_days: 3,
    validations_per_active_day: 1.33,
    no_change_validation_ratio: 0.25,
    fatigue_score: 0.08,
    alert_triggered: false,
    alert_reasons: [],
    thresholds: { fatigue_score: 0.5 }
  },
  minutes_saved: {
    findings_triaged: 6,
    findings_automatically_triaged: 4,
    manual_minutes_if_all_human: 72,
    estimated_minutes_spent: 28,
    minutes_saved: 44,
    hours_saved: 0.73,
    assumptions: { measured: false, is_estimate: true }
  },
  corpus: {
    size: 5,
    coverage_ratio: 0.6,
    covered_risk_types: ['IDOR', 'SQLI'],
    configured_risk_types: ['IDOR', 'SQLI', 'BrokenAuth'],
    observed_risk_types: ['IDOR', 'SQLI', 'BrokenAuth', 'SSRF'],
    gaps: ['BrokenAuth', 'SSRF']
  }
};

/** Forme plate : chaque métrique au premier niveau. Le backend peut renvoyer
 * cette forme ; le portail doit la tolérer sans casser. Hors type volontaire. */
const FLAT = {
  tenant_id: 'demo-a',
  findings_total: 6,
  human_intervention_rate: 0.5,
  agent_human_divergence_rate: 0.25,
  minutes_saved: 30,
  fatigue_score: 0.9,
  alert_triggered: true,
  alert_reasons: ['queue too long'],
  coverage_ratio: 0.4,
  gaps: ['SSRF']
} as unknown as Industrialization;

function renderPage() {
  return render(
    <MemoryRouter>
      <IndustrializationPage />
    </MemoryRouter>
  );
}

describe('Industrialization page', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(
      'rempart_session',
      JSON.stringify({ role: 'analyst', tenant_id: 'demo-a' })
    );
    vi.spyOn(portalApi, 'getTenants').mockResolvedValue(TENANTS);
  });

  afterEach(() => vi.restoreAllMocks());

  it('reads the grouped payload: intervention, divergence, fatigue, minutes, corpus', async () => {
    vi.spyOn(portalApi, 'getIndustrialization').mockResolvedValue(NESTED);
    renderPage();

    await waitFor(() => expect(screen.getByText('33%')).toBeDefined());
    expect(screen.getByText('17%')).toBeDefined();
    expect(screen.getByText('44 min')).toBeDefined();
    expect(screen.getAllByText('0.08').length).toBeGreaterThan(0);
    expect(screen.getByText('No alert')).toBeDefined();
    expect(screen.getByText('60%')).toBeDefined();
    expect(screen.getByText('BrokenAuth, SSRF')).toBeDefined();
    expect(screen.getByText(/findings_with_human_decision \/ findings_total/)).toBeDefined();
  });

  it('reads a flat payload the same way', async () => {
    vi.spyOn(portalApi, 'getIndustrialization').mockResolvedValue(FLAT);
    renderPage();

    await waitFor(() => expect(screen.getByText('50%')).toBeDefined());
    expect(screen.getByText('30 min')).toBeDefined();
    expect(screen.getByText('ALERT TRIGGERED')).toBeDefined();
    expect(screen.getByText('queue too long')).toBeDefined();
  });

  it('shows a clean message when the frozen dataset has no industrialization collection', async () => {
    vi.spyOn(portalApi, 'getIndustrialization').mockResolvedValue(null);
    renderPage();

    await waitFor(() => expect(screen.getByTestId('data-unavailable')).toBeDefined());
    expect(screen.getByTestId('data-unavailable').textContent).toContain('industrialization');
  });
});

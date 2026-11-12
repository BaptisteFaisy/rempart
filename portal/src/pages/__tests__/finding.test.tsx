import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { FindingPage } from '../Finding';
import { portalApi } from '../../api/service';
import { EvidencePack, Finding } from '../../types';

const FINDING: Finding = {
  finding_id: 'f-app-shop-4',
  app_id: 'app-shop',
  tenant_id: 'demo-a',
  run_id: 'run-app-shop-2',
  fingerprint: 'fp-legacy',
  title: 'Legacy endpoint without authentication',
  risk_type: 'BrokenAuth',
  severity: 'Medium',
  confidence: 'High',
  priority: 'P3',
  status: 'risk_accepted',
  due_at: '2027-01-04T10:00:00Z',
  ticket_url: 'https://github.com/demo/shoplite/issues/42',
  remediation_pr_url: null,
  created_at: '2026-10-06T10:00:00Z',
  updated_at: '2026-10-08T09:00:00Z',
  risk_review_at: '2026-10-08T09:00:00Z',
  risk_review_by: 'security@northwind.example'
};

const DOSSIER: EvidencePack = {
  identity: { tenant_id: 'demo-a', period: '2026-10' },
  decision_chains: [
    {
      finding: { finding_id: 'f-app-shop-4', title: FINDING.title, priority: 'P3' },
      decisions: [
        {
          decision_id: 'dec-a',
          author_type: 'agent',
          author: 'triage-agent',
          action: 'CONFIRMED',
          justification: 'deterministic matrix: Medium/High',
          created_at: '2026-10-06T10:05:00Z'
        },
        {
          decision_id: 'dec-h',
          author_type: 'human',
          author: 'security@northwind.example',
          action: 'risk_accepted',
          justification: 'internal network only, compensated control',
          created_at: '2026-10-08T09:00:00Z'
        }
      ]
    }
  ]
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/findings/f-app-shop-4']}>
      <Routes>
        <Route path="/findings/:findingId" element={<FindingPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('Finding page enrichment', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(
      'rempart_session',
      JSON.stringify({ role: 'client_security', tenant_id: 'demo-a' })
    );
    vi.spyOn(portalApi, 'getFinding').mockResolvedValue(FINDING);
    vi.spyOn(portalApi, 'getEvidence').mockResolvedValue(DOSSIER);
  });

  afterEach(() => vi.restoreAllMocks());

  it('shows priority, due date and the risk acceptance with its review date', async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText('Legacy endpoint without authentication')).toBeDefined());
    expect(screen.getByTestId('priority-badge').textContent).toBe('P3');
    expect(screen.getByText('2027-01-04T10:00:00Z')).toBeDefined();
    expect(screen.getByText('Risk accepted')).toBeDefined();
    expect(screen.getAllByText('2026-10-08T09:00:00Z').length).toBeGreaterThan(0);
    expect(screen.getAllByText('security@northwind.example').length).toBeGreaterThan(0);
    expect(screen.getByText('https://github.com/demo/shoplite/issues/42')).toBeDefined();
  });

  it('shows the decision chain (agent then human) from the evidence dossier', async () => {
    renderPage();

    await waitFor(() => expect(screen.getByTestId('decision-chain')).toBeDefined());
    const chain = screen.getByTestId('decision-chain');
    expect(chain.textContent).toContain('agent');
    expect(chain.textContent).toContain('human');
    expect(chain.textContent).toContain('compensated control');
  });

  it('requests a remediation pull request through POST /v1/findings/{id}/remediation', async () => {
    const remediation = vi.spyOn(portalApi, 'postRemediation').mockResolvedValue({
      finding: {
        ...FINDING,
        status: 'in_remediation',
        remediation_pr_url: 'https://github.com/demo/shoplite/pull/77'
      },
      remediation: { started: true }
    });
    renderPage();

    fireEvent.click(await screen.findByTestId('finding-remediation'));

    await waitFor(() => expect(remediation).toHaveBeenCalledWith('f-app-shop-4'));
    await waitFor(() =>
      expect(screen.getByText('https://github.com/demo/shoplite/pull/77')).toBeDefined()
    );
  });
});

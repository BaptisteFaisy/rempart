import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { EvidencePage } from '../Evidence';
import { portalApi } from '../../api/service';
import { EvidencePack, Tenant } from '../../types';

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

const PACK: EvidencePack = {
  identity: {
    product: 'Rempart',
    evidence_version: '1.0',
    tenant_id: 'demo-a',
    tenant_name: 'Northwind Retail',
    period: '2026-10',
    generated_at: '2026-11-01T06:00:00Z',
    mandate_status: 'valid',
    plan: 'continu'
  },
  scope: [{ app_id: 'app-shop', name: 'ShopLite', environment: 'staging' }],
  tests: [{ run_id: 'run-app-shop-1', status: 'completed', started_at: '2026-10-06T02:00:00Z' }],
  decision_chains: [
    {
      finding: {
        finding_id: 'f-app-shop-0',
        title: 'IDOR on order details',
        priority: 'P1',
        status: 'closed'
      },
      decisions: [
        {
          decision_id: 'dec-1',
          author_type: 'agent',
          author: 'triage-agent',
          action: 'CONFIRMED',
          justification: 'deterministic matrix',
          created_at: '2026-10-06T10:00:00Z'
        },
        {
          decision_id: 'dec-2',
          author_type: 'human',
          author: 'analyst@rempart',
          action: 'confirmed',
          justification: 'reproduced',
          created_at: '2026-10-06T11:00:00Z'
        }
      ]
    }
  ],
  closure_proofs: [
    {
      finding_id: 'f-app-shop-0',
      title: 'IDOR on order details',
      priority: 'P1',
      closed_at: '2026-10-20T09:48:00Z',
      proven_by_run_id: 'run-app-shop-3'
    }
  ],
  exceptions: {
    false_positives: [
      { finding_id: 'f-app-shop-2', title: 'Verbose header', severity: 'Low', priority: 'P4' }
    ],
    risk_accepted: [
      { finding_id: 'f-app-shop-4', title: 'Legacy endpoint', severity: 'Medium', priority: 'P3' }
    ]
  },
  audit_events: [
    {
      audit_id: 'aud-1',
      actor: 'analyst@rempart',
      action: 'finding.decision',
      object_type: 'finding',
      object_id: 'f-app-shop-0',
      result: 'ok',
      created_at: '2026-10-06T11:00:00Z'
    }
  ],
  integrity: {
    algorithm: 'sha256',
    digest: 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
    canonical_form: 'JSON, sort_keys=True, indent=2, ensure_ascii=False',
    recompute: 'sha256(render_evidence_pack_json(pack_without_integrity))'
  }
};

function renderPage() {
  return render(
    <MemoryRouter>
      <EvidencePage />
    </MemoryRouter>
  );
}

describe('Evidence page', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(
      'rempart_session',
      JSON.stringify({ role: 'analyst', tenant_id: 'demo-a' })
    );
    vi.spyOn(portalApi, 'getTenants').mockResolvedValue(TENANTS);
  });

  afterEach(() => vi.restoreAllMocks());

  it('shows the SHA-256 fingerprint, the decision chain, closure proofs and exceptions', async () => {
    vi.spyOn(portalApi, 'getEvidence').mockResolvedValue(PACK);
    renderPage();

    await waitFor(() => expect(screen.getByTestId('evidence-digest')).toBeDefined());
    expect(screen.getByTestId('evidence-digest').textContent).toContain('a1b2c3d4');
    expect(screen.getByText('agent:CONFIRMED → human:confirmed')).toBeDefined();
    expect(screen.getByText('run-app-shop-3')).toBeDefined();
    expect(screen.getByText('Verbose header')).toBeDefined();
    expect(screen.getByText('Legacy endpoint')).toBeDefined();
  });

  it('generates a dossier through POST /v1/tenants/{id}/evidence', async () => {
    vi.spyOn(portalApi, 'getEvidence').mockResolvedValue(null);
    const generate = vi.spyOn(portalApi, 'postEvidence').mockResolvedValue(PACK);
    renderPage();

    fireEvent.click(await screen.findByTestId('evidence-generate'));

    await waitFor(() => expect(generate).toHaveBeenCalledWith('demo-a', undefined));
    await waitFor(() => expect(screen.getByTestId('evidence-digest')).toBeDefined());
  });

  it('shows a clean message when the frozen dataset has no evidence collection', async () => {
    vi.spyOn(portalApi, 'getEvidence').mockResolvedValue(null);
    renderPage();

    await waitFor(() => expect(screen.getByTestId('data-unavailable')).toBeDefined());
    expect(screen.getByTestId('data-unavailable').textContent).toContain('evidence');
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TriageQueue } from '../pages/TriageQueue';
import { portalApi } from '../api/service';
import { Finding } from '../types';

const sampleFinding: Finding = {
  finding_id: 'test-find-1',
  app_id: 'app-shoplite',
  tenant_id: 'demo-tenant-shoplite',
  run_id: 'run-1',
  fingerprint: 'fp-1234',
  title: 'BOLA on user invoices',
  risk_type: 'BOLA',
  severity: 'Critical',
  confidence: 'High',
  priority: 'P1',
  status: 'pending_validation',
  created_at: '2026-11-10T12:00:00Z',
  updated_at: '2026-11-10T12:00:00Z'
};

describe('TriageQueue page', () => {
  beforeEach(() => {
    localStorage.clear();
    // Use analyst persona so buttons are enabled
    localStorage.setItem(
      'rempart_session',
      JSON.stringify({ role: 'analyst', tenant_id: 'demo-tenant-shoplite' })
    );
  });

  it('renders pending findings and handles confirmation click', async () => {
    vi.spyOn(portalApi, 'getFindings').mockResolvedValueOnce([sampleFinding]);
    const decisionSpy = vi.spyOn(portalApi, 'postDecision').mockResolvedValueOnce({
      decision_id: 'dec-1',
      finding_id: 'test-find-1',
      author_type: 'human',
      author: 'analyst@rempart',
      action: 'confirmed',
      justification: 'Looks real',
      created_at: '2026-11-10T12:05:00Z'
    });

    render(<TriageQueue />);

    await waitFor(() => {
      expect(screen.getByText('BOLA on user invoices')).toBeDefined();
    });

    const confirmBtn = screen.getByTestId('btn-confirm');
    expect(confirmBtn).toBeDefined();

    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(decisionSpy).toHaveBeenCalledWith(
        'test-find-1',
        'confirmed',
        expect.stringContaining('Confirmed')
      );
    });
  });
});

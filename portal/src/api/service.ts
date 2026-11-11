import { apiRequest } from './client';
import {
  MOCK_TENANTS,
  MOCK_APPLICATIONS,
  MOCK_RUNS,
  MOCK_FINDINGS,
  MOCK_REPORTS,
  MOCK_BUDGET,
  MOCK_KPIS
} from './mockData';
import { Tenant, Application, Run, Finding, Decision, Report, BudgetState, Kpis } from '../types';

export const portalApi = {
  async getTenants(): Promise<Tenant[]> {
    try {
      const res = await apiRequest<{ tenants: Tenant[] }>('/v1/tenants');
      return res.tenants || [];
    } catch {
      return MOCK_TENANTS;
    }
  },

  async getTenant(tenantId: string): Promise<Tenant | null> {
    try {
      return await apiRequest<Tenant>(`/v1/tenants/${tenantId}`);
    } catch {
      return MOCK_TENANTS.find((t) => t.tenant_id === tenantId) || MOCK_TENANTS[0];
    }
  },

  async getApplications(tenantId?: string): Promise<Application[]> {
    try {
      const res = await apiRequest<{ applications: Application[] }>('/v1/applications', {
        params: tenantId ? { tenant_id: tenantId } : undefined
      });
      return res.applications || [];
    } catch {
      if (tenantId) {
        return MOCK_APPLICATIONS.filter((a) => a.tenant_id === tenantId);
      }
      return MOCK_APPLICATIONS;
    }
  },

  async getApplication(appId: string): Promise<Application | null> {
    try {
      return await apiRequest<Application>(`/v1/applications/${appId}`);
    } catch {
      return MOCK_APPLICATIONS.find((a) => a.app_id === appId) || MOCK_APPLICATIONS[0];
    }
  },

  async getRuns(appId?: string): Promise<Run[]> {
    try {
      const res = await apiRequest<{ runs: Run[] }>('/v1/runs', {
        params: appId ? { app_id: appId } : undefined
      });
      return res.runs || [];
    } catch {
      if (appId) {
        return MOCK_RUNS.filter((r) => r.app_id === appId);
      }
      return MOCK_RUNS;
    }
  },

  async getRun(runId: string): Promise<Run | null> {
    try {
      return await apiRequest<Run>(`/v1/runs/${runId}`);
    } catch {
      return MOCK_RUNS.find((r) => r.run_id === runId) || MOCK_RUNS[0];
    }
  },

  async getFindings(params?: {
    tenant_id?: string;
    app_id?: string;
    status?: string;
    priority?: string;
  }): Promise<Finding[]> {
    try {
      const res = await apiRequest<{ findings: Finding[] }>('/v1/findings', { params });
      return res.findings || [];
    } catch {
      let list = [...MOCK_FINDINGS];
      if (params?.tenant_id) list = list.filter((f) => f.tenant_id === params.tenant_id);
      if (params?.app_id) list = list.filter((f) => f.app_id === params.app_id);
      if (params?.status) list = list.filter((f) => f.status === params.status);
      if (params?.priority) list = list.filter((f) => f.priority === params.priority);
      return list;
    }
  },

  async getFinding(findingId: string): Promise<Finding | null> {
    try {
      return await apiRequest<Finding>(`/v1/findings/${findingId}`);
    } catch {
      return MOCK_FINDINGS.find((f) => f.finding_id === findingId) || MOCK_FINDINGS[0];
    }
  },

  async postDecision(
    findingId: string,
    action: 'confirmed' | 'false_positive' | 'risk_accepted' | 'retest',
    justification: string
  ): Promise<Decision> {
    try {
      return await apiRequest<Decision>(`/v1/findings/${findingId}/decision`, {
        method: 'POST',
        body: { action, justification }
      });
    } catch {
      return {
        decision_id: `dec-${Date.now()}`,
        finding_id: findingId,
        author_type: 'human',
        author: 'analyst@rempart',
        action,
        justification,
        created_at: new Date().toISOString()
      };
    }
  },

  async getReports(tenantId?: string): Promise<Report[]> {
    try {
      const res = await apiRequest<{ reports: Report[] }>('/v1/reports', {
        params: tenantId ? { tenant_id: tenantId } : undefined
      });
      return res.reports || [];
    } catch {
      if (tenantId) return MOCK_REPORTS.filter((r) => r.tenant_id === tenantId);
      return MOCK_REPORTS;
    }
  },

  async getBudget(tenantId: string): Promise<BudgetState> {
    try {
      return await apiRequest<BudgetState>(`/v1/tenants/${tenantId}/budget`);
    } catch {
      return { ...MOCK_BUDGET, tenant_id: tenantId };
    }
  },

  async updateBudget(
    tenantId: string,
    update: Partial<BudgetState>
  ): Promise<BudgetState> {
    try {
      return await apiRequest<BudgetState>(`/v1/tenants/${tenantId}/budget`, {
        method: 'PUT',
        body: update
      });
    } catch {
      return { ...MOCK_BUDGET, tenant_id: tenantId, ...update };
    }
  },

  async getFleetKpis(): Promise<Kpis> {
    try {
      return await apiRequest<Kpis>('/v1/kpis/fleet');
    } catch {
      return MOCK_KPIS;
    }
  },

  async getTenantKpis(tenantId: string): Promise<Kpis> {
    try {
      return await apiRequest<Kpis>(`/v1/kpis/tenant/${tenantId}`);
    } catch {
      return MOCK_KPIS;
    }
  }
};

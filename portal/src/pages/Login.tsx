import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Role } from '../types';
import { useSession } from '../hooks/useSession';

const ROLES: { value: Role; label: string }[] = [
  { value: 'demo', label: 'Judge Demo (Read-Only)' },
  { value: 'platform_admin', label: 'Platform Admin (MSP Lead)' },
  { value: 'analyst', label: 'Security Analyst' },
  { value: 'account_manager', label: 'Account Manager' },
  { value: 'client_security', label: 'Client Security' },
  { value: 'client_dev', label: 'Client Developer' },
  { value: 'executive', label: 'Executive' }
];

export function Login() {
  const { session, update } = useSession();
  const [role, setRole] = useState<Role>(session.role);
  const [tenantId, setTenantId] = useState(session.tenant_id ?? 'demo-tenant-shoplite');
  const navigate = useNavigate();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    update({ role, tenant_id: tenantId || undefined });
    navigate('/fleet');
  };

  return (
    <div className="container" style={{ maxWidth: 480, marginTop: 60 }}>
      <div className="card">
        <h1 className="card-title" style={{ fontSize: '1.4rem', justifyContent: 'center' }}>
          🛡️ Rempart Control Plane
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: 20, textAlign: 'center' }}>
          Sign in or switch persona for AWS MSP AI Pentesting review
        </p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="login-role">Persona / Role</label>
            <select
              id="login-role"
              className="form-control"
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
            >
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="login-tenant">Tenant ID (optional)</label>
            <input
              id="login-tenant"
              className="form-control"
              type="text"
              placeholder="e.g. demo-tenant-shoplite"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
            />
          </div>

          <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: 8 }}>
            Enter Rempart Portal
          </button>
        </form>
      </div>
    </div>
  );
}

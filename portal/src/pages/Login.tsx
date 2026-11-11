import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';
import { ROLES } from '../auth/cognito';
import { Role } from '../types';

const ROLE_LABELS: Record<Role, string> = {
  demo: 'Judge Demo (Read-Only)',
  platform_admin: 'Platform Admin (MSP Lead)',
  analyst: 'Security Analyst',
  account_manager: 'Account Manager',
  client_security: 'Client Security',
  client_dev: 'Client Developer',
  executive: 'Executive'
};

function DemoModeBanner() {
  return (
    <div
      role="status"
      data-testid="demo-mode-banner"
      style={{
        background: '#fef3c7',
        border: '1px solid #f59e0b',
        color: '#92400e',
        borderRadius: 6,
        padding: '8px 12px',
        fontSize: '0.82rem',
        marginBottom: 16
      }}
    >
      Demo mode — not authenticated. Set <code>VITE_COGNITO_CLIENT_ID</code> and{' '}
      <code>VITE_COGNITO_DOMAIN</code> to sign in with Amazon Cognito.
    </div>
  );
}

function CognitoSignIn({ onSignIn, pending }: { onSignIn: () => void; pending: boolean }) {
  return (
    <div>
      <DemoModeBanner />
      <button
        type="button"
        className="btn btn-primary"
        style={{ width: '100%' }}
        onClick={onSignIn}
        disabled={pending}
      >
        {pending ? 'Signing in…' : 'Sign in with Amazon Cognito'}
      </button>
    </div>
  );
}

function PersonaPicker({ onEnter }: { onEnter: (role: Role, tenantId: string) => void }) {
  const [role, setRole] = useState<Role>('demo');
  const [tenantId, setTenantId] = useState<string>('demo-tenant-shoplite');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onEnter(role, tenantId);
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-group">
        <label htmlFor="login-role">Persona / Role</label>
        <select
          id="login-role"
          className="form-control"
          value={role}
          onChange={(e) => setRole(e.target.value as Role)}
        >
          {ROLES.map((value) => (
            <option key={value} value={value}>
              {ROLE_LABELS[value]}
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
  );
}

export function Login() {
  const { cognito, pending, signIn, useDemoPersona } = useAuth();
  const navigate = useNavigate();

  const handleDemoEnter = (role: Role, tenantId: string) => {
    useDemoPersona({ role, tenant_id: tenantId || undefined, username: 'judge-demo' });
    navigate('/fleet');
  };

  return (
    <div className="container" style={{ maxWidth: 480, marginTop: 60 }}>
      <div className="card">
        <h1 className="card-title" style={{ fontSize: '1.4rem', justifyContent: 'center' }}>
          🛡️ Rempart Control Plane
        </h1>
        <p
          style={{
            color: 'var(--text-muted)',
            fontSize: '0.9rem',
            marginBottom: 20,
            textAlign: 'center'
          }}
        >
          {cognito
            ? 'Sign in with your Cognito user. Role and tenant come from your token claims.'
            : 'AWS MSP AI Hackathon — Track 2 review build'}
        </p>

        {cognito ? (
          <CognitoSignIn onSignIn={signIn} pending={pending} />
        ) : (
          <>
            <DemoModeBanner />
            <PersonaPicker onEnter={handleDemoEnter} />
          </>
        )}
      </div>
    </div>
  );
}

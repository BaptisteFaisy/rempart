import { Link } from 'react-router-dom';
import { Role, Tenant } from '../types';
import { useSession } from '../hooks/useSession';

const ROLES: Role[] = [
  'platform_admin',
  'analyst',
  'account_manager',
  'client_security',
  'client_dev',
  'executive',
  'demo'
];

interface NavbarProps {
  tenants?: Tenant[];
}

export function Navbar({ tenants = [] }: NavbarProps) {
  const { session, update, logout } = useSession();

  const navLinks = [
    { to: '/fleet', label: 'Fleet' },
    { to: '/triage', label: 'Triage Queue' },
    { to: '/reports', label: 'Reports' },
    { to: '/budget', label: 'Budget' }
  ];

  return (
    <nav className="navbar" data-testid="navbar">
      <Link to="/fleet" className="brand">
        🛡️ Rempart
      </Link>
      <div className="nav-links">
        {navLinks.map((l) => (
          <Link key={l.to} to={l.to}>
            {l.label}
          </Link>
        ))}
      </div>
      <div className="nav-controls">
        <select
          aria-label="Role"
          value={session.role}
          onChange={(e) => update({ ...session, role: e.target.value as Role })}
          className="form-control nav-select"
          data-testid="role-select"
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <select
          aria-label="Tenant"
          value={session.tenant_id ?? ''}
          onChange={(e) => update({ ...session, tenant_id: e.target.value || undefined })}
          className="form-control nav-select"
          data-testid="tenant-select"
        >
          <option value="">All tenants</option>
          {tenants.map((t) => (
            <option key={t.tenant_id} value={t.tenant_id}>
              {t.name}
            </option>
          ))}
        </select>
        <span className="user-indicator" data-testid="user-indicator">
          {session.role}
          {session.tenant_id ? ` · ${session.tenant_id}` : ''}
        </span>
        <button className="btn btn-secondary" onClick={logout}>
          Log out
        </button>
      </div>
    </nav>
  );
}

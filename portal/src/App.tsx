import { useEffect, useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Tenant } from './types';
import { portalApi } from './api/service';
import { useSession } from './hooks/useSession';
import { isCognitoEnabled } from './auth/cognito';
import { Navbar } from './components/Navbar';
import { DemoBanner } from './components/DemoBanner';
import { Login } from './pages/Login';
import { Fleet } from './pages/Fleet';
import { TenantPage } from './pages/Tenant';
import { ApplicationPage } from './pages/Application';
import { RunPage } from './pages/Run';
import { FindingPage } from './pages/Finding';
import { TriageQueue } from './pages/TriageQueue';
import { Reports } from './pages/Reports';
import { Budget } from './pages/Budget';
import { AuditPage } from './pages/Audit';
import { PolicyPage } from './pages/Policy';
import { EvidencePage } from './pages/Evidence';
import { IndustrializationPage } from './pages/Industrialization';

export function App() {
  const { session } = useSession();
  const [tenants, setTenants] = useState<Tenant[]>([]);

  // Cognito activé = API hébergée = jeton OIDC obligatoire. Sans jeton, la
  // session « démo » par défaut n'a AUCUN droit : l'API répond 401 et le
  // navigateur bloque la réponse (preflight refusé) — le portail affichait
  // « API unreachable (Failed to fetch) » au lieu de proposer la connexion.
  const cognitoEnabled = isCognitoEnabled();
  const authenticated = !cognitoEnabled || Boolean(session.token);

  useEffect(() => {
    if (!authenticated) return;
    portalApi.getTenants().then(setTenants).catch(() => {});
  }, [authenticated]);

  if (cognitoEnabled && !authenticated) {
    return <Login />;
  }

  const isDemo = session.role === 'demo' && !cognitoEnabled;

  return (
    <div className="app-layout">
      {isDemo ? <DemoBanner /> : null}
      <Navbar tenants={tenants} />
      <main>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/fleet" element={<Fleet />} />
          <Route path="/tenants/:tenantId" element={<TenantPage />} />
          <Route path="/applications/:appId" element={<ApplicationPage />} />
          <Route path="/runs/:runId" element={<RunPage />} />
          <Route path="/findings/:findingId" element={<FindingPage />} />
          <Route path="/triage" element={<TriageQueue />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/budget" element={<Budget />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/policy" element={<PolicyPage />} />
          <Route path="/evidence" element={<EvidencePage />} />
          <Route path="/industrialization" element={<IndustrializationPage />} />
          <Route path="*" element={<Navigate to="/fleet" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;

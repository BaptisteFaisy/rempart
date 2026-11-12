import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../App';
import { portalApi } from '../api/service';

/**
 * Gate d'authentification du portail.
 *
 * Constat réel du 2026-11-12 sur le portail CloudFront déployé : avec Cognito
 * configuré, `App` rendait quand même le shell applicatif (la session « démo »
 * par défaut n'est jamais vide) et appelait `/v1/tenants` avec des en-têtes
 * « persona ». L'API hébergée, elle, exige un jeton Cognito : la réponse était
 * bloquée par le navigateur et le portail affichait
 * « API unreachable (Failed to fetch). Is scripts/serve_local.py running? »
 * au lieu de proposer la connexion.
 */
describe("App — porte d'authentification", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it('avec Cognito configuré et sans jeton : page de connexion, aucun appel API', async () => {
    vi.stubEnv('VITE_COGNITO_CLIENT_ID', 'client-1');
    vi.stubEnv('VITE_COGNITO_DOMAIN', 'https://pool.auth.eu-north-1.amazoncognito.com');
    const getTenants = vi.spyOn(portalApi, 'getTenants').mockResolvedValue([]);

    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByRole('button', { name: /sign in with amazon cognito/i })).toBeTruthy();
    expect(getTenants).not.toHaveBeenCalled();
  });

  it('avec un jeton en session : le shell s’affiche et l’API est appelée', async () => {
    vi.stubEnv('VITE_COGNITO_CLIENT_ID', 'client-1');
    vi.stubEnv('VITE_COGNITO_DOMAIN', 'https://pool.auth.eu-north-1.amazoncognito.com');
    localStorage.setItem(
      'rempart_session',
      JSON.stringify({
        role: 'analyst',
        tenant_id: 't-a',
        token: 'header.payload.signature'
      })
    );
    const getTenants = vi.spyOn(portalApi, 'getTenants').mockResolvedValue([]);
    // La page Fleet est rendue : ses appels sont mockés pour ne pas tenter
    // de réseau dans jsdom (rejetion non gérée = échec de la suite).
    vi.spyOn(portalApi, 'getFleetKpis').mockResolvedValue(null as never);

    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => expect(getTenants).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /sign in with amazon cognito/i })).toBeNull();
  });

  it('sans Cognito : le mode démo reste possible et l’API est appelée', async () => {
    vi.stubEnv('VITE_COGNITO_CLIENT_ID', '');
    vi.stubEnv('VITE_COGNITO_DOMAIN', '');
    const getTenants = vi.spyOn(portalApi, 'getTenants').mockResolvedValue([]);

    // /login évite que la page Fleet tente un appel réseau inutile en jsdom.
    render(
      <MemoryRouter initialEntries={['/login']}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => expect(getTenants).toHaveBeenCalled());
  });
});

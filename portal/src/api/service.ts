import { liveApi } from './liveApi';
import { offlineApi } from './offlineApi';
import { DEMO_COLLECTIONS, DEMO_ITEM_COUNT } from './mockData';
import { PortalApi } from './contracts';

export type { PortalApi, DecisionAction, FindingQuery, VerificationMethod } from './contracts';

/**
 * Two explicit modes — never a silent fallback.
 *
 * - API mode (default): every call goes to VITE_API_URL. A failure throws
 *   `ApiError` and is surfaced by the banner in `client.ts`; no invented rows.
 * - Offline demo mode (`VITE_USE_MOCKS=1`): calls are answered from the frozen
 *   dataset `demo/seed/demo-dataset.json` — the very same file
 *   `scripts/serve_local.py` loads — and a banner says so.
 */
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === '1';

export const isOfflineDemoMode = (): boolean => USE_MOCKS;

const OFFLINE_BANNER_ID = 'rempart-offline-demo-banner';

/**
 * Tell the judge, loudly, that nothing on screen came from a live backend.
 * Rendered from the API layer because the offline switch lives here; pages keep
 * rendering the same components in both modes.
 */
export function installOfflineDemoBanner(): void {
  if (!USE_MOCKS || typeof document === 'undefined') return;
  if (document.getElementById(OFFLINE_BANNER_ID)) return;
  const banner = document.createElement('div');
  banner.id = OFFLINE_BANNER_ID;
  banner.setAttribute('data-testid', 'offline-demo-banner');
  banner.setAttribute('role', 'status');
  banner.style.cssText =
    'position:fixed;bottom:0;left:0;right:0;z-index:1000;padding:8px 16px;' +
    'background:#78350f;color:#fde68a;font:13px/1.4 system-ui,sans-serif;text-align:center';
  banner.textContent =
    `OFFLINE DEMO MODE (VITE_USE_MOCKS=1) — ${DEMO_ITEM_COUNT} frozen items from ` +
    `demo/seed/demo-dataset.json (${DEMO_COLLECTIONS.join(', ')}). No API call, no AWS.`;
  document.body.appendChild(banner);
}

installOfflineDemoBanner();

/**
 * The portal's single data entry point. Errors in API mode are reported and
 * rethrown (never replaced by placeholder data); offline mode answers from the
 * frozen dataset only.
 */
export const portalApi: PortalApi = USE_MOCKS ? offlineApi : liveApi;

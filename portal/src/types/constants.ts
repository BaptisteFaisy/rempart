import { Priority, Role, Severity } from './index';

/** Priorities of the deterministic matrix (backend `PRIORITIES`). */
export const PRIORITIES: Priority[] = ['P1', 'P2', 'P3', 'P4'];

/** Severities of the deterministic matrix (backend `SEVERITIES`). */
export const SEVERITIES: Severity[] = [
  'Critical',
  'High',
  'Medium',
  'Low',
  'Informational'
];

/**
 * Simultaneous tests per AWS account and region (EF-ORC-05). The platform
 * enforces it; no route exposes the configured value, so the portal only shows
 * it as the documented account limit next to the observed occupancy.
 */
export const AWS_CONCURRENT_TEST_QUOTA = 5;

/** Roles the API accepts for a write (`authorize_write` in the backend). */
export const WRITE_ROLES: Role[] = [
  'platform_admin',
  'analyst',
  'client_security',
  'client_dev'
];

/** The contract policy has a single writer role (`POLICY_WRITER_ROLE`). */
export const POLICY_WRITER_ROLE: Role = 'platform_admin';

export const canWrite = (role?: Role): boolean => role !== undefined && WRITE_ROLES.includes(role);

export const canWritePolicy = (role?: Role): boolean => role === POLICY_WRITER_ROLE;

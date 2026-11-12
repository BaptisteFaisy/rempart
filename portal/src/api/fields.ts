/**
 * Defensive readers for API payloads whose shape is owned by the backend.
 *
 * Several endpoints (industrialization, forecast, evidence) aggregate blocks
 * that may come back flat (`{human_intervention_rate: 0.4}`) or grouped
 * (`{human_intervention: {human_intervention_rate: 0.4}}`). The portal reads
 * both without inventing a number: when nothing matches, the caller gets
 * `null` and renders "not reported by the API".
 */

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** The payload itself, then its first level of object values (one level deep). */
export function searchScopes(source: unknown): UnknownRecord[] {
  if (!isRecord(source)) return [];
  const nested = Object.values(source).filter(isRecord);
  return [source, ...nested];
}

function firstMatch<T>(
  source: unknown,
  names: string[],
  isValid: (value: unknown) => boolean
): T | null {
  for (const scope of searchScopes(source)) {
    for (const name of names) {
      const value = scope[name];
      if (value !== undefined && isValid(value)) return value as T;
    }
  }
  return null;
}

export function readNumber(source: unknown, names: string[]): number | null {
  return firstMatch<number>(source, names, (v) => typeof v === 'number');
}

export function readString(source: unknown, names: string[]): string | null {
  return firstMatch<string>(source, names, (v) => typeof v === 'string');
}

export function readBoolean(source: unknown, names: string[]): boolean | null {
  return firstMatch<boolean>(source, names, (v) => typeof v === 'boolean');
}

export function readRecord(source: unknown, names: string[]): UnknownRecord | null {
  return firstMatch<UnknownRecord>(source, names, isRecord);
}

export function readArray<T>(source: unknown, names: string[]): T[] | null {
  return firstMatch<T[]>(source, names, Array.isArray);
}

/** Unwrap a payload nested under one of `names` (e.g. `{evidence: {...}}`). */
export function unwrapPayload<T>(payload: unknown, names: string[]): T {
  if (isRecord(payload)) {
    for (const name of names) {
      if (isRecord(payload[name])) return payload[name] as T;
    }
  }
  return payload as T;
}

/** `0.42` -> `42%`, `null` -> a visible "not reported". */
export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return NOT_REPORTED;
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatNumber(
  value: number | null | undefined,
  suffix = '',
  digits = 1
): string {
  if (value === null || value === undefined) return NOT_REPORTED;
  return `${value.toFixed(digits)}${suffix}`;
}

export function formatText(value: string | null | undefined, fallback = '—'): string {
  return value === null || value === undefined || value === '' ? fallback : value;
}

export const NOT_REPORTED = 'not reported by the API';

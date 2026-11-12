import { useCallback, useState } from 'react';

export interface ApiActionState {
  busy: boolean;
  message: string | null;
  error: string | null;
  run: <T>(action: () => Promise<T>, successMessage: string) => Promise<T | null>;
  clear: () => void;
}

/**
 * One place for "call the API from a button": busy flag, success message and
 * error message. Failures are also shown by the banner in `client.ts`; the
 * local message keeps the reason next to the button that caused it.
 */
export function useApiAction(): ApiActionState {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async <T,>(action: () => Promise<T>, successMessage: string): Promise<T | null> => {
      setBusy(true);
      setMessage(null);
      setError(null);
      try {
        const result = await action();
        setMessage(successMessage);
        return result;
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause));
        return null;
      } finally {
        setBusy(false);
      }
    },
    []
  );

  const clear = useCallback(() => {
    setMessage(null);
    setError(null);
  }, []);

  return { busy, message, error, run, clear };
}

interface ActionNoticeProps {
  message: string | null;
  error: string | null;
}

/** Result of a write action, shown next to the button that triggered it. */
export function ActionNotice({ message, error }: ActionNoticeProps) {
  if (!message && !error) return null;
  return (
    <div
      className="card"
      role="status"
      data-testid="action-notice"
      style={{
        marginTop: 12,
        background: 'var(--bg-secondary)',
        borderColor: error ? 'var(--danger)' : 'var(--accent)',
        fontSize: '0.9rem'
      }}
    >
      {error ?? message}
    </div>
  );
}

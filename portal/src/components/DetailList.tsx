import { CSSProperties, ReactNode } from 'react';

export interface DetailItem {
  label: string;
  value?: ReactNode;
}

const ROW: CSSProperties = { display: 'flex', gap: 12, padding: '3px 0' };
const LABEL: CSSProperties = { minWidth: 210, color: 'var(--text-muted)' };

/** Label/value list — the read-only detail block used by every detail page. */
export function DetailList({ items }: { items: DetailItem[] }) {
  return (
    <dl style={{ margin: 0 }} data-testid="detail-list">
      {items.map((item) => (
        <div key={item.label} style={ROW}>
          <dt style={LABEL}>{item.label}</dt>
          <dd style={{ margin: 0, wordBreak: 'break-word' }}>
            {item.value === undefined || item.value === null || item.value === '' ? '—' : item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

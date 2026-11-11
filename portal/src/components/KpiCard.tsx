interface KpiCardProps {
  label: string;
  value: string | number;
  sub?: string;
  tone?: 'default' | 'good' | 'warn' | 'bad';
}

export function KpiCard({ label, value, sub, tone = 'default' }: KpiCardProps) {
  return (
    <div className={`card kpi-card kpi-${tone}`} data-testid="kpi-card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub ? <div className="kpi-sub">{sub}</div> : null}
    </div>
  );
}

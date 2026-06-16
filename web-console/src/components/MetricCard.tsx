interface MetricCardProps {
  label: string;
  value: string | number;
  hint: string;
}

export function MetricCard({ label, value, hint }: MetricCardProps) {
  return (
    <section className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{hint}</small>
    </section>
  );
}

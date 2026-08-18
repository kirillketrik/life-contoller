/**
 * Plain div/Tailwind bars, not a Lightweight Charts series: category
 * breakdowns (label -> count) have no time axis, and Lightweight Charts is a
 * time-scale library — a poor fit here. See CLAUDE.md's "chart library
 * split" note. Reserve Lightweight Charts for genuinely time-series data
 * (see `MonthlyTrendChart`).
 */
export function HorizontalBarList({
  items,
  emptyLabel,
}: {
  items: { label: string; value: number }[];
  emptyLabel: string;
}) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">{emptyLabel}</p>;
  }

  const max = Math.max(...items.map((item) => item.value));

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-3">
          <span className="w-28 shrink-0 truncate text-sm text-muted-foreground" title={item.label}>
            {item.label}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${max > 0 ? (item.value / max) * 100 : 0}%` }}
            />
          </div>
          <span className="w-8 shrink-0 text-right text-sm tabular-nums">{item.value}</span>
        </div>
      ))}
    </div>
  );
}

/** One min/max/avg/current stat tile — shared by the metric detail page's
 * dashboard card and each dashboard element block, so both render the same
 * "—" for null / value+unit shape. */
export function SummaryStat({
  label,
  value,
  unit,
}: {
  label: string;
  value: number | null;
  unit: string;
}) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold tabular-nums">
        {value === null ? (
          "—"
        ) : (
          <>
            {value.toFixed(1)}
            {unit && <span className="ml-1 text-sm font-normal text-muted-foreground">{unit}</span>}
          </>
        )}
      </p>
    </div>
  );
}

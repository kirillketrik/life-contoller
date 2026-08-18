"use client";

import { AreaSeries, ColorType, type IChartApi, createChart, type UTCTimestamp } from "lightweight-charts";
import { useTheme } from "next-themes";
import { useEffect, useRef } from "react";

const CHART_COLORS = {
  light: { background: "#ffffff", text: "#0f172a", grid: "#e2e8f0", border: "#cbd5e1", line: "#2563eb" },
  dark: { background: "#0a0a0a", text: "#e4e4e7", grid: "#27272a", border: "#3f3f46", line: "#60a5fa" },
};

function toUnixSeconds(month: string): UTCTimestamp {
  return Math.floor(new Date(`${month}-01T00:00:00Z`).getTime() / 1000) as UTCTimestamp;
}

export function MonthlyTrendChart({
  data,
  emptyLabel,
}: {
  data: { month: string; count: number }[];
  emptyLabel: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    const container = containerRef.current;
    if (!container || data.length === 0) return;

    const colors = resolvedTheme === "dark" ? CHART_COLORS.dark : CHART_COLORS.light;
    const chart: IChartApi = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: colors.background },
        textColor: colors.text,
      },
      grid: {
        vertLines: { color: colors.grid },
        horzLines: { color: colors.grid },
      },
      rightPriceScale: { borderColor: colors.border },
      timeScale: { borderColor: colors.border },
      autoSize: true,
    });

    const series = chart.addSeries(AreaSeries, {
      lineColor: colors.line,
      topColor: `${colors.line}33`,
      bottomColor: `${colors.line}00`,
      lineWidth: 2,
    });
    series.setData(
      [...data]
        .sort((a, b) => a.month.localeCompare(b.month))
        .map((point) => ({ time: toUnixSeconds(point.month), value: point.count })),
    );
    chart.timeScale().fitContent();

    return () => chart.remove();
  }, [data, resolvedTheme]);

  if (data.length === 0) {
    return (
      <div className="flex h-64 w-full items-center justify-center text-sm text-muted-foreground">
        {emptyLabel}
      </div>
    );
  }

  return <div ref={containerRef} className="h-64 w-full" />;
}

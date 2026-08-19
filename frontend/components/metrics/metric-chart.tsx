"use client";

import {
  ColorType,
  type IChartApi,
  LineSeries,
  LineStyle,
  createChart,
  type UTCTimestamp,
} from "lightweight-charts";
import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import { useEffect, useRef } from "react";

import type { MetricDataPoint, ThresholdBounds, TimeframeUnit } from "@/lib/types";

const CHART_COLORS = {
  light: {
    background: "#ffffff",
    text: "#0f172a",
    grid: "#e2e8f0",
    border: "#cbd5e1",
    line: "#2563eb",
    threshold: "#dc2626",
  },
  dark: {
    background: "#0a0a0a",
    text: "#e4e4e7",
    grid: "#27272a",
    border: "#3f3f46",
    line: "#60a5fa",
    threshold: "#f87171",
  },
};

function toUnixSeconds(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

export function MetricChart({
  points,
  timeframeUnit,
  threshold,
}: {
  points: MetricDataPoint[];
  timeframeUnit: TimeframeUnit;
  threshold?: ThresholdBounds | null;
}) {
  const t = useTranslations("metricChart");
  const tThreshold = useTranslations("threshold");
  const containerRef = useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

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
      timeScale: {
        borderColor: colors.border,
        timeVisible: timeframeUnit === "minute" || timeframeUnit === "hour",
      },
      autoSize: true,
    });

    const sortedPoints = [...points].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    // lightweight-charts requires strictly increasing, unique per-second
    // timestamps — two entries logged within the same second collapse to
    // one, keeping the later value (same "last write wins" rule as an OHLC
    // bucket's `close`).
    const byTime = new Map<number, number>();
    for (const point of sortedPoints) {
      byTime.set(toUnixSeconds(point.timestamp), point.value);
    }

    const series = chart.addSeries(LineSeries, { color: colors.line, lineWidth: 2 });
    series.setData(
      [...byTime.entries()].map(([time, value]) => ({ time: time as UTCTimestamp, value })),
    );

    // The threshold's configured range, drawn as red bound lines on top of
    // the series — not part of the data, so a plain price line rather than
    // a second series.
    if (threshold?.lower_bound != null) {
      series.createPriceLine({
        price: threshold.lower_bound,
        color: colors.threshold,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: tThreshold("lowerBound"),
      });
    }
    if (threshold?.upper_bound != null) {
      series.createPriceLine({
        price: threshold.upper_bound,
        color: colors.threshold,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: tThreshold("upperBound"),
      });
    }

    chart.timeScale().fitContent();

    return () => chart.remove();
  }, [points, timeframeUnit, resolvedTheme, threshold, tThreshold]);

  if (points.length === 0) {
    return (
      <div className="flex h-80 w-full items-center justify-center text-sm text-muted-foreground">
        {t("noData")}
      </div>
    );
  }

  return <div ref={containerRef} className="h-80 w-full" />;
}

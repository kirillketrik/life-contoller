"use client";

import {
  CandlestickSeries,
  ColorType,
  type IChartApi,
  LineSeries,
  createChart,
  type UTCTimestamp,
} from "lightweight-charts";
import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import { useEffect, useRef } from "react";

import type { OHLCBucket, TimeframeUnit } from "@/lib/types";

const CHART_COLORS = {
  light: {
    background: "#ffffff",
    text: "#0f172a",
    grid: "#e2e8f0",
    border: "#cbd5e1",
    up: "#16a34a",
    down: "#dc2626",
    line: "#2563eb",
  },
  dark: {
    background: "#0a0a0a",
    text: "#e4e4e7",
    grid: "#27272a",
    border: "#3f3f46",
    up: "#22c55e",
    down: "#ef4444",
    line: "#60a5fa",
  },
};

function toUnixSeconds(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

/** Candlestick if a meaningful share of buckets actually have spread
 * (high !== low, i.e. more than one distinct reading in the bucket);
 * otherwise the data is sparse (roughly one point per bucket, e.g. a daily
 * weight log) and a line reads far more cleanly than flat-bodied candles. */
function shouldRenderCandlesticks(buckets: OHLCBucket[]): boolean {
  if (buckets.length === 0) return false;
  const bucketsWithSpread = buckets.filter((bucket) => bucket.high !== bucket.low).length;
  return bucketsWithSpread / buckets.length > 0.2;
}

export function MetricChart({ buckets, timeframeUnit }: { buckets: OHLCBucket[]; timeframeUnit: TimeframeUnit }) {
  const t = useTranslations("metricChart");
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

    const sortedBuckets = [...buckets].sort((a, b) => a.bucket_start.localeCompare(b.bucket_start));

    if (shouldRenderCandlesticks(sortedBuckets)) {
      const series = chart.addSeries(CandlestickSeries, {
        upColor: colors.up,
        downColor: colors.down,
        borderVisible: false,
        wickUpColor: colors.up,
        wickDownColor: colors.down,
      });
      series.setData(
        sortedBuckets.map((bucket) => ({
          time: toUnixSeconds(bucket.bucket_start),
          open: bucket.open,
          high: bucket.high,
          low: bucket.low,
          close: bucket.close,
        })),
      );
    } else {
      const series = chart.addSeries(LineSeries, { color: colors.line, lineWidth: 2 });
      series.setData(
        sortedBuckets.map((bucket) => ({
          time: toUnixSeconds(bucket.bucket_start),
          value: bucket.close,
        })),
      );
    }

    chart.timeScale().fitContent();

    return () => chart.remove();
  }, [buckets, timeframeUnit, resolvedTheme]);

  if (buckets.length === 0) {
    return (
      <div className="flex h-80 w-full items-center justify-center text-sm text-muted-foreground">
        {t("noData")}
      </div>
    );
  }

  return <div ref={containerRef} className="h-80 w-full" />;
}

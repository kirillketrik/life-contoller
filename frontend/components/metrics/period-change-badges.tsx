"use client";

import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";
import type { PeriodChanges } from "@/lib/types";

const PERIOD_ORDER: (keyof PeriodChanges)[] = ["24h", "7d", "30d", "3m", "1y"];

/** The 24h/7d/30d/3m/1y % change badges shown next to a metric's name —
 * green/red per sign, "—" when there's no data far enough back to compare
 * against. Shared by the favorite chart card and the metric detail page. */
export function PeriodChangeBadges({
  changes,
  className,
}: {
  changes: PeriodChanges;
  className?: string;
}) {
  const t = useTranslations("periodChange");
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs tabular-nums text-muted-foreground",
        className,
      )}
    >
      {PERIOD_ORDER.map((label) => {
        const value = changes[label];
        return (
          <span key={label}>
            {t(label)}:{" "}
            {value === null ? (
              <span className="text-foreground">—</span>
            ) : (
              <span className={value >= 0 ? "text-success" : "text-destructive"}>
                {value >= 0 ? "+" : ""}
                {value.toFixed(1)}%
              </span>
            )}
          </span>
        );
      })}
    </div>
  );
}

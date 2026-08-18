"use client";

import { useDraggable } from "@dnd-kit/core";
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { metricTypes } from "@/lib/api";
import { METRIC_TYPES_QUERY_KEY } from "@/lib/query-keys";
import type { MetricType } from "@/lib/types";

interface MetricsPaletteProps {
  excludeMetricTypeId?: number;
  disabled: boolean;
}

export function MetricsPalette({ excludeMetricTypeId, disabled }: MetricsPaletteProps) {
  const t = useTranslations("formulaBuilder");
  const [search, setSearch] = useState("");

  const query = useQuery({ queryKey: METRIC_TYPES_QUERY_KEY, queryFn: () => metricTypes.list() });
  const allTypes = query.data?.results ?? [];
  const visible = allTypes.filter(
    (type) =>
      type.id !== excludeMetricTypeId &&
      type.name.toLowerCase().includes(search.trim().toLowerCase()),
  );

  return (
    <div className="space-y-2">
      <Input
        placeholder={t("searchMetrics")}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto">
        {visible.length === 0 && <p className="text-xs text-muted-foreground">{t("noMetrics")}</p>}
        {visible.map((type) => (
          <MetricChip key={type.id} metricType={type} disabled={disabled} />
        ))}
      </div>
    </div>
  );
}

function MetricChip({ metricType, disabled }: { metricType: MetricType; disabled: boolean }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `metric-${metricType.id}`,
    data: { kind: "metric", metricTypeId: metricType.id },
    disabled,
  });

  return (
    <Badge
      ref={setNodeRef}
      variant="secondary"
      className={disabled ? "opacity-40" : `cursor-grab ${isDragging ? "opacity-50" : ""}`}
      {...listeners}
      {...attributes}
    >
      {metricType.name}
    </Badge>
  );
}

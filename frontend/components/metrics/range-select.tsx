"use client";

import { useTranslations } from "next-intl";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RANGE_PRESETS } from "@/lib/metric-range-presets";

export function RangeSelect({
  value,
  onChange,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  const t = useTranslations("metricDashboard");
  return (
    <Select
      items={Object.fromEntries(RANGE_PRESETS.map((option) => [option.key, t(option.labelKey)]))}
      value={value}
      onValueChange={(v) => onChange(v ?? "30d")}
    >
      <SelectTrigger className={className ?? "w-36"}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {RANGE_PRESETS.map((option) => (
          <SelectItem key={option.key} value={option.key}>
            {t(option.labelKey)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

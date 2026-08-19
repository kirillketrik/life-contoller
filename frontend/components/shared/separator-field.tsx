"use client";

import { useTranslations } from "next-intl";

import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export interface SeparatorPreset {
  value: string;
  label: string;
  separator: string;
}

function useDefaultSeparatorPresets(): SeparatorPreset[] {
  const t = useTranslations("separatorField");
  return [
    { value: "space", label: t("space"), separator: " " },
    { value: "tab", label: t("tab"), separator: "\t" },
    { value: "comma", label: t("comma"), separator: "," },
    { value: "semicolon", label: t("semicolon"), separator: ";" },
    { value: "newline", label: t("newline"), separator: "\n" },
    { value: "custom", label: t("custom"), separator: "" },
  ];
}

function presetForSeparator(separator: string, presets: SeparatorPreset[]): string {
  const preset = presets.find((p) => p.value !== "custom" && p.separator === separator);
  return preset?.value ?? "custom";
}

/** Separator picker with presets (space/tab/comma/semicolon/newline) plus a
 * custom-character input — the separator half of the bulk-import template
 * builder. Domain-agnostic: pass `presets` to override the defaults. */
export function SeparatorField({
  value,
  onChange,
  presets,
}: {
  value: string;
  onChange: (separator: string) => void;
  presets?: SeparatorPreset[];
}) {
  const t = useTranslations("separatorField");
  const defaultPresets = useDefaultSeparatorPresets();
  const activePresets = presets ?? defaultPresets;
  const activePreset = presetForSeparator(value, activePresets);

  return (
    <div className="flex items-center gap-2">
      <Select
        items={Object.fromEntries(activePresets.map((p) => [p.value, p.label]))}
        value={activePreset}
        onValueChange={(preset) => {
          if (!preset) return;
          if (preset === "custom") {
            onChange("");
            return;
          }
          const found = activePresets.find((p) => p.value === preset);
          onChange(found?.separator ?? "");
        }}
      >
        <SelectTrigger className="w-48">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {activePresets.map((p) => (
            <SelectItem key={p.value} value={p.value}>
              {p.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {activePreset === "custom" && (
        <Input
          className="w-24"
          placeholder={t("customPlaceholder")}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  );
}

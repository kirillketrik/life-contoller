"use client";

import { ArrowLeftRight } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

import { type SeparatorPreset, SeparatorField } from "./separator-field";

function buildTemplate<TField extends string>(fields: TField[], separator: string): string {
  return fields.map((field) => `{${field}}`).join(separator);
}

interface TemplateBuilderProps<TField extends string> {
  template: string;
  onTemplateChange: (template: string) => void;
  separator: string;
  onSeparatorChange: (separator: string) => void;
  validFields: TField[];
  fieldLabels: Record<TField, string>;
  extractFields: (template: string) => TField[];
  separatorPresets?: SeparatorPreset[];
}

/** A row of toggle buttons — one per available field — that builds an
 * ordered `{field1}{separator}{field2}` template string; each selected field
 * shows its position number and a "swap with next" button for reordering.
 * Domain-agnostic (generic over the field union) so the same component
 * serves any positional-template use case, not just one resource. */
export function TemplateBuilder<TField extends string>({
  template,
  onTemplateChange,
  separator,
  onSeparatorChange,
  validFields,
  fieldLabels,
  extractFields,
  separatorPresets,
}: TemplateBuilderProps<TField>) {
  const t = useTranslations("templateBuilder");
  const fields = extractFields(template);
  const unselectedFields = validFields.filter((field) => !fields.includes(field));
  const orderedFields = [...fields, ...unselectedFields];

  function toggle(field: TField) {
    const next = fields.includes(field) ? fields.filter((f) => f !== field) : [...fields, field];
    onTemplateChange(buildTemplate(next, separator));
  }

  function swapWithNext(position: number) {
    if (position < 0 || position >= fields.length - 1) return;
    const next = [...fields];
    const temp = next[position]!;
    next[position] = next[position + 1]!;
    next[position + 1] = temp;
    onTemplateChange(buildTemplate(next, separator));
  }

  function handleSeparatorChange(nextSeparator: string) {
    onSeparatorChange(nextSeparator);
    onTemplateChange(buildTemplate(fields, nextSeparator));
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {orderedFields.map((field) => {
          const position = fields.indexOf(field);
          const selected = position !== -1;
          return (
            <div key={field} className="flex items-center gap-0.5">
              <Button
                type="button"
                variant={selected ? "default" : "outline"}
                size="sm"
                onClick={() => toggle(field)}
              >
                {selected && `${position + 1}. `}
                {fieldLabels[field]}
              </Button>
              {selected && position < fields.length - 1 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  onClick={() => swapWithNext(position)}
                  aria-label={t("swapWithNext")}
                >
                  <ArrowLeftRight />
                </Button>
              )}
            </div>
          );
        })}
      </div>
      <div>
        <Label>{t("separator")}</Label>
        <div className="mt-1.5">
          <SeparatorField value={separator} onChange={handleSeparatorChange} presets={separatorPresets} />
        </div>
      </div>
      <p className="text-sm text-muted-foreground">
        {t("template")}: <span className="font-mono">{template || "—"}</span>
      </p>
    </div>
  );
}

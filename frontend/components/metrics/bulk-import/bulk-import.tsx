"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { TemplateBuilder } from "@/components/shared/template-builder";
import { ApiError, metricBulkImport, metricImportSettings, metricTypes } from "@/lib/api";
import { extractBulkImportTemplateFields, parseImportTemplate, toBulkImportItems } from "@/lib/metric-bulk-parse";
import { METRIC_TYPES_QUERY_KEY } from "@/lib/query-keys";
import type { BulkImportDuplicatePolicy, BulkImportRequest } from "@/lib/types";

import { BulkImportPreviewTable } from "./preview-table";
import { useBulkImport } from "./use-bulk-import";

const TEMPLATE_ERROR_KEY: Record<string, string> = {
  separatorRequired: "templateErrorSeparatorRequired",
  atLeastOneField: "templateErrorAtLeastOneField",
  unknownFields: "templateErrorUnknownFields",
  duplicateFields: "templateErrorDuplicateFields",
  valueFieldRequired: "templateErrorValueFieldRequired",
};

export function BulkImport() {
  const t = useTranslations("bulkImport");
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [activeTab, setActiveTab] = useState("input");

  const metricTypesQuery = useQuery({
    queryKey: METRIC_TYPES_QUERY_KEY,
    queryFn: () => metricTypes.list(),
  });
  const importableTypes = (metricTypesQuery.data?.results ?? []).filter(
    (type) => !type.is_computed && !type.is_singleton,
  );

  const bulk = useBulkImport(importableTypes);
  const templateResult = parseImportTemplate(bulk.form.template, bulk.form.separator);
  const items = toBulkImportItems(bulk.parsedRows);

  const request: BulkImportRequest | null =
    bulk.metricTypeId !== null && templateResult.fields.length > 0 && items.length > 0
      ? {
          items,
          date_format: bulk.form.dateFormat,
          decimal_separator: bulk.form.decimalSeparator,
          duplicate_policy: bulk.form.duplicatePolicy,
        }
      : null;

  const previewQuery = useQuery({
    queryKey: ["metric-bulk-import-preview", bulk.metricTypeId, request],
    queryFn: () => metricBulkImport.preview(bulk.metricTypeId as number, request as BulkImportRequest),
    enabled: activeTab === "preview" && bulk.metricTypeId !== null && request !== null,
  });

  const setDefaultMutation = useMutation({
    mutationFn: () =>
      metricImportSettings.set(bulk.metricTypeId as number, {
        template: bulk.form.template,
        separator: bulk.form.separator,
        date_format: bulk.form.dateFormat,
        decimal_separator: bulk.form.decimalSeparator,
      }),
    onSuccess: () => {
      bulk.invalidateSettings();
      toast.success(t("defaultSaved"));
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : t("defaultSaveFailed"));
    },
  });

  const importMutation = useMutation({
    mutationFn: () => metricBulkImport.run(bulk.metricTypeId as number, request as BulkImportRequest),
    onSuccess: (result) => {
      bulk.invalidateAfterImport();
      queryClient.invalidateQueries({ queryKey: ["metric-bulk-import-preview"] });
      toast.success(
        t("importSucceeded", {
          created: result.created_count,
          updated: result.updated_count,
          skipped: result.skipped_count,
          invalid: result.invalid_count,
        }),
      );
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : t("importFailed"));
    },
  });

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      bulk.setRawText(String(reader.result ?? ""));
    };
    reader.readAsText(file);
  }

  const summary = previewQuery.data?.items.reduce(
    (acc, item) => {
      acc[item.status] += 1;
      return acc;
    },
    { new: 0, duplicate_skip: 0, duplicate_overwrite: 0, invalid: 0 } as Record<string, number>,
  );

  return (
    <div className="space-y-6">
      <div className="max-w-sm space-y-2">
        <Label>{t("metricLabel")}</Label>
        {metricTypesQuery.isLoading ? (
          <Skeleton className="h-8" />
        ) : (
          <Select
            items={Object.fromEntries(importableTypes.map((type) => [String(type.id), type.name]))}
            value={bulk.metricTypeId !== null ? String(bulk.metricTypeId) : ""}
            onValueChange={(v) => bulk.selectMetricType(v ? Number(v) : null)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t("metricPlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              {importableTypes.map((type) => (
                <SelectItem key={type.id} value={String(type.id)}>
                  {type.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {!metricTypesQuery.isLoading && importableTypes.length === 0 && (
          <p className="text-xs text-muted-foreground">{t("noImportableMetrics")}</p>
        )}
      </div>

      {bulk.metricType && (
        <>
          <div className="space-y-4 rounded-md border p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium">{t("templateSectionTitle")}</h2>
              <div className="flex items-center gap-2">
                <Label htmlFor="advanced-mode" className="text-sm font-normal text-muted-foreground">
                  {t("advancedMode")}
                </Label>
                <Switch id="advanced-mode" checked={bulk.advancedMode} onCheckedChange={bulk.setAdvancedMode} />
              </div>
            </div>

            {bulk.advancedMode ? (
              <div className="space-y-2">
                <Label htmlFor="raw-template">{t("advancedTemplateLabel")}</Label>
                <Input
                  id="raw-template"
                  className="font-mono"
                  placeholder={t("advancedTemplatePlaceholder")}
                  value={bulk.form.template}
                  onChange={(e) => bulk.setForm((f) => ({ ...f, template: e.target.value }))}
                />
              </div>
            ) : (
              <TemplateBuilder
                template={bulk.form.template}
                onTemplateChange={(template) => bulk.setForm((f) => ({ ...f, template }))}
                separator={bulk.form.separator}
                onSeparatorChange={(separator) => bulk.setForm((f) => ({ ...f, separator }))}
                validFields={["value", "date"]}
                fieldLabels={{ value: t("fieldValue"), date: t("fieldDate") }}
                extractFields={extractBulkImportTemplateFields}
              />
            )}
            {templateResult.error && (
              <p className="text-sm text-destructive">
                {t(TEMPLATE_ERROR_KEY[templateResult.error] ?? "templateInvalid")}
              </p>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="date-format">{t("dateFormatLabel")}</Label>
                <Input
                  id="date-format"
                  className="font-mono"
                  placeholder={t("dateFormatPlaceholder")}
                  value={bulk.form.dateFormat}
                  onChange={(e) => bulk.setForm((f) => ({ ...f, dateFormat: e.target.value }))}
                />
                <p className="text-xs text-muted-foreground">{t("dateFormatHint")}</p>
              </div>

              <div className="space-y-2">
                <Label>{t("decimalSeparatorLabel")}</Label>
                <RadioGroup
                  value={bulk.form.decimalSeparator}
                  onValueChange={(v) => bulk.setForm((f) => ({ ...f, decimalSeparator: v as "." | "," }))}
                >
                  <label className="flex items-center gap-2 text-sm">
                    <RadioGroupItem value="." />
                    {t("decimalSeparatorDot")}
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <RadioGroupItem value="," />
                    {t("decimalSeparatorComma")}
                  </label>
                </RadioGroup>
              </div>
            </div>

            <div className="space-y-2">
              <Label>{t("duplicatePolicyLabel")}</Label>
              <RadioGroup
                value={bulk.form.duplicatePolicy}
                onValueChange={(v) =>
                  bulk.setForm((f) => ({ ...f, duplicatePolicy: v as BulkImportDuplicatePolicy }))
                }
              >
                <label className="flex items-center gap-2 text-sm">
                  <RadioGroupItem value="skip" />
                  {t("duplicatePolicySkip")}
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <RadioGroupItem value="overwrite" />
                  {t("duplicatePolicyOverwrite")}
                </label>
              </RadioGroup>
            </div>

            <div className="flex justify-end">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={setDefaultMutation.isPending || !templateResult.fields.length}
                onClick={() => setDefaultMutation.mutate()}
              >
                {setDefaultMutation.isPending ? t("settingDefault") : t("setDefault")}
              </Button>
            </div>
          </div>

          <Tabs value={activeTab} onValueChange={(v) => v && setActiveTab(v)}>
            <TabsList>
              <TabsTrigger value="input">{t("inputTab")}</TabsTrigger>
              <TabsTrigger value="preview">{t("previewTab")}</TabsTrigger>
            </TabsList>

            <TabsContent value="input" className="space-y-3 pt-3">
              <div className="flex items-center justify-between">
                <Label htmlFor="bulk-import-text">{t("textareaLabel")}</Label>
                <div className="flex items-center gap-2">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,.txt,text/csv,text/plain"
                    className="hidden"
                    onChange={handleFileChange}
                  />
                  <Button type="button" variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
                    {t("uploadFile")}
                  </Button>
                </div>
              </div>
              <Textarea
                id="bulk-import-text"
                rows={10}
                className="font-mono"
                placeholder={t("textareaPlaceholder")}
                value={bulk.rawText}
                onChange={(e) => bulk.setRawText(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">{t("rowsCount", { count: bulk.parsedRows.length })}</p>
            </TabsContent>

            <TabsContent value="preview" className="space-y-3 pt-3">
              {bulk.parsedRows.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("previewEmpty")}</p>
              ) : previewQuery.isFetching ? (
                <Skeleton className="h-40" />
              ) : previewQuery.data ? (
                <div className="space-y-3">
                  {summary && (
                    <div className="flex flex-wrap gap-3 text-sm text-muted-foreground">
                      <span>{t("summaryNew", { count: summary.new })}</span>
                      <span>{t("summaryDuplicateSkip", { count: summary.duplicate_skip })}</span>
                      <span>{t("summaryDuplicateOverwrite", { count: summary.duplicate_overwrite })}</span>
                      <span>{t("summaryInvalid", { count: summary.invalid })}</span>
                    </div>
                  )}
                  <BulkImportPreviewTable items={previewQuery.data.items} />
                </div>
              ) : null}
            </TabsContent>
          </Tabs>

          <div className="flex justify-end">
            <Button
              disabled={importMutation.isPending || request === null}
              onClick={() => importMutation.mutate()}
            >
              {importMutation.isPending ? t("importing") : t("importButton")}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

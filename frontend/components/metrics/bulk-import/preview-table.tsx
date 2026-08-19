"use client";

import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { BulkImportItemResult, BulkImportItemStatus } from "@/lib/types";

const STATUS_BADGE_VARIANT: Record<BulkImportItemStatus, "default" | "secondary" | "destructive" | "outline"> = {
  new: "default",
  duplicate_skip: "outline",
  duplicate_overwrite: "secondary",
  invalid: "destructive",
};

const STATUS_LABEL_KEY: Record<BulkImportItemStatus, string> = {
  new: "statusNew",
  duplicate_skip: "statusDuplicateSkip",
  duplicate_overwrite: "statusDuplicateOverwrite",
  invalid: "statusInvalid",
};

const ERROR_MESSAGE_KEY: Record<string, string> = {
  missing_value: "errorMissingValue",
  invalid_number: "errorInvalidNumber",
  unknown_choice: "errorUnknownChoice",
  invalid_boolean: "errorInvalidBoolean",
  invalid_date: "errorInvalidDate",
};

export function BulkImportPreviewTable({ items }: { items: BulkImportItemResult[] }) {
  const t = useTranslations("bulkImport");

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("colLine")}</TableHead>
          <TableHead>{t("colRawValue")}</TableHead>
          <TableHead>{t("colRawDate")}</TableHead>
          <TableHead>{t("colParsedValue")}</TableHead>
          <TableHead>{t("colRecordedAt")}</TableHead>
          <TableHead>{t("colStatus")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow key={item.line_number}>
            <TableCell className="text-muted-foreground">{item.line_number}</TableCell>
            <TableCell>{item.raw_value ?? "—"}</TableCell>
            <TableCell>{item.raw_date ?? "—"}</TableCell>
            <TableCell>{item.value !== null ? String(item.value) : "—"}</TableCell>
            <TableCell>
              {item.recorded_at ? new Date(item.recorded_at).toLocaleString("ru-RU") : "—"}
            </TableCell>
            <TableCell>
              <Badge variant={STATUS_BADGE_VARIANT[item.status]}>{t(STATUS_LABEL_KEY[item.status])}</Badge>
              {item.status === "invalid" && item.error_code && (
                <p className="mt-1 text-xs text-muted-foreground">
                  {t(ERROR_MESSAGE_KEY[item.error_code] ?? "errorUnknown")}
                </p>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

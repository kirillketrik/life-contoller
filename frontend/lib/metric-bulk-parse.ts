/** Client-side parsing for the bulk metric-entry import page — positionally
 * splits pasted/uploaded text into `{value, date}` tokens per line, using the
 * same template-builder pattern as a prior project's bulk-asset-create page
 * (see CLAUDE.md's bulk-import notes), adapted to the metric-entry model's
 * two importable fields. The actual value/date *parsing* (numeric, choice
 * code/label matching, date-format parsing) happens server-side, shared
 * between the preview and create endpoints — this module only produces the
 * raw string tokens sent to those endpoints.
 */

export type BulkImportField = "value" | "date";

export const BULK_IMPORT_VALID_FIELDS: BulkImportField[] = ["value", "date"];

const TEMPLATE_TOKEN_RE = /\{([a-zA-Z0-9_]+)\}/g;

/** Best-effort ordered list of known fields present in a template — used to
 * initialize/derive the template builder UI. Unlike `parseImportTemplate`,
 * this never errors: unknown placeholders and repeats are silently dropped. */
export function extractBulkImportTemplateFields(template: string): BulkImportField[] {
  const tokens = [...template.matchAll(TEMPLATE_TOKEN_RE)].map((m) => m[1]);
  const fields: BulkImportField[] = [];
  for (const t of tokens) {
    if (BULK_IMPORT_VALID_FIELDS.includes(t as BulkImportField) && !fields.includes(t as BulkImportField)) {
      fields.push(t as BulkImportField);
    }
  }
  return fields;
}

export interface ParsedImportTemplate {
  fields: BulkImportField[];
  error?: string;
}

/** Splits a template like "{date} {value}" into an ordered list of field
 * tokens using the given separator. Every token must be one of the known
 * field names (no literal text mixed in), and `{value}` must always be
 * present — every metric entry needs a value. */
export function parseImportTemplate(template: string, separator: string): ParsedImportTemplate {
  if (!separator) return { fields: [], error: "separatorRequired" };

  const tokens = template
    .split(separator)
    .map((t) => t.trim())
    .filter((t) => t.length > 0)
    .map((t) => t.replace(/^\{|\}$/g, ""));

  if (tokens.length === 0) return { fields: [], error: "atLeastOneField" };

  const invalid = tokens.filter((t) => !BULK_IMPORT_VALID_FIELDS.includes(t as BulkImportField));
  if (invalid.length > 0) return { fields: [], error: "unknownFields" };

  const duplicates = tokens.filter((t, i) => tokens.indexOf(t) !== i);
  if (duplicates.length > 0) return { fields: [], error: "duplicateFields" };

  if (!tokens.includes("value")) return { fields: [], error: "valueFieldRequired" };

  return { fields: tokens as BulkImportField[] };
}

export interface ParsedImportLine {
  raw: string;
  value: string | null;
  date: string | null;
  incomplete: boolean;
}

/** Splits `line` by `separator` into at most `maxParts` pieces, with the last
 * piece absorbing any remaining separator-containing text. JS has no
 * built-in equivalent of Python's `str.split(sep, maxsplit)`. */
function splitWithMaxParts(line: string, separator: string, maxParts: number): string[] {
  if (maxParts <= 1) return [line];
  const parts: string[] = [];
  let rest = line;
  for (let i = 0; i < maxParts - 1; i++) {
    const idx = rest.indexOf(separator);
    if (idx === -1) {
      parts.push(rest);
      rest = "";
      break;
    }
    parts.push(rest.slice(0, idx));
    rest = rest.slice(idx + separator.length);
  }
  if (parts.length < maxParts) parts.push(rest);
  return parts;
}

export function parseImportLine(
  line: string,
  fields: BulkImportField[],
  separator: string,
): ParsedImportLine {
  const parts = splitWithMaxParts(line, separator, fields.length);
  const result: ParsedImportLine = { raw: line, value: null, date: null, incomplete: false };

  fields.forEach((field, i) => {
    const value = parts[i]?.trim();
    if (!value) {
      result.incomplete = true;
      return;
    }
    result[field] = value;
  });

  return result;
}

/** Every non-blank line of `text`, positionally split by `fields`/`separator`. */
export function parseImportText(
  text: string,
  fields: BulkImportField[],
  separator: string,
): ParsedImportLine[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => parseImportLine(line, fields, separator));
}

export interface BulkImportItemPayload {
  value: string | null;
  date: string | null;
}

export function toBulkImportItems(rows: ParsedImportLine[]): BulkImportItemPayload[] {
  return rows.map((row) => ({ value: row.value, date: row.date }));
}

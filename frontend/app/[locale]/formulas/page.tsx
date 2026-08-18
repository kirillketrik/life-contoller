"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { useAuth } from "@/components/auth-provider";
import { CreateFormulaDefinitionDialog } from "@/components/metrics/create-formula-definition-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useRouter } from "@/i18n/navigation";
import { formulaDefinitions, metricTypes } from "@/lib/api";
import { FORMULA_DEFINITIONS_QUERY_KEY, METRIC_TYPES_QUERY_KEY } from "@/lib/query-keys";

export default function FormulasPage() {
  const t = useTranslations("formulas");
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [authLoading, user, router]);

  const enabled = Boolean(user?.is_admin);

  const definitionsQuery = useQuery({
    queryKey: FORMULA_DEFINITIONS_QUERY_KEY,
    queryFn: () => formulaDefinitions.list(),
    enabled,
  });
  const metricTypesQuery = useQuery({
    queryKey: METRIC_TYPES_QUERY_KEY,
    queryFn: () => metricTypes.list(),
    enabled,
  });

  if (!authLoading && user && !user.is_admin) {
    return <p className="text-sm text-muted-foreground">{t("adminsOnly")}</p>;
  }

  const definitions = definitionsQuery.data?.results ?? [];
  const typesById = new Map((metricTypesQuery.data?.results ?? []).map((type) => [type.id, type]));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("description")}</p>
        </div>
        <CreateFormulaDefinitionDialog />
      </div>

      {definitionsQuery.isLoading ? (
        <Skeleton className="h-40" />
      ) : definitions.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("empty")}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("colComputed")}</TableHead>
              <TableHead>{t("colFormula")}</TableHead>
              <TableHead>{t("colInputs")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {definitions.map((definition) => (
              <TableRow key={definition.id}>
                <TableCell>
                  {typesById.get(definition.computed_metric_type)?.name ?? definition.computed_metric_type}
                </TableCell>
                <TableCell>{definition.formula_key}</TableCell>
                <TableCell className="text-muted-foreground">
                  {Object.entries(definition.input_mapping)
                    .map(([variable, id]) => `${variable} = ${typesById.get(id)?.name ?? id}`)
                    .join(", ")}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

"use client";

import { useQuery } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DeleteRecipeButton } from "@/components/nutrition/delete-recipe-button";
import { RecipeDialog } from "@/components/nutrition/recipe-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useRouter } from "@/i18n/navigation";
import { recipes } from "@/lib/api";
import { recipesQueryKey } from "@/lib/query-keys";

export default function RecipesPage() {
  const t = useTranslations("recipes");
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [authLoading, user, router]);

  const { data, isLoading } = useQuery({
    queryKey: recipesQueryKey(search),
    queryFn: () => recipes.list(search || undefined),
    enabled: Boolean(user),
  });

  const items = data?.results ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("description")}</p>
        </div>
        <RecipeDialog />
      </div>

      <Input
        placeholder={t("searchPlaceholder")}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="max-w-sm"
      />

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{search ? t("noResults") : t("empty")}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("nameHeader")}</TableHead>
              <TableHead className="text-right">{t("servingsHeader")}</TableHead>
              <TableHead className="text-right">{t("caloriesHeader")}</TableHead>
              <TableHead className="text-right">{t("actionsHeader")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="font-medium">{item.name}</TableCell>
                <TableCell className="text-right">{item.servings}</TableCell>
                <TableCell className="text-right">{item.calories_per_serving}</TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <RecipeDialog
                      recipe={item}
                      trigger={
                        <Button variant="ghost" size="icon" aria-label={t("editAction")}>
                          <Pencil className="size-4" />
                        </Button>
                      }
                    />
                    <DeleteRecipeButton recipe={item} />
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

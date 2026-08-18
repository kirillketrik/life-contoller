"use client";

import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { useAuth } from "@/components/auth-provider";
import { FormulaBuilder } from "@/components/metrics/formula-builder/formula-builder";
import { useRouter } from "@/i18n/navigation";

export default function FormulaBuilderPage() {
  const t = useTranslations("formulaBuilder");
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [authLoading, user, router]);

  if (!authLoading && user && !user.is_admin) {
    return <p className="text-sm text-muted-foreground">{t("adminsOnly")}</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("description")}</p>
      </div>
      <FormulaBuilder />
    </div>
  );
}

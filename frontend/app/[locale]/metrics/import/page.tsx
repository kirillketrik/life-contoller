"use client";

import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { useAuth } from "@/components/auth-provider";
import { BulkImport } from "@/components/metrics/bulk-import/bulk-import";
import { useRouter } from "@/i18n/navigation";

export default function BulkImportPage() {
  const t = useTranslations("bulkImport");
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [authLoading, user, router]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("description")}</p>
      </div>
      <BulkImport />
    </div>
  );
}

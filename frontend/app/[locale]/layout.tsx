import "@fontsource-variable/geist";
import "../globals.css";

import type { Metadata } from "next";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";
import { notFound } from "next/navigation";

import { AuthProvider } from "@/components/auth-provider";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { QueryProvider } from "@/components/query-provider";
import { ThemeProvider } from "@/components/theme-provider";
import { ThemeToggle } from "@/components/theme-toggle";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { routing } from "@/i18n/routing";

export const metadata: Metadata = {
  title: "Life Controller",
  description: "Персональное приложение для отслеживания жизни",
};

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();

  const messages = await getMessages();

  return (
    <html lang={locale} suppressHydrationWarning className="h-full antialiased">
      <body className="min-h-full">
        <QueryProvider>
          <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
            <NextIntlClientProvider messages={messages}>
              <AuthProvider>
                <TooltipProvider>
                  <SidebarProvider>
                    <AppSidebar />
                    <SidebarInset>
                      <div className="flex items-center justify-between border-b px-4 py-2 sm:px-6 lg:px-8">
                        <SidebarTrigger />
                        <ThemeToggle />
                      </div>
                      <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
                    </SidebarInset>
                  </SidebarProvider>
                </TooltipProvider>
                <Toaster />
              </AuthProvider>
            </NextIntlClientProvider>
          </ThemeProvider>
        </QueryProvider>
      </body>
    </html>
  );
}

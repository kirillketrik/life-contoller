"use client";

import { ChevronsUpDown, LayoutDashboard, ListTree, LogOut, Package, Pencil, Sigma } from "lucide-react";
import { useTranslations } from "next-intl";

import { useAuth } from "@/components/auth-provider";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { Link, usePathname } from "@/i18n/navigation";

export function AppSidebar() {
  const t = useTranslations("nav");
  const { user, logout } = useAuth();
  const pathname = usePathname();

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<Link href="/" />}>
              <div className="flex size-6 shrink-0 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground">
                <Package className="size-4" />
              </div>
              <span className="font-heading font-semibold">{t("brand")}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  render={<Link href="/" />}
                  isActive={pathname === "/"}
                  tooltip={t("dashboard")}
                >
                  <LayoutDashboard />
                  <span>{t("dashboard")}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <Collapsible defaultOpen>
          <SidebarGroup>
            <SidebarGroupLabel render={<CollapsibleTrigger />} className="cursor-pointer">
              {t("metricsGroup")}
            </SidebarGroupLabel>
            <CollapsibleContent>
              <SidebarGroupContent>
                <SidebarMenu>
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      render={<Link href="/metrics" />}
                      isActive={pathname.startsWith("/metrics")}
                      tooltip={t("metricTypes")}
                    >
                      <ListTree />
                      <span>{t("metricTypes")}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                </SidebarMenu>
              </SidebarGroupContent>
            </CollapsibleContent>
          </SidebarGroup>
        </Collapsible>

        {user?.is_admin && (
          <Collapsible defaultOpen>
            <SidebarGroup>
              <SidebarGroupLabel render={<CollapsibleTrigger />} className="cursor-pointer">
                {t("adminGroup")}
              </SidebarGroupLabel>
              <CollapsibleContent>
                <SidebarGroupContent>
                  <SidebarMenu>
                    <SidebarMenuItem>
                      <SidebarMenuButton
                        render={<Link href="/formulas" />}
                        isActive={pathname.startsWith("/formulas")}
                        tooltip={t("formulas")}
                      >
                        <Sigma />
                        <span>{t("formulas")}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  </SidebarMenu>
                </SidebarGroupContent>
              </CollapsibleContent>
            </SidebarGroup>
          </Collapsible>
        )}
      </SidebarContent>

      <SidebarFooter>
        {user && (
          <SidebarMenu>
            <SidebarMenuItem>
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <SidebarMenuButton size="lg">
                      <Avatar>
                        <AvatarFallback>{user.username.slice(0, 2).toUpperCase()}</AvatarFallback>
                      </Avatar>
                      <div className="grid flex-1 text-left leading-tight">
                        <span className="truncate text-sm font-medium">{user.username}</span>
                        {user.is_admin && (
                          <Badge variant="secondary" className="mt-0.5 w-fit">
                            {t("admin")}
                          </Badge>
                        )}
                      </div>
                      <ChevronsUpDown className="ml-auto size-4 text-sidebar-foreground/50" />
                    </SidebarMenuButton>
                  }
                />
                <DropdownMenuContent side="top" align="start" className="w-(--anchor-width) min-w-56">
                  <DropdownMenuItem>
                    <Pencil />
                    {t("editProfile")}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => logout()}>
                    <LogOut />
                    {t("logout")}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </SidebarMenuItem>
          </SidebarMenu>
        )}
      </SidebarFooter>
    </Sidebar>
  );
}

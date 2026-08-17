"use client";

import Link from "next/link";

import { useAuth } from "@/components/auth-provider";
import { ThemeToggle } from "@/components/theme-toggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function NavBar() {
  const { user, logout, loading } = useAuth();

  return (
    <header className="border-b">
      <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
        <Link href="/" className="text-sm font-semibold tracking-tight">
          Life Controller
        </Link>
        <nav className="flex items-center gap-3">
          {!loading && user && (
            <>
              <Link href="/metrics" className="text-sm text-muted-foreground hover:text-foreground">
                Metrics
              </Link>
              {user.is_admin && <Badge variant="secondary">admin</Badge>}
              <span className="text-sm text-muted-foreground">{user.username}</span>
              <Button variant="ghost" size="sm" onClick={() => logout()}>
                Log out
              </Button>
            </>
          )}
          <ThemeToggle />
        </nav>
      </div>
    </header>
  );
}

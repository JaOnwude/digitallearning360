"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, useAuthLogout, useAuthMe, type MeOut } from "@dl360/api-client";
import { LogOut, Menu } from "lucide-react";
import { routeForStep } from "@/components/auth/steps";
import { useSchool } from "@/components/school/school-context";
import { SchoolLogo } from "@/components/school/school-logo";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { useLiveUpdates } from "@/lib/live-updates";
import { cn } from "@/lib/utils";
import { navFor, ROLE_LABEL } from "./nav";
import { MeProvider } from "./me-context";

/** Signed-in pages. The API enforces access; this only routes people to the right screen. */
export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const me = useAuthMe({ query: { retry: false } });
  const user = me.data?.data;
  useLiveUpdates(user?.next === "done");

  useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) router.replace("/login");
    else if (me.error instanceof ApiError && me.error.status === 403) router.replace("/login");
    else if (user && user.next !== "done") router.replace(routeForStep[user.next]);
  }, [me.error, user, router]);

  if (!user || user.next !== "done") {
    return (
      <div className="grid min-h-dvh place-items-center p-6">
        <Skeleton className="h-40 w-full max-w-md" />
      </div>
    );
  }

  return (
    <MeProvider me={user}>
      <div className="flex min-h-dvh">
        <Sidebar me={user} className="hidden w-64 shrink-0 md:flex" />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar me={user} />
          <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6">{children}</main>
        </div>
      </div>
    </MeProvider>
  );
}

function Sidebar({ me, className }: { me: MeOut; className?: string }) {
  const school = useSchool();
  const pathname = usePathname();
  return (
    <aside className={cn("bg-sidebar flex-col border-r", className)}>
      <div className="flex items-center gap-3 border-b p-4">
        <SchoolLogo className="size-10" />
        <p className="text-sm leading-tight font-semibold">{school.name}</p>
      </div>
      <nav className="grid gap-1 p-3" aria-label="Main">
        {navFor(me.roles).map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-brand/15 text-brand-ink"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <item.icon className="size-4" aria-hidden />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

function TopBar({ me }: { me: MeOut }) {
  const router = useRouter();
  const school = useSchool();
  const queryClient = useQueryClient();
  const logout = useAuthLogout();

  async function signOut() {
    await logout.mutateAsync().catch(() => undefined);
    queryClient.clear();
    router.replace("/login");
  }

  return (
    <header className="bg-background/95 sticky top-0 z-10 flex h-14 items-center gap-3 border-b px-4 backdrop-blur sm:px-6">
      <div className="flex items-center gap-2 md:hidden">
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" size="icon" aria-label="Open menu" />}>
            <Menu />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {navFor(me.roles).map((item) => (
              <DropdownMenuItem key={item.href} onClick={() => router.push(item.href)}>
                <item.icon aria-hidden /> {item.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <SchoolLogo className="size-8" />
        <span className="max-w-[12rem] truncate text-sm font-semibold">{school.name}</span>
      </div>
      <div className="ml-auto">
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" className="gap-2" />}>
            <span className="bg-brand text-brand-foreground grid size-7 place-items-center rounded-full text-xs font-semibold">
              {me.full_name.slice(0, 1).toUpperCase()}
            </span>
            <span className="hidden max-w-[10rem] truncate sm:inline">{me.full_name}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-56">
            <DropdownMenuLabel>
              <p className="font-medium">{me.full_name}</p>
              <p className="text-muted-foreground text-xs font-normal">
                {me.roles.map((r) => ROLE_LABEL[r]).join(", ")}
              </p>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={signOut}>
              <LogOut aria-hidden /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}

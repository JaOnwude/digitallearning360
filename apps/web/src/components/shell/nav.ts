import type { Role } from "@dl360/api-client";
import { LayoutDashboard, type LucideIcon } from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon; roles: Role[] | "all" };

/** Sidebar entries. Each feature adds its pages here as it ships (M1: setup, students, staff). */
export const NAV: NavItem[] = [{ href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, roles: "all" }];

export function navFor(roles: Role[]): NavItem[] {
  return NAV.filter((item) => item.roles === "all" || item.roles.some((r) => roles.includes(r)));
}

export const ROLE_LABEL: Record<Role, string> = {
  school_admin: "School admin",
  section_head: "Section head",
  bursar: "Bursar",
  teacher: "Teacher",
  counsellor: "Guidance counsellor",
  parent: "Parent",
  student: "Student",
};

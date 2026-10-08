"use client";

import Link from "next/link";
import { BookOpen, ChevronRight, GraduationCap, Settings2, Users, Wallet } from "lucide-react";
import { PortalResults } from "@/components/results/portal-results";
import { useMe } from "@/components/shell/me-context";
import { useSchool } from "@/components/school/school-context";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const STAFF_LINKS = [
  { href: "/classes", title: "My classes", body: "Enter scores, rate students, approve results.", icon: BookOpen, roles: ["teacher", "section_head", "counsellor", "school_admin"] },
  { href: "/fees", title: "Fees", body: "Collections, invoices and transfer proofs to confirm.", icon: Wallet, roles: ["bursar", "school_admin"] },
  { href: "/students", title: "Students & parents", body: "Records, CSV import and sign-in slips.", icon: GraduationCap, roles: ["school_admin"] },
  { href: "/staff", title: "Staff", body: "Accounts and roles.", icon: Users, roles: ["school_admin"] },
  { href: "/setup", title: "School setup", body: "Classes, terms, subjects, teaching and results settings.", icon: Settings2, roles: ["school_admin"] },
] as const;

const TITLES = new Set(["mr", "mrs", "ms", "miss", "dr", "chief", "prof", "engr", "rev", "barr", "pastor", "alhaji", "alhaja"]);

/** "Mrs Ngozi Okafor" → "Ngozi": greet by first name, not by title. */
function greetingName(fullName: string): string {
  const words = fullName.split(/\s+/).filter(Boolean);
  return words.find((w) => !TITLES.has(w.replace(/\.$/, "").toLowerCase())) ?? words[0] ?? "";
}

export default function DashboardPage() {
  const me = useMe();
  const school = useSchool();
  const firstName = greetingName(me.full_name);
  const links = STAFF_LINKS.filter((l) => l.roles.some((r) => (me.roles as string[]).includes(r)));

  return (
    <div className="grid gap-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Welcome, {firstName}</h1>
        <p className="text-muted-foreground">{school.name}</p>
      </div>
      {me.kind === "staff" ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="group">
              <Card className="group-hover:border-brand h-full transition-colors">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <l.icon className="text-brand-ink size-4" /> {l.title}
                  </CardTitle>
                  <CardDescription>{l.body}</CardDescription>
                </CardHeader>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <section className="grid gap-3">
          <Link href="/fees" className="hover:border-brand flex min-h-14 items-center gap-3 rounded-lg border p-3 transition-colors">
            <Wallet className="text-brand-ink size-5" />
            <span className="flex-1 font-medium">School fees: invoices, payment and receipts</span>
            <ChevronRight className="text-muted-foreground size-4" />
          </Link>
          <h2 className="text-lg font-semibold">{me.kind === "parent" ? "Your children's results" : "Your results"}</h2>
          <PortalResults isParent={me.kind === "parent"} />
        </section>
      )}
    </div>
  );
}

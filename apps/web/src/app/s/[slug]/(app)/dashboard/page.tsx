"use client";

import { useMe } from "@/components/shell/me-context";
import { useSchool } from "@/components/school/school-context";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** M1 placeholder. Each role's real dashboard fills in as results (M2) and fees (M3) ship. */
const COMING: Record<string, { title: string; body: string }[]> = {
  staff: [
    { title: "School setup", body: "Classes, arms, subjects and terms." },
    { title: "Students & parents", body: "Records and CSV import." },
    { title: "Results", body: "Score entry and report cards (M2)." },
  ],
  parent: [
    { title: "Results", body: "Your children's report cards, once published." },
    { title: "Fees", body: "Invoices, payments and receipts." },
  ],
  student: [{ title: "My results", body: "Your report cards, once published." }],
};

export default function DashboardPage() {
  const me = useMe();
  const school = useSchool();
  const firstName = me.full_name.split(" ")[0];
  return (
    <div className="grid gap-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Welcome, {firstName}</h1>
        <p className="text-muted-foreground">{school.name}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {(COMING[me.kind] ?? []).map((c) => (
          <Card key={c.title}>
            <CardHeader>
              <CardTitle>{c.title}</CardTitle>
              <CardDescription>{c.body}</CardDescription>
            </CardHeader>
            <CardContent>
              <span className="text-muted-foreground text-xs">Coming soon</span>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

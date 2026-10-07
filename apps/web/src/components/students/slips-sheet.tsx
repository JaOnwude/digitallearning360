"use client";

import type { LoginSlip } from "@dl360/api-client";
import { Printer, X } from "lucide-react";
import { useSchool } from "@/components/school/school-context";
import { Button } from "@/components/ui/button";

/**
 * Printable sign-in slips: cut along the dashed lines and hand one to each student.
 * Passwords exist only in this screen's memory; closing it discards them.
 */
export function SlipsSheet({ slips, onClose }: { slips: LoginSlip[]; onClose: () => void }) {
  const school = useSchool();
  return (
    <div className="print-area bg-background fixed inset-0 z-50 overflow-y-auto">
      <div className="bg-background sticky top-0 flex items-center gap-2 border-b p-3 print:hidden">
        <p className="mr-auto text-sm">
          {slips.length} sign-in slip{slips.length === 1 ? "" : "s"}. Print now: the passwords
          won&apos;t be shown again.
        </p>
        <Button variant="brand" onClick={() => window.print()}>
          <Printer /> Print
        </Button>
        <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
          <X />
        </Button>
      </div>
      <div className="mx-auto grid max-w-3xl grid-cols-1 gap-0 p-4 sm:grid-cols-2 print:max-w-none print:p-0">
        {slips.map((s) => (
          <section key={s.student_id} className="break-inside-avoid border border-dashed p-4 text-sm">
            <p className="font-semibold">{school.name}</p>
            <p className="text-muted-foreground mb-3 text-xs">Student sign-in</p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
              <dt className="text-muted-foreground">Name</dt>
              <dd>{s.full_name}</dd>
              <dt className="text-muted-foreground">Class</dt>
              <dd>{s.class_name ?? "—"}</dd>
              <dt className="text-muted-foreground">Admission no.</dt>
              <dd className="font-mono">{s.admission_no}</dd>
              <dt className="text-muted-foreground">Password</dt>
              <dd className="font-mono text-base font-semibold">{s.temporary_password}</dd>
            </dl>
            <p className="text-muted-foreground mt-3 text-xs">
              Sign in on the school portal (Student tab). You&apos;ll choose your own password.
            </p>
          </section>
        ))}
      </div>
    </div>
  );
}

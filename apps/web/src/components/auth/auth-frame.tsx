"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { SchoolLogo } from "@/components/school/school-logo";
import { useSchool } from "@/components/school/school-context";

/** Sign-in pages: the school's identity beside (desktop) or above (phone) the form. */
export function AuthFrame({ children }: { children: ReactNode }) {
  const school = useSchool();
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <aside
        className="relative hidden flex-col justify-between overflow-hidden bg-neutral-950 p-10 text-white lg:flex"
        // A gradient, not a blurred element: cheap to paint on low-end devices.
        style={{
          backgroundImage:
            "radial-gradient(circle at 100% 0%, color-mix(in oklch, var(--brand) 22%, transparent), transparent 55%)",
        }}
      >
        <p className="text-sm font-medium tracking-wide text-white/70">DigitalLearning360</p>
        <div className="relative space-y-6">
          <SchoolLogo className="size-40" />
          <div className="space-y-2">
            <h1 className="text-3xl font-semibold tracking-tight text-balance">{school.name}</h1>
            {school.motto && <p className="text-brand text-lg italic">“{school.motto}”</p>}
          </div>
        </div>
        <p className="text-sm text-white/60">
          Results, fees and school updates, in one place for parents, students and staff.
        </p>
      </aside>

      <main className="flex flex-col items-center justify-center px-4 py-10 sm:px-8">
        <div className="mb-8 flex flex-col items-center gap-3 text-center lg:hidden">
          <SchoolLogo className="size-20" />
          <p className="text-lg font-semibold text-balance">{school.name}</p>
        </div>
        <div className="w-full max-w-sm">{children}</div>
        <Link href="/privacy" className="text-muted-foreground mt-10 text-xs underline-offset-4 hover:underline">
          How we use your data
        </Link>
      </main>
    </div>
  );
}

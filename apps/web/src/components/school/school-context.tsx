"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { PublicSchoolOut } from "@dl360/api-client";

const SchoolContext = createContext<PublicSchoolOut | null>(null);

export function SchoolProvider({
  school,
  children,
}: {
  school: PublicSchoolOut;
  children: ReactNode;
}) {
  return <SchoolContext value={school}>{children}</SchoolContext>;
}

/** The school whose site we're on. Available in every page under /s/[slug]. */
export function useSchool(): PublicSchoolOut {
  const school = useContext(SchoolContext);
  if (!school) throw new Error("useSchool must be used inside a school page");
  return school;
}
